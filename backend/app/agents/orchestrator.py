"""
Orchestrator Agent - Coordinates the entire video generation workflow
基于 Shared Working Memory（共享黑板）作为唯一对外事实源；取消对 WorkflowState 的依赖。
"""
import asyncio
import os
import logging
import json
import uuid
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session

from .base import BaseAgent, AgentError
from ..models import Task, TaskStatus, AgentType
from .adapters.memory_views import (
    build_media_agent_context,
    build_image_generation_context,
    build_video_generation_context,
    build_voice_synthesis_context,
)
from ..services.memory_provider import build_memory_services, MemoryServices
# legacy WM singleton removed - use injected self._memory_services.short_term
from .utils.memory_helpers import (
    agent_scope,
    mas_scope,
    get_mas_working_memory,
    write_shared_fact,
    read_shared_fact,
)

from ..events.models import EventKind
from ..events.publisher import publish_event
from .concept_planner import ConceptPlannerAgent
from .script_writer import ScriptWriterAgent
from .image_generator import ImageGeneratorAgent
from .video_generator import VideoGeneratorAgent
from .audio_generator import AudioGeneratorAgent
from .voice_synthesizer import VoiceSynthesizerAgent
from .video_composer import VideoComposerAgent
from .quality_checker import QualityCheckerAgent
from .tools.tool_registry import get_tool_registry
from ..core.config import settings
from ..core.video_config_manager import get_video_config


class OrchestratorAgent(BaseAgent):
    """
    Orchestrator Agent manages the complete video generation workflow
    by coordinating all specialized agents in the correct order
    """
    
    def __init__(self, memory_services: Optional[MemoryServices] = None):
        import os
        from .utils.llm_policy import LLMPolicyManager
        policy_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'llm_policies.yaml')
        self._llm_policy = LLMPolicyManager(policy_file)
        self._memory_services = memory_services or build_memory_services()
        self.video_config = get_video_config()
        super().__init__(
            agent_type=AgentType.ORCHESTRATOR,
            agent_name="orchestrator",
            timeout_seconds=getattr(settings, 'ORCHESTRATOR_TIMEOUT_SECONDS', 1800),
            max_retries=1,
            llms=self._llm_policy.build_llms_for_agent('orchestrator'),
            memory_services=self._memory_services,
        )
        
        # Initialize all specialized agents
        self.agents = {
            AgentType.CONCEPT_PLANNER: ConceptPlannerAgent(
                llms=self._llm_policy.build_llms_for_agent('concept_planner'),
                memory_services=self._memory_services,
            ),
            AgentType.SCRIPT_WRITER: ScriptWriterAgent(
                llms=self._llm_policy.build_llms_for_agent('script_writer'),
                memory_services=self._memory_services,
            ),
            AgentType.VOICE_SYNTHESIZER: VoiceSynthesizerAgent(
                llms=self._llm_policy.build_llms_for_agent('voice_synthesizer'),
                memory_services=self._memory_services,
            ),
            AgentType.IMAGE_GENERATOR: ImageGeneratorAgent(
                llms=self._llm_policy.build_llms_for_agent('image_generator'),
                memory_services=self._memory_services,
            ),
            AgentType.VIDEO_GENERATOR: VideoGeneratorAgent(
                llms=self._llm_policy.build_llms_for_agent('video_generator'),
                memory_services=self._memory_services,
            ),
            AgentType.AUDIO_GENERATOR: AudioGeneratorAgent(
                llms=self._llm_policy.build_llms_for_agent('audio_generator'),
                memory_services=self._memory_services,
            ),
            AgentType.VIDEO_COMPOSER: VideoComposerAgent(
                llms=self._llm_policy.build_llms_for_agent('video_composer'),
                memory_services=self._memory_services,
            ),
            AgentType.QUALITY_CHECKER: QualityCheckerAgent(
                llms=self._llm_policy.build_llms_for_agent('quality_checker'),
                memory_services=self._memory_services,
            ),
        }

        # Per-step repeat counters for policy decisions
        self._step_repeat_counts: Dict[AgentType, int] = {}

        # 打印每个Agent的LLM注入摘要，便于排查：role -> provider/model
        try:
            for atype, agent in self.agents.items():
                roles = {}
                llms = getattr(agent, "_llms", {}) or {}
                for role, handle in llms.items():
                    try:
                        provider = getattr(handle._service, 'get_provider_name', lambda: 'unknown')()
                        model = getattr(handle, '_model', None) or 'default'
                        roles[role] = f"{provider}/{model}"
                    except Exception:
                        roles[role] = "unknown"
                self.logger.info(f"LLM injected for {atype.value}: {roles}")
        except Exception:
            pass
        
        # Define workflow execution order
        self.workflow_order = [
            AgentType.CONCEPT_PLANNER,
            AgentType.SCRIPT_WRITER,
            AgentType.IMAGE_GENERATOR,
            AgentType.VIDEO_GENERATOR,
            AgentType.VOICE_SYNTHESIZER,
            AgentType.VIDEO_COMPOSER,  # 视频合成：拼接场景视频 + 后续语音混流
            AgentType.AUDIO_GENERATOR,  # 音频生成：基于完整视频生成匹配音乐
            AgentType.QUALITY_CHECKER
        ]

    def _persist_scene_info_ref(
        self,
        *,
        workflow_id: str,
        agent_type: AgentType,
        payload: Dict[str, Any],
    ) -> Optional[str]:
        """Persist scene info payload as JSON and return a local ref path."""
        if not payload or not workflow_id:
            return None
        try:
            base_dir = Path(settings.TEMP_PATH) / "context"
            base_dir.mkdir(parents=True, exist_ok=True)
            filename = f"{agent_type.value}_{workflow_id}.json"
            ref_path = (base_dir / filename).resolve()
            with open(ref_path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False)
            try:
                backend_root = Path(__file__).resolve().parents[2]
                return str(ref_path.relative_to(backend_root))
            except Exception:
                return str(ref_path)
        except Exception as exc:
            try:
                self.logger.warning("scene_info_ref persist failed: %s", exc)
            except Exception:
                pass
            return None

    def reset_repeat_counters(self) -> None:
        """Clear per-step repeat counters so retries start fresh."""
        self._step_repeat_counts = {}

    def _load_workflow_overview(self, workflow_id: str) -> Dict[str, Any]:
        try:
            value = read_shared_fact(workflow_id, "workflow_overview", {}, service=self.short_term_service)
        except Exception as exc:
            raise AgentError(f"Failed to read workflow_overview from MAS WM: {exc}") from exc
        return dict(value) if isinstance(value, dict) else {}

    def _store_workflow_overview(self, workflow_id: str, payload: Dict[str, Any]) -> None:
        try:
            write_shared_fact(workflow_id, "workflow_overview", payload or {}, service=self.short_term_service)
        except Exception as exc:
            raise AgentError(f"Failed to write workflow_overview to MAS WM: {exc}") from exc

    def _update_workflow_overview(self, workflow_id: str, updates: Dict[str, Any], *, raise_error: bool = True) -> None:
        try:
            current = self._load_workflow_overview(workflow_id)
            current.update(updates)
            self._store_workflow_overview(workflow_id, current)
        except AgentError as exc:
            if raise_error:
                raise
            self.logger.warning("Workflow overview update skipped: %s", exc)

    async def _execute_impl(
        self, 
        task: Task, 
        input_data: Dict[str, Any], 
        db: Session
    ) -> Dict[str, Any]:
        """Execute the complete video generation workflow using Shared Working Memory"""
        
        self._current_task = task
        mem_service = self._memory_services.short_term
        mem_service.create_or_get(str(task.task_id), mas_scope(str(task.task_id)))
        
        # 使用 Task.task_id 作为本次工作流的 Shared WM 标识
        wf_id = str(task.task_id)
        self.logger.info(f"🚀 开始工作流执行，Workflow ID: {wf_id}")

        try:
            write_shared_fact(
                wf_id,
                "workflow_overview",
                {
                    "status": "INITIALIZING",
                    "progress": 0,
                    "current_step": "Starting workflow",
                    "step_index": 0,
                    "total_steps": len(self.workflow_order),
                },
                service=self.short_term_service,
            )
        except Exception as wm_err:
            raise AgentError(f"Failed to initialize workflow_overview in shared memory: {wm_err}") from wm_err
        
        workflow_data = input_data.copy()
        workflow_data.setdefault("resolution", input_data.get("resolution") or settings.DEFAULT_VIDEO_RESOLUTION)
        workflow_data.setdefault("target_resolution", workflow_data.get("resolution"))
        # 将 workflow_state_id 传递给 Agent，Agent 从 Shared WM 读取上下文
        workflow_data["workflow_state_id"] = wf_id
        # Episode/Project 上下文直接留在 workflow_data，由 _prepare_agent_context 注入到各 Agent 输入；
        # Shared WM 作为唯一对外事实源，不再引用本地 WorkflowState 实例。

        workflow_results = {}
        # 任务分解（LLM → per-agent 指令），失败则回退
        task_specs, conditional_task_specs = await self._llm_decompose_tasks(workflow_data, wf_id)
        if not isinstance(conditional_task_specs, dict) or not conditional_task_specs:
            raise AgentError("LLM task decomposition missing conditional_tasks (required)")
        if "video_composer_bgm_mix" not in conditional_task_specs:
            raise AgentError("LLM task decomposition missing conditional task: video_composer_bgm_mix")

        total_steps = len(self.workflow_order)
        
        try:
            for step_index, agent_type in enumerate(self.workflow_order):
                agent = self.agents[agent_type]
                try:
                    shared_view = get_mas_working_memory(wf_id, service=self.short_term_service)
                    scope = agent_scope(wf_id, agent.agent_name)
                    try:
                        mem_service.reset(scope, wf_id)
                    except Exception:
                        pass
                    mem_service.create_or_get(
                        wf_id,
                        scope,
                        owner_agent=agent.agent_name,
                        shared_view=shared_view,
                    )
                except Exception as mem_err:
                    raise AgentError(
                        f"Failed to initialise iteration memory for {agent.agent_name}: {mem_err}"
                    ) from mem_err

                # LLM 指定 run=False 时跳过
                try:
                    spec_run = task_specs.get(agent_type, {}).get("run") if isinstance(task_specs, dict) else None
                    if spec_run is False:
                        self.logger.info(f"⏭️ Skipping {agent.agent_name} (directive run=false)")
                        continue
                except Exception:
                    pass

                if not self._should_run_agent(agent_type, wf_id):
                    self.logger.info(f"⏭️ Skipping {agent.agent_name} due to workflow conditions")
                    continue
                
                # Update progress
                progress_percentage = int((step_index / total_steps) * 90)  # 为持久化预留10%
                current_step = f"Executing {agent.agent_name}"
                
                await self._update_progress(
                    progress_percentage, 
                    current_step,
                    db
                )
                
                # Update task progress + 共享黑板概览
                task.update_progress(current_step, progress_percentage)
                try:
                    self._update_workflow_overview(
                        wf_id,
                        {
                            "status": "RUNNING",
                            "progress": progress_percentage,
                            "current_step": current_step,
                            "step_index": step_index + 1,
                            "total_steps": total_steps,
                            "current_agent": agent.agent_name,
                        },
                        raise_error=True,
                    )
                except AgentError as wm_err:
                    raise AgentError(
                        f"Failed to update workflow_overview in shared memory (step {step_index + 1}): {wm_err}"
                    ) from wm_err
                self.logger.info(f"Starting workflow step {step_index + 1}/{total_steps}: {agent.agent_name}")
                
                try:
                    # Prepare agent input with creative context (if available)
                    self.logger.info(f"🧠 DEBUG: Preparing context for {agent_type.value}")
                    agent_input = await self._prepare_agent_context(workflow_data, agent_type, wf_id)
                    # 注入 task 指令（LLM 分解或回退），与 static_context 并行
                    try:
                        task_spec = task_specs.get(agent_type) if isinstance(task_specs, dict) else None
                    except Exception:
                        task_spec = None
                    if not task_spec:
                        task_spec = self._build_fallback_task(agent_type)
                        task_spec["scope"]["workflow_id"] = wf_id
                        task_spec["fallback_used"] = True
                        self.logger.warning("TASK_FALLBACK agent=%s (no directive from LLM)", agent.agent_name)
                    else:
                        scope = task_spec.get("scope") or {}
                        if isinstance(scope, dict):
                            scope.setdefault("workflow_id", wf_id)
                            task_spec["scope"] = scope
                    agent_input["task"] = task_spec
                    
                    # Debug: Check if context contains creative guidance
                    if agent_type in [AgentType.IMAGE_GENERATOR, AgentType.VIDEO_GENERATOR]:
                        has_creative_guidance = "creative_guidance" in agent_input
                        scene_guidances_count = len(agent_input.get("scene_guidances", {}))
                        self.logger.info(f"🧠 DEBUG: {agent_type.value} context - creative_guidance: {has_creative_guidance}, scene_guidances: {scene_guidances_count}")

                    # Hard gate: quality_checker requires a final video deliverable in MAS SoT.
                    if agent_type == AgentType.QUALITY_CHECKER:
                        try:
                            from .adapters.state.agent_outputs import assess_final_video_ready

                            delivery = assess_final_video_ready(str(wf_id), service=self.short_term_service)
                            if not delivery.get("ready"):
                                raise AgentError("Cannot run quality_checker: project.final_video missing in MAS WM")
                        except AgentError:
                            raise
                        except Exception as err:
                            raise AgentError(f"Cannot run quality_checker: final_video check failed: {err}") from err
                    
                    # Execute the agent (now purely stateless)
                    agent_output = await agent.execute(
                        task=task,
                        input_data=agent_input,
                        db=db,
                        execution_order=step_index + 1
                    )
                    
                    # Store results and prepare input for next agent
                    workflow_results[agent_type.value] = agent_output
                    workflow_data.update(agent_output)

                    if agent_type == AgentType.VIDEO_COMPOSER:
                        self._store_composer_outputs(str(wf_id), agent_output)

                    # Composer re-entry: after composer/audion-agent, optionally add VO/BGM in composer mode
                    try:
                        mixing_mode = getattr(settings, 'AUDIO_MIXING_MODE', 'composer')
                    except Exception:
                        mixing_mode = 'composer'
                    if agent_type == AgentType.AUDIO_GENERATOR and mixing_mode == 'composer':
                        try:
                            prereq = None
                            try:
                                from .adapters.state.agent_outputs import assess_composer_bgm_prereq

                                prereq = assess_composer_bgm_prereq(
                                    str(wf_id),
                                    service=self.short_term_service,
                                )
                            except Exception:
                                prereq = None
                            eligible = bool(prereq.get("eligible")) if isinstance(prereq, dict) else False
                            if not eligible:
                                reason = (prereq or {}).get("reason") if isinstance(prereq, dict) else None
                                if reason == "final_video_missing":
                                    self.logger.warning("Skip composer add_bgm: project.final_video missing")
                                    raise RuntimeError("skip_add_bgm_missing_final_video")
                                if reason == "bgm_missing":
                                    self.logger.warning("Skip composer add_bgm: project.background_music missing")
                                    raise RuntimeError("skip_add_bgm_missing_bgm")
                                raise RuntimeError("skip_add_bgm_missing_bgm")

                            self.logger.info("🎼 Scheduling composer to add background music")
                            if AgentType.VIDEO_COMPOSER.value + "_add_bgm" in workflow_results:
                                # Avoid repeating the same post-step composition within one workflow run.
                                raise RuntimeError("skip_add_bgm_already_done")
                            comp_agent = self.agents.get(AgentType.VIDEO_COMPOSER)
                            comp_input = {
                                "workflow_state_id": wf_id,
                                "add_bgm": True
                            }
                            comp_task = conditional_task_specs.get("video_composer_bgm_mix")
                            if not isinstance(comp_task, dict) or not comp_task:
                                raise AgentError("add_bgm missing preplanned task spec: video_composer_bgm_mix")
                            comp_input["task"] = comp_task
                            try:
                                from .adapters.memory_views import build_video_composer_context

                                comp_input["static_context"] = build_video_composer_context(
                                    wf_id,
                                    service=self.short_term_service,
                                    requests={
                                        "compose_requested": False,
                                        "voiceover_requested": False,
                                        "bgm_requested": True,
                                    },
                                )
                            except Exception:
                                pass
                            static_ctx = comp_input.get("static_context") if isinstance(comp_input, dict) else None
                            if isinstance(static_ctx, dict):
                                requests_ctx = static_ctx.get("requests") or {}
                                bgm_ctx = static_ctx.get("background_music") or {}
                                bgm_path = (
                                    bgm_ctx.get("audio_path")
                                    or bgm_ctx.get("path")
                                    or bgm_ctx.get("file_path")
                                    or ""
                                )
                                bgm_url = bgm_ctx.get("audio_url") or bgm_ctx.get("url") or ""
                                self.logger.info(
                                    "🧠 add_bgm static_context requests=%s bgm_path=%s bgm_url=%s bgm_requested=%s",
                                    requests_ctx,
                                    bgm_path or None,
                                    bgm_url or None,
                                    bool(requests_ctx.get("bgm_requested")),
                                )
                            else:
                                self.logger.warning("add_bgm static_context missing or invalid")
                            scope = agent_scope(wf_id, comp_agent.agent_name)
                            shared_view = get_mas_working_memory(wf_id, service=self.short_term_service)
                            try:
                                mem_service.reset(scope, wf_id)
                            except Exception:
                                pass
                            mem_service.create_or_get(
                                wf_id,
                                scope,
                                owner_agent=comp_agent.agent_name,
                                shared_view=shared_view,
                            )
                            comp_out = await comp_agent.execute(
                                task=task,
                                input_data=comp_input,
                                db=db,
                                execution_order=step_index + 1
                            )
                            self._store_composer_outputs(str(wf_id), comp_out or {})
                            # Ensure final video and mix receipt are available after BGM mixing.
                            try:
                                from .adapters.state.agent_outputs import assess_composer_mix_delivery

                                delivery = assess_composer_mix_delivery(
                                    str(wf_id),
                                    mix_type="bgm",
                                    service=self.short_term_service,
                                )
                                st = str(delivery.get("subtask_state") or "").strip().lower()
                                if st != "complete":
                                    reason = delivery.get("reason") or "mix_incomplete"
                                    raise AgentError(f"Composer add_bgm verification failed: {reason}")
                            except AgentError:
                                raise
                            except Exception as vf_err:
                                raise AgentError(f"Composer add_bgm final_video verification failed: {vf_err}") from vf_err
                            workflow_results[AgentType.VIDEO_COMPOSER.value + "_add_bgm"] = comp_out
                            workflow_data.update(comp_out)
                            base_result = workflow_results.get(AgentType.VIDEO_COMPOSER.value)
                            if isinstance(base_result, dict):
                                merged_result = dict(base_result)
                                merged_result.update(comp_out or {})
                                workflow_results[AgentType.VIDEO_COMPOSER.value] = merged_result
                            else:
                                workflow_results[AgentType.VIDEO_COMPOSER.value] = comp_out
                        except Exception as e:
                            if isinstance(e, RuntimeError) and str(e) == "skip_add_bgm_already_done":
                                pass
                            elif isinstance(e, RuntimeError) and str(e) in ("skip_add_bgm_missing_final_video", "skip_add_bgm_missing_bgm"):
                                pass
                            else:
                                raise AgentError(f"Composer add_bgm failed: {e}") from e

                    # Orchestrator policy-first decision; acceptance is derived from MAS WM (SoT facts).
                    try:
                        from .adapters.state.agent_outputs import assess_agent_delivery

                        delivery = assess_agent_delivery(str(wf_id), agent_type, service=self.short_term_service)
                        st = str(delivery.get("subtask_state") or "partial").strip().lower()
                        try:
                            pending_cnt = int(delivery.get("pending") or 0)
                        except Exception:
                            pending_cnt = 0

                        max_repeat = getattr(settings, "ORCHESTRATOR_MAX_REPEAT_PER_STEP", 1)
                        cnt = self._step_repeat_counts.get(agent_type, 0)

                        # Policy decision: prefer facts-based gating; LLM provides optional advice when ambiguous.
                        if st == "complete":
                            decision = "proceed_next"
                        elif pending_cnt > 0 and cnt < max_repeat:
                            decision = "repeat_agent"
                        elif pending_cnt > 0 and cnt >= max_repeat and agent_type in (
                            AgentType.VIDEO_COMPOSER,
                            AgentType.AUDIO_GENERATOR,
                        ):
                            # Fail fast for critical deliverables to avoid downstream false negatives.
                            decision = "halt_workflow"
                        else:
                            decision = await self._decide_next_step_llm(
                                current_agent=agent_type,
                                workflow_id=wf_id,
                            )

                        if decision == "repeat_agent":
                            self.logger.info(f"🔁 Orchestrator decided to repeat {agent.agent_name}")
                            if cnt < max_repeat:
                                self._step_repeat_counts[agent_type] = cnt + 1
                                try:
                                    scope = agent_scope(wf_id, agent.agent_name)
                                    shared_view = get_mas_working_memory(wf_id, service=self.short_term_service)
                                    try:
                                        mem_service.reset(scope, wf_id)
                                    except Exception:
                                        pass
                                    mem_service.create_or_get(
                                        wf_id,
                                        scope,
                                        owner_agent=agent.agent_name,
                                        shared_view=shared_view,
                                    )
                                except Exception:
                                    pass
                                agent_output = await agent.execute(
                                    task=task,
                                    input_data=agent_input,
                                    db=db,
                                    execution_order=step_index + 1,
                                )
                                workflow_results[agent_type.value] = agent_output
                                workflow_data.update(agent_output)

                                # Post-repeat hard gate: do not proceed with missing MAS SoT deliverables.
                                if agent_type in (AgentType.VIDEO_COMPOSER, AgentType.AUDIO_GENERATOR):
                                    delivery_after = assess_agent_delivery(
                                        str(wf_id), agent_type, service=self.short_term_service
                                    )
                                    st_after = str(delivery_after.get("subtask_state") or "").strip().lower()
                                    if st_after != "complete":
                                        raise AgentError(
                                            f"{agent.agent_name} repeated but still missing required MAS deliverables"
                                        )
                            else:
                                self.logger.warning(
                                    f"⚠️ Repeat limit reached for {agent.agent_name} (max={max_repeat}); proceeding to next step"
                                )
                        elif decision == "halt_workflow":
                            raise AgentError("Workflow halted by orchestrator decision (missing deliverables)")
                        else:
                            self.logger.info(f"➡️ Orchestrator decided to proceed to next step")
                    except Exception as ce:
                        # If decision fails, proceed sequentially (do not crash orchestrator here).
                        self.logger.warning(
                            f"⚠️ Orchestrator decision failed: {ce}. Proceeding sequentially."
                        )
                    
                    # Handoff final results to WF (only when agent reports completion via final_* fields)
                    # 仅写 Shared WM；不再回写 WorkflowState（避免双轨）
                    tracked_kind = None
                    if agent_type == AgentType.IMAGE_GENERATOR:
                        tracked_kind = "image"
                    elif agent_type == AgentType.VIDEO_GENERATOR:
                        tracked_kind = "video"
                    elif agent_type == AgentType.AUDIO_GENERATOR:
                        tracked_kind = "audio"
                    if tracked_kind:
                        shared = get_mas_working_memory(str(wf_id), service=self.short_term_service)
                        bucket = shared.get(f"scene_outputs.{tracked_kind}", {}) if shared is not None else {}
                        committed = len(bucket) if isinstance(bucket, dict) else 0
                        extra: Dict[str, Any] = {}
                        if tracked_kind == "audio":
                            try:
                                bgm = shared.get("project.background_music", {}) if shared is not None else {}
                                extra["project_background_music"] = bool(
                                    isinstance(bgm, dict)
                                    and (str(bgm.get("audio_path") or "").strip() or str(bgm.get("audio_url") or "").strip())
                                )
                            except Exception:
                                extra["project_background_music"] = False
                        self.logger.info(
                            "WM_COMMIT(%s): agent=%s committed=%s extra=%s",
                            tracked_kind,
                            agent.agent_name,
                            committed,
                            extra or None,
                        )

                    # Handle memory storage if this agent produced memory data
                    if agent_type == AgentType.CONCEPT_PLANNER:
                        self.logger.info("🧠 DEBUG: About to store creative guidance from ConceptPlanner")
                        await self._store_creative_guidance_from_output(agent_output)
                        
                        # 🔧 同步概念计划到 Shared WM facts（去除 WorkflowState 依赖）
                        if "concept_plan" in agent_output:
                            try:
                                write_shared_fact(wf_id, "project.concept_plan", agent_output["concept_plan"], service=self.short_term_service)
                            except Exception:
                                pass
                    else:
                        self.logger.info(f"🧠 DEBUG: No memory storage needed for {agent_type.value}")
                    
                    self.logger.info(f"Completed workflow step {step_index + 1}/{total_steps}: {agent.agent_name}")

                    # 通过事件通道通知 coarse-grained UI 信号
                    try:
                        from .adapters.state.memory_state import build_memory_state
                        from .adapters.state.mas_state import build_mas_state_view
                        shared = get_mas_working_memory(str(wf_id), service=self.short_term_service)
                        wm_state = build_memory_state(shared)
                        mas_state = build_mas_state_view(str(wf_id), service=self.short_term_service)
                        if agent_type == AgentType.IMAGE_GENERATOR and self._is_image_step_completed(wf_id):
                            await publish_event(
                                kind=EventKind.STATE,
                                payload={
                                    "state": "image_assets_ready",
                                    "images_count": int(wm_state.get("outputs", {}).get("image", 0)),
                                    "mas_state": mas_state,
                                },
                                task_id=str(task.task_id),
                                task_db_id=self._task_db_id,
                                workflow_state_id=wf_id,
                                agent_type=self.agent_type.value,
                                agent_name=self.agent_name,
                            )
                        if agent_type == AgentType.VIDEO_GENERATOR and self._is_video_step_completed(wf_id):
                            await publish_event(
                                kind=EventKind.STATE,
                                payload={
                                    "state": "video_assets_ready",
                                    "videos_count": int(wm_state.get("outputs", {}).get("video", 0)),
                                    "mas_state": mas_state,
                                },
                                task_id=str(task.task_id),
                                task_db_id=self._task_db_id,
                                workflow_state_id=wf_id,
                                agent_type=self.agent_type.value,
                                agent_name=self.agent_name,
                            )
                    except Exception as _ws_sig_err:
                        self.logger.warning(f"Event coarse signal failed: {str(_ws_sig_err)}")
                    
                except Exception as e:
                    error_msg = f"Workflow failed at step {step_index + 1} ({agent.agent_name}): {str(e)}"
                    self.logger.error(error_msg)
                    
                    # Check if we should retry the failed step
                    if await self._should_retry_step(agent_type, e, db):
                        self.logger.info(f"Retrying step {step_index + 1}: {agent.agent_name}")
                        agent_input = await self._prepare_agent_context(workflow_data, agent_type, wf_id)
                        agent_output = await agent.execute(
                            task=task,
                            input_data=agent_input,
                            db=db,
                            execution_order=step_index + 1
                        )
                        workflow_results[agent_type.value] = agent_output
                        workflow_data.update(agent_output)
                        if agent_type == AgentType.CONCEPT_PLANNER and "concept_plan" in agent_output:
                            try:
                                write_shared_fact(wf_id, "project.concept_plan", agent_output["concept_plan"], service=self.short_term_service)
                                self.logger.info("🎭 重试后 concept_plan 已写入 MAS WM")
                            except Exception:
                                pass
                        continue

                    # 不重试：标记失败并通知
                    await self._send_workflow_failure(task, error_msg)
                    raise AgentError(error_msg) from e
            
            # Workflow completed successfully
            await self._update_progress(90, "Workflow completed, dispatching completion event", db)
            try:
                self._update_workflow_overview(
                    wf_id,
                    {
                        "status": "PERSISTING",  # 保持概要一致，后续事件化由监听器处理
                        "progress": 90,
                        "current_step": "Dispatching completion event",
                    },
                    raise_error=True,
                )
            except AgentError as wm_err:
                raise AgentError(f"Failed to mark workflow_overview as PERSISTING: {wm_err}") from wm_err
            
            # 发布完成事件（监听器异步落库），不再同步持久化
            shared_final = None
            try:
                shared_final = get_mas_working_memory(str(wf_id), service=self.short_term_service)
            except Exception:
                shared_final = None
            fv = shared_final.get("project.final_video", {}) if shared_final is not None else {}
            final_url = ""
            if isinstance(fv, dict):
                final_url = str(fv.get("url") or fv.get("path") or "").strip()
            if not final_url:
                final_url = str(workflow_results.get("video_composer", {}).get("final_video_url") or "").strip()

            # 提取最小持久化 Payload（场景/资源索引），保证 DB 闭环（读取 MAS SoT）
            persistence_data = self._build_persistence_payload(str(wf_id))
            
            try:
                from .adapters.state.mas_state import build_mas_state_view
                mas_state = build_mas_state_view(str(wf_id), service=self.short_term_service)
            except Exception:
                mas_state = {}

            task.status = TaskStatus.COMPLETED
            task.update_progress("Completed", 100)
            try:
                ov = self._load_workflow_overview(wf_id)
                ov.update(
                    {
                        "status": "COMPLETED",
                        "progress": 100,
                        "current_step": "Workflow completed",
                        "outputs": {"final_video_url": final_url},
                    }
                )
                self._store_workflow_overview(wf_id, ov)
            except AgentError as wm_err:
                raise AgentError(f"Failed to update workflow_overview on completion: {wm_err}") from wm_err

            try:
                # 合并 persistence_data 到事件 payload
                event_payload = {
                    "state": "workflow_completed",
                    "status": "COMPLETED",
                    "final_video_url": final_url,
                    "mas_state": mas_state,
                }
                event_payload.update(
                    {
                        "scenes": persistence_data.get("scenes") or [],
                        "resources": persistence_data.get("resources") or [],
                    }
                )
                
                await publish_event(
                    kind=EventKind.STATE,
                    payload=event_payload,
                    task_id=str(task.task_id),
                    task_db_id=self._task_db_id,
                    workflow_state_id=wf_id,
                    agent_type=self.agent_type.value,
                    agent_name=self.agent_name,
                )
            except Exception as evt_err:
                self.logger.warning("Failed to publish workflow_completed event: %s", evt_err)
            
            # Send final WebSocket notification
            await self._send_workflow_completion(task, workflow_results)
            
            self.logger.info(f"🎉 工作流完成，任务ID: {task.task_id}")
            
            return {
                "workflow_status": "completed",
                "total_steps": total_steps,
                "results": workflow_results,
                "final_video_url": final_url,
                "quality_score": workflow_results.get("quality_checker", {}).get("quality_score"),
                "persistence_status": "deferred",
                "workflow_state_id": wf_id
            }
            
        except Exception as e:
            # Workflow failed
            error_msg = f"Workflow failed: {str(e)}"
            
            # 记录错误到共享黑板概览
            try:
                ov = self._load_workflow_overview(wf_id)
                prog = int(ov.get("progress") or 0)
                ov.update({"status": "FAILED", "progress": prog, "last_error": error_msg})
                self._store_workflow_overview(wf_id, ov)
            except AgentError as wm_err:
                raise AgentError(f"Failed to record workflow failure in shared memory: {wm_err}") from wm_err
            
            try:
                await publish_event(
                    kind=EventKind.STATE,
                    payload={
                        "state": "workflow_failed",
                        "status": "FAILED",
                        "error": error_msg,
                    },
                    task_id=str(task.task_id),
                    task_db_id=self._task_db_id,
                    workflow_state_id=wf_id,
                    agent_type=self.agent_type.value,
                    agent_name=self.agent_name,
                )
            except Exception as evt_err:
                self.logger.warning("Failed to publish workflow_failed event: %s", evt_err)
            await self._send_workflow_failure(task, error_msg)
            
            raise AgentError(error_msg) from e
        finally:
            try:
                mem_service.cleanup_workflow(wf_id)
            except Exception as cleanup_err:
                self.logger.warning(
                    "Iteration memory cleanup failed for workflow %s: %s",
                    wf_id,
                    cleanup_err,
                )

    def _build_persistence_payload(self, workflow_id: str) -> Dict[str, Any]:
        """Extract minimal scenes/resources from MAS WM (SoT) for persistence (lightweight only)."""
        scenes: List[Dict[str, Any]] = []
        resources: List[Dict[str, Any]] = []

        wf_id = str(workflow_id or "")
        shared = None
        try:
            shared = get_mas_working_memory(wf_id, service=self.short_term_service)
        except Exception:
            shared = None

        overview = shared.get("scene_overview", {}) if shared is not None else {}
        raw_scenes = overview.get("scenes") if isinstance(overview, dict) else []
        if isinstance(raw_scenes, list):
            for s in raw_scenes:
                if not isinstance(s, dict):
                    continue
                scenes.append(
                    {
                        "scene_number": s.get("scene_number"),
                        "title": s.get("title") or s.get("scene_title"),
                        "description": s.get("description")
                        or s.get("narrative_description")
                        or s.get("visual_description"),
                        "duration": s.get("duration"),
                    }
                )

        def _iter_bucket(key: str) -> List[Dict[str, Any]]:
            if shared is None:
                return []
            try:
                bucket = shared.get(key, {})
            except Exception:
                bucket = {}
            if not isinstance(bucket, dict):
                return []
            out: List[Dict[str, Any]] = []
            for k, v in bucket.items():
                if not isinstance(v, dict):
                    continue
                rec = dict(v)
                sn = rec.get("scene_number")
                if sn is None:
                    try:
                        sn = int(k)
                    except Exception:
                        sn = k
                    rec["scene_number"] = sn
                out.append(rec)
            return out

        # Scene-level resources
        for rec in _iter_bucket("scene_outputs.video"):
            url = rec.get("video_url") or rec.get("url")
            path = rec.get("video_path") or rec.get("path") or rec.get("file_path")
            if url or path:
                sn = rec.get("scene_number")
                resources.append(
                    {
                        "scene_number": sn,
                        "type": "video",
                        "resource_type": "video",
                        "url": url,
                        "path": path,
                        "filename": f"scene_{sn}_video.mp4",
                    }
                )

        for rec in _iter_bucket("scene_outputs.image"):
            url = rec.get("image_url") or rec.get("url")
            path = rec.get("image_path") or rec.get("path") or rec.get("file_path")
            if url or path:
                sn = rec.get("scene_number")
                resources.append(
                    {
                        "scene_number": sn,
                        "type": "image",
                        "resource_type": "image",
                        "url": url,
                        "path": path,
                        "filename": f"scene_{sn}_image.jpg",
                    }
                )

        for rec in _iter_bucket("scene_outputs.voice"):
            url = rec.get("audio_url") or rec.get("url")
            path = rec.get("audio_path") or rec.get("path") or rec.get("file_path")
            if url or path:
                sn = rec.get("scene_number")
                resources.append(
                    {
                        "scene_number": sn,
                        "type": "audio",
                        "resource_type": "audio",
                        "url": url,
                        "path": path,
                        "filename": f"scene_{sn}_audio.mp3",
                    }
                )

        # Project-level deliverables
        final_video = shared.get("project.final_video", {}) if shared is not None else {}
        if isinstance(final_video, dict):
            final_url = final_video.get("url") or ""
            final_path = final_video.get("path") or ""
            if final_url or final_path:
                resources.append(
                    {
                        "scope": "task",
                        "kind": "final_video",
                        "resource_type": "video",
                        "url": final_url,
                        "path": final_path,
                        "filename": "final_video.mp4",
                    }
                )

        bgm = shared.get("project.background_music", {}) if shared is not None else {}
        if isinstance(bgm, dict):
            bgm_url = bgm.get("audio_url") or ""
            bgm_path = bgm.get("audio_path") or ""
            if bgm_url or bgm_path:
                resources.append(
                    {
                        "scope": "task",
                        "kind": "background_music",
                        "resource_type": "audio",
                        "url": bgm_url,
                        "path": bgm_path,
                        "filename": "background_music",
                    }
                )

        return {"scenes": scenes, "resources": resources}

    async def _decide_next_step_llm(self, current_agent: AgentType, workflow_id: str) -> str:
        """Use a lightweight LLM + orchestrator_control tool to decide next step.
        Returns: 'proceed_next' | 'repeat_agent' | 'halt_workflow'
        """
        # Build observation (concise, facts-only) from MAS WM (SoT)
        try:
            from .adapters.state.agent_outputs import assess_agent_delivery
            from .adapters.state.mas_state import build_mas_state_view

            delivery = assess_agent_delivery(str(workflow_id), current_agent, service=self.short_term_service)
            mas_state = build_mas_state_view(str(workflow_id), service=self.short_term_service)
        except Exception:
            delivery = {}
            mas_state = {}

        meta = {"workflow_id": str(workflow_id), "mas_state": mas_state}
        summary = {"delivery": delivery}
        try:
            success_count = int((delivery or {}).get("completed") or 0)
        except Exception:
            success_count = 0
        fail_count = 0

        # 使用模板生成系统指令（保持中立，不暴露工具/参数名）
        # 使用统一提示体系：优先读取 YAML 中 orchestrator 的系统指令；如不可用则回退到简短中立文案
        # Render decision prompts from templates
        pm = self.prompt_manager
        try:
            agent_sys = self.get_system_instructions() or {}
            pr = agent_sys.get("primary_role") or "工作流编排器"
        except Exception:
            pr = "工作流编排器"
        sys_content = pm.render_template(
            "agents/orchestrator",
            "decision_system",
            variables={"primary_role": pr},
            use_cache=True,
            auto_reload=False,
        )
        import json as _json
        user_content = pm.render_template(
            "agents/orchestrator",
            "decision_user",
            variables={
                "agent_name": current_agent.value,
                "meta_json": _json.dumps(meta, ensure_ascii=False),
                "summary_json": _json.dumps(summary, ensure_ascii=False),
                "success_count": success_count,
                "fail_count": fail_count,
            },
            use_cache=True,
            auto_reload=False,
        )
        sys_msg = {"role": "system", "content": sys_content}
        user_msg = {"role": "user", "content": user_content}

        # Use a light model for orchestration
        model_name = getattr(settings, 'ORCHESTRATOR_DECISION_MODEL', 'glm-4.5-air')
        result = await self.llm_function_call(
            messages=[sys_msg, user_msg],
            context_description="Workflow step decision",
            model=model_name,
            temperature=0.2,
            # 统一使用结构化 JSON 回执，降低长尾解析风险
            response_format={"type": "json_object"}
        )

        if result.get("approach") == "function_call_plan" and result.get("tool_calls"):
            exec_res = await self.execute_tool_calls(result["tool_calls"])  # 执行控制动作
            for call in exec_res:
                tool_name = call.get("tool") or ""
                if tool_name == "orchestrator_control_repeat_agent" and call.get("success"):
                    return "repeat_agent"
                if tool_name == "orchestrator_control_halt_workflow" and call.get("success"):
                    return "halt_workflow"
                if tool_name == "orchestrator_control_proceed_next" and call.get("success"):
                    return "proceed_next"
        # 无工具可用：尝试解析严格 JSON 文本决策
        if result.get("approach") == "text_response":
            try:
                content = (result.get("content") or "").strip()
                import json as _json
                data = _json.loads(content) if content else {}
                decision = str(data.get("decision") or "").strip()
                rationale = str(data.get("rationale") or "").strip()
                subtask_state = str(data.get("subtask_state") or "").strip()
                loop_end_reason = str(data.get("loop_end_reason") or "").strip()
                # 记录一次可观测诊断，但不影响决策落地
                try:
                    self.logger.info(
                        f"ORCH_DECISION_JSON: decision={decision} state={subtask_state} reason={loop_end_reason} rationale={rationale[:120]}"
                    )
                except Exception:
                    pass
                if decision in ("repeat_agent", "proceed_next", "halt_workflow"):
                    return decision
            except Exception:
                # 解析失败走默认
                pass
        # Default fallback: proceed
        return "proceed_next"
    
    # WorkflowStatus 已移除；概览在共享黑板 facts.workflow_overview 中维护
    
    async def _should_retry_step(
        self,
        agent_type: AgentType,
        error: Exception,
        db: Session
    ) -> bool:
        """Determine if a failed workflow step should be retried"""
        # 简化：按错误类型和策略决定，不依赖 AgentExecution 表
        retry_conditions = {
            AgentType.IMAGE_GENERATOR: ["timeout", "api_rate_limit", "temporary_service_error"],
            AgentType.VIDEO_GENERATOR: ["timeout", "api_rate_limit", "temporary_service_error"],
            AgentType.VIDEO_COMPOSER: ["processing_error", "temporary_file_error"],
        }

        error_type = type(error).__name__.lower()
        if agent_type in retry_conditions:
            return any(condition in error_type for condition in retry_conditions[agent_type])
        return "timeout" in error_type or "temporary" in error_type

    def _is_image_step_completed(self, workflow_id: str) -> bool:
        """Gate condition for image generation step completion."""
        try:
            shared = get_mas_working_memory(str(workflow_id), service=self.short_term_service)
            outputs = shared.get("scene_outputs.image", {}) if shared is not None else {}
            if isinstance(outputs, dict) and outputs:
                return True
        except Exception:
            pass
        self.logger.warning("Image step not completed: no scene_outputs.image found in MAS WM")
        return False

    def _is_video_step_completed(self, workflow_id: str) -> bool:
        """Gate condition for video generation step completion."""
        try:
            shared = get_mas_working_memory(str(workflow_id), service=self.short_term_service)
            outputs = shared.get("scene_outputs.video", {}) if shared is not None else {}
            if isinstance(outputs, dict) and outputs:
                return True
        except Exception:
            pass
        self.logger.warning("Video step not completed: no scene_outputs.video found in MAS WM")
        return False
    
    async def _send_workflow_completion(self, task: Task, results: Dict[str, Any]):
        """Send workflow completion notification via event bus"""
        try:
            await publish_event(
                kind=EventKind.STATE,
                payload={
                    "state": "workflow_completed",
                    "results": results,
                },
                task_id=str(task.task_id),
                task_db_id=self._task_db_id,
                workflow_state_id=self.workflow_state_id,
                agent_type=self.agent_type.value,
                agent_name=self.agent_name,
            )
        except Exception as e:
            self.logger.warning(f"Failed to publish workflow completion event: {e}")
    
    async def _send_workflow_failure(self, task: Task, error_message: str):
        """Send workflow failure notification via event bus"""
        try:
            await publish_event(
                kind=EventKind.STATE,
                payload={
                    "state": "workflow_failed",
                    "error": error_message,
                },
                task_id=str(task.task_id),
                task_db_id=self._task_db_id,
                workflow_state_id=self.workflow_state_id,
                agent_type=self.agent_type.value,
                agent_name=self.agent_name,
            )
        except Exception as e:
            self.logger.warning(f"Failed to publish workflow failure event: {e}")
    
    def get_workflow_status(self, task: Task, db: Session) -> Dict[str, Any]:
        """Get current workflow status and progress"""
        
        workflow_status = {
            "task_id": str(task.task_id),
            "overall_status": task.status.value,
            "overall_progress": task.progress_percentage,
            "current_step": task.current_step,
            "total_steps": len(self.workflow_order),
            "completed_steps": 0,
            "failed_steps": 0,
            "steps": []
        }

        # 仅返回粗粒度状态；详细执行信息改为事件/缓存，不依赖 AgentExecution 表
        for agent_type in self.workflow_order:
            workflow_status["steps"].append(
                {
                    "agent_type": agent_type.value,
                    "status": "unknown",
                    "progress": None,
                    "duration": None,
                    "error": None,
                }
            )
        
        return workflow_status
    
    async def _store_creative_guidance_from_output(self, agent_output: Dict[str, Any]):
        """从ConceptPlanner输出中存储创意指导到全局记忆"""
        
        try:
            memory_data = agent_output.get("memory_for_storage")
            if not memory_data:
                self.logger.warning("No memory data found in ConceptPlanner output")
                return
            
            success = await self.memory_service.store_creative_guidance(
                workflow_id=memory_data["workflow_id"],
                concept_plan=memory_data["concept_plan"],
                agent_name=memory_data["agent_name"]
            )
            
            if success:
                self.logger.info(f"✅ Orchestrator stored creative guidance for workflow {memory_data['workflow_id']}")
            else:
                self.logger.error(f"❌ Failed to store creative guidance for workflow {memory_data['workflow_id']}")
                
        except Exception as e:
            self.logger.error(f"❌ Orchestrator failed to handle memory storage: {e}")

    def _store_composer_outputs(self, workflow_id: str, agent_output: Dict[str, Any]) -> None:
        wf_id = str(workflow_id or "")
        if not wf_id or not isinstance(agent_output, dict):
            return
        final_path = str(agent_output.get("final_video_path") or "").strip()
        final_url = str(agent_output.get("final_video_url") or "").strip()
        mix_receipt = agent_output.get("mix_receipt")
        if not (final_path or final_url or isinstance(mix_receipt, dict)):
            return
        try:
            if final_path or final_url:
                payload = {
                    "path": final_path,
                    "url": final_url,
                    "storage": {
                        "provider": "local",
                        "url": final_url,
                        "skipped": True,
                    },
                }
                write_shared_fact(wf_id, "project.final_video", payload, service=self.short_term_service)
            if isinstance(mix_receipt, dict) and mix_receipt:
                write_shared_fact(
                    wf_id,
                    "project.final_video_mix",
                    dict(mix_receipt),
                    service=self.short_term_service,
                )
        except Exception as exc:
            self.logger.error("❌ Failed to store composer outputs: %s", exc, exc_info=True)
            raise AgentError("Shared WM write failed (final_video)") from exc

    @staticmethod
    def _normalize_audio_strategy(value: Any) -> str:
        """Normalize orchestration strategy to known values."""
        raw = str(value or "").strip().lower()
        alias_map = {
            "adaptive": "adaptive",
            "auto": "adaptive",
            "prefer_native": "adaptive",
            "provider_only": "provider_only",
            "native_only": "provider_only",
            "mas_only": "mas_only",
            "agent_only": "mas_only",
        }
        return alias_map.get(raw, "adaptive")

    def _resolve_audio_orchestration_strategy(self, workflow_state_id: str) -> str:
        """Resolve orchestration strategy from global configuration."""
        _ = workflow_state_id
        return self._normalize_audio_strategy(getattr(settings, "VIDEO_AUDIO_STRATEGY", "adaptive"))

    def _get_video_audio_capability(self) -> Dict[str, Any]:
        """Read current provider audio capability from video config manager."""
        try:
            provider_cfg = self.video_config.get_current_provider_config()
            return {
                "provider": provider_cfg.provider_name,
                "supports_native_audio": bool(getattr(provider_cfg, "supports_native_audio", False)),
                "native_audio_param_name": str(getattr(provider_cfg, "native_audio_param_name", "generate_audio") or "generate_audio"),
                "native_audio_default_enabled": getattr(provider_cfg, "native_audio_default_enabled", None),
            }
        except Exception:
            return {
                "provider": "",
                "supports_native_audio": False,
                "native_audio_param_name": "generate_audio",
                "native_audio_default_enabled": None,
            }

    def _should_run_audio_generator(self, workflow_state_id: str) -> bool:
        """Runtime-fact driven audio orchestration.

        Decision principle:
        - Only skip AUDIO_GENERATOR when runtime facts confirm all scene videos have audio streams.
        - Any unknown/silent/missing evidence keeps AUDIO_GENERATOR enabled.
        """
        strategy = self._resolve_audio_orchestration_strategy(workflow_state_id)
        audio_facts = self._collect_runtime_video_audio_facts(workflow_state_id)
        all_have_audio = bool(audio_facts.get("all_have_audio"))

        if strategy == "mas_only":
            return True
        if strategy in {"provider_only", "adaptive"}:
            return not all_have_audio
        return True

    def _collect_runtime_video_audio_facts(self, workflow_state_id: str) -> Dict[str, Any]:
        """Collect runtime audio facts from scene_outputs.video.

        Returns conservative facts: any missing path/probe failure is treated as unknown.
        """
        wf_id = str(workflow_state_id or "").strip()
        if not wf_id:
            return {
                "total_scenes": 0,
                "records": 0,
                "checked": 0,
                "with_audio": 0,
                "without_audio": 0,
                "unknown": 0,
                "all_have_audio": False,
                "reason": "workflow_id_missing",
            }

        try:
            wm = get_mas_working_memory(wf_id, service=self.short_term_service)
        except Exception:
            wm = None

        overview = wm.get("scene_overview", {}) if wm is not None else {}
        raw_scenes = overview.get("scenes") if isinstance(overview, dict) else []
        total_scenes = len(raw_scenes) if isinstance(raw_scenes, list) else 0

        video_bucket = wm.get("scene_outputs.video", {}) if wm is not None else {}
        if not isinstance(video_bucket, dict):
            video_bucket = {}

        records = 0
        checked = 0
        with_audio = 0
        without_audio = 0
        unknown = 0

        for rec in video_bucket.values():
            if not isinstance(rec, dict):
                continue
            records += 1
            video_path = (
                rec.get("video_path")
                or rec.get("path")
                or rec.get("file_path")
                or ""
            )
            if not isinstance(video_path, str) or not video_path.strip():
                unknown += 1
                continue
            normalized = video_path.strip()
            if normalized.startswith("file://"):
                normalized = normalized[7:]
            if not os.path.exists(normalized):
                unknown += 1
                continue
            has_audio = self._probe_video_audio_stream(normalized)
            if has_audio is None:
                unknown += 1
                continue
            checked += 1
            if has_audio:
                with_audio += 1
            else:
                without_audio += 1

        expected = total_scenes or records
        all_have_audio = bool(
            expected > 0
            and checked >= expected
            and without_audio == 0
            and unknown == 0
        )
        reason = "all_have_audio" if all_have_audio else "audio_missing_or_unknown"
        if records == 0:
            reason = "video_outputs_missing"

        return {
            "total_scenes": total_scenes,
            "records": records,
            "checked": checked,
            "with_audio": with_audio,
            "without_audio": without_audio,
            "unknown": unknown,
            "all_have_audio": all_have_audio,
            "reason": reason,
        }

    @staticmethod
    def _probe_video_audio_stream(video_path: str) -> Optional[bool]:
        """Probe local video audio stream presence via ffprobe.

        Returns:
        - True/False when probe succeeds
        - None when probe cannot be completed
        """
        try:
            probe = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    "a:0",
                    "-show_entries",
                    "stream=index",
                    "-of",
                    "csv=p=0",
                    video_path,
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if probe.returncode != 0:
                return None
            return bool((probe.stdout or "").strip())
        except Exception:
            return None
    
    def _should_run_agent(self, agent_type: AgentType, workflow_state_id: str) -> bool:
        if agent_type == AgentType.VOICE_SYNTHESIZER:
            voice_plan = read_shared_fact(workflow_state_id, "project.voice_plan", {}, service=self.short_term_service) or {}
            if not voice_plan or not voice_plan.get("enabled"):
                return False
            if str(voice_plan.get("mode", "none")).lower() == "none":
                return False
            scene_guidance = voice_plan.get("scene_guidance") or []
            if scene_guidance:
                return any(bool(g.get("should_narrate", True)) for g in scene_guidance if isinstance(g, dict))
            # 若缺少逐场景指导，则默认尝试执行，由下游Agent自我校验
            return True
        if agent_type == AgentType.AUDIO_GENERATOR:
            should_run = self._should_run_audio_generator(workflow_state_id)
            try:
                capability = self._get_video_audio_capability()
                strategy = self._resolve_audio_orchestration_strategy(workflow_state_id)
                facts = self._collect_runtime_video_audio_facts(workflow_state_id)
                self.logger.info(
                    "AUDIO_ORCHESTRATION: strategy=%s provider=%s supports_native_audio=%s run_audio_agent=%s facts=%s",
                    strategy,
                    capability.get("provider"),
                    bool(capability.get("supports_native_audio")),
                    should_run,
                    {
                        "records": facts.get("records"),
                        "checked": facts.get("checked"),
                        "with_audio": facts.get("with_audio"),
                        "without_audio": facts.get("without_audio"),
                        "unknown": facts.get("unknown"),
                        "all_have_audio": facts.get("all_have_audio"),
                        "reason": facts.get("reason"),
                    },
                )
            except Exception:
                pass
            return should_run
        return True

    async def _prepare_agent_context(self, workflow_data: Dict[str, Any], agent_type: AgentType, workflow_id: str) -> Dict[str, Any]:
        """为Agent准备包含创意指导的上下文数据"""
        
        try:
            # 复制基础工作流数据
            agent_input = workflow_data.copy()

            if agent_type in [AgentType.CONCEPT_PLANNER, AgentType.SCRIPT_WRITER]:
                episode_ctx = None
                project_ctx = None
                episode_ctx = workflow_data.get("episode_context")
                project_ctx = workflow_data.get("project_context")

                if episode_ctx:
                    agent_input["episode_context"] = episode_ctx
                    approved_flag = bool(str(episode_ctx.get("approved_script", "")).strip())
                    self.logger.info(
                        "🧠 Episode context injected for %s (approved_script=%s)",
                        agent_type.value,
                        approved_flag,
                    )
                if project_ctx:
                    agent_input["project_context"] = project_ctx
                    try:
                        self.logger.info(
                            "🧠 Project context injected for %s",
                            agent_type.value,
                        )
                    except Exception:
                        pass

            def _merge_media_context(
                include_roles: bool,
                *,
                include_audio_requirements: bool = False,
                sfx_required_default: Optional[bool] = None,
                sfx_required_override: Optional[bool] = None,
            ) -> Dict[str, Any]:
                context_bundle = build_media_agent_context(
                    workflow_id,
                    service=self.short_term_service,
                    include_scripts=True,
                    include_roles=include_roles,
                    include_audio_requirements=include_audio_requirements,
                    sfx_required_default=sfx_required_default,
                    sfx_required_override=sfx_required_override,
                )
                for key, value in context_bundle.items():
                    if value:
                        agent_input[key] = value
                return context_bundle

            # 统一静态上下文（静态背景 + 场景视图），传递给 ReAct 基类处理
            static_context: Dict[str, Any] = {}
            if agent_type == AgentType.IMAGE_GENERATOR:
                static_context.update(_merge_media_context(include_roles=True) or {})
            elif agent_type == AgentType.AUDIO_GENERATOR:
                audio_req = workflow_data.get("audio_requirements") if isinstance(workflow_data, dict) else None
                sfx_override = None
                if isinstance(audio_req, dict) and audio_req.get("sfx_required") is not None:
                    sfx_override = bool(audio_req.get("sfx_required"))
                elif isinstance(workflow_data, dict) and workflow_data.get("sfx_required") is not None:
                    sfx_override = bool(workflow_data.get("sfx_required"))
                static_context.update(
                    _merge_media_context(
                        include_roles=False,
                        include_audio_requirements=True,
                        sfx_required_default=getattr(settings, "AUDIO_SFX_REQUIRED_DEFAULT", False),
                        sfx_required_override=sfx_override,
                    )
                    or {}
                )
                if isinstance(audio_req, dict) and audio_req:
                    merged_req = dict(static_context.get("audio_requirements") or {})
                    merged_req.update(audio_req)
                    static_context["audio_requirements"] = merged_req
            elif agent_type == AgentType.VIDEO_COMPOSER:
                from .adapters.memory_views import build_video_composer_context

                composer_requests = {}
                if agent_input.get("compose_requested") is not None:
                    composer_requests["compose_requested"] = bool(agent_input.get("compose_requested"))
                composer_requests["voiceover_requested"] = bool(agent_input.get("add_voiceover"))
                composer_requests["bgm_requested"] = bool(agent_input.get("add_bgm"))
                composer_ctx = build_video_composer_context(
                    workflow_id,
                    service=self.short_term_service,
                    requests=composer_requests,
                )
                if composer_ctx:
                    static_context.update(composer_ctx)
                try:
                    scene_videos = composer_ctx.get("scene_videos") if isinstance(composer_ctx, dict) else []
                    total = len(scene_videos) if isinstance(scene_videos, list) else 0
                    local_count = 0
                    url_only = 0
                    if isinstance(scene_videos, list):
                        for item in scene_videos:
                            if not isinstance(item, dict):
                                continue
                            if item.get("local_path"):
                                local_count += 1
                            elif item.get("video_url"):
                                url_only += 1
                    final_video = composer_ctx.get("final_video") if isinstance(composer_ctx, dict) else {}
                    final_path = final_video.get("path") if isinstance(final_video, dict) else ""
                    self.logger.info(
                        "🧠 video_composer static_context scene_videos=%s local_paths=%s url_only=%s final_video_path=%s",
                        total,
                        local_count,
                        url_only,
                        final_path or None,
                    )
                except Exception:
                    pass

            if agent_type == AgentType.IMAGE_GENERATOR:
                image_ctx = build_image_generation_context(workflow_id, service=self.short_term_service)
                if isinstance(image_ctx, dict) and image_ctx.get("context"):
                    ctx_payload = image_ctx.get("context") or {}
                    scene_info_payload = image_ctx.get("scene_info_payload") or {}
                    payload_for_ref = scene_info_payload or ctx_payload
                    ref_path = self._persist_scene_info_ref(
                        workflow_id=str(workflow_id),
                        agent_type=agent_type,
                        payload=payload_for_ref,
                    )
                    if ref_path:
                        ctx_payload = dict(ctx_payload)
                        ctx_payload["scene_info_ref"] = ref_path
                        static_context.update(ctx_payload)
                        try:
                            self.logger.info(
                                "🧠 image_generator scene_info_ref_ready=True ref_file=%s static_keys=%s",
                                Path(ref_path).name,
                                list(ctx_payload.keys()),
                            )
                        except Exception:
                            pass
                    else:
                        fallback_ctx = dict(ctx_payload)
                        if scene_info_payload:
                            fallback_ctx["scene_info_payload"] = scene_info_payload
                        static_context.update(fallback_ctx)
                        try:
                            self.logger.info(
                                "🧠 image_generator scene_info_ref_ready=False static_keys=%s",
                                list(fallback_ctx.keys()),
                            )
                        except Exception:
                            pass
            elif agent_type == AgentType.VIDEO_GENERATOR:
                video_ctx = build_video_generation_context(workflow_id, service=self.short_term_service)
                if isinstance(video_ctx, dict) and video_ctx.get("context"):
                    ctx_payload = video_ctx.get("context") or {}
                    scene_info_payload = video_ctx.get("scene_info_payload") or {}
                    try:
                        scenes_to_generate_count = len(scene_info_payload.get("scenes_to_generate") or [])
                        self.logger.info(
                            "🧠 video_generator static_context scenes_to_generate=%s total_scenes=%s has_scene_overview=%s",
                            scenes_to_generate_count,
                            scene_info_payload.get("total_scenes"),
                            bool(scene_info_payload.get("scene_overview")),
                        )
                    except Exception:
                        pass

                    ref_path = self._persist_scene_info_ref(
                        workflow_id=str(workflow_id),
                        agent_type=agent_type,
                        payload=scene_info_payload,
                    )

                    if ref_path:
                        ctx_payload = dict(ctx_payload)
                        ctx_payload["scene_info_ref"] = ref_path
                        key_illustration = dict(ctx_payload.get("key_illustration") or {})
                        key_illustration.setdefault("task_overview", "全局故事与风格/角色概览，仅用于规划")
                        key_illustration.setdefault("scene_dependency_graph", "场景依赖关系，表示生成顺序")
                        key_illustration["scene_info_ref"] = "场景详细信息的引用地址（包含所有场景的具体规划数据）"
                        ctx_payload["key_illustration"] = key_illustration
                        static_context.update(ctx_payload)
                        try:
                            ref_name = Path(ref_path).name
                            self.logger.info(
                                "🧠 video_generator scene_info_ref_ready=True ref_file=%s static_keys=%s",
                                ref_name,
                                list(ctx_payload.keys()),
                            )
                        except Exception:
                            pass
                    else:
                        fallback_ctx = dict(ctx_payload)
                        if scene_info_payload:
                            fallback_ctx["scene_info_payload"] = scene_info_payload
                        static_context.update(fallback_ctx)
                        try:
                            self.logger.info(
                                "🧠 video_generator scene_info_ref_ready=False static_keys=%s",
                                list(fallback_ctx.keys()),
                            )
                        except Exception:
                            pass

            elif agent_type == AgentType.VOICE_SYNTHESIZER:
                voice_ctx = build_voice_synthesis_context(workflow_id, service=self.short_term_service)
                if isinstance(voice_ctx, dict) and voice_ctx.get("context"):
                    ctx_payload = voice_ctx.get("context") or {}
                    static_context.update(ctx_payload)
                    try:
                        self.logger.info(
                            "🧠 voice_synthesizer static_context scenes_to_synthesize=%s scenes_completed=%s scenes_blocked=%s",
                            len(ctx_payload.get("scenes_to_synthesize") or []),
                            len(ctx_payload.get("scenes_completed") or []),
                            len(ctx_payload.get("scenes_blocked") or []),
                        )
                    except Exception:
                        pass

            if static_context:
                agent_input["static_context"] = static_context

            if agent_type in [AgentType.IMAGE_GENERATOR, AgentType.VIDEO_GENERATOR, AgentType.AUDIO_GENERATOR]:
                overall_guidance = workflow_data.get("creative_guidance")
                if overall_guidance:
                    agent_input["creative_guidance"] = overall_guidance
                scene_guidances = workflow_data.get("scene_guidances")
                if scene_guidances:
                    agent_input["scene_guidances"] = scene_guidances

            return agent_input
            
        except Exception as e:
            self.logger.error(f"❌ Failed to prepare agent context for {agent_type.value}: {e}")
            # 返回原始数据，不阻塞workflow
            return workflow_data

    def _build_fallback_task(self, agent_type: AgentType) -> Dict[str, Any]:
        """构造默认 task 指令（LLM 分解失败或缺失时使用）。"""
        goal_map = {
            AgentType.CONCEPT_PLANNER: "concept_generation",
            AgentType.SCRIPT_WRITER: "script_writing",
            AgentType.IMAGE_GENERATOR: "batch_image_generation",
            AgentType.VIDEO_GENERATOR: "video_generation",
            AgentType.VIDEO_COMPOSER: "video_composition",
            AgentType.VOICE_SYNTHESIZER: "voice_synthesis",
            AgentType.AUDIO_GENERATOR: "bgm_generation",
            AgentType.QUALITY_CHECKER: "quality_check",
        }
        instruction_map = {
            AgentType.CONCEPT_PLANNER: "基于用户需求生成视频概念和场景大纲",
            AgentType.SCRIPT_WRITER: "基于概念/场景大纲生成逐场景脚本和旁白",
            AgentType.IMAGE_GENERATOR: "基于当前场景定义生成所需图片",
            AgentType.VIDEO_GENERATOR: "基于场景资源生成视频片段",
            AgentType.VIDEO_COMPOSER: "将视频片段/音频合成为成片",
            AgentType.VOICE_SYNTHESIZER: "为场景脚本生成旁白音频",
            AgentType.AUDIO_GENERATOR: "为成片生成背景音乐",
            AgentType.QUALITY_CHECKER: "检查成片质量并输出改进建议",
        }
        boundaries = {
            AgentType.IMAGE_GENERATOR: ["不要覆盖已有 image_url", "遵循风格/分辨率配置"],
            AgentType.VIDEO_GENERATOR: ["避免重复生成已完成场景", "使用现有图片/提示"],
            AgentType.VIDEO_COMPOSER: ["不修改原始片段", "保持音画同步"],
            AgentType.VOICE_SYNTHESIZER: ["尊重 voice_plan 设置", "缺场景时跳过"],
            AgentType.AUDIO_GENERATOR: ["交付物需可用于后续合成", "如产物为远程链接，需提供可用的本地文件路径"],
        }.get(agent_type, [])
        expected_output = {
            AgentType.IMAGE_GENERATOR: "每个待处理场景输出图片或链接",
            AgentType.VIDEO_GENERATOR: "每个场景输出视频片段",
            AgentType.SCRIPT_WRITER: "逐场景脚本文本/旁白/动作要点",
            AgentType.CONCEPT_PLANNER: "概念计划及场景大纲",
            AgentType.VOICE_SYNTHESIZER: "逐场景旁白音频",
            AgentType.AUDIO_GENERATOR: "背景音乐（可用于后续合成的本地文件路径或等价可落盘资源）",
            AgentType.VIDEO_COMPOSER: "合成后的完整视频",
            AgentType.QUALITY_CHECKER: "质量报告与建议",
        }.get(agent_type, "本阶段的标准产出")
        return {
            "instruction": instruction_map.get(agent_type, f"执行 {agent_type.value} 任务"),
            "goal": goal_map.get(agent_type, agent_type.value.lower()),
            "expected_output": expected_output,
            "boundaries": boundaries,
            "scope": {"workflow_id": None},
            "fallback_used": True,
        }

    def _build_bgm_mix_task_spec(self, workflow_id: str, *, fallback_used: bool) -> Dict[str, Any]:
        """为背景音乐混流构造明确的任务说明（预分配或兜底使用）。"""
        spec = self._build_fallback_task(AgentType.VIDEO_COMPOSER)
        spec["instruction"] = "将已生成的背景音乐混入现有成片，输出可播放的最终成片"
        spec["goal"] = "bgm_mix"
        spec["expected_output"] = "带背景音乐的成片文件路径或可访问URL"
        spec["boundaries"] = [
            "仅在已有成片上进行混音，不重新生成场景视频",
            "若背景音乐不可用，明确阻塞原因并停止无效操作",
        ]
        scope = spec.get("scope") or {}
        if isinstance(scope, dict):
            scope["workflow_id"] = workflow_id
            spec["scope"] = scope
        spec["fallback_used"] = bool(fallback_used)
        return spec

    async def _llm_decompose_tasks(
        self,
        workflow_data: Dict[str, Any],
        workflow_id: str,
    ) -> Tuple[Dict[AgentType, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
        """LLM 生成 per-Agent 指令与条件任务说明，失败时返回空映射，由回退处理。"""
        try:
            user_prompt = workflow_data.get("user_prompt") or workflow_data.get("prompt") or ""
            page_params = {
                "duration": workflow_data.get("duration"),
                "resolution": workflow_data.get("resolution"),
                "target_resolution": workflow_data.get("target_resolution"),
            }
            available_agents = [atype.value for atype in self.workflow_order]
            system_text = (
                "你是多智能体编排器，需输出每个子Agent的执行指令。"
                "返回JSON，必须包含 agents 列表，元素含：agent（枚举），run（bool），"
                "instruction，goal，expected_output，boundaries（数组，可空），scope（对象，可空），order（数字，可选）。"
                "必须提供 conditional_tasks 列表，用于描述条件触发的额外任务，元素含："
                "task_id（字符串），agent（枚举），instruction，goal，expected_output，boundaries（数组，可空），"
                "scope（对象，可空），trigger（字符串，可选）。"
                "conditional_tasks 中必须包含用于背景音乐混流的任务，task_id 固定为 video_composer_bgm_mix。"
                "不要编造场景内容，指示子Agent使用当前 MAS 记忆中的事实。"
            )
            user_content = {
                "user_prompt": user_prompt,
                "page_params": page_params,
                "available_agents": available_agents,
            }
            messages = [
                {"role": "system", "content": system_text},
                {"role": "user", "content": json.dumps(user_content, ensure_ascii=False)},
            ]
            llm = self.get_llm("plan")
            resp = await llm.chat_completion(
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.2,
                max_tokens=getattr(settings, "LLM_MAX_TOKENS_STANDARD", 2048),
            )
            content = resp.get("content") if isinstance(resp, dict) else None
            if not content:
                raise ValueError("LLM decomposition returned empty content")
            data = json.loads(content)
            agents = data.get("agents") if isinstance(data, dict) else None
            task_map: Dict[AgentType, Dict[str, Any]] = {}
            conditional_task_specs: Dict[str, Dict[str, Any]] = {}
            if isinstance(agents, list):
                for item in agents:
                    if not isinstance(item, dict):
                        continue
                    name = (item.get("agent") or "").upper()
                    try:
                        atype = AgentType[name]
                    except Exception:
                        continue
                    run_flag = item.get("run")
                    spec = {
                        "instruction": item.get("instruction"),
                        "goal": item.get("goal"),
                        "expected_output": item.get("expected_output"),
                        "boundaries": item.get("boundaries") or [],
                        "scope": item.get("scope") or {"workflow_id": workflow_id},
                        "order": item.get("order"),
                        "run": bool(run_flag) if run_flag is not None else True,
                        "fallback_used": False,
                    }
                    task_map[atype] = spec
            conditional_tasks = data.get("conditional_tasks") if isinstance(data, dict) else None
            if not isinstance(conditional_tasks, list):
                raise ValueError("LLM task decomposition missing conditional_tasks list")
            for item in conditional_tasks:
                if not isinstance(item, dict):
                    continue
                task_id = str(item.get("task_id") or "").strip()
                if not task_id:
                    continue
                name = (item.get("agent") or "").upper()
                try:
                    atype = AgentType[name]
                except Exception:
                    continue
                spec = {
                    "agent": atype.value,
                    "instruction": item.get("instruction"),
                    "goal": item.get("goal"),
                    "expected_output": item.get("expected_output"),
                    "boundaries": item.get("boundaries") or [],
                    "scope": item.get("scope") or {"workflow_id": workflow_id},
                    "trigger": item.get("trigger"),
                    "fallback_used": False,
                }
                conditional_task_specs[task_id] = spec
            if "video_composer_bgm_mix" not in conditional_task_specs:
                raise ValueError("LLM task decomposition missing video_composer_bgm_mix task")
            return task_map, conditional_task_specs
        except Exception as e:
            try:
                self.logger.error("LLM task decomposition failed: %s (required)", e)
            except Exception:
                pass
            raise AgentError("LLM task decomposition is required but failed") from e
