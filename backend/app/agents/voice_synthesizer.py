"""Voice Synthesizer Agent - generate scene voice-overs via MAS ReAct loop."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from .react_agent import ReActAgent, AgentError
from .utils.progress_snapshot import emit_progress_snapshot
from ..models import Task, AgentType
from ..core.config import settings
from .utils.artifacts import (
    normalize_executed_calls_to_artifacts,
    persist_scene_outputs,
    finalize_scene_outputs,
)
from .utils.fc_messages import build_neutral_act_messages
from .utils.memory_helpers import get_mas_working_memory


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

    def _build_voice_orchestration_report(
        self,
        *,
        status: str,
        completion_state: str,
        completed_count: int,
        failed_count: int,
        reported_gaps: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        return {
            "status": status,
            "boundary_event": "scene_voice_completed",
            "gate_triggers": [],
            "artifacts": [{"kind": "shared_fact", "ref": "scene_outputs.voice"}],
            "reflection": {
                "completion_state": completion_state,
                "reported_gaps": list(reported_gaps or []),
                "reported_hints": [],
                "completed_scene_count": int(completed_count),
                "failed_scene_count": int(failed_count),
            },
        }

    async def _execute_impl(
        self,
        task: Task,
        input_data: Dict[str, Any],
        db: Session = None,
    ) -> Dict[str, Any]:
        return await super()._execute_impl(task, input_data, db)


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
                stored = store.get("voice_settings", {}) or {}
            except Exception as exc:
                self.logger.error("Shared memory read voice_settings failed: %s", exc, exc_info=True)
                raise AgentError("Shared memory read failed (voice_settings)") from exc

        settings_payload = self._build_voice_settings_payload(incoming, stored)
        if persist and store is not None:
            try:
                if settings_payload != stored:
                    store.put("voice_settings", settings_payload)
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

    def _persist_voice_artifacts(
        self,
        *,
        workflow_state_id: str,
        voice_settings: Dict[str, Any],
        artifacts: List[Dict[str, Any]],
    ) -> None:
        if not artifacts:
            return
        shared_wm = get_mas_working_memory(str(workflow_state_id), service=self.short_term_service)
        try:
            assets = shared_wm.get("voice_assets", {}) or {}
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
                "audio_path": art.get("audio_path") or art.get("file_path", ""),
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
            shared_wm.put("voice_assets", assets)
        except Exception as exc:
            self.logger.error("Shared memory write voice_assets failed: %s", exc, exc_info=True)
            raise AgentError("Shared memory write failed (voice_assets)") from exc

    async def _think_and_plan(
        self,
        current_state: Dict[str, Any],
        task: Task,
        iteration: int,
    ) -> Dict[str, Any]:
        plan_ctx = current_state or {}

        messages = self.build_plan_messages(plan_ctx)
        fc_plan = await self.llm_function_call(
            messages=messages,
            context_description="voice_synthesis_plan_fc",
            temperature=0.2,
        )
        tool_calls = list(fc_plan.get("tool_calls") or []) if isinstance(fc_plan, dict) else []
        plan_llm = fc_plan.get("llm_response") if isinstance(fc_plan, dict) else None

        if not tool_calls:
            return {
                "action": "noop",
                "reason": "no_calls_planned",
                "plan_llm": plan_llm,
            }

        return {
            "action": "execute_tool_calls",
            "tool_calls": tool_calls,
            "plan_llm": plan_llm,
        }

    @staticmethod
    def _try_fill_scene_number_for_voice_call(args: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize tool-call args for voice synthesis: ensure `scene_number` is present when derivable."""
        if not isinstance(args, dict):
            return args
        scene_number = args.get("scene_number")
        if scene_number is not None:
            # Ensure reference_id exists for audit/dedup when possible.
            if not args.get("reference_id"):
                try:
                    sn = int(scene_number)
                    return {**args, "reference_id": f"scene_{sn}_narration"}
                except Exception:
                    return args
            return args
        reference_id = args.get("reference_id")
        if not isinstance(reference_id, str) or not reference_id:
            md = args.get("metadata")
            if isinstance(md, dict) and md.get("scene_number") is not None:
                return {**args, "scene_number": md.get("scene_number")}
            return args
        import re as _re

        m = _re.search(r"(?:^|[^0-9])scene[_-]?(?P<num>[0-9]{1,4})(?:[^0-9]|$)", reference_id.lower())
        if not m:
            return args
        try:
            sn = int(m.group("num"))
        except Exception:
            return args
        return {**args, "scene_number": sn}

    async def _execute_action(
        self,
        action_plan: Dict[str, Any],
        input_data: Dict[str, Any],
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
        # Contract-first normalization: fill missing scene_number from reference_id for legacy plans.
        normalized_calls: List[Dict[str, Any]] = []
        for call in tool_calls:
            if not isinstance(call, dict):
                normalized_calls.append(call)
                continue
            fn = (call.get("function") or {}).get("name")
            if not isinstance(fn, str) or not fn.startswith("voice_synth_tool."):
                normalized_calls.append(call)
                continue
            func = dict(call.get("function") or {})
            raw_args = func.get("arguments", {})
            if isinstance(raw_args, str):
                try:
                    import json as _json

                    raw_args = _json.loads(raw_args)
                except Exception:
                    normalized_calls.append(call)
                    continue
            if not isinstance(raw_args, dict):
                normalized_calls.append(call)
                continue
            func["arguments"] = self._try_fill_scene_number_for_voice_call(raw_args)
            normalized_calls.append({**call, "function": func})
        tool_calls = normalized_calls
        exec_out = await self.execute_tool_calls(tool_calls, collect_facts=True)
        executed_calls = exec_out.get("executed_calls") or []
        act_log = exec_out.get("act_log") or []
        react_metrics = exec_out.get("react_metrics") or {}

        artifacts = normalize_executed_calls_to_artifacts(
            executed_calls,
            kind="audio",
            include_prompt=False,
        )
        shared_wm = get_mas_working_memory(wf_id, service=self.short_term_service) if wf_id else None
        await persist_scene_outputs(
            artifacts=artifacts,
            kind="voice",
            agent_memory=None,
            shared_memory=shared_wm,
            include_prompt=False,
        )
        voice_settings = self._resolve_voice_settings(
            wf_id,
            incoming={},
            store=shared_wm,
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
    ) -> str:
        # Deprecated: 工具调用应在 PLAN→ACT 中通过 execute_tool_calls 执行，不再直连。
        raise AgentError("Deprecated: _store_voice_asset is not used; use FC tool calls.")

    @emit_progress_snapshot
    async def _reflect_on_results(
        self,
        action_result: Dict[str, Any],
        current_state: Dict[str, Any],
        task: Task,
        iteration: int,
    ) -> Dict[str, Any]:
        artifacts = action_result.get("voice_artifacts") or []
        completed_count = len(artifacts) if isinstance(artifacts, list) else 0
        summary = f"生成 {completed_count} 条旁白" if completed_count else "本轮无新增旁白"
        return {"success": True, "reflection_summary": summary}

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
        result["orchestration_report"] = self._build_voice_orchestration_report(
            status="completed",
            completion_state="completed",
            completed_count=len(finals),
            failed_count=len(failed),
        )
        return result

    async def _finalize_incomplete_results(
        self,
        context: Dict[str, Any],
        task: Task,
    ) -> Dict[str, Any]:
        result = await super()._finalize_incomplete_results(context, task)
        wf_id = context.get("workflow_state_id") or self.workflow_state_id
        finals, failed = finalize_scene_outputs(
            kind="voice",
            workflow_id=str(wf_id) if wf_id else None,
            agent_memory=self.wm,
        )
        result["final_completed_scenes"] = finals
        result["final_failed_scenes"] = failed
        result["orchestration_report"] = self._build_voice_orchestration_report(
            status="partial",
            completion_state=str(result.get("subtask_state") or "partial"),
            completed_count=len(finals),
            failed_count=len(failed),
            reported_gaps=["scene_voice_generation_incomplete"],
        )
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
