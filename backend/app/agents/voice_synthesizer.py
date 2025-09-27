"""Voice Synthesizer Agent - generate scene voice-overs via MAS ReAct loop."""
from __future__ import annotations

import json
import os
import re
import math
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from .react_agent import ReActAgent, AgentError
from ..models import Task, AgentExecution, AgentType
from ..core.workflow_state import workflow_manager, WorkflowStatus
from ..core.config import settings
from ..services.voice_service import voice_service


class VoiceSynthesizerAgent(ReActAgent):
    """Generate per-scene narration audio using supplier-agnostic TTS tools."""

    def __init__(self, llms=None):
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
        )
        self._batch_size = 1
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
        iteration_context: Dict[str, Any],
        iteration: int,
    ) -> Dict[str, Any]:
        self._validate_input(input_data, ["workflow_state_id"])
        wf_id = input_data["workflow_state_id"]
        workflow_state = workflow_manager.get_workflow(wf_id)
        if not workflow_state:
            raise AgentError(f"WorkflowState {wf_id} not found")

        incoming_settings = input_data.get("voice_settings") or {}
        wf_voice_settings = workflow_state.voice_settings if isinstance(workflow_state.voice_settings, dict) else {}
        preferred_voice_ids = incoming_settings.get("preferred_voice_ids")
        if preferred_voice_ids is None:
            preferred_voice_ids = wf_voice_settings.get("preferred_voice_ids")
        if isinstance(preferred_voice_ids, str):
            preferred_voice_ids = [v.strip() for v in preferred_voice_ids.replace(";", ",").split(",") if v.strip()]
        elif isinstance(preferred_voice_ids, list):
            preferred_voice_ids = [str(v).strip() for v in preferred_voice_ids if str(v).strip()]
        else:
            preferred_voice_ids = None

        default_auto = getattr(settings, "VOICE_AUTO_SELECT_DEFAULT", True)
        auto_select_source = incoming_settings.get("auto_select")
        if auto_select_source is None:
            auto_select_source = wf_voice_settings.get("auto_select")
        auto_select_flag = self._coerce_bool(auto_select_source, default_auto)

        voice_id_raw = incoming_settings.get("voice_id")
        if not voice_id_raw:
            voice_id_raw = wf_voice_settings.get("voice_id")
        if isinstance(voice_id_raw, str):
            voice_id = voice_id_raw.strip()
        elif voice_id_raw is None:
            voice_id = ""
        else:
            voice_id = str(voice_id_raw).strip()
        if not voice_id:
            voice_id = getattr(settings, "VOICE_DEFAULT_VOICE_ID", "")

        default_settings = {
            "voice_id": voice_id,
            "language": incoming_settings.get("language") or wf_voice_settings.get("language") or "zh-CN",
            "speed": incoming_settings.get("speed", wf_voice_settings.get("speed", 1.0)),
            "pitch": incoming_settings.get("pitch", wf_voice_settings.get("pitch", 1.0)),
            "sample_rate": incoming_settings.get(
                "sample_rate",
                wf_voice_settings.get("sample_rate", getattr(settings, "VOICE_DEFAULT_SAMPLE_RATE", 16000)),
            ),
            "audio_format": incoming_settings.get(
                "audio_format",
                wf_voice_settings.get("audio_format", getattr(settings, "VOICE_DEFAULT_FORMAT", "wav")),
            ),
            "style": incoming_settings.get("style", wf_voice_settings.get("style")),
            "auto_select": auto_select_flag,
            "preferred_voice_ids": preferred_voice_ids,
        }
        if not default_settings["voice_id"]:
            default_settings["voice_id"] = "voice_default"
        workflow_state.update_voice_settings(default_settings)
        iteration_context["voice_settings"] = default_settings
        working_state = iteration_context.setdefault("working_state", {})
        working_state["voice_settings"] = default_settings

        voice_plan = input_data.get("voice_plan") or getattr(workflow_state, "voice_plan", {}) or {}
        iteration_context["voice_plan"] = voice_plan

        guidance_map: Dict[int, Dict[str, Any]] = {}
        for entry in voice_plan.get("scene_guidance", []) or []:
            if not isinstance(entry, dict):
                continue
            scene_key = entry.get("scene_number") or entry.get("sceneIndex")
            try:
                scene_number = int(scene_key)
            except (TypeError, ValueError):
                continue
            should_raw = entry.get("should_narrate")
            if isinstance(should_raw, str):
                should = should_raw.strip().lower() not in {"false", "0", "no", "off"}
            else:
                should = should_raw
            raw_points = entry.get("key_points") or entry.get("topics") or entry.get("highlights") or []
            if isinstance(raw_points, str):
                key_points = [seg.strip() for seg in raw_points.replace("、", ",").split(",") if seg.strip()]
            elif isinstance(raw_points, list):
                key_points = [str(seg).strip() for seg in raw_points if str(seg).strip()]
            else:
                key_points = []
            pace_tag = str(entry.get("pace_tag", "")).strip().lower()
            target_chars = entry.get("target_char_count")
            guidance_map[scene_number] = {
                "scene_number": scene_number,
                "should_narrate": should,
                "objective": entry.get("objective") or entry.get("purpose") or "",
                "emotion": entry.get("emotion") or entry.get("tone") or "",
                "key_points": key_points,
                "pace_tag": pace_tag,
                "target_char_count": target_chars,
            }

        concept_plan = getattr(workflow_state, "concept_plan", {}) or {}
        iteration_context["concept_plan"] = concept_plan
        scene_cache = iteration_context.setdefault("scene_context_cache", {})

        default_enabled = bool(voice_plan.get("enabled")) and str(voice_plan.get("mode", "none")).lower() != "none"

        scenes = workflow_state.scenes
        pending: List[Dict[str, Any]] = []
        completed: List[Dict[str, Any]] = []
        skipped: List[int] = []

        for scene in scenes:
            scene_number = getattr(scene, "scene_number", None)
            if scene_number is None:
                continue
            guidance = dict(guidance_map.get(scene_number, {}) or {})
            scene_pacing = getattr(scene, "pacing_and_timing", {}) or {}

            if scene_pacing:
                scene_should = scene_pacing.get("should_narrate")
                if scene_should is not None:
                    guidance["should_narrate"] = bool(scene_should)
                pace_from_scene = scene_pacing.get("pace_tag")
                if pace_from_scene:
                    guidance["pace_tag"] = str(pace_from_scene).strip().lower()
                char_count_hint = scene_pacing.get("target_char_count")
                if char_count_hint is not None:
                    try:
                        guidance["target_char_count"] = int(char_count_hint)
                    except (TypeError, ValueError):
                        guidance["target_char_count"] = char_count_hint

                # 保持其他在 voice_plan 中的提示，例如 objective/emotion
                if "scene_number" not in guidance:
                    guidance["scene_number"] = scene_number

            should_narrate = guidance.get("should_narrate")
            if should_narrate is None:
                should_narrate = default_enabled
            if not should_narrate:
                skipped.append(scene_number)
                scene_cache.pop(scene_number, None)
                guidance_map[scene_number] = guidance
                continue

            target_duration = float(getattr(scene, "duration", 0.0) or 0.0)
            existing_path = getattr(scene, "voice_over_audio_path", "") or ""
            video_ref = getattr(scene, "video_path", None) or getattr(scene, "video_url", "")
            existing_text = (getattr(scene, "voice_over_text", "") or "").strip()

            payload = {
                "scene_number": scene_number,
                "scene_title": getattr(scene, "title", ""),
                "target_duration": target_duration,
                "scene_duration": target_duration,
                "narrative_description": getattr(scene, "narrative_description", ""),
                "visual_description": getattr(scene, "visual_description", ""),
                "mood": getattr(scene, "mood_and_atmosphere", ""),
                "script_text": getattr(scene, "script_text", ""),
                "video_prompt": getattr(scene, "video_prompt", "") or getattr(scene, "video_generation_params", {}).get("prompt", ""),
                "video_url": video_ref,
                "video_generation_params": getattr(scene, "video_generation_params", {}),
                "voice_guidance": guidance,
                "existing_text": existing_text,
                "existing_path": existing_path,
                "concept_overview": concept_plan.get("overview", ""),
                "original_char_count": len(existing_text),
            }
            # 更新 guidance_map，确保后续使用最新的 pacing 信息
            guidance_map[scene_number] = guidance
            scene_cache[scene_number] = payload.copy()

            if existing_path and os.path.exists(existing_path):
                completed.append(payload)
            else:
                pending.append(payload)

        iteration_context["pending_scenes"] = pending
        iteration_context.setdefault("completed_scenes", [])
        working_state["pending_scene_numbers"] = [item.get("scene_number") for item in pending]
        working_state["skipped_scene_numbers"] = skipped

        facts = {
            "summary": {
                "total_scenes": len(scenes),
                "pending": len(pending),
                "completed": len(completed),
                "skipped": len(skipped),
            },
            "voice_settings": default_settings,
            "voice_plan": voice_plan,
            "pending_scenes": pending[: self._batch_size],
            "completed_scenes": completed,
            "max_chars_per_request": self._max_chars,
        }

        try:
            workflow_state.set_status(
                WorkflowStatus.VOICE_SYNTHESIZING,
                f"Voice synthesis pending {len(pending)} scenes",
                workflow_state.progress_percentage,
            )
        except Exception:
            pass

        return facts

    async def _think_and_plan(
        self,
        current_state: Dict[str, Any],
        task: Task,
        execution: AgentExecution,
        iteration: int,
    ) -> Dict[str, Any]:
        pending = self.iteration_context.get("pending_scenes", [])
        if not pending:
            return {"action": "noop", "parameters": {}}
        planned_batches = self.iteration_context.get("planned_batches") or []
        batch: List[Dict[str, Any]] = []
        if planned_batches:
            batch = planned_batches.pop(0)
            self.iteration_context["planned_batches"] = planned_batches
        if not batch:
            batch = pending[: self._batch_size]
        try:
            working_state = self.iteration_context.setdefault("working_state", {})
            working_state["current_plan_batch"] = [
                item.get("scene_number") for item in batch if isinstance(item, dict)
            ]
        except Exception:
            pass
        return {
            "action": "voice_synthesis_fc",
            "parameters": {
                "batch": batch,
                "batch_size": len(batch),
            },
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
        if action == "noop":
            return {
                "success": True,
                "subtask_state": "complete",
                "processed": 0,
                "loop_end_reason": "no_pending_voice",
            }
        if action not in {"voice_synthesis_fc", "synthesize_scene_batch"}:
            raise AgentError(f"Unknown action for voice agent: {action}")

        batch = action_plan.get("parameters", {}).get("batch", [])
        if not batch:
            return {
                "success": True,
                "subtask_state": "complete",
                "processed": 0,
                "loop_end_reason": "empty_batch",
            }

        wf_id = input_data["workflow_state_id"]
        workflow_state = workflow_manager.get_workflow(wf_id)
        if not workflow_state:
            raise AgentError(f"WorkflowState {wf_id} not found during execution")

        voice_settings = dict(self.iteration_context.get("voice_settings", {}))
        voice_plan = self.iteration_context.get("voice_plan", {}) or {}
        scene_cache = self.iteration_context.setdefault("scene_context_cache", {})
        batch_map = {item.get("scene_number"): item for item in batch if item.get("scene_number") is not None}

        processed = 0
        errors: List[str] = []
        uploads: List[Dict[str, Any]] = []
        completed_scene_numbers: set = set()
        failed_scene_numbers: List[int] = []

        for item in batch:
            scene_number = item.get("scene_number")
            if scene_number is None:
                continue

            scene_context = (scene_cache.get(scene_number) or {}).copy()
            scene_context.update(item)

            text = (scene_context.get("existing_text") or "").strip()
            if not text:
                raise AgentError(
                    f"Scene {scene_number} 缺少 voice_over_text，请检查脚本阶段是否生成旁白文案"
                )

            scene_context["narration_text"] = text
            scene_context["existing_text"] = text
            scene_cache[scene_number] = scene_context

            target_duration = float(scene_context.get("target_duration", 0.0) or 0.0)
            if target_duration <= 0:
                raise AgentError(
                    f"Scene {scene_number} 缺少有效的目标时长，无法匹配配音节奏"
                )

            voice_guidance = scene_context.get("voice_guidance", {}) or {}
            pace_tag = str(voice_guidance.get("pace_tag", "")).strip().lower()
            char_rate_map = getattr(settings, "VOICE_PACE_CHAR_RATES", {}) or {}
            speed_map = getattr(settings, "VOICE_PACE_SPEED_MAP", {}) or {}
            if pace_tag not in char_rate_map or pace_tag not in speed_map:
                raise AgentError(
                    f"Scene {scene_number} pace_tag 无法识别: {pace_tag or 'empty'}"
                )

            char_rate = float(char_rate_map[pace_tag])
            if char_rate <= 0:
                raise AgentError(
                    f"Scene {scene_number} pace_tag={pace_tag} 对应的字符速率无效"
                )
            recommended_speed = float(speed_map[pace_tag])
            char_count = len(text)
            estimated_duration = char_count / char_rate
            coverage_ratio = estimated_duration / target_duration if target_duration > 0 else None

            scene_context["recommended_speed"] = recommended_speed
            scene_context["speech_duration_estimate"] = estimated_duration
            if coverage_ratio is not None:
                scene_context["speech_coverage_ratio"] = round(coverage_ratio, 3)

            try:
                preview = self._clean_text_fragment(text, 120)
                if preview:
                    self.logger.info(
                        "Scene %s narration preview: %s",
                        scene_number,
                        preview,
                    )
            except Exception:
                pass

            target_char_count = voice_guidance.get("target_char_count")
            if target_char_count is not None:
                try:
                    target_char_count = int(target_char_count)
                except (TypeError, ValueError):
                    target_char_count = None
            if target_char_count:
                tolerance = max(6, int(round(target_char_count * 0.2)))
                diff = abs(char_count - target_char_count)
                if diff > tolerance:
                    self.logger.warning(
                        "Scene %s 旁白字数与规划不符 (实际 %s / 目标 %s)",
                        scene_number,
                        char_count,
                        target_char_count,
                    )

            try:
                self.logger.info(
                    "Scene %s narration pacing: text_len=%s target=%.2fs estimated=%.2fs speed=%.2f coverage=%.2f target_chars=%s",
                    scene_number,
                    char_count,
                    target_duration,
                    estimated_duration,
                    recommended_speed,
                    coverage_ratio if coverage_ratio is not None else -1.0,
                    target_char_count,
                )
            except Exception:
                pass

            auto_select_voice = bool(voice_settings.get("auto_select", True))
            voice_id = voice_settings.get("voice_id")
            voice_selection_debug: Optional[Dict[str, Any]] = None
            if auto_select_voice or not voice_id:
                voice_id, voice_selection_debug = await self._select_voice_for_scene(
                    scene_context,
                    voice_plan,
                    voice_settings,
                )
            scene_context["selected_voice_id"] = voice_id
            if voice_selection_debug:
                scene_context["voice_selection_debug"] = voice_selection_debug

            truncated_text = self._truncate_text(text)
            tts_request = {
                "text": truncated_text,
                "voice_id": voice_id,
                "language": voice_settings.get("language", "zh-CN"),
                "speed": recommended_speed,
                "pitch": voice_settings.get("pitch", 1.0),
                "sample_rate": voice_settings.get("sample_rate"),
                "audio_format": voice_settings.get("audio_format"),
                "style": voice_settings.get("style"),
                "reference_id": f"{workflow_state.task_id}_scene_{scene_number}",
                "metadata": {
                    "scene_number": scene_number,
                    "voice_plan_mode": voice_plan.get("mode"),
                    "narration_text": text,
                    "voice_guidance": scene_context.get("voice_guidance", {}),
                    "recommended_speed": recommended_speed,
                    "target_duration": target_duration,
                    "estimated_speech_duration": estimated_duration,
                    "speech_coverage_ratio": scene_context.get("speech_coverage_ratio"),
                    "target_char_count": target_char_count,
                    "selected_voice_id": voice_id,
                },
            }
            if voice_selection_debug:
                safe_debug = dict(voice_selection_debug)
                prefs = safe_debug.get("preferred_filters")
                if isinstance(prefs, dict) and isinstance(prefs.get("categories"), set):
                    prefs = prefs.copy()
                    prefs["categories"] = sorted(prefs["categories"])
                    safe_debug["preferred_filters"] = prefs
                tts_request["metadata"]["voice_selection"] = safe_debug

            try:
                synth_result = await self.use_tool("voice_synth_tool", "synthesize_voice", tts_request)
            except Exception as exc:
                errors.append(f"scene {scene_number}: TTS failed ({exc})")
                failed_scene_numbers.append(scene_number)
                continue

            synth_payload = getattr(synth_result, "result", synth_result) or {}
            metadata = synth_payload.get("metadata") or {}
            metadata.update(tts_request.get("metadata", {}))
            synth_payload["metadata"] = metadata

            try:
                audio_url = await self._store_voice_asset(
                    workflow_state,
                    scene_number,
                    synth_payload,
                    voice_settings,
                    execution,
                )
            except Exception as exc:
                errors.append(f"scene {scene_number}: {exc}")
                failed_scene_numbers.append(scene_number)
                continue

            processed += 1
            uploads.append({"scene": scene_number, "url": audio_url})
            completed_scene_numbers.add(scene_number)
            scene_cache[scene_number] = scene_context
            batch_map[scene_number] = scene_context

        if completed_scene_numbers:
            self._finalize_batch_progress(completed_scene_numbers, batch_map)
        else:
            if not failed_scene_numbers and batch_map:
                failed_scene_numbers = list(batch_map.keys())

        if failed_scene_numbers:
            plan_batches = self.iteration_context.setdefault("planned_batches", [])
            requeue_batch: List[Dict[str, Any]] = []
            for number in failed_scene_numbers:
                ctx = scene_cache.get(number)
                if ctx:
                    requeue_batch.append(dict(ctx))
            if requeue_batch:
                plan_batches.insert(0, requeue_batch)
                try:
                    self.logger.debug(
                        "Requeued failed scenes for next iteration: %s",
                        failed_scene_numbers,
                    )
                except Exception:
                    pass
        pending_remaining = len(self.iteration_context.get("pending_scenes", []))
        success_flag = processed > 0 and not errors

        return {
            "success": processed > 0,
            "processed": processed,
            "errors": errors,
            "uploads": uploads,
            "pending_remaining": pending_remaining,
            "subtask_state": "complete" if pending_remaining == 0 else "partial",
            "loop_end_reason": "natural_complete" if pending_remaining == 0 else "pending_remaining",
            "react_metadata": {
                "success": success_flag,
                "drafted": processed,
            },
        }

    async def _draft_narration(
        self,
        scene_context: Dict[str, Any],
        voice_plan: Dict[str, Any],
        workflow_state,
    ) -> str:
        raise AgentError("VoiceSynthesizerAgent 禁止自动撰写旁白文案")

    async def _build_plan_only_messages(
        self,
        input_data: Dict[str, Any],
        current_state: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        pending = self.iteration_context.get("pending_scenes", []) or []
        if not pending:
            return []

        summary_payload: List[Dict[str, Any]] = []
        for item in pending:
            if not isinstance(item, dict):
                continue
            narration_text = (item.get("existing_text") or "").strip()
            summary_payload.append(
                {
                    "scene_number": item.get("scene_number"),
                    "title": item.get("scene_title"),
                    "duration": item.get("target_duration", item.get("scene_duration")),
                    "pace_tag": (item.get("voice_guidance", {}) or {}).get("pace_tag"),
                    "target_char_count": (item.get("voice_guidance", {}) or {}).get("target_char_count"),
                    "char_count": len(narration_text),
                }
            )

        voice_plan = self.iteration_context.get("voice_plan", {}) or {}
        voice_overview = {
            "persona": voice_plan.get("persona"),
            "tone_keywords": voice_plan.get("tone_keywords"),
            "style_notes": voice_plan.get("style_notes"),
        }
        concept_plan = self.iteration_context.get("concept_plan", {}) or {}
        concept_overview = {
            "overview": concept_plan.get("overview"),
            "key_messages": concept_plan.get("key_messages"),
        }

        variables = {
            "pending_scenes_json": json.dumps(summary_payload, ensure_ascii=False),
            "iteration_budget": self.max_iterations,
            "default_batch_size": self._batch_size,
            "voice_plan_meta": json.dumps(voice_overview, ensure_ascii=False),
            "concept_meta": json.dumps(concept_overview, ensure_ascii=False),
        }

        try:
            sys_prompt = self.prompt_manager.render_template(
                self.agent_name,
                "planning_round0",
                variables,
                auto_reload=False,
            )
        except Exception as exc:
            self.logger.warning(f"plan_only 模板渲染失败，回退空规划：{exc}")
            return []

        user_hint = "请严格输出 JSON（不可带代码围栏）。"
        return [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_hint},
        ]

    async def _on_plan_only_completed(
        self,
        plan_round: Dict[str, Any],
        input_data: Dict[str, Any],
        current_state: Dict[str, Any],
    ) -> None:
        contract = plan_round.get("contract") if isinstance(plan_round, dict) else None
        context_updates = (contract or {}).get("context_updates", {}) if isinstance(contract, dict) else {}
        planned_batches = context_updates.get("planned_batches") if isinstance(context_updates, dict) else None

        pending = self.iteration_context.get("pending_scenes", []) or []
        index_map = {}
        for item in pending:
            if isinstance(item, dict) and item.get("scene_number") is not None:
                index_map[int(item["scene_number"])]=item

        resolved_batches: List[List[Dict[str, Any]]] = []
        if isinstance(planned_batches, list) and planned_batches:
            for batch in planned_batches:
                batch_contexts: List[Dict[str, Any]] = []
                if isinstance(batch, list):
                    for sn in batch:
                        try:
                            scene_number = int(sn)
                        except (TypeError, ValueError):
                            continue
                        ctx = index_map.get(scene_number)
                        if ctx:
                            batch_contexts.append(dict(ctx))
                if batch_contexts:
                    resolved_batches.append(batch_contexts)

        if not resolved_batches:
            resolved_batches = self._compute_fallback_batches(pending)
            self.logger.info("VOICE_PLAN_FALLBACK: 使用默认批次规划")
        else:
            self.logger.info(
                "VOICE_PLAN_INIT: planned_batches=%s",
                [
                    [item.get("scene_number") for item in batch]
                    for batch in resolved_batches
                ],
            )

        self.iteration_context["planned_batches"] = resolved_batches
        working_state = self.iteration_context.setdefault("working_state", {})
        working_state["planned_batches"] = [
            [item.get("scene_number") for item in batch if isinstance(item, dict)]
            for batch in resolved_batches
        ]

    def _compute_fallback_batches(self, pending: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        batch_size = self._derive_fallback_batch_size(len(pending))
        chunks: List[List[Dict[str, Any]]] = []
        for idx in range(0, len(pending), batch_size):
            segment = pending[idx : idx + batch_size]
            if segment:
                chunks.append([dict(item) for item in segment if isinstance(item, dict)])
        return chunks

    def _derive_fallback_batch_size(self, total_pending: int) -> int:
        if total_pending <= 0:
            return 1
        base_batch = max(1, self._batch_size)
        capacity_batch = max(1, math.ceil(total_pending / max(1, self.max_iterations)))
        return max(base_batch, capacity_batch)

    async def _store_voice_asset(
        self,
        workflow_state,
        scene_number: int,
        synth_payload: Dict[str, Any],
        voice_settings: Dict[str, Any],
        execution: AgentExecution,
    ) -> str:
        audio_path = synth_payload.get("audio_path")
        if not audio_path or not os.path.exists(audio_path):
            raise AgentError(f"Voice synthesis produced no file for scene {scene_number}")

        scene = workflow_state.get_scene(scene_number)
        target_duration = float(getattr(scene, "duration", 0.0) or 0.0)
        audio_format = synth_payload.get("audio_format") or voice_settings.get("audio_format", "wav")
        raw_duration = float(synth_payload.get("duration", 0.0) or 0.0)
        final_duration = raw_duration
        duration_adjusted = False
        if target_duration > 0 and raw_duration > 0:
            tolerance = 0.05
            if raw_duration - target_duration > tolerance:
                try:
                    ensure = await self.use_tool(
                        "audio_processor",
                        "ensure_duration",
                        {
                            "input_path": audio_path,
                            "target_duration": target_duration,
                            "tolerance": 0.1,
                            "allow_shrink": True,
                            "allow_pad": False,
                            "sample_rate": voice_settings.get("sample_rate", 16000),
                            "audio_format": audio_format,
                            "fade_out": 0.5,
                        },
                    )
                    ensure_payload = getattr(ensure, "result", ensure) or {}
                    adjusted_path = ensure_payload.get("output_path") or audio_path
                    final_duration = float(ensure_payload.get("final_duration", target_duration))
                    duration_adjusted = bool(ensure_payload.get("adjusted"))
                    if adjusted_path != audio_path and os.path.exists(adjusted_path):
                        audio_path = adjusted_path
                except Exception as exc:
                    self.logger.warning(
                        f"ensure_duration failed for scene {scene_number}, using raw audio: {exc}"
                    )
        synth_payload["audio_path"] = audio_path
        raw_speech_duration = raw_duration
        synth_payload.setdefault("metadata", {})
        synth_payload["metadata"].setdefault("spoken_duration_sec", raw_speech_duration)
        synth_payload["metadata"]["final_duration_sec"] = final_duration
        synth_payload["metadata"]["duration_adjusted"] = duration_adjusted
        synth_payload["duration"] = final_duration

        audio_format = synth_payload.get("audio_format") or voice_settings.get("audio_format", "wav")
        audio_url = ""
        try:
            upload = await self.use_tool(
                "file_storage_tool",
                "upload_file",
                {
                    "file_path": audio_path,
                    "destination_key": f"audio/voiceovers/scene_{scene_number}_{execution.id}.{audio_format}",
                    "content_type": f"audio/{audio_format}",
                    "public": False,
                    "metadata": {
                        "scene_number": scene_number,
                        "agent": self.agent_name,
                        "provider": synth_payload.get("provider"),
                    },
                },
            )
            upload_payload = getattr(upload, "result", upload) or {}
            audio_url = upload_payload.get("url", "")
        except Exception as exc:
            self.logger.warning(f"Voice upload failed (soft) for scene {scene_number}: {exc}")

        workflow_state.register_voice_asset(
            scene_number=scene_number,
            local_path=audio_path,
            duration=final_duration,
            provider=synth_payload.get("provider", ""),
            voice_id=synth_payload.get("voice_id", voice_settings.get("voice_id", "")),
            metadata=synth_payload.get("metadata", {}),
            audio_url=audio_url,
        )
        return audio_url

    def _finalize_batch_progress(
        self,
        completed_scene_numbers: set,
        batch_map: Dict[int, Dict[str, Any]],
    ) -> None:
        if not completed_scene_numbers:
            return
        pending = [
            item
            for item in self.iteration_context.get("pending_scenes", [])
            if item.get("scene_number") not in completed_scene_numbers
        ]
        self.iteration_context["pending_scenes"] = pending
        completed_log = self.iteration_context.setdefault("completed_scenes", [])
        for number in completed_scene_numbers:
            data = batch_map.get(number)
            if data:
                completed_log.append(data)
        working_state = self.iteration_context.setdefault("working_state", {})
        working_state["pending_scene_numbers"] = [item.get("scene_number") for item in pending]
        completed_numbers = working_state.setdefault("completed_scene_numbers", [])
        for number in completed_scene_numbers:
            if number not in completed_numbers:
                completed_numbers.append(number)

    async def _reflect_on_results(
        self,
        action_result: Dict[str, Any],
        current_state: Dict[str, Any],
        task: Task,
        iteration: int,
    ) -> Dict[str, Any]:
        pending_remaining = len(self.iteration_context.get("pending_scenes", []))
        success = bool(action_result.get("success")) or pending_remaining == 0
        should_stop = pending_remaining == 0 or iteration + 1 >= self.max_iterations
        summary = "Voice synthesis completed" if pending_remaining == 0 else "Voice synthesis ongoing"
        return {
            "task_complete": pending_remaining == 0,
            "should_stop": should_stop,
            "context_updates": {},
            "reflection_summary": summary,
            "react_metadata": {
                "pending_remaining": pending_remaining,
                "success": success,
            },
        }

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

    async def _select_voice_for_scene(
        self,
        scene_context: Dict[str, Any],
        voice_plan: Dict[str, Any],
        voice_settings: Dict[str, Any],
    ) -> Tuple[str, Dict[str, Any]]:
        scene_number = scene_context.get("scene_number")
        selection_cache = self.iteration_context.setdefault("scene_voice_selection", {})
        if scene_number in selection_cache:
            return selection_cache[scene_number]

        shortlist, preferences, fallback_id, debug_info = self._build_voice_candidates(
            scene_context,
            voice_plan,
            voice_settings,
        )

        decision_source = "fallback"
        llm_reason = ""
        selected_voice_id = fallback_id

        if shortlist:
            shortlisted_ids = {item["id"] for item in shortlist if item.get("id")}
            fallback_from_shortlist = shortlist[0]["id"] if shortlist else fallback_id
            try:
                selected_voice_id, llm_reason = await self._choose_voice_via_llm(
                    scene_context,
                    voice_plan,
                    shortlist,
                    preferences,
                    fallback_from_shortlist,
                )
                if selected_voice_id not in shortlisted_ids:
                    selected_voice_id = fallback_from_shortlist
                    llm_reason = "LLM returned invalid voice, fallback to shortlist[0]"
                    decision_source = "fallback"
                else:
                    decision_source = "llm"
            except Exception as exc:
                self.logger.warning(
                    "Voice selection LLM call failed for scene %s: %s", scene_number, exc
                )
                selected_voice_id = fallback_from_shortlist
                llm_reason = "LLM unavailable, fallback to shortlist[0]"
                decision_source = "fallback"
        else:
            llm_reason = "No shortlist available; using fallback voice"

        debug_info.update(
            {
                "decision_source": decision_source,
                "decision_reason": llm_reason,
                "selected_id": selected_voice_id,
            }
        )

        selection_cache[scene_number] = (selected_voice_id, debug_info)
        return selection_cache[scene_number]

    def _build_voice_candidates(
        self,
        scene_context: Dict[str, Any],
        voice_plan: Dict[str, Any],
        voice_settings: Dict[str, Any],
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any], str, Dict[str, Any]]:
        profiles = self._get_voice_profiles()
        fallback_id = voice_settings.get("voice_id") or getattr(settings, "VOICE_DEFAULT_VOICE_ID", "siqi")
        if not profiles:
            debug_info = {
                "preferred_filters": {},
                "shortlist": [],
                "reason": "voice_manifest_empty",
            }
            return [], {}, fallback_id, debug_info

        preferences = self._infer_voice_preferences(scene_context, voice_plan, voice_settings)
        candidates = self._filter_voice_candidates(profiles, preferences)
        if not candidates:
            candidates = profiles

        ranked = self._rank_voice_candidates(candidates, preferences)
        shortlist = [
            {
                "id": profile.get("id"),
                "label": profile.get("label", ""),
                "language": profile.get("language"),
                "tier": profile.get("tier"),
                "score": round(float(score), 3),
                "traits": sorted(profile.get("traits", set())),
            }
            for score, profile in ranked[:5]
            if profile.get("id")
        ]

        if not shortlist and profiles:
            top_profile = profiles[0]
            shortlist = [
                {
                    "id": top_profile.get("id"),
                    "label": top_profile.get("label", ""),
                    "language": top_profile.get("language"),
                    "tier": top_profile.get("tier"),
                    "score": 0.0,
                    "traits": sorted(top_profile.get("traits", set())),
                }
            ]

        debug_info = {
            "preferred_filters": {
                "language": preferences.get("language"),
                "gender": preferences.get("gender"),
                "age": preferences.get("age"),
                "categories": sorted(preferences.get("categories", [])),
                "supports_emotion": preferences.get("supports_emotion"),
                "preferred_ids": preferences.get("preferred_ids"),
            },
            "shortlist": shortlist,
        }

        return shortlist, preferences, fallback_id, debug_info

    async def _choose_voice_via_llm(
        self,
        scene_context: Dict[str, Any],
        voice_plan: Dict[str, Any],
        shortlist: List[Dict[str, Any]],
        preferences: Dict[str, Any],
        fallback_id: str,
    ) -> Tuple[str, str]:
        if not shortlist:
            return fallback_id, "shortlist empty"

        llm = None
        try:
            llm = self.get_llm("plan")
        except Exception:
            try:
                llm = self.get_llm("default")
            except Exception:
                llm = None
        if not llm:
            return fallback_id, "LLM unavailable"

        scene_number = scene_context.get("scene_number")
        tone_keywords = voice_plan.get("tone_keywords", []) if isinstance(voice_plan, dict) else []
        persona = voice_plan.get("persona") if isinstance(voice_plan, dict) else ""
        guidance = scene_context.get("voice_guidance", {}) or {}

        prompt_payload = {
            "scene_number": scene_number,
            "scene_title": scene_context.get("scene_title") or scene_context.get("title"),
            "narration_text": scene_context.get("narration_text"),
            "tone_keywords": tone_keywords,
            "persona": persona,
            "scene_emotion": guidance.get("emotion") or scene_context.get("mood"),
            "objective": guidance.get("objective"),
            "voice_preferences": preferences,
            "voice_candidates": shortlist,
        }

        system_prompt = (
            "你是配音导演，请从候选音色中挑选最适合该场景的一种。"
            "只能从提供的 `voice_candidates` 列表中选择，并给出简短理由。"
            "输出 JSON，对象格式为 {\"voice_id\": string, \"reason\": string, \"confidence\": number }。"
            "如果多种音色都合适，任选最贴合情绪和人物的那个。"
        )

        user_prompt = (
            "请基于以下场景信息挑选音色，只能使用 voice_candidates 中的 id：\n"
            f"{json.dumps(prompt_payload, ensure_ascii=False, indent=2, default=self._json_default)}"
        )

        try:
            response = await llm.chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                max_tokens=400,
                response_format={"type": "json_object"},
            )
            content = response.get("content") if isinstance(response, dict) else None
            if not content:
                return fallback_id, "LLM returned empty content"

            parsed = json.loads(content)
            voice_id = str(parsed.get("voice_id") or "").strip()
            reason = str(parsed.get("reason") or "")
            if voice_id:
                return voice_id, reason
            return fallback_id, "LLM response missing voice_id"
        except Exception as exc:
            self.logger.debug(
                "Voice selection LLM exception for scene %s: %s", scene_number, exc
            )
            return fallback_id, f"LLM exception: {exc}"[:200]

    def _get_voice_profiles(self) -> List[Dict[str, Any]]:
        cached = self.iteration_context.get("voice_profiles")
        if cached is not None:
            return cached

        manifest_entries = voice_service.voice_manifest or []
        profiles: List[Dict[str, Any]] = []
        for order, entry in enumerate(manifest_entries):
            categories = set(entry.get("categories") or [])
            label = entry.get("label", "")
            language = (entry.get("language") or "zh-CN").lower()
            tier = entry.get("tier", "standard")
            supports_emotion = bool(entry.get("supports_emotion"))

            gender = None
            label_lower = label.lower()
            if any(token in label for token in ["女", "妹", "她"]) or "female" in label_lower:
                gender = "female"
            elif any(token in label for token in ["男", "哥", "他"]) or "male" in label_lower:
                gender = "male"

            age = "adult"
            if "child" in categories or any(token in label for token in ["童", "孩", "儿童", "小朋友"]):
                age = "child"

            traits = set(categories)
            warm_tokens = ["温柔", "温暖", "柔", "治愈"]
            energetic_tokens = ["激昂", "热血", "激情", "promo", "广告"]
            if any(token in label for token in warm_tokens):
                traits.add("warm")
            if any(token in label for token in energetic_tokens):
                traits.add("energetic")
            if "直播" in label:
                traits.add("live")
            if "对话" in label_lower or "dialogue" in categories:
                traits.add("dialogue")
            if age == "child":
                traits.add("child")

            profiles.append(
                {
                    "id": entry.get("id"),
                    "label": label,
                    "language": language,
                    "categories": categories,
                    "traits": traits,
                    "tier": tier,
                    "supports_emotion": supports_emotion,
                    "gender": gender,
                    "age": age,
                    "order": order,
                }
            )

        self.iteration_context["voice_profiles"] = profiles
        return profiles

    def _infer_voice_preferences(
        self,
        scene_context: Dict[str, Any],
        voice_plan: Dict[str, Any],
        voice_settings: Dict[str, Any],
    ) -> Dict[str, Any]:
        language = (voice_settings.get("language") or "zh-CN").lower()
        preferences: Dict[str, Any] = {
            "language": language,
            "gender": None,
            "age": None,
            "categories": {"narration"},
            "supports_emotion": False,
            "preferred_ids": [],
        }

        preferred_ids: List[str] = []
        for source in [voice_settings.get("preferred_voice_ids"), voice_plan.get("preferred_voice_ids") if isinstance(voice_plan, dict) else None]:
            if not source:
                continue
            if isinstance(source, str):
                tokens = [seg.strip() for seg in source.replace(";", ",").split(",") if seg.strip()]
            elif isinstance(source, list):
                tokens = [str(seg).strip() for seg in source if str(seg).strip()]
            else:
                tokens = []
            for token in tokens:
                if token not in preferred_ids:
                    preferred_ids.append(token)
        preferences["preferred_ids"] = preferred_ids

        persona = ""
        tone_keywords: List[str] = []
        style_notes = ""
        if isinstance(voice_plan, dict):
            persona = str(voice_plan.get("persona") or "")
            tone_keywords = [str(tok) for tok in voice_plan.get("tone_keywords", []) or []]
            style_notes = str(voice_plan.get("style_notes") or "")

        voice_guidance = scene_context.get("voice_guidance") or {}
        guidance_emotion = str(voice_guidance.get("emotion") or "")
        guidance_objective = str(voice_guidance.get("objective") or "")
        guidance_points = " ".join(str(point) for point in (voice_guidance.get("key_points") or []))

        combined_segments = [
            persona,
            " ".join(tone_keywords),
            style_notes,
            str(scene_context.get("mood") or ""),
            guidance_emotion,
            guidance_objective,
            guidance_points,
        ]
        combined_text = " ".join(seg for seg in combined_segments if seg)
        combined_text_lower = combined_text.lower()

        if language in {"", "zh-cn", None}:
            if any(token in combined_text for token in ["英文", "英语", "English"]):
                preferences["language"] = "en-us"
            elif any(token in combined_text for token in ["英式", "英国"]):
                preferences["language"] = "en-gb"
            elif "粤语" in combined_text:
                preferences["language"] = "zh-yue"
            elif any(token in combined_text for token in ["四川话", "川话"]):
                preferences["language"] = "zh-sichuan"

        female_hints = ["女", "女性", "她", "柔", "温柔", "女声"]
        male_hints = ["男", "男性", "他", "低沉", "磁性", "阳刚", "男声"]
        child_hints = ["童", "儿童", "孩", "小朋友", "稚嫩", "少儿"]

        if any(token in combined_text for token in child_hints):
            preferences["age"] = "child"
            preferences["categories"].add("child")

        if any(token in combined_text for token in female_hints):
            preferences["gender"] = "female"
        elif any(token in combined_text for token in male_hints):
            preferences["gender"] = "male"

        emotional_hints = ["激昂", "热血", "澎湃", "激情", "情感", "动情", "深情", "戏剧"]
        warm_hints = ["温柔", "治愈", "轻柔", "舒缓", "平静", "内敛"]
        promo_hints = ["宣传", "广告", "促销", "解说", "官方", "气势"]
        live_hints = ["直播", "互动", "主持"]
        dialogue_hints = ["对白", "对话"]

        if any(token in combined_text for token in emotional_hints):
            preferences["categories"].add("emotional")
            preferences["supports_emotion"] = True
        if any(token in combined_text for token in warm_hints):
            preferences["categories"].add("warm")
        if any(token in combined_text for token in promo_hints):
            preferences["categories"].add("promo")
        if any(token in combined_text for token in live_hints):
            preferences["categories"].add("live")
        if any(token in combined_text for token in dialogue_hints):
            preferences["categories"].add("dialogue")

        return preferences

    def _filter_voice_candidates(
        self,
        profiles: List[Dict[str, Any]],
        preferences: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        candidates = profiles
        language = preferences.get("language")
        if language:
            filtered = [p for p in candidates if p.get("language") == language]
            if filtered:
                candidates = filtered

        preferred_ids = preferences.get("preferred_ids") or []
        if preferred_ids:
            filtered = [p for p in candidates if p.get("id") in preferred_ids]
            if filtered:
                candidates = filtered

        if preferences.get("age") == "child":
            filtered = [p for p in candidates if p.get("age") == "child"]
            if filtered:
                candidates = filtered

        gender = preferences.get("gender")
        if gender:
            filtered = [p for p in candidates if p.get("gender") == gender]
            if filtered:
                candidates = filtered

        for category in sorted(preferences.get("categories") or []):
            filtered = [
                p
                for p in candidates
                if category in p.get("categories", set()) or category in p.get("traits", set())
            ]
            if filtered:
                candidates = filtered

        if preferences.get("supports_emotion"):
            filtered = [p for p in candidates if p.get("supports_emotion")]
            if filtered:
                candidates = filtered

        return candidates

    def _rank_voice_candidates(
        self,
        candidates: List[Dict[str, Any]],
        preferences: Dict[str, Any],
    ) -> List[Tuple[float, Dict[str, Any]]]:
        ranked: List[Tuple[float, Dict[str, Any]]] = []
        categories_pref = preferences.get("categories") or set()
        preferred_ids = preferences.get("preferred_ids") or []

        for profile in candidates:
            score = 0.0
            if profile.get("id") in preferred_ids:
                score += 5.0
            if preferences.get("gender") and profile.get("gender") == preferences.get("gender"):
                score += 2.5
            if preferences.get("age") == "child" and profile.get("age") == "child":
                score += 2.0
            overlap = (profile.get("categories", set()) | profile.get("traits", set())) & categories_pref
            score += len(overlap) * 1.5
            if preferences.get("supports_emotion") and profile.get("supports_emotion"):
                score += 1.0
            tier = profile.get("tier")
            if tier == "standard":
                score += 0.3
            elif tier == "premium":
                score += 0.2
            ranked.append((score, profile))

        ranked.sort(key=lambda item: (-item[0], item[1].get("order", 0)))
        return ranked

    @staticmethod
    def _coerce_bool(value: Any, default: bool) -> bool:
        if value is None:
            return bool(default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() not in {"false", "0", "no", "off", ""}
        try:
            return bool(value)
        except Exception:
            return bool(default)

    @staticmethod
    def _json_default(value: Any):
        if isinstance(value, set):
            return sorted(value)
        raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")
