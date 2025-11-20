"""Voice Synthesizer Agent - generate scene voice-overs via MAS ReAct loop."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from .react_agent import ReActAgent, AgentError
from .utils.progress_snapshot import emit_progress_snapshot
from ..models import Task, AgentExecution, AgentType
from ..core.config import settings
from .utils.artifacts import (
    normalize_executed_calls_to_artifacts,
    persist_scene_outputs,
    finalize_scene_outputs,
)
from .utils.fc_messages import build_neutral_act_messages
from .utils.memory_helpers import ensure_mas_memory


class VoiceSynthesizerAgent(ReActAgent):
    """Generate per-scene narration audio using supplier-agnostic TTS tools."""

    def __init__(self, llms=None, memory_services=None):
        max_iters = getattr(settings, "VOICE_SYNTHESIZER_MAX_ITERATIONS", 2) or 2
        if max_iters < 2:
            max_iters = 2

        super().__init__(
            agent_type=AgentType.VOICE_SYNTHESIZER,
            agent_name="voice_synthesizer",
            timeout_seconds=600,
            max_retries=1,
            max_iterations=max_iters,
            tools=[
                "voice_synth_tool",
                "audio_processor",
                "audio_analysis_tool",
                "file_storage_tool",
            ],
            llms=llms,
            memory_services=memory_services,
        )
        self._max_chars = int(getattr(settings, "VOICE_MAX_CHARS_PER_REQUEST", 300))

    async def _execute_impl(
        self,
        task: Task,
        input_data: Dict[str, Any],
        execution: AgentExecution,
        db: Session,
    ) -> Dict[str, Any]:
        return await super()._execute_impl(task, input_data, execution, db)

    async def _observe_current_state(
        self,
        input_data: Dict[str, Any],
        base_observation: Dict[str, Any],
        iteration: int,
    ) -> Dict[str, Any]:
        self._validate_input(input_data, ["workflow_state_id"])
        wf_id = str(input_data["workflow_state_id"])
        wm = self.wm
        observation: Dict[str, Any] = dict(base_observation or {})
        store = self.shared_memory_store

        voice_settings = self._resolve_voice_settings(
            wf_id,
            incoming=input_data.get("voice_settings") or {},
            store=store,
            persist=True,
        )
        voice_plan = self._resolve_voice_plan(
            wf_id,
            incoming=input_data.get("voice_plan"),
            store=store,
        )
        concept_plan = self._resolve_concept_plan(
            wf_id,
            store=store,
        )
        voice_assets = self._load_voice_assets(wf_id, store)
        scenes_payload = input_data.get("voice_scenes")
        scene_facts = self._build_voice_scene_facts(
            wm=wm,
            scenes_payload=scenes_payload,
            voice_plan=voice_plan,
            concept_plan=concept_plan,
            voice_assets=voice_assets,
        )

        observation.update({
            "voice_settings": voice_settings,
            "voice_plan": voice_plan,
            "concept_plan_overview": concept_plan.get("overview") if isinstance(concept_plan, dict) else "",
            "voice_scene_facts": scene_facts,
            "max_chars_per_request": self._max_chars,
        })
        return observation

    def _resolve_voice_settings(
        self,
        workflow_state_id: str,
        *,
        incoming: Optional[Dict[str, Any]],
        store: Optional[Any],
        persist: bool,
    ) -> Dict[str, Any]:
        incoming = incoming or {}
        stored: Dict[str, Any] = {}
        if store is not None:
            try:
                stored = store.get(
                    str(workflow_state_id),
                    "voice_settings",
                    agent=self.agent_name,
                    default={},
                ) or {}
            except Exception as exc:
                self.logger.error("Shared memory read voice_settings failed: %s", exc, exc_info=True)
                raise AgentError("Shared memory read failed (voice_settings)") from exc

        settings_payload = self._build_voice_settings_payload(incoming, stored)
        if persist and store is not None:
            try:
                if settings_payload != stored:
                    store.put(
                        str(workflow_state_id),
                        "voice_settings",
                        settings_payload,
                        agent=self.agent_name,
                    )
            except Exception as exc:
                self.logger.error("Shared memory write voice_settings failed: %s", exc, exc_info=True)
                raise AgentError("Shared memory write failed (voice_settings)") from exc
        return settings_payload

    def _build_voice_settings_payload(
        self,
        incoming: Dict[str, Any],
        stored: Dict[str, Any],
    ) -> Dict[str, Any]:
        def pick(key: str, default: Any = None) -> Any:
            sentinel = object()
            val = incoming.get(key, sentinel)
            if val is not sentinel and val is not None:
                return val
            val = stored.get(key, sentinel)
            if val is not sentinel and val is not None:
                return val
            return default

        preferred_ids_raw = pick("preferred_voice_ids")
        preferred_voice_ids = self._normalize_voice_ids(preferred_ids_raw)
        auto_default = getattr(settings, "VOICE_AUTO_SELECT_DEFAULT", True)
        auto_select_flag = self._coerce_bool(
            incoming.get("auto_select") if incoming.get("auto_select") is not None else stored.get("auto_select"),
            auto_default,
        )
        voice_id_raw = pick("voice_id", getattr(settings, "VOICE_DEFAULT_VOICE_ID", ""))
        voice_id = str(voice_id_raw or "").strip() or "voice_default"
        payload = {
            "voice_id": voice_id,
            "language": pick("language", "zh-CN"),
            "speed": pick("speed", 1.0),
            "pitch": pick("pitch", 1.0),
            "sample_rate": pick("sample_rate", getattr(settings, "VOICE_DEFAULT_SAMPLE_RATE", 16000)),
            "audio_format": pick("audio_format", getattr(settings, "VOICE_DEFAULT_FORMAT", "wav")),
            "style": pick("style"),
            "auto_select": auto_select_flag,
            "preferred_voice_ids": preferred_voice_ids,
        }
        return payload

    @staticmethod
    def _normalize_voice_ids(value: Any) -> Optional[List[str]]:
        if value is None:
            return None
        if isinstance(value, str):
            items = [
                seg.strip()
                for seg in value.replace(";", ",").split(",")
                if seg and seg.strip()
            ]
            return items or None
        if isinstance(value, list):
            items = [str(seg).strip() for seg in value if str(seg).strip()]
            return items or None
        return None

    def _resolve_voice_plan(
        self,
        workflow_state_id: str,
        *,
        incoming: Optional[Dict[str, Any]],
        store: Optional[Any],
    ) -> Dict[str, Any]:
        if isinstance(incoming, dict) and incoming:
            if store is not None:
                try:
                    store.put(str(workflow_state_id), "voice_plan", incoming, agent=self.agent_name)
                except Exception as exc:
                    self.logger.error("Shared memory write voice_plan failed: %s", exc, exc_info=True)
                    raise AgentError("Shared memory write failed (voice_plan)") from exc
            return incoming
        if store is None:
            return {}
        try:
            return store.get(
                str(workflow_state_id),
                "voice_plan",
                agent=self.agent_name,
                default={},
            ) or {}
        except Exception as exc:
            self.logger.error("Shared memory read voice_plan failed: %s", exc, exc_info=True)
            raise AgentError("Shared memory read failed (voice_plan)") from exc

    def _resolve_concept_plan(
        self,
        workflow_state_id: str,
        *,
        store: Optional[Any],
    ) -> Dict[str, Any]:
        if store is None:
            return {}
        try:
            return store.get(
                str(workflow_state_id),
                "concept_plan",
                agent=self.agent_name,
                default={},
            ) or {}
        except Exception as exc:
            self.logger.error("Shared memory read concept_plan failed: %s", exc, exc_info=True)
            raise AgentError("Shared memory read failed (concept_plan)") from exc

    def _load_voice_assets(self, workflow_state_id: str, store: Optional[Any]) -> Dict[int, Dict[str, Any]]:
        if store is None:
            return {}
        try:
            assets = store.get(
                str(workflow_state_id),
                "voice_assets",
                agent=self.agent_name,
                default={},
            ) or {}
        except Exception as exc:
            self.logger.error("Shared memory read voice_assets failed: %s", exc, exc_info=True)
            raise AgentError("Shared memory read failed (voice_assets)") from exc
        normalized: Dict[int, Dict[str, Any]] = {}
        if isinstance(assets, dict):
            for key, value in assets.items():
                try:
                    scene_number = int(key)
                except Exception:
                    continue
                if isinstance(value, dict):
                    normalized[scene_number] = value
        return normalized

    def _build_voice_scene_facts(
        self,
        *,
        wm: Any,
        scenes_payload: Optional[List[Dict[str, Any]]],
        voice_plan: Dict[str, Any],
        concept_plan: Dict[str, Any],
        voice_assets: Dict[int, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        scenes = self._materialize_scene_payloads(wm, scenes_payload)
        guidance_map = self._build_guidance_map(voice_plan)
        default_enabled = bool(voice_plan.get("enabled")) and str(voice_plan.get("mode", "none")).lower() not in {"none", "off"}
        facts: List[Dict[str, Any]] = []
        concept_overview = concept_plan.get("overview") if isinstance(concept_plan, dict) else ""

        for scene in scenes:
            if not isinstance(scene, dict):
                continue
            scene_number = scene.get("scene_number")
            if scene_number is None:
                continue
            try:
                scene_number = int(scene_number)
            except Exception:
                continue
            guidance = dict(guidance_map.get(scene_number, {}) or {})
            pacing = scene.get("pacing_and_timing") or {}
            if isinstance(pacing, dict):
                if pacing.get("should_narrate") is not None:
                    guidance["should_narrate"] = bool(pacing.get("should_narrate"))
                if pacing.get("pace_tag"):
                    guidance["pace_tag"] = str(pacing.get("pace_tag")).strip().lower()
                if pacing.get("target_char_count") is not None:
                    try:
                        guidance["target_char_count"] = int(pacing.get("target_char_count"))
                    except (TypeError, ValueError):
                        guidance["target_char_count"] = pacing.get("target_char_count")
            scene_guidance = scene.get("voice_guidance")
            if isinstance(scene_guidance, dict):
                for key, value in scene_guidance.items():
                    if value is not None:
                        guidance[key] = value

            should_narrate = guidance.get("should_narrate")
            if should_narrate is None:
                should_narrate = default_enabled
            target_duration = float(scene.get("duration") or scene.get("target_duration") or 0.0)
            raw_text = (
                scene.get("voice_over_text")
                or scene.get("existing_text")
                or scene.get("script_text")
                or ""
            )
            char_limit = self._estimate_char_limit(target_duration)
            sanitized_text = self._sanitize_narration_text(raw_text, char_limit)
            asset_info = voice_assets.get(scene_number)
            has_asset = bool(
                asset_info
                and (asset_info.get("audio_path") or asset_info.get("audio_url"))
            )

            fact_status = "skipped"
            if should_narrate:
                fact_status = "ready" if has_asset else "pending"

            fact = {
                "scene_number": scene_number,
                "should_narrate": bool(should_narrate),
                "fact_status": fact_status,
                "target_duration": target_duration,
                "existing_text": sanitized_text,
                "original_char_count": len(raw_text or ""),
                "voice_guidance": guidance,
                "has_voice_asset": has_asset,
                "existing_asset": asset_info if has_asset else {},
                "video_url": scene.get("video_url") or "",
                "script_excerpt": self._clean_text_fragment(scene.get("script_text") or "", 200),
                "narrative_description": self._clean_text_fragment(scene.get("narrative_description") or "", 200),
                "visual_description": self._clean_text_fragment(scene.get("visual_description") or "", 200),
                "concept_overview": concept_overview,
            }
            facts.append(fact)
        return facts

    def _materialize_scene_payloads(
        self,
        wm: Any,
        scenes_payload: Optional[List[Dict[str, Any]]],
    ) -> List[Dict[str, Any]]:
        if isinstance(scenes_payload, list) and scenes_payload:
            prepared: List[Dict[str, Any]] = []
            for item in scenes_payload:
                if isinstance(item, dict) and item.get("scene_number") is not None:
                    prepared.append(dict(item))
            if prepared:
                return prepared

        prepared = []
        if wm is None:
            return prepared
        try:
            scene_numbers = list(getattr(wm, "scene_numbers", []))
        except Exception:
            scene_numbers = []
        for sn in scene_numbers:
            snapshot = getattr(wm, "scenes", {}).get(sn)
            prepared.append(
                {
                    "scene_number": sn,
                    "duration": float(getattr(snapshot, "duration", 0.0) or 0.0) if snapshot else 0.0,
                    "narrative_description": getattr(snapshot, "narrative_description", "") if snapshot else "",
                    "visual_description": getattr(snapshot, "visual_description", "") if snapshot else "",
                    "script_text": "",
                    "video_url": "",
                }
            )
        return prepared

    @staticmethod
    def _build_guidance_map(voice_plan: Dict[str, Any]) -> Dict[int, Dict[str, Any]]:
        mapping: Dict[int, Dict[str, Any]] = {}
        entries = voice_plan.get("scene_guidance") if isinstance(voice_plan, dict) else None
        if not isinstance(entries, list):
            return mapping
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            scene_key = entry.get("scene_number") or entry.get("sceneIndex")
            try:
                scene_number = int(scene_key)
            except (TypeError, ValueError):
                continue
            should_raw = entry.get("should_narrate")
            if isinstance(should_raw, str):
                should_val = should_raw.strip().lower() not in {"false", "0", "no", "off"}
            else:
                should_val = should_raw
            raw_points = entry.get("key_points") or entry.get("topics") or entry.get("highlights") or []
            if isinstance(raw_points, str):
                key_points = [
                    seg.strip()
                    for seg in raw_points.replace("、", ",").split(",")
                    if seg.strip()
                ]
            elif isinstance(raw_points, list):
                key_points = [str(seg).strip() for seg in raw_points if str(seg).strip()]
            else:
                key_points = []
            mapping[scene_number] = {
                "scene_number": scene_number,
                "should_narrate": should_val,
                "objective": entry.get("objective") or entry.get("purpose") or "",
                "emotion": entry.get("emotion") or entry.get("tone") or "",
                "key_points": key_points,
                "pace_tag": str(entry.get("pace_tag", "")).strip().lower(),
                "target_char_count": entry.get("target_char_count"),
            }
        return mapping

    def _persist_voice_artifacts(
        self,
        *,
        workflow_state_id: str,
        voice_settings: Dict[str, Any],
        artifacts: List[Dict[str, Any]],
    ) -> None:
        if not artifacts:
            return
        store = self.shared_memory_store
        try:
            assets = store.get(
                str(workflow_state_id),
                "voice_assets",
                agent=self.agent_name,
                default={},
            ) or {}
        except Exception as exc:
            self.logger.error("Shared memory read voice_assets failed: %s", exc, exc_info=True)
            raise AgentError("Shared memory read failed (voice_assets)") from exc

        changed = False
        for art in artifacts:
            scene_number = art.get("scene_number")
            try:
                if scene_number is None:
                    continue
                scene_number = int(scene_number)
            except Exception:
                continue
            record = {
                "audio_url": art.get("audio_url", ""),
                "audio_path": art.get("file_path", ""),
                "duration": float(art.get("duration_sec") or 0.0),
                "provider": art.get("provider", ""),
                "voice_id": art.get("voice_id") or voice_settings.get("voice_id", ""),
                "metadata": art.get("metadata", {}),
            }
            assets[str(scene_number)] = record
            changed = True
            try:
                self.write_shared_artifact(
                    kind="voice",
                    stage="voiceover",
                    payload={
                        "file_path": record.get("audio_path", ""),
                        "url": record.get("audio_url", ""),
                        "duration_sec": record.get("duration", 0.0),
                        "metadata": record.get("metadata", {}),
                    },
                    scene_number=scene_number,
                    tool="voice_synth_tool",
                    workflow_state_id=str(workflow_state_id),
                )
            except Exception:
                pass

        if not changed:
            return
        try:
            from ..core.config import settings as _cfg
            if bool(getattr(_cfg, "ARTIFACTS_SINGLE_WRITE_MODE", False)):
                return
            store.put(
                str(workflow_state_id),
                "voice_assets",
                assets,
                agent=self.agent_name,
            )
        except Exception as exc:
            self.logger.error("Shared memory write voice_assets failed: %s", exc, exc_info=True)
            raise AgentError("Shared memory write failed (voice_assets)") from exc

    async def _think_and_plan(
        self,
        current_state: Dict[str, Any],
        task: Task,
        execution: AgentExecution,
        iteration: int,
    ) -> Dict[str, Any]:
        current_state = current_state or {}
        scene_facts = current_state.get("voice_scene_facts") or []
        actionable = [
            fact
            for fact in scene_facts
            if fact.get("should_narrate", True) and not fact.get("has_voice_asset")
        ]
        if not actionable:
            return {
                "action": "noop",
                "reason": "no_actionable_scene",
                "plan_llm": None,
            }

        messages = build_neutral_act_messages(self.agent_name, current_state)
        fc_plan = await self.llm_function_call(
            messages=messages,
            context_description="voice_synthesis_plan_fc",
            temperature=0.2,
        )
        planned_calls = list(fc_plan.get("tool_calls") or []) if isinstance(fc_plan, dict) else []
        plan_llm = fc_plan.get("llm_response") if isinstance(fc_plan, dict) else None

        if not planned_calls:
            return {
                "action": "noop",
                "reason": "no_calls_planned",
                "plan_llm": plan_llm,
            }

        return {
            "action": "execute_planned_calls",
            "tool_calls": planned_calls,
            "plan_llm": plan_llm,
        }

    async def _execute_action(
        self,
        action_plan: Dict[str, Any],
        input_data: Dict[str, Any],
        execution: AgentExecution,
        db: Session,
        iteration: int,
    ) -> Dict[str, Any]:
        action = action_plan.get("action")
        plan_llm = action_plan.get("plan_llm")
        wf_id = str(input_data["workflow_state_id"])
        if action == "noop" or not action_plan.get("tool_calls"):
            return {
                "success": True,
                "subtask_state": "complete",
                "processed": 0,
                "executed_calls": [],
                "act_log": [],
                "react_metrics": {},
                "plan_llm": plan_llm,
                "reason": action_plan.get("reason") or "noop",
            }

        tool_calls = list(action_plan.get("tool_calls") or [])
        exec_out = await self.execute_tool_calls(tool_calls, collect_facts=True)
        executed_calls = exec_out.get("executed_calls") or []
        act_log = exec_out.get("act_log") or []
        react_metrics = exec_out.get("react_metrics") or {}

        artifacts = normalize_executed_calls_to_artifacts(
            executed_calls,
            kind="audio",
            include_prompt=False,
        )
        shared_wm = ensure_mas_memory(wf_id) if wf_id else None
        await persist_scene_outputs(
            artifacts=artifacts,
            kind="voice",
            agent_memory=self.wm,
            shared_memory=shared_wm,
            include_prompt=False,
        )
        store = self.shared_memory_store
        voice_settings = self._resolve_voice_settings(
            wf_id,
            incoming={},
            store=store,
            persist=False,
        )
        self._persist_voice_artifacts(
            workflow_state_id=wf_id,
            voice_settings=voice_settings,
            artifacts=artifacts,
        )

        processed = len(artifacts)
        success = any(call.get("success") for call in executed_calls)

        return {
            "success": success,
            "subtask_state": "complete" if success else "partial",
            "processed": processed,
            "plan_llm": plan_llm,
            "executed_calls": executed_calls,
            "act_log": act_log,
            "react_metrics": react_metrics,
            "voice_artifacts": artifacts,
        }

    async def _draft_narration(
        self,
        scene_context: Dict[str, Any],
        voice_plan: Dict[str, Any],
    ) -> str:
        raise AgentError("VoiceSynthesizerAgent 禁止自动撰写旁白文案")

    async def _store_voice_asset(
        self,
        task_id: str,
        scene_number: int,
        target_duration: float,
        synth_payload: Dict[str, Any],
        voice_settings: Dict[str, Any],
        execution: AgentExecution,
    ) -> str:
        # Deprecated: 工具调用应在 PLAN→ACT 中通过 execute_tool_calls 执行，不再直连。
        raise AgentError("Deprecated: _store_voice_asset is not used; use FC-planned and executed calls.")

    @emit_progress_snapshot
    async def _reflect_on_results(
        self,
        action_result: Dict[str, Any],
        current_state: Dict[str, Any],
        task: Task,
        iteration: int,
    ) -> Dict[str, Any]:
        current_state = current_state or {}
        scene_facts = current_state.get("voice_scene_facts") or []
        actionable = [
            fact for fact in scene_facts if fact.get("should_narrate", True)
        ]
        newly_completed = {
            int(art.get("scene_number"))
            for art in (action_result.get("voice_artifacts") or [])
            if art.get("scene_number") is not None
        }
        remaining = [
            fact
            for fact in actionable
            if not fact.get("has_voice_asset") and fact.get("scene_number") not in newly_completed
        ]
        completed_count = len(newly_completed)
        summary_bits: List[str] = []
        if completed_count:
            summary_bits.append(f"生成 {completed_count} 条旁白")
        if remaining:
            summary_bits.append(f"剩余 {len(remaining)} 条待生成")
        if not summary_bits:
            summary_bits.append("本轮无新增旁白")
        summary = "；".join(summary_bits)

        return {
            "task_complete": len(remaining) == 0,
            "completed_reason": summary if len(remaining) == 0 else None,
            "reflection_summary": summary,
        }

    async def _finalize_success_results(
        self,
        final_action_result: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        base = await super()._finalize_success_results(final_action_result, context)
        wf_id = context.get("workflow_state_id") or self.workflow_state_id
        finals, failed = finalize_scene_outputs(
            kind="voice",
            workflow_id=str(wf_id) if wf_id else None,
            agent_memory=self.wm,
        )
        result = dict(base or {})
        result["final_completed_scenes"] = finals
        result["final_failed_scenes"] = failed
        return result

    def _truncate_text(self, text: str) -> str:
        if len(text) <= self._max_chars:
            return text
        clipped = text[: self._max_chars]
        # Avoid cutting in the middle of a sentence if possible
        for delimiter in ["。", "！", "？", ".", "!", "?"]:
            idx = clipped.rfind(delimiter)
            if idx > self._max_chars * 0.6:
                return clipped[: idx + 1]
        return clipped

    @staticmethod
    def _clean_text_fragment(value: str, max_len: int = 240) -> str:
        if not value:
            return ""
        text = str(value)
        text = re.sub(r"[\[\]{}（）()<>]", "", text)
        text = re.sub(r"[【】]", "", text)
        text = re.sub(r"[·•●◎◇◆☆★]+", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) > max_len:
            text = text[: max_len - 1].rstrip() + "…"
        return text

    def _build_prompt_context(self, scene_context: Dict[str, Any], voice_plan: Dict[str, Any]) -> str:
        scene_number = scene_context.get("scene_number")
        title = self._clean_text_fragment(scene_context.get("scene_title", ""), 80)
        narrative_desc = self._clean_text_fragment(scene_context.get("narrative_description", ""), 140)
        visual_desc = self._clean_text_fragment(scene_context.get("visual_description", ""), 140)
        script_excerpt = self._clean_text_fragment(scene_context.get("script_text", ""), 160)
        concept_overview = self._clean_text_fragment(scene_context.get("concept_overview", ""), 160)
        guidance = scene_context.get("voice_guidance", {}) or {}
        objective = self._clean_text_fragment(guidance.get("objective", ""), 80)
        emotion = self._clean_text_fragment(guidance.get("emotion", ""), 40)
        key_points = guidance.get("key_points") or []
        if isinstance(key_points, str):
            key_points = [seg.strip() for seg in key_points.replace("、", ",").split(",") if seg.strip()]
        key_points = [self._clean_text_fragment(item, 40) for item in key_points if item]
        tone_keywords = voice_plan.get("tone_keywords", []) or []
        persona = self._clean_text_fragment(voice_plan.get("persona", ""), 60)
        style_notes = self._clean_text_fragment(voice_plan.get("style_notes", ""), 100)

        lines: List[str] = []
        if scene_number is not None:
            lines.append(f"场景#{scene_number}")
        if title:
            lines.append(f"标题：{title}")
        if objective:
            lines.append(f"旁白意图：{objective}")
        if emotion:
            lines.append(f"情绪倾向：{emotion}")
        if key_points:
            lines.append("重点：" + "、".join(key_points[:4]))
        if narrative_desc:
            lines.append(f"故事描述：{narrative_desc}")
        elif visual_desc:
            lines.append(f"视觉氛围：{visual_desc}")
        if script_excerpt and script_excerpt not in lines:
            lines.append(f"脚本提示：{script_excerpt}")
        if concept_overview:
            lines.append(f"世界观提示：{concept_overview}")
        if persona:
            lines.append(f"旁白人设：{persona}")
        if tone_keywords:
            lines.append("语气关键词：" + "、".join(tone_keywords[:5]))
        if style_notes:
            lines.append(f"额外风格提示：{style_notes}")

        return "\n".join(lines)

    def _estimate_char_limit(self, target_duration: float) -> int:
        if target_duration and target_duration > 0:
            approx = int(round(target_duration * 3.6))
        else:
            approx = 200
        approx = max(28, min(self._max_chars, approx))
        return approx

    def _determine_token_budget(self, char_limit: int) -> int:
        """Scale token budget without introducing brittle magic numbers."""
        upper = getattr(settings, "LLM_MAX_TOKENS_STANDARD", 12800)
        # 语音文案通常精简，但需要足够空间容纳 JSON 包装
        base = max(int(char_limit * 6), 400)
        # 对长场景低限度放宽，但仍受 global 上限约束
        return min(max(base, 400), upper)

    def _sanitize_narration_text(self, text: str, char_limit: int) -> str:
        narration_text = (text or "").strip()
        if not narration_text:
            return ""
        for prefix in ("旁白：", "旁白:", "解说：", "解说:"):
            if narration_text.startswith(prefix):
                narration_text = narration_text[len(prefix):].lstrip()
        if len(narration_text) > char_limit:
            narration_text = narration_text[: char_limit - 1].rstrip("，,。；; ") + "…"
        return narration_text

    def _suggest_speed_multiplier(
        self,
        target_duration: float,
        char_count: int,
        base_speed: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Suggest voice speed settings without forcing narration去填满时长."""
        natural_duration = 0.0
        if char_count > 0:
            natural_duration = max(char_count / 4.0, 0.5)

        base = 1.0
        try:
            if base_speed is not None:
                base = max(0.5, min(2.0, float(base_speed)))
        except (TypeError, ValueError):
            base = 1.0

        coverage_ratio: Optional[float] = None
        if target_duration > 0 and natural_duration > 0:
            coverage_ratio = round(natural_duration / target_duration, 2)

        if settings.VOICE_AUTO_SPEED_MATCH:
            # legacy behaviour: gently adjust speed when开启自动匹配
            multiplier = natural_duration / target_duration if target_duration > 0 else base
            multiplier = max(settings.VOICE_MIN_AUTO_SPEED, min(settings.VOICE_MAX_AUTO_SPEED, multiplier))
            multiplier = round(multiplier, 2)
        else:
            multiplier = base

        return {
            "multiplier": multiplier,
            "natural_duration": natural_duration,
            "coverage_ratio": coverage_ratio,
        }

    # Removed voice selection helper chain; voice_id 由工具 schema 枚举，PLAN 直接选择。

    # Removed: _build_voice_candidates

    # Removed: _choose_voice_via_llm

    # Removed: _get_voice_profiles（改由工具提供能力或 schema 枚举）

    # Removed: _infer_voice_preferences

    # Removed: _filter_voice_candidates

    # Removed: _rank_voice_candidates

    @staticmethod
    def _coerce_bool(value: Any, default: bool) -> bool:
        if value is None:
            return bool(default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() not in {"false", "0", "no", "off", ""}
        return bool(value)
