"""
Concept Planner Agent - multi-stage concept planning with structured sub tasks.
"""

import json
import asyncio
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from .base import BaseAgent, AgentError
from ..core.config import settings
from ..models import Task, AgentExecution, AgentType, Scene, SceneType
from ..core.prompt_manager import get_prompt_manager
from ..core.story_plan import normalize_character_elements
from .utils import SceneDurationCalculator,safe_json_loads
from .services.mas_shared_memory import get_shared_wm
from .memory.short_term.working_memory import SceneSnapshot


class ConceptPlannerAgent(BaseAgent):
    """Concept Planner agent that orchestrates skeleton, style, audio, and scene sub-tasks."""

    SCENE_BATCH_SIZE = 2

    def __init__(self, llms=None, memory_services=None):
        super().__init__(
            agent_type=AgentType.CONCEPT_PLANNER,
            agent_name="concept_planner",
            timeout_seconds=getattr(settings, "CONCEPT_PLANNER_TIMEOUT_SECONDS", 200),
            max_retries=2,
            llms=llms,
            memory_services=memory_services,
        )

    async def _execute_impl(
        self,
        task: Task,
        input_data: Dict[str, Any],
        execution: AgentExecution,
        db: Session,
    ) -> Dict[str, Any]:
        self._validate_input(input_data, ["user_prompt", "duration", "workflow_state_id"])

        concept_mode = str(input_data.get("concept_mode", "episode") or "episode").lower()
        user_prompt = input_data["user_prompt"]
        style_preference = input_data.get("style_preference")
        style_taxonomy_summary = input_data.get("style_taxonomy_summary")
        predefined_style_profile = input_data.get("predefined_style_profile")

        from ..core.video_config_manager import get_video_config

        video_config = get_video_config()
        duration_capability = video_config.get_system_duration_capability()
        default_duration = (
            duration_capability["min_duration"] + duration_capability["max_duration"]
        ) // 2
        duration = input_data.get("duration", default_duration)

        validation = video_config.validate_duration_request(duration)
        if not validation["is_valid"]:
            self.logger.warning(
                "🎭 Requested duration %ss not supported by %s, using %ss",
                duration,
                validation["provider"],
                validation["suggestion"],
            )
            duration = validation["suggestion"]

        aspect_ratio = input_data.get("aspect_ratio", "16:9")
        workflow_state_id = input_data["workflow_state_id"]

        # 移除 WorkflowState 依赖：从 Shared WM facts 读取已有风格（如有）
        if not predefined_style_profile:
            try:
                existing_plan = self.fetch_memory_slot(
                    workflow_state_id,
                    "project.concept_plan",
                    default={}
                ) or {}
            except Exception:
                existing_plan = {}
            if isinstance(existing_plan, dict):
                predefined_style_profile = existing_plan.get("intelligent_style_design") or None

        project_character_bible = input_data.get("character_bible") or {}
        if not project_character_bible:
            project_ctx = input_data.get("project_context") or {}
            project_character_bible = project_ctx.get("character_bible") or {}

        provider_config = video_config.get_current_provider_config()
        raw_capabilities = provider_config.duration_capabilities or getattr(
            settings, "AVAILABLE_SCENE_DURATIONS", [5, 10]
        )
        duration_capabilities = sorted({int(cap) for cap in raw_capabilities if cap}) or [5, 10]
        scene_count_min = getattr(settings, "SCENE_COUNT_RANGE_MIN", 3)
        scene_count_max = getattr(settings, "SCENE_COUNT_RANGE_MAX", 10)
        optimal_scene_count = video_config.calculate_optimal_scene_count(duration)
        optimal_scene_count = max(scene_count_min, min(optimal_scene_count, scene_count_max))

        system_prompt = self._build_system_prompt()

        from ..core.ai_config import get_ai_config

        ai_config_manager = get_ai_config()
        concept_model = ai_config_manager.get_model_for_agent("concept_planner")
        model_config = ai_config_manager.get_model_config(concept_model)
        fallback_model = (
            ai_config_manager.get_fallback_model_for_agent("concept_planner")
            or (
                model_config.fallback_model
                if model_config and getattr(model_config, "fallback_model", None)
                else None
            )
            or ai_config_manager.agent_model_mapping.get("default")
        )
        fallback_model_config = (
            ai_config_manager.get_model_config(fallback_model) if fallback_model else None
        )

        try:
            total_timeout = int(getattr(settings, "CONCEPT_PLANNER_TIMEOUT_SECONDS", 180))
        except Exception:
            total_timeout = 180

        stage_timeouts, stage_token_limits = self._compute_stage_budgets(
            total_timeout, model_config
        )
        skeleton_timeout = stage_timeouts["skeleton"]
        style_timeout = stage_timeouts["style"]
        voice_timeout = stage_timeouts["voice"]
        scene_timeout = stage_timeouts["scene"]

        try:
            fallback_request_timeout = int(getattr(settings, "LLM_FALLBACK_TIMEOUT_MAX", 60))
        except Exception:
            fallback_request_timeout = 60

        skeleton_max_tokens = stage_token_limits["skeleton"]
        style_max_tokens = stage_token_limits["style"]
        voice_max_tokens = stage_token_limits["voice"]
        scene_max_tokens = stage_token_limits["scene"]

        base_temperature = getattr(model_config, "temperature", 0.7) if model_config else 0.7
        skeleton_temperature = min(0.65, base_temperature)
        style_temperature = min(0.7, base_temperature)
        voice_temperature = min(0.7, base_temperature)
        scene_temperature = base_temperature

        await self._update_progress(execution, 20, "Drafting concept skeleton", db)

        skeleton_payload, skeleton_usage = await self._generate_skeleton(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            duration=duration,
            aspect_ratio=aspect_ratio,
            duration_capabilities=duration_capabilities,
            scene_count_min=scene_count_min,
            scene_count_max=scene_count_max,
            optimal_scene_count=optimal_scene_count,
            model_name=concept_model,
            model_config=model_config,
            fallback_model=fallback_model,
            fallback_model_config=fallback_model_config,
            request_timeout=skeleton_timeout,
            fallback_request_timeout=fallback_request_timeout,
            max_tokens=skeleton_max_tokens,
            temperature=skeleton_temperature,
        )
        self._update_token_usage(execution, skeleton_usage)

        skeleton_json = self._compact_json(skeleton_payload)
        user_prompt_brief = self._build_prompt_snippet(user_prompt)

        await self._update_progress(execution, 40, "Designing style and voice plan", db)

        style_task = asyncio.create_task(
            self._generate_style_bundle(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                skeleton_json=skeleton_json,
                style_preference=style_preference,
                model_name=concept_model,
                model_config=model_config,
                fallback_model=fallback_model,
                fallback_model_config=fallback_model_config,
                request_timeout=style_timeout,
                fallback_request_timeout=fallback_request_timeout,
                max_tokens=style_max_tokens,
                temperature=style_temperature,
                concept_mode=concept_mode,
                style_profile_override=predefined_style_profile,
                taxonomy_summary=style_taxonomy_summary,
                character_bible=project_character_bible,
            )
        )
        voice_task = asyncio.create_task(
            self._generate_voice_plan(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                skeleton_json=skeleton_json,
                model_name=concept_model,
                model_config=model_config,
                fallback_model=fallback_model,
                fallback_model_config=fallback_model_config,
                request_timeout=voice_timeout,
                fallback_request_timeout=fallback_request_timeout,
                max_tokens=voice_max_tokens,
                temperature=voice_temperature,
            )
        )

        style_bundle, voice_bundle = await asyncio.gather(style_task, voice_task)
        self._update_token_usage(execution, style_bundle["usage"])
        self._update_token_usage(execution, voice_bundle["usage"])

        intelligent_style_design = style_bundle["payload"].get("intelligent_style_design", {})
        if predefined_style_profile:
            intelligent_style_design = self._merge_style_profiles(
                predefined_style_profile,
                intelligent_style_design,
            )
        content_elements_raw = style_bundle["payload"].get("content_elements", {}) or {}
        if not isinstance(content_elements_raw, dict):
            content_elements_raw = {}
        characters_raw = content_elements_raw.get("characters")
        sanitized_characters, _ = normalize_character_elements(characters_raw)
        if sanitized_characters or characters_raw is not None:
            content_elements_raw = dict(content_elements_raw)
            content_elements_raw["characters"] = sanitized_characters
        content_elements = content_elements_raw
        consistency_hints = style_bundle["payload"].get("consistency_hints", {})

        if intelligent_style_design:
            try:
                self.logger.info(
                    "🎨 风格规划完成：intelligent_style_design=%s",
                    intelligent_style_design,
                )
            except Exception:
                pass
        else:
            try:
                self.logger.warning("⚠️ 风格规划输出为空，需排查 style 生成链路")
            except Exception:
                pass

        # 共享记忆作为事实源，WorkflowState 写回移除

        voice_plan_raw = voice_bundle["payload"].get("voice_plan", {})
        voice_plan = self._normalize_voice_plan(voice_plan_raw)
        voice_plan = self._apply_voice_plan_pacing(
            voice_plan,
            skeleton_payload,
        )
        # 共享记忆作为事实源，WorkflowState 写回移除

        await self._update_progress(execution, 65, "Detailing scenes", db)

        if concept_mode == "project":
            scenes = []
            scene_notes: Dict[str, List[str]] = {}
            total_planned_duration = float(duration)
            scene_results_usage = 0
        else:
            scene_results = await self._generate_scene_details(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                skeleton_payload=skeleton_payload,
                style_payload=style_bundle["payload"],
                voice_plan=voice_plan,
                duration_capabilities=duration_capabilities,
                duration=duration,
                model_name=concept_model,
                model_config=model_config,
                fallback_model=fallback_model,
                fallback_model_config=fallback_model_config,
                request_timeout=scene_timeout,
                fallback_request_timeout=fallback_request_timeout,
                max_tokens=scene_max_tokens,
                temperature=scene_temperature,
            )

            scene_results_usage = scene_results["usage"]
            scenes = scene_results["scenes"]
            scene_notes = scene_results["notes"]
            total_planned_duration = scene_results["total_duration"]

        self._update_token_usage(execution, scene_results_usage)

        await self._update_progress(execution, 85, "Finalizing concept plan", db)

        concept_plan = self._finalize_concept_plan(
            skeleton_payload,
            intelligent_style_design,
            content_elements,
            consistency_hints,
            voice_plan,
            scenes,
            scene_notes,
            duration,
            total_planned_duration,
        )

        # 共享记忆作为事实源，WorkflowState 写回移除

        # --- Write to Shared Working Memory (facts + scenes) ---
        try:
            from .utils.memory_helpers import write_shared_fact
            write_shared_fact(workflow_state_id, "project.concept_plan", concept_plan)
        except Exception as _wm_err:
            self.logger.warning(f"WM write failed for concept_plan: {_wm_err}")
        try:
            from .utils.memory_helpers import write_shared_fact
            write_shared_fact(workflow_state_id, "project.voice_plan", voice_plan)
        except Exception:
            pass
        # 保留 slot 写入兼容路径（待彻底迁移后可删除）
        try:
            self.store_memory_slot(workflow_state_id, "project.concept_plan", concept_plan)
        except Exception as _slot_err:
            self.logger.warning(f"Slot write failed for concept_plan: {_slot_err}")
        try:
            self.store_memory_slot(workflow_state_id, "project.voice_plan", voice_plan)
        except Exception as _slot_err:
            self.logger.warning(f"Slot write failed for voice_plan: {_slot_err}")

        try:
            shared = get_shared_wm()
            try:
                self.logger.info(
                    "SHARED_FACT_WRITE concept_plan keys=%s",
                    list((intelligent_style_design or {}).keys()),
                )
            except Exception:
                pass
            shared.set_facts(
                workflow_state_id,
                {
                    "intelligent_style_design": intelligent_style_design,
                    "content_elements": content_elements,
                },
            )

            # Project concept scenes into shared scene snapshots
            for s in concept_plan.get("scenes", []) or []:
                try:
                    sn = int(s.get("scene_number") or 0)
                except Exception:
                    sn = 0
                if sn <= 0:
                    continue
                try:
                    dur = float(s.get("final_duration", s.get("duration", 0.0)) or 0.0)
                except Exception:
                    dur = 0.0
                snap = SceneSnapshot(
                    scene_number=sn,
                    depends_on_scene=None,
                    duration=dur,
                    visual_description=s.get("visual_description", ""),
                    narrative_description=s.get("narrative_description", ""),
                    image_url=s.get("image_url", ""),
                    motion_beats=s.get("motion_beats", []) if isinstance(s.get("motion_beats"), list) else [],
                )
                shared.upsert_scene(workflow_state_id, snap)
        except Exception as _wm_err:
            # Fail-fast is reserved for agent core flow; memory write is best-effort
            self.logger.warning(f"Shared WM write failed (non-fatal): {_wm_err}")

        if concept_mode == "project":
            scenes_data: List[Dict[str, Any]] = []
        else:
            # 直接使用 concept_plan.scenes（已写入 Shared WM 场景快照）
            try:
                scenes_data = list(concept_plan.get("scenes", []) or []) if isinstance(concept_plan, dict) else []
            except Exception:
                scenes_data = []

        try:
            memory_stored = await self.store_creative_guidance(
                workflow_id=workflow_state_id,
                concept_plan=concept_plan,
            )
            self.logger.info(
                "🧠 ConceptPlanner: creative guidance stored in MAS memory (success=%s)",
                memory_stored,
            )
        except Exception as exc:
            self.logger.warning(f"⚠️ ConceptPlanner: failed to store creative guidance - {exc}")

        await self._update_progress(execution, 100, "Concept planning completed", db)

        if concept_mode != "project":
            try:
                await self.websocket_manager.broadcast_to_task(
                    str(task.task_id),
                    {
                        "type": "concept_plan_ready",
                        "task_id": str(task.task_id),
                        "scenes_count": len(scenes_data),
                        "estimated_duration": duration,
                    },
                )
            except Exception as ws_err:
                self.logger.warning(f"Failed to broadcast concept_plan_ready: {ws_err}")

        return {
            "concept_plan": concept_plan,
            "voice_plan": voice_plan,
            "total_scenes": len(scenes_data),
            "estimated_duration": duration,
            "video_concept": concept_plan.get("overview", ""),
            "visual_style": self._extract_intelligent_style_summary(concept_plan),
            "target_audience": concept_plan.get("target_audience", "general"),
            "key_messages": concept_plan.get("key_messages", []),
            "workflow_state_id": workflow_state_id,
        }

    def _build_system_prompt(self) -> str:
        try:
            pm = get_prompt_manager()
            mas_sys = pm.render_template(
                "mas_system", "system", variables={}, use_cache=True, auto_reload=False
            )
            agent_sys = pm.render_template(
                "concept_planner", "system", variables={}, use_cache=True, auto_reload=False
            )
            # 根因定位：记录模板来源文件，避免串味/误加载
            try:
                mas_cfg = pm.get_config("mas_system")
                ag_cfg = pm.get_config("concept_planner")
                mas_src = getattr(mas_cfg, "source_path", None) if mas_cfg else None
                ag_src = getattr(ag_cfg, "source_path", None) if ag_cfg else None
                self.logger.info(f"SYSTEM_SRC concept_planner mas={mas_src} agent={ag_src}")
            except Exception:
                pass
            parts: List[str] = []
            if mas_sys and isinstance(mas_sys, str) and mas_sys.strip():
                parts.append(mas_sys.strip())
            if agent_sys and isinstance(agent_sys, str) and agent_sys.strip():
                if agent_sys.strip() not in parts:
                    parts.append(agent_sys.strip())
            return "\n\n".join(parts).strip()
        except Exception as exc:
            self.logger.debug("Failed to build system prompt: %s", exc)
            return ""

    def _compose_messages(self, system_prompt: str, user_prompt: str) -> List[Dict[str, str]]:
        messages: List[Dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})
        return messages

    async def _generate_skeleton(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        duration: int,
        aspect_ratio: str,
        duration_capabilities: List[int],
        scene_count_min: int,
        scene_count_max: int,
        optimal_scene_count: int,
        model_name: str,
        model_config: Any,
        fallback_model: Optional[str],
        fallback_model_config: Any,
        request_timeout: int,
        fallback_request_timeout: int,
        max_tokens: int,
        temperature: float,
    ) -> Tuple[Dict[str, Any], int]:
        prompt = self.render_prompt(
            "skeleton_generation",
            user_prompt=user_prompt,
            duration=duration,
            aspect_ratio=aspect_ratio,
            duration_capabilities=duration_capabilities,
            scene_count_min=scene_count_min,
            scene_count_max=scene_count_max,
            optimal_scene_count=optimal_scene_count,
        )
        messages = self._compose_messages(system_prompt, prompt)
        response = await self._invoke_concept_model(
            messages=messages,
            model_name=model_name,
            model_config=model_config,
            fallback_model=fallback_model,
            fallback_model_config=fallback_model_config,
            request_timeout=request_timeout,
            fallback_request_timeout=fallback_request_timeout,
            max_tokens=max_tokens,
            temperature=temperature,
            response_format={"type": "json_object"},
            context_description="skeleton_generation",
        )
        payload = safe_json_loads(
            response.get("content", ""),
            logger=self.logger,
            context="skeleton_generation",
            allow_fallback=False,
        )
        if not isinstance(payload, dict):
            raise AgentError("Skeleton generation returned invalid payload")
        if "scene_blueprint" not in payload or not isinstance(payload["scene_blueprint"], list):
            raise AgentError("Skeleton generation missing scene_blueprint array")
        usage = response.get("usage", {}).get("total_tokens", 0)
        return payload, usage

    async def _generate_style_bundle(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        skeleton_json: str,
        style_preference: Optional[str],
        model_name: str,
        model_config: Any,
        fallback_model: Optional[str],
        fallback_model_config: Any,
        request_timeout: int,
        fallback_request_timeout: int,
        max_tokens: int,
        temperature: float,
        concept_mode: str,
        style_profile_override: Optional[Dict[str, Any]],
        taxonomy_summary: Optional[str],
        character_bible: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        user_prompt_brief = self._build_prompt_snippet(user_prompt)
        override_json = (
            json.dumps(style_profile_override, ensure_ascii=False, indent=2)
            if style_profile_override
            else ""
        )
        character_bible_json = (
            json.dumps(character_bible, ensure_ascii=False, indent=2)
            if character_bible
            else ""
        )
        prompt = self.render_prompt(
            "style_elements_generation",
            user_prompt=user_prompt,
            skeleton_json=skeleton_json,
            style_preference=style_preference,
            user_prompt_brief=user_prompt_brief,
            concept_mode=concept_mode,
            predefined_style_profile=override_json,
            style_taxonomy_summary=taxonomy_summary or "",
            project_character_bible=character_bible_json,
        )
        messages = self._compose_messages(system_prompt, prompt)
        response = await self._invoke_concept_model(
            messages=messages,
            model_name=model_name,
            model_config=model_config,
            fallback_model=fallback_model,
            fallback_model_config=fallback_model_config,
            request_timeout=request_timeout,
            fallback_request_timeout=fallback_request_timeout,
            max_tokens=max_tokens,
            temperature=temperature,
            response_format={"type": "json_object"},
            context_description="style_elements_generation",
        )
        try:
            payload = safe_json_loads(
                response.get("content", ""),
                logger=self.logger,
                context="style_elements_generation",
                allow_fallback=False,
            )
        except Exception as _pe:
            # 打印原始返回内容的更完整快照，便于定位非JSON根因
            try:
                raw = response.get("content", "")
                clen = len(raw or "")
                try:
                    max_len = int(getattr(settings, 'CONTENT_PREVIEW_CHARS', 1000))
                except Exception:
                    max_len = 1000
                preview = (raw or "")[:max_len].replace("\n", " ")
                meta = {
                    "finish_reason": response.get("finish_reason"),
                    "model": response.get("model"),
                    "provider": response.get("provider"),
                    "usage": response.get("usage"),
                    "len": clen,
                }
                self.logger.warning(
                    "Style elements raw response snapshot: meta=%s preview=%r",
                    meta,
                    preview,
                )
            except Exception:
                pass
            raise
        if not isinstance(payload, dict) or "intelligent_style_design" not in payload:
            # 定位是什么问题
            if not isinstance(payload, dict):
                self.logger.info("Style generation payload is not a dict: %s", payload)
            elif "intelligent_style_design" not in payload:
                self.logger.info("Style generation missing intelligent_style_design: %s", payload)
            raise AgentError("Style generation returned invalid payload")
        # 调试：直接打印 consistency_hints（不改变行为）
        try:
            ch = payload.get("consistency_hints", {})
            import json as _json
            ch_text = _json.dumps(ch, ensure_ascii=False)
            # 控制长度，避免刷屏
            if len(ch_text) > 1500:
                ch_text = ch_text[:1500] + "...<trunc>"
            self.logger.info(f"CONSISTENCY_HINTS: {ch_text}")
        except Exception:
            pass
        return {"payload": payload, "usage": response.get("usage", {}).get("total_tokens", 0)}

    async def _generate_voice_plan(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        skeleton_json: str,
        model_name: str,
        model_config: Any,
        fallback_model: Optional[str],
        fallback_model_config: Any,
        request_timeout: int,
        fallback_request_timeout: int,
        max_tokens: int,
        temperature: float,
    ) -> Dict[str, Any]:
        user_prompt_brief = self._build_prompt_snippet(user_prompt)
        prompt = self.render_prompt(
            "voice_plan_generation",
            user_prompt=user_prompt,
            skeleton_json=skeleton_json,
            user_prompt_brief=user_prompt_brief,
        )
        messages = self._compose_messages(system_prompt, prompt)
        response = await self._invoke_concept_model(
            messages=messages,
            model_name=model_name,
            model_config=model_config,
            fallback_model=fallback_model,
            fallback_model_config=fallback_model_config,
            request_timeout=request_timeout,
            fallback_request_timeout=fallback_request_timeout,
            max_tokens=max_tokens,
            temperature=temperature,
            response_format={"type": "json_object"},
            context_description="voice_plan_generation",
        )
        payload = safe_json_loads(
            response.get("content", ""),
            logger=self.logger,
            context="voice_plan_generation",
            allow_fallback=False,
        )
        if not isinstance(payload, dict) or "voice_plan" not in payload:
            raise AgentError("Voice plan generation returned invalid payload")
        return {"payload": payload, "usage": response.get("usage", {}).get("total_tokens", 0)}

    async def _generate_scene_details(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        skeleton_payload: Dict[str, Any],
        style_payload: Dict[str, Any],
        voice_plan: Dict[str, Any],
        duration_capabilities: List[int],
        duration: int,
        model_name: str,
        model_config: Any,
        fallback_model: Optional[str],
        fallback_model_config: Any,
        request_timeout: int,
        fallback_request_timeout: int,
        max_tokens: int,
        temperature: float,
    ) -> Dict[str, Any]:
        scene_slots = skeleton_payload.get("scene_blueprint", [])
        if not isinstance(scene_slots, list) or not scene_slots:
            raise AgentError("Scene blueprint is empty; cannot generate details")

        batches = self._make_scene_batches(scene_slots, self.SCENE_BATCH_SIZE)
        skeleton_json = self._compact_json(skeleton_payload)
        style_json = self._compact_json(style_payload)
        voice_json = self._compact_json({"voice_plan": voice_plan})
        user_prompt_brief = self._build_prompt_snippet(user_prompt)

        combined_scenes: List[Dict[str, Any]] = []
        notes_consistency: List[str] = []
        notes_duration: List[str] = []
        total_usage = 0

        for batch_index, batch in enumerate(batches):
            scene_batch_json = self._compact_json(batch)
            prompt = self.render_prompt(
                "scene_detail_batch_generation",
                user_prompt=user_prompt,
                skeleton_json=skeleton_json,
                style_guidance_json=style_json,
                voice_plan_json=voice_json,
                scene_batch_json=scene_batch_json,
                duration_capabilities=duration_capabilities,
                user_prompt_brief=user_prompt_brief,
            )
            messages = self._compose_messages(system_prompt, prompt)
            response = await self._invoke_concept_model(
                messages=messages,
                model_name=model_name,
                model_config=model_config,
                fallback_model=fallback_model,
                fallback_model_config=fallback_model_config,
                request_timeout=request_timeout,
                fallback_request_timeout=fallback_request_timeout,
                max_tokens=max_tokens,
                temperature=temperature,
                response_format={"type": "json_object"},
                context_description=f"scene_detail_batch_generation_batch_{batch_index+1}",
            )
            payload = safe_json_loads(
                response.get("content", ""),
                logger=self.logger,
                context=f"scene_detail_batch_generation_batch_{batch_index+1}",
                allow_fallback=False,
            )
            if not isinstance(payload, dict) or "scenes" not in payload:
                raise AgentError("Scene detail generation returned invalid payload")
            batch_scenes = payload.get("scenes", [])
            if not isinstance(batch_scenes, list):
                raise AgentError("Scene detail generation produced invalid scenes list")
            combined_scenes.extend(batch_scenes)
            notes = payload.get("notes", {}) or {}
            if isinstance(notes.get("consistency"), str) and notes["consistency"].strip():
                notes_consistency.append(notes["consistency"].strip())
            if isinstance(notes.get("duration_adjustment"), str) and notes["duration_adjustment"].strip():
                notes_duration.append(notes["duration_adjustment"].strip())
            total_usage += response.get("usage", {}).get("total_tokens", 0)

        combined_scenes.sort(key=lambda s: s.get("scene_number", 0))
        optimized_scenes = SceneDurationCalculator.optimize_scene_durations(
            combined_scenes,
            duration,
        )
        total_duration = sum(
            scene.get("final_duration", scene.get("duration", 0))
            for scene in optimized_scenes
        )

        return {
            "scenes": optimized_scenes,
            "notes": {
                "consistency": notes_consistency,
                "duration": notes_duration,
            },
            "usage": total_usage,
            "total_duration": total_duration,
        }

    def _compute_stage_budgets(self, total_timeout: int, model_config: Any) -> Tuple[Dict[str, int], Dict[str, int]]:
        """Compute per-stage timeout and token budgets, mirroring diagnostic flow."""

        try:
            timeout_ratio = float(getattr(settings, "LLM_PRIMARY_TIMEOUT_RATIO", 0.5))
        except Exception:
            timeout_ratio = 0.5
        if timeout_ratio <= 0:
            timeout_ratio = 0.5

        base_timeout = max(5, int(total_timeout * timeout_ratio))
        stage_timeouts = {
            "skeleton": max(40, int(base_timeout * 0.5)),
            "style": max(20, int(base_timeout * 0.3)),
            "voice": max(15, int(base_timeout * 0.25)),
            "scene": max(30, int(base_timeout * 0.35)),
        }

        try:
            standard_limit = int(getattr(settings, "LLM_MAX_TOKENS_STANDARD", 12800) or 12800)
        except Exception:
            standard_limit = 12800

        stage_tokens = {
            "skeleton": standard_limit,
            "style": standard_limit,
            "voice": standard_limit,
            "scene": standard_limit,
        }

        # 除非显式配置，否则把场景阶段再限制到全局场景上限
        from ..core.config import settings as _settings
        global_scene_max = getattr(_settings, "LLM_MAX_TOKENS_SCENE_DETAIL", None)
        if global_scene_max:
            try:
                scene_cap = int(global_scene_max)
                stage_tokens["scene"] = min(stage_tokens["scene"], scene_cap)
            except Exception:
                pass

        model_token_limit: Optional[int] = None
        if model_config is not None:
            candidate = getattr(model_config, "max_tokens", None)
            try:
                if candidate:
                    model_token_limit = int(candidate)
            except Exception:
                model_token_limit = None

        if model_token_limit and model_token_limit > 0:
            for key, value in stage_tokens.items():
                stage_tokens[key] = min(value, model_token_limit)

        return stage_timeouts, stage_tokens

    def _make_scene_batches(self, scene_slots: List[Dict[str, Any]], batch_size: int) -> List[List[Dict[str, Any]]]:
        batches: List[List[Dict[str, Any]]] = []
        for i in range(0, len(scene_slots), batch_size):
            batches.append(scene_slots[i : i + batch_size])
        return batches

    def _build_prompt_snippet(self, text: str, limit: int = 600) -> str:
        if not text:
            return ""
        cleaned = " ".join(text.strip().split())
        if len(cleaned) <= limit:
            return cleaned
        return cleaned[:limit].rstrip() + "…"

    def _compact_json(self, payload: Dict[str, Any]) -> str:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    def _merge_style_profiles(
        self,
        primary: Optional[Dict[str, Any]],
        fallback: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Merge style profiles, preserving primary values when provided."""

        if not primary and not fallback:
            return {}

        merged: Dict[str, Any] = dict(primary or {})

        for key, value in (fallback or {}).items():
            if key not in merged or not merged[key]:
                merged[key] = value
            elif isinstance(merged[key], dict) and isinstance(value, dict):
                nested = dict(merged[key])
                for sub_key, sub_value in value.items():
                    if sub_key not in nested or not nested[sub_key]:
                        nested[sub_key] = sub_value
                merged[key] = nested

        return merged

    def _finalize_concept_plan(
        self,
        skeleton: Dict[str, Any],
        intelligent_style_design: Dict[str, Any],
        content_elements: Dict[str, Any],
        consistency_hints: Dict[str, Any],
        voice_plan: Dict[str, Any],
        scenes: List[Dict[str, Any]],
        scene_notes: Dict[str, List[str]],
        target_duration: int,
        total_planned_duration: float,
    ) -> Dict[str, Any]:
        concept_plan = {
            "overview": skeleton.get("overview", ""),
            "genre_and_theme": skeleton.get("genre_and_theme", {}),
            "target_audience": skeleton.get("target_audience", ""),
            "key_messages": skeleton.get("key_messages", []),
            "intelligent_style_design": intelligent_style_design,
            "content_elements": content_elements,
            "voice_plan": voice_plan,
            "scenes": scenes,
            "consistency_guidelines": self._build_consistency_guidelines(
                consistency_hints,
                scene_notes,
            ),
            "success": True,
            "total_planned_duration": total_planned_duration,
            "duration_gap": round(target_duration - total_planned_duration, 2),
        }
        return concept_plan

    def _build_consistency_guidelines(
        self,
        consistency_hints: Dict[str, Any],
        scene_notes: Dict[str, List[str]],
    ) -> Dict[str, str]:
        visual_hint = consistency_hints.get("visual") if isinstance(consistency_hints, dict) else ""
        narrative_hint = consistency_hints.get("narrative") if isinstance(consistency_hints, dict) else ""
        # 根因定位日志：记录 consistency_hints.color_palette 的结构，用于后续契约化修复
        cp = []
        if isinstance(consistency_hints, dict):
            cp = consistency_hints.get("color_palette", [])
        try:
            head = (cp[:5] if isinstance(cp, (list, tuple)) else cp)
            head_types = (
                [type(x).__name__ for x in head] if isinstance(head, (list, tuple)) else [type(head).__name__]
            )
            self.logger.info(
                f"STYLE_DIAG consistency_hints_type={type(consistency_hints).__name__} "
                f"color_palette_type={type(cp).__name__} head_types={head_types} head={head}"
            )
        except Exception:
            pass
        # 保持原有行为：直接 join，若结构不合规让错误暴露出来（便于定位根因）
        if isinstance(consistency_hints, dict):
            try:
                color_hint = ", ".join(cp)
            except Exception as e:
                try:
                    self.logger.error(
                        f"STYLE_JOIN_ERROR color_palette not flat-str-list: type={type(cp).__name__} err={e}"
                    )
                except Exception:
                    pass
                raise
        else:
            color_hint = ""

        scene_consistency = "; ".join(scene_notes.get("consistency", [])) if scene_notes else ""

        return {
            "character_consistency": visual_hint or "确保角色外形与特征在所有场景保持一致。",
            "environment_consistency": narrative_hint or "场景氛围和叙事节奏需延续骨架设定。",
            "object_consistency": "重复出现的关键道具需保持造型与用途一致。",
            "style_consistency": (color_hint or "坚持既定的风格组合和色彩基调。")
            + (f" {scene_consistency}" if scene_consistency else ""),
        }

    def _normalize_voice_plan(self, voice_plan_raw: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(voice_plan_raw, dict):
            voice_plan_raw = {}
        enabled_raw = voice_plan_raw.get("enabled")
        if isinstance(enabled_raw, str):
            enabled = enabled_raw.strip().lower() not in {"false", "0", "no", "off"}
        elif isinstance(enabled_raw, bool):
            enabled = enabled_raw
        else:
            enabled = True
        mode = str(voice_plan_raw.get("mode", "narration")).strip().lower()
        if mode not in {"narration", "storytelling", "explainer", "none"}:
            mode = "none" if not enabled else "narration"
        if not enabled:
            mode = "none"
        tone_raw = voice_plan_raw.get("tone_keywords", [])
        if isinstance(tone_raw, str):
            tone_keywords = [tok.strip() for tok in tone_raw.replace("、", ",").split(",") if tok.strip()]
        elif isinstance(tone_raw, list):
            tone_keywords = [str(tok).strip() for tok in tone_raw if str(tok).strip()]
        else:
            tone_keywords = []
        scene_guidance = voice_plan_raw.get("scene_guidance", [])
        if not isinstance(scene_guidance, list):
            scene_guidance = []
        normalized_guidance = []
        for entry in scene_guidance:
            if not isinstance(entry, dict):
                continue
            try:
                scene_number = int(entry.get("scene_number"))
            except (TypeError, ValueError):
                continue
            should = entry.get("should_narrate", True)
            if isinstance(should, str):
                should = should.strip().lower() not in {"false", "0", "no"}
            normalized_guidance.append(
                {
                    "scene_number": scene_number,
                    "should_narrate": bool(should),
                    "objective": entry.get("objective", ""),
                    "emotion": entry.get("emotion", ""),
                    "key_points": entry.get("key_points", []) if isinstance(entry.get("key_points"), list) else [],
                    "pace_tag": str(entry.get("pace_tag", "")).strip(),
                    "target_char_count": entry.get("target_char_count"),
                }
            )
        normalized_guidance.sort(key=lambda g: g.get("scene_number", 0))
        audio_strategy = voice_plan_raw.get("audio_strategy", {}) if isinstance(voice_plan_raw.get("audio_strategy"), dict) else {}
        return {
            "enabled": bool(enabled),
            "mode": mode,
            "persona": voice_plan_raw.get("persona", ""),
            "tone_keywords": tone_keywords,
            "style_notes": voice_plan_raw.get("style_notes", ""),
            "scene_guidance": normalized_guidance,
            "audio_strategy": audio_strategy,
        }

    def _apply_voice_plan_pacing(
        self,
        voice_plan: Dict[str, Any],
        skeleton_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not isinstance(voice_plan, dict):
            raise AgentError("Voice plan normalization produced invalid structure")

        scene_guidance = voice_plan.get("scene_guidance") or []
        if not isinstance(scene_guidance, list) or not scene_guidance:
            return voice_plan

        char_rates = getattr(settings, "VOICE_PACE_CHAR_RATES", {}) or {}
        allowed_paces = set(char_rates.keys())
        if not allowed_paces:
            raise AgentError("VOICE_PACE_CHAR_RATES configuration is empty")

        blueprint = skeleton_payload.get("scene_blueprint", []) if isinstance(skeleton_payload, dict) else []
        duration_map: Dict[int, float] = {}
        for entry in blueprint:
            if not isinstance(entry, dict):
                continue
            try:
                scene_number = int(entry.get("scene_number"))
            except (TypeError, ValueError):
                continue
            duration_hint = entry.get("duration_hint")
            if duration_hint is None:
                duration_hint = entry.get("duration")
            try:
                duration_value = float(duration_hint)
            except (TypeError, ValueError):
                duration_value = 0.0
            duration_map[scene_number] = max(duration_value, 0.0)

        max_chars = getattr(settings, "VOICE_MAX_CHARS_PER_REQUEST", 300)

        for guidance in scene_guidance:
            scene_number = guidance.get("scene_number")
            if scene_number is None:
                raise AgentError("Voice plan scene guidance missing scene_number")
            pace_raw = str(guidance.get("pace_tag", "")).strip().lower()
            if pace_raw not in allowed_paces:
                raise AgentError(
                    f"Voice plan pace_tag 无效: scene {scene_number} -> {pace_raw or '空值'}"
                )
            if scene_number not in duration_map or duration_map[scene_number] <= 0:
                # 增加日志定位是什么问题导致的报错
                if not duration_map:
                    self.logger.error("duration_map is empty")
                elif scene_number not in duration_map:
                    self.logger.error(f"scene_number {scene_number} not in duration_map keys: {list(duration_map.keys())}")
                else:
                    self.logger.error(f"scene_number {scene_number} has non-positive duration: {duration_map[scene_number]}")
                raise AgentError(
                    f"Scene {scene_number} 缺少有效的时长提示，无法计算目标字数"
                )
            char_rate = float(char_rates[pace_raw])
            target_chars = int(round(duration_map[scene_number] * char_rate))
            target_chars = max(20, min(max_chars, target_chars))
            guidance["pace_tag"] = pace_raw
            guidance["target_char_count"] = target_chars

        voice_plan["scene_guidance"] = scene_guidance
        return voice_plan

    async def _invoke_concept_model(
        self,
        *,
        messages: List[Dict[str, Any]],
        model_name: str,
        model_config: Any,
        fallback_model: Optional[str],
        fallback_model_config: Any,
        request_timeout: int,
        fallback_request_timeout: int,
        max_tokens: int,
        temperature: float,
        response_format: Dict[str, Any],
        context_description: str,
    ) -> Dict[str, Any]:
        primary_err: Optional[Exception] = None
        response: Optional[Dict[str, Any]] = None

        try:
            response = await self.llm_function_call(
                messages=messages,
                model=model_name,
                context_description=context_description,
                temperature=temperature,
                max_tokens=max_tokens,
                request_timeout=request_timeout,
                response_format=response_format,
                thinking={"type": "disabled"},
            )
        except Exception as exc:
            primary_err = exc

        need_fallback = False
        if primary_err is not None or not response:
            need_fallback = True
        elif isinstance(response, dict):
            content = response.get("content")
            if not content:
                self.logger.warning(
                    "ConceptPlanner empty content from primary model during %s", context_description
                )
                primary_err = primary_err or Exception("empty content")
                need_fallback = True

        if need_fallback:
            if not fallback_model:
                error = primary_err or Exception("LLM returned empty content")
                raise AgentError(f"ConceptPlanner failed during {context_description}") from error
            self.logger.warning(
                "ConceptPlanner fallback engaged: primary=%s, fallback=%s, reason=%s",
                model_name,
                fallback_model,
                primary_err or (response.get("error") if isinstance(response, dict) else "empty content"),
            )
            llm = self.get_llm("plan")
            fallback_max_tokens = min(
                getattr(settings, "LLM_MAX_TOKENS_STANDARD", 8000),
                getattr(fallback_model_config, "max_tokens", max_tokens) if fallback_model_config else max_tokens,
            )
            fallback_temperature = (
                getattr(fallback_model_config, "temperature", 0.5) if fallback_model_config else 0.5
            )
            response = await llm.chat_completion(
                messages=messages,
                model=fallback_model,
                temperature=fallback_temperature,
                max_tokens=fallback_max_tokens,
                request_timeout=fallback_request_timeout,
                response_format=response_format,
                thinking={"type": "disabled"},
            )
        if not response or not response.get("content"):
            self.logger.error(
                "ConceptPlanner final response missing content during %s", context_description
            )
            raise AgentError(f"ConceptPlanner received invalid response during {context_description}")
        return response


    async def _create_scenes(
        self,
        task: Task,
        concept_plan: Dict[str, Any],
        db: Session,
    ) -> List[Scene]:
        scenes = []
        current_start_time = 0.0
        for scene_data in concept_plan.get("scenes", []):
            scene = Scene(
                task_id=task.id,
                scene_number=scene_data.get("scene_number", len(scenes) + 1),
                scene_type=self._map_scene_type(scene_data.get("scene_type", "main_content")),
                title=scene_data.get("title", f"Scene {len(scenes) + 1}"),
                description=scene_data.get("description", ""),
                narrative_description=scene_data.get("narrative_description", ""),
                visual_description=scene_data.get("visual_description", ""),
                duration=float(scene_data.get("final_duration", scene_data.get("duration", 5))),
                start_time=current_start_time,
                duration_reasoning=scene_data.get("duration_reasoning", ""),
                background_prompt=scene_data.get("visual_description", ""),
                character_descriptions=scene_data.get("content_elements", {}).get("characters_present", []),
                props_and_objects=scene_data.get("content_elements", {}).get("key_objects", []),
                mood_and_atmosphere=scene_data.get("mood_and_atmosphere", "")[:100],
                camera_angle=scene_data.get("camera_angle", "medium shot")[:50],
                lighting_style=scene_data.get("lighting_style", scene_data.get("lighting", "natural"))[:50],
                art_style=concept_plan.get("intelligent_style_design", {}).get("style_name", "")[:100],
                color_palette=concept_plan.get("intelligent_style_design", {}).get("color_palette", []),
            )
            scene.end_time = current_start_time + scene.duration
            current_start_time = scene.end_time
            db.add(scene)
            scenes.append(scene)
        db.commit()
        for scene in scenes:
            db.refresh(scene)
        return scenes

    async def _create_scenes_in_workflow_state(
        self,
        workflow_state,
        concept_plan: Dict[str, Any],
    ) -> List:
        scenes_data = []
        current_start_time = 0.0
        from ..core.workflow_state import SceneData

        for scene_data in concept_plan.get("scenes", []):
            scene = SceneData(
                scene_number=scene_data.get("scene_number", len(scenes_data) + 1),
                scene_type=scene_data.get("scene_type", "main_content"),
                title=scene_data.get("title", f"Scene {len(scenes_data) + 1}"),
                description=scene_data.get("description", ""),
                narrative_description=scene_data.get("narrative_description", ""),
                visual_description=scene_data.get("visual_description", ""),
                duration=float(scene_data.get("final_duration", scene_data.get("duration", 5))),
                start_time=current_start_time,
                duration_reasoning=scene_data.get("duration_reasoning", ""),
                characters_present=scene_data.get("content_elements", {}).get("characters_present", []),
                props_and_objects=scene_data.get("content_elements", {}).get("key_objects", []),
                mood_and_atmosphere=scene_data.get("mood_and_atmosphere", ""),
                camera_angle=scene_data.get("camera_angle", "medium shot"),
                lighting_style=scene_data.get("lighting_style", scene_data.get("lighting", "natural")),
                art_style=concept_plan.get("intelligent_style_design", {}).get("style_name", ""),
                color_palette=concept_plan.get("intelligent_style_design", {}).get("color_palette", []),
            )
            scene.end_time = current_start_time + scene.duration
            current_start_time = scene.end_time
            workflow_state.add_scene(scene)
            scenes_data.append(scene)
        return scenes_data

    def _map_scene_type(self, scene_type_str: str) -> SceneType:
        if not scene_type_str:
            return SceneType.MAIN_CONTENT
        scene_type_lower = scene_type_str.lower().strip()
        english_mapping = {
            "intro": SceneType.INTRO,
            "introduction": SceneType.INTRO,
            "opening": SceneType.INTRO,
            "main_content": SceneType.MAIN_CONTENT,
            "main": SceneType.MAIN_CONTENT,
            "content": SceneType.MAIN_CONTENT,
            "transition": SceneType.TRANSITION,
            "bridge": SceneType.TRANSITION,
            "outro": SceneType.OUTRO,
            "conclusion": SceneType.OUTRO,
            "ending": SceneType.OUTRO,
            "background": SceneType.BACKGROUND,
        }
        if scene_type_lower in english_mapping:
            return english_mapping[scene_type_lower]
        return SceneType.MAIN_CONTENT

    def _scene_to_dict(self, scene: Scene) -> Dict[str, Any]:
        return {
            "id": scene.id,
            "scene_number": scene.scene_number,
            "scene_type": scene.scene_type.value,
            "title": scene.title,
            "description": scene.description,
            "duration": scene.duration,
            "start_time": scene.start_time,
            "end_time": scene.end_time,
            "visual_description": scene.visual_description,
            "narrative_description": scene.narrative_description,
            "mood": scene.mood_and_atmosphere,
            "camera_angle": scene.camera_angle,
            "lighting": scene.lighting_style,
            "art_style": scene.art_style,
            "characters": scene.character_descriptions,
            "props": scene.props_and_objects,
            "color_palette": scene.color_palette,
        }

    def _extract_intelligent_style_summary(self, concept_plan: Dict[str, Any]) -> str:
        style_design = concept_plan.get("intelligent_style_design", {})
        if isinstance(style_design, dict):
            style_name = style_design.get("style_name")
            visual_approach = style_design.get("visual_approach")
            narrative_style = style_design.get("narrative_style")
            if style_name:
                return style_name
            parts = [part for part in [visual_approach, narrative_style] if part]
            if parts:
                return " + ".join(parts)
        return "智能生成风格"
