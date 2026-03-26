"""
Orchestrator Agent - Coordinates the entire video generation workflow.
"""
import asyncio
import os
import logging
import json
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session

from .base import BaseAgent, AgentError
from ..models import (
    Task,
    TaskStatus,
    AgentType,
    WorkflowNodeStatus,
    WorkflowSessionStatus,
)
from ..services.memory_provider import build_memory_services, MemoryServices
from ..services.audio_delivery_gate_evaluator import AudioDeliveryGateEvaluator
from ..services.context_assembler import ContextContractAssembler
from ..services.orchestration_observation_adapter import OrchestrationObservationAdapter
from ..services.orchestration_control_plane import (
    OrchestrationControlPlane,
    OrchestrationControlPlaneError,
)
from ..services.orchestration_protocol import OrchestrationProtocol, OrchestrationProtocolError
from ..services.orchestration_queue_policy import OrchestrationQueuePolicy
from ..services.orchestration_runtime_controller import (
    OrchestrationRuntimeController,
    OrchestrationRuntimeControllerError,
)
from ..services.orchestration_state_adapter import OrchestrationStateAdapter
from ..services.workflow_completion_adapter import WorkflowCompletionAdapter
from ..services.runtime_session_service import RuntimeSessionService
from ..services.script_review_contract import (
    get_script_review_contract,
)
# legacy WM singleton removed - use injected self._memory_services.short_term
from .utils.memory_helpers import (
    agent_scope,
    mas_scope,
    get_mas_working_memory,
    write_shared_fact,
    read_shared_fact,
)

from ..events.execution import execution_context_var
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
    
    @classmethod
    def create_default(cls) -> "OrchestratorAgent":
        return cls(memory_services=build_memory_services())

    def __init__(self, memory_services: Optional[MemoryServices] = None):
        import os
        from .utils.llm_policy import LLMPolicyManager
        policy_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'llm_policies.yaml')
        self._llm_policy = LLMPolicyManager(policy_file)
        if memory_services is None:
            raise ValueError("memory_services is required for OrchestratorAgent")
        self._memory_services = memory_services
        self._audio_delivery_gate = AudioDeliveryGateEvaluator(memory_services=self._memory_services)
        self._context_contract_assembler = ContextContractAssembler(self._memory_services)
        self._orchestration_state = OrchestrationStateAdapter(self._memory_services)
        self._orchestration_observation = OrchestrationObservationAdapter(self._memory_services)
        self._orchestration_protocol = OrchestrationProtocol()
        self._runtime_controller = OrchestrationRuntimeController(
            memory_services=self._memory_services,
            orchestration_state=self._orchestration_state,
        )
        self._orchestration_control_plane = OrchestrationControlPlane(
            memory_services=self._memory_services,
            protocol=self._orchestration_protocol,
            orchestration_state=self._orchestration_state,
            audio_delivery_gate=self._audio_delivery_gate,
            observation_adapter=self._orchestration_observation,
            runtime_controller=self._runtime_controller,
        )
        self._workflow_completion_adapter = WorkflowCompletionAdapter(
            self._memory_services,
            owner_agent_name="orchestrator",
        )
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
        self._last_audio_route_payload: Dict[str, Any] = {}

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

    def reset_repeat_counters(self) -> None:
        """Clear per-step repeat counters so retries start fresh."""
        self._step_repeat_counts = {}

    @staticmethod
    def _runtime_node_key_for_agent(agent_type: AgentType) -> Optional[str]:
        mapping = {
            AgentType.CONCEPT_PLANNER: "concept",
            AgentType.SCRIPT_WRITER: "script",
            AgentType.IMAGE_GENERATOR: "image",
            AgentType.VIDEO_GENERATOR: "video",
            AgentType.VOICE_SYNTHESIZER: "voice",
            AgentType.VIDEO_COMPOSER: "compose",
            AgentType.AUDIO_GENERATOR: "audio",
            AgentType.QUALITY_CHECKER: "quality",
        }
        return mapping.get(agent_type)

    @staticmethod
    def _agent_type_for_runtime_node_key(node_key: str) -> Optional[AgentType]:
        normalized = str(node_key or "").strip().lower()
        if not normalized:
            return None
        for agent_type in AgentType:
            if OrchestratorAgent._runtime_node_key_for_agent(agent_type) == normalized:
                return agent_type
        return None

    @staticmethod
    def _parse_agent_type(value: Any) -> Optional[AgentType]:
        if isinstance(value, AgentType):
            return value
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            return AgentType[raw.upper()]
        except Exception:
            pass
        try:
            return AgentType(raw.lower())
        except Exception:
            pass
        try:
            return AgentType(raw)
        except Exception:
            return None

    def _registered_agents(self) -> List[AgentType]:
        agents = getattr(self, "agents", {}) or {}
        return [agent_type for agent_type in agents.keys() if isinstance(agent_type, AgentType)]

    @staticmethod
    def _planning_agent_catalog() -> Dict[str, str]:
        return {
            AgentType.CONCEPT_PLANNER.value: "负责概念规划、整体创意方向与场景方案设计",
            AgentType.SCRIPT_WRITER.value: "负责将概念方案扩展成可执行的视频脚本与镜头台词",
            AgentType.IMAGE_GENERATOR.value: "负责生成分镜图片与关键静态视觉素材",
            AgentType.VIDEO_GENERATOR.value: "负责生成场景视频片段与动态画面",
            AgentType.VOICE_SYNTHESIZER.value: "负责旁白、角色配音或语音合成",
            AgentType.VIDEO_COMPOSER.value: "负责拼接、合成与最终视频组装",
            AgentType.AUDIO_GENERATOR.value: "负责背景音乐、音效或后置音频生成",
            AgentType.QUALITY_CHECKER.value: "负责结果审查、完整性核验与质量把关",
        }

    @staticmethod
    def _extract_planning_task_traits(workflow_data: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(workflow_data or {})
        audio_contract = dict(payload.get("audio_contract") or {})
        return {
            "duration": payload.get("duration"),
            "resolution": payload.get("resolution") or payload.get("target_resolution"),
            "has_voice_settings": isinstance(payload.get("voice_settings"), dict),
            "has_voice_plan": isinstance(payload.get("voice_plan"), dict),
            "has_audio_requirements": isinstance(payload.get("audio_requirements"), dict),
            "has_script_review_contract": isinstance(payload.get("script_review_contract"), dict),
            "allow_silence": bool(audio_contract.get("allow_silence", True)),
            "need_voiceover": bool(audio_contract.get("need_voiceover", False)),
            "need_global_bgm": bool(audio_contract.get("need_global_bgm", False)),
        }

    @staticmethod
    def _normalize_assignment_constraints(value: Any) -> List[str]:
        if isinstance(value, list):
            constraints: List[str] = []
            for item in value:
                text = str(item or "").strip()
                if text:
                    constraints.append(text)
            return constraints
        text = str(value or "").strip()
        return [text] if text else []

    @staticmethod
    def _normalize_runtime_hints(value: Any) -> Dict[str, Any]:
        return dict(value) if isinstance(value, dict) else {}

    def _get_orchestration_state_adapter(self) -> OrchestrationStateAdapter:
        adapter = getattr(self, "_orchestration_state", None)
        if adapter is None:
            adapter = OrchestrationStateAdapter(memory_services=self._memory_services)
            self._orchestration_state = adapter
        return adapter

    def _get_context_contract_assembler(self) -> ContextContractAssembler:
        assembler = getattr(self, "_context_contract_assembler", None)
        if assembler is None:
            assembler = ContextContractAssembler(self._memory_services)
            self._context_contract_assembler = assembler
        return assembler

    def _get_orchestration_observation_adapter(self) -> OrchestrationObservationAdapter:
        adapter = getattr(self, "_orchestration_observation", None)
        if adapter is None:
            adapter = OrchestrationObservationAdapter(memory_services=self._memory_services)
            self._orchestration_observation = adapter
        return adapter

    def _get_orchestration_control_plane(self) -> OrchestrationControlPlane:
        control_plane = getattr(self, "_orchestration_control_plane", None)
        if control_plane is None:
            control_plane = OrchestrationControlPlane(
                memory_services=self._memory_services,
                protocol=getattr(self, "_orchestration_protocol", None),
                orchestration_state=self._get_orchestration_state_adapter(),
                audio_delivery_gate=getattr(self, "_audio_delivery_gate", None),
                observation_adapter=self._get_orchestration_observation_adapter(),
                runtime_controller=getattr(self, "_runtime_controller", None),
            )
            self._orchestration_control_plane = control_plane
        return control_plane

    @staticmethod
    def _resolve_runtime_script_state(
        db: Session,
        task: Task,
    ) -> Tuple[Optional[Any], Optional[Any], Optional[Any], str]:
        if db is None:
            return None, None, None, ""
        runtime_session = RuntimeSessionService.get_or_create_session_for_task_sync(
            db,
            task,
            mode="quick",
        )
        script_gate = RuntimeSessionService.get_latest_gate_for_node_sync(
            db,
            runtime_session.id,
            "script",
        )
        latest_decision = None
        if script_gate is not None:
            latest_decision = RuntimeSessionService.get_latest_decision_for_gate_sync(
                db,
                script_gate.id,
            )

        resume_action = ""
        if latest_decision is not None and runtime_session.status == WorkflowSessionStatus.RESUMING.value:
            resume_action = str(latest_decision.action or "").strip().lower()

        return runtime_session, script_gate, latest_decision, resume_action

    def _open_script_review_gate(
        self,
        *,
        runtime_session: Any,
        task: Task,
        db: Session,
        workflow_id: str,
        script_attempt_id: int,
        trigger_reason: str,
        script_output: Dict[str, Any],
    ) -> Dict[str, Any]:
        boundary = self._get_context_contract_assembler().publish_script_review_boundary_sync(
            db=db,
            session=runtime_session,
            workflow_state_id=workflow_id,
            attempt_id=script_attempt_id,
            script_output=script_output,
        )
        gate = RuntimeSessionService.complete_script_attempt_and_open_review_gate_sync(
            db,
            runtime_session,
            task=task,
            workflow_state_id=workflow_id,
            attempt_id=script_attempt_id,
            trigger_reason=trigger_reason,
            script_output=script_output,
            artifact_ref=dict(boundary.get("artifact_ref") or {}),
            script_preview_text=str(boundary.get("script_preview_text") or ""),
        )
        return {
            "status": "waiting_gate",
            "session_id": runtime_session.id,
            "gate_id": gate.id,
            "node_key": "script",
        }

    async def _llm_select_candidate_agents(
        self,
        *,
        workflow_data: Dict[str, Any],
        workflow_id: str,
    ) -> Tuple[List[AgentType], str]:
        registered_agents = self._registered_agents()
        if not registered_agents:
            raise AgentError("No registered agents available for candidate selection")

        task_traits = self._extract_planning_task_traits(workflow_data)
        page_params = {
            "duration": workflow_data.get("duration"),
            "resolution": workflow_data.get("resolution"),
            "target_resolution": workflow_data.get("target_resolution"),
        }
        pm = self.prompt_manager
        try:
            agent_sys = self.get_system_instructions() or {}
            pr = agent_sys.get("primary_role") or "工作流编排器"
        except Exception:
            pr = "工作流编排器"

        system_text = pm.render_template(
            "agents/orchestrator",
            "candidate_selection_system",
            variables={"primary_role": pr},
            use_cache=True,
            auto_reload=False,
        )
        user_text = pm.render_template(
            "agents/orchestrator",
            "candidate_selection_user",
            variables={
                "user_prompt": str(
                    workflow_data.get("user_prompt") or workflow_data.get("prompt") or ""
                ),
                "page_params_json": json.dumps(page_params, ensure_ascii=False),
                "registered_agents_json": json.dumps(
                    [agent.value for agent in registered_agents], ensure_ascii=False
                ),
                "agent_catalog_json": json.dumps(
                    self._planning_agent_catalog(), ensure_ascii=False
                ),
                "task_traits_json": json.dumps(task_traits, ensure_ascii=False),
                "runtime_constraints_json": json.dumps(
                    {
                        "audio_contract": workflow_data.get("audio_contract") or {},
                        "audio_capability": workflow_data.get("audio_capability") or {},
                        "workflow_state_id": workflow_id,
                    },
                    ensure_ascii=False,
                ),
            },
            use_cache=True,
            auto_reload=False,
        )
        llm = self.get_llm("plan")
        resp = await llm.chat_completion(
            messages=[
                {"role": "system", "content": system_text},
                {"role": "user", "content": user_text},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=getattr(settings, "LLM_MAX_TOKENS_STANDARD", 2048),
        )
        content = resp.get("content") if isinstance(resp, dict) else None
        if not content:
            raise AgentError("LLM candidate selection returned empty content")

        try:
            data = json.loads(content)
        except Exception as exc:
            raise AgentError(f"LLM candidate selection returned invalid JSON: {exc}") from exc

        raw_agents = data.get("candidate_agents") if isinstance(data, dict) else None
        if not isinstance(raw_agents, list) or not raw_agents:
            raise AgentError("LLM candidate selection missing candidate_agents list")

        registered_set = set(registered_agents)
        candidate_agents: List[AgentType] = []
        unknown_agents: List[str] = []
        for raw in raw_agents:
            parsed = self._parse_agent_type(raw)
            if parsed is None or parsed not in registered_set:
                unknown_agents.append(str(raw))
                continue
            if parsed not in candidate_agents:
                candidate_agents.append(parsed)
        if unknown_agents:
            raise AgentError(
                "LLM candidate selection returned unknown agents: "
                + ", ".join(unknown_agents)
            )
        if not candidate_agents:
            raise AgentError("LLM candidate selection produced no valid candidate agents")
        rationale = (
            str(data.get("selection_rationale") or "").strip()
            if isinstance(data, dict)
            else ""
        )
        return candidate_agents, rationale

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
            audio_capability = self._get_video_audio_capability()
            audio_contract = self._orchestration_state.build_audio_contract(
                workflow_state_id=wf_id,
                input_data=input_data,
            )
        except Exception as route_err:
            raise AgentError(f"Failed to initialize orchestration context: {route_err}") from route_err

        runtime_session, script_gate, latest_script_decision, script_resume_action = (
            self._resolve_runtime_script_state(db, task)
        )
        if script_gate is not None and latest_script_decision is None:
            return {
                "status": "waiting_gate",
                "session_id": runtime_session.id,
                "gate_id": script_gate.id,
                "node_key": "script",
            }

        runtime_input_payload = dict(getattr(runtime_session, "input_payload", {}) or {})
        workflow_data = runtime_input_payload.copy() if runtime_input_payload else input_data.copy()
        workflow_data.setdefault("resolution", input_data.get("resolution") or settings.DEFAULT_VIDEO_RESOLUTION)
        workflow_data.setdefault("target_resolution", workflow_data.get("resolution"))
        # 将 workflow_state_id 传递给 Agent，Agent 从 Shared WM 读取上下文
        workflow_data["workflow_state_id"] = wf_id
        workflow_data["audio_contract"] = dict(audio_contract)
        workflow_data["audio_capability"] = dict(audio_capability)
        skip_agents: set[AgentType] = set()
        raw_skip_agents = input_data.get("skip_agents") if isinstance(input_data, dict) else []
        if isinstance(raw_skip_agents, list):
            for item in raw_skip_agents:
                try:
                    skip_agents.add(AgentType(str(item)))
                except Exception:
                    continue
        review_contract = get_script_review_contract(getattr(runtime_session, "input_payload", None))
        if script_resume_action in {"revise", "replan"} and isinstance(review_contract, dict) and review_contract:
            workflow_data["script_review_contract"] = dict(review_contract)
        else:
            workflow_data.pop("script_review_contract", None)

        candidate_agents, selection_rationale = await self._llm_select_candidate_agents(
            workflow_data=workflow_data,
            workflow_id=wf_id,
        )
        self._orchestration_state.persist_llm_planning_context(
            workflow_state_id=wf_id,
            registered_agents=self._registered_agents(),
            candidate_agents=list(candidate_agents),
            audio_contract=audio_contract,
            capability_snapshot=audio_capability,
            selection_rationale=selection_rationale,
        )

        if script_resume_action == "approve":
            skip_agents.update({AgentType.CONCEPT_PLANNER, AgentType.SCRIPT_WRITER})
            script_node = RuntimeSessionService.get_node_by_key_sync(db, runtime_session.id, "script")
            if script_node is not None and script_node.status == WorkflowNodeStatus.APPROVED.value:
                script_node.status = WorkflowNodeStatus.COMPLETED.value
            runtime_session.status = WorkflowSessionStatus.RUNNING.value
            runtime_session.current_node_key = None
            runtime_session.current_attempt_id = None
            task.status = TaskStatus.IN_PROGRESS.value
            db.commit()

        workflow_results = {}
        # 任务分解（LLM → per-agent 指令），失败则回退
        task_specs, _conditional_task_specs = await self._llm_decompose_tasks(
            workflow_data,
            wf_id,
            candidate_agents=list(candidate_agents),
        )
        self._orchestration_state.persist_task_specs(
            workflow_state_id=wf_id,
            task_specs=task_specs,
            conditional_task_specs=_conditional_task_specs,
            candidate_agents=list(candidate_agents),
        )

        execution_queue = self._build_execution_queue(task_specs, candidate_agents=list(candidate_agents))
        standby_agents = self._build_standby_agents(task_specs, candidate_agents=list(candidate_agents))
        replan_count = 0
        max_replans = int(getattr(settings, "ORCHESTRATOR_MAX_REPLAN_ACTIVATIONS", 2))
        total_steps = len(execution_queue)
        script_attempt_id: Optional[int] = None
        script_trigger_reason = (
            script_resume_action if script_resume_action in {"revise", "replan"} else "initial"
        )
        script_requested_by = (
            str(getattr(latest_script_decision, "actor_type", "") or "system")
            if latest_script_decision is not None
            else "system"
        )
        
        try:
            for step_index, agent_type in enumerate(execution_queue):
                total_steps = max(len(execution_queue), 1)
                agent = self.agents[agent_type]
                if agent_type in skip_agents:
                    self.logger.info("⏭️ Skipping %s due to runtime skip_agents", agent.agent_name)
                    continue
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

                self._emit_pre_dispatch_diagnostics(agent_type, wf_id)
                if (
                    runtime_session is not None
                    and script_attempt_id is None
                    and agent_type == AgentType.SCRIPT_WRITER
                    and agent_type not in skip_agents
                ):
                    script_attempt = RuntimeSessionService.start_node_attempt_sync(
                        db,
                        runtime_session,
                        node_key="script",
                        trigger_reason=script_trigger_reason,
                        requested_by=script_requested_by,
                        input_contract={"stage": "script", "workflow_state_id": wf_id},
                        task=task,
                        progress_step="Generating script",
                        progress_percentage=15,
                    )
                    script_attempt_id = script_attempt.id
                elif runtime_session is not None:
                    runtime_node_key = self._runtime_node_key_for_agent(agent_type)
                    if runtime_node_key is not None:
                        RuntimeSessionService.mark_node_running_sync(
                            db,
                            runtime_session,
                            node_key=runtime_node_key,
                            task=task,
                        )
                
                # Update progress
                progress_percentage = int((step_index / total_steps) * 90)  # 为持久化预留10%
                current_step = f"Executing {agent.agent_name}"
                
                await self._update_progress(
                    progress_percentage, 
                    current_step,
                    db
                )
                
                # Update task progress
                task.update_progress(current_step, progress_percentage)
                self.logger.info(f"Starting workflow step {step_index + 1}/{total_steps}: {agent.agent_name}")
                
                try:
                    # Prepare agent input with creative context (if available)
                    self.logger.info(f"🧠 DEBUG: Preparing context for {agent_type.value}")
                    agent_input = await self._prepare_agent_context(
                        workflow_data,
                        agent_type,
                        wf_id,
                        runtime_input_payload=runtime_input_payload,
                    )
                    boundary_assembler = self._get_context_contract_assembler()
                    runtime_hints = boundary_assembler.resolve_runtime_hints(
                        workflow_state_id=wf_id,
                        agent_type=agent_type,
                    )
                    execution_contract = boundary_assembler.build_execution_contract(
                        agent_type=agent_type,
                        workflow_state_id=wf_id,
                        runtime_hints=runtime_hints,
                    )
                    if isinstance(execution_contract, dict) and execution_contract:
                        agent_input["execution_contract"] = execution_contract
                        agent_input = boundary_assembler.apply_execution_boundary(
                            agent_type=agent_type,
                            agent_input=agent_input,
                            execution_contract=execution_contract,
                        )
                    # 注入 task 指令（LLM 分解或回退），与 static_context 并行
                    try:
                        task_spec = task_specs.get(agent_type) if isinstance(task_specs, dict) else None
                    except Exception:
                        task_spec = None
                    if not isinstance(task_spec, dict):
                        raise AgentError(
                            f"Missing task_spec for scheduled agent: {agent_type.value}"
                        )
                    task_spec = dict(task_spec)
                    task_spec.setdefault("agent", agent_type.value)
                    task_spec.setdefault("constraints", [])
                    task_spec.setdefault("runtime_hints", {})
                    task_spec.setdefault("run", True)
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

                    if runtime_session is not None and agent_type != AgentType.SCRIPT_WRITER:
                        runtime_node_key = self._runtime_node_key_for_agent(agent_type)
                        if runtime_node_key is not None:
                            RuntimeSessionService.mark_node_completed_sync(
                                db,
                                runtime_session,
                                node_key=runtime_node_key,
                            )

                    if (
                        runtime_session is not None
                        and agent_type == AgentType.SCRIPT_WRITER
                        and script_attempt_id is not None
                    ):
                        return self._open_script_review_gate(
                            runtime_session=runtime_session,
                            task=task,
                            db=db,
                            workflow_id=wf_id,
                            script_attempt_id=script_attempt_id,
                            trigger_reason=script_trigger_reason,
                            script_output=dict(agent_output or {}),
                        )

                    # Runtime decisions are driven by subagent reports plus boundary-triggered gate results.
                    try:
                        runtime_cycle = await self._evaluate_runtime_boundary_cycle(
                            workflow_state_id=wf_id,
                            current_agent=agent_type,
                            agent_output=agent_output,
                            audio_contract=dict(audio_contract or {}),
                            candidate_agents=list(candidate_agents),
                            standby_agents=standby_agents,
                            replan_count=replan_count,
                            max_replans=max_replans,
                            current_index=step_index,
                            execution_queue=execution_queue,
                            task_specs=task_specs,
                            conditional_task_specs=_conditional_task_specs,
                        )
                        runtime_decision = runtime_cycle.get("runtime_decision") or {}
                        replan_action = str(runtime_decision.get("action") or "continue").strip()
                        replan_reason = str(runtime_decision.get("reason") or "none").strip()
                        apply_result = runtime_cycle.get("apply_result") or {}
                        if apply_result.get("status") == "activated":
                            target_agent = apply_result.get("target_agent")
                            updated_queue = apply_result.get("execution_queue")
                            if isinstance(updated_queue, list):
                                execution_queue[:] = list(updated_queue)
                            updated_task_specs = apply_result.get("task_specs")
                            if isinstance(updated_task_specs, dict):
                                task_specs.clear()
                                task_specs.update(updated_task_specs)
                            standby_agents = list(apply_result.get("standby_agents") or standby_agents)
                            replan_count = int(apply_result.get("replan_count") or replan_count)
                            self.logger.info(
                                "ADAPTIVE_REPLAN action=activate_from_standby target=%s reason=%s queue_changed=%s count=%s",
                                target_agent.value if isinstance(target_agent, AgentType) else target_agent,
                                replan_reason,
                                bool(apply_result.get("queue_changed")),
                                replan_count,
                            )
                        elif apply_result.get("status") == "abort":
                            raise AgentError(f"Workflow halted by runtime decision: {replan_reason}")
                        decision_ack = runtime_cycle.get("decision_ack") or {}
                        self.logger.debug(
                            "RUNTIME_DECISION_ACK %s",
                            json.dumps(decision_ack, ensure_ascii=False),
                        )
                    except AgentError:
                        raise
                    except Exception as replan_err:
                        raise AgentError(
                            f"Runtime decision evaluation failed: {replan_err}"
                        ) from replan_err
                    
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

                except Exception as e:
                    if (
                        runtime_session is not None
                        and script_attempt_id is not None
                        and agent_type in {AgentType.CONCEPT_PLANNER, AgentType.SCRIPT_WRITER}
                    ):
                        RuntimeSessionService.fail_node_attempt_sync(
                            db,
                            runtime_session,
                            node_key="script",
                            attempt_id=script_attempt_id,
                            error_message=str(e),
                            diagnostics=[
                                {
                                    "code": "script_stage_failed",
                                    "stage": "script",
                                    "message": str(e),
                                }
                            ],
                        )
                        script_attempt_id = None
                    error_msg = f"Workflow failed at step {step_index + 1} ({agent.agent_name}): {str(e)}"
                    self.logger.error(error_msg)
                    
                    # Check if we should retry the failed step
                    if await self._should_retry_step(agent_type, e, db):
                        self.logger.info(f"Retrying step {step_index + 1}: {agent.agent_name}")
                        if (
                            runtime_session is not None
                            and agent_type in {AgentType.CONCEPT_PLANNER, AgentType.SCRIPT_WRITER}
                            and script_attempt_id is None
                        ):
                            retry_trigger_reason = (
                                script_trigger_reason
                                if script_trigger_reason in {"revise", "replan"}
                                else "retry"
                            )
                            retry_attempt = RuntimeSessionService.start_node_attempt_sync(
                                db,
                                runtime_session,
                                node_key="script",
                                trigger_reason=retry_trigger_reason,
                                requested_by=script_requested_by,
                                input_contract={"stage": "script", "workflow_state_id": wf_id},
                                task=task,
                                progress_step="Generating script",
                                progress_percentage=15,
                            )
                            script_attempt_id = retry_attempt.id
                        agent_input = await self._prepare_agent_context(
                            workflow_data,
                            agent_type,
                            wf_id,
                            runtime_input_payload=runtime_input_payload,
                        )
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
                        if (
                            runtime_session is not None
                            and agent_type == AgentType.SCRIPT_WRITER
                            and script_attempt_id is not None
                        ):
                            retry_trigger_reason = (
                                script_trigger_reason
                                if script_trigger_reason in {"revise", "replan"}
                                else "retry"
                            )
                            return self._open_script_review_gate(
                                runtime_session=runtime_session,
                                task=task,
                                db=db,
                                workflow_id=wf_id,
                                script_attempt_id=script_attempt_id,
                                trigger_reason=retry_trigger_reason,
                                script_output=dict(agent_output or {}),
                            )
                        continue

                    # 不重试：标记失败并通知
                    raise AgentError(error_msg) from e
            
            # Workflow completed successfully
            await self._update_progress(90, "Workflow completed, dispatching completion event", db)
            
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

            task.status = TaskStatus.COMPLETED
            task.update_progress("Completed", 100)

            completion_payload = await self._workflow_completion_adapter.publish_completed(
                task=task,
                workflow_id=wf_id,
                results=workflow_results,
                quality_score=workflow_results.get("quality_checker", {}).get("quality_score"),
            )
            if runtime_session is not None:
                RuntimeSessionService.mark_session_completed_sync(
                    db,
                    runtime_session,
                    task=task,
                    summary_output={
                        "status": "completed",
                        "final_video_url": completion_payload.get("final_video_url") or final_url,
                        "quality_score": workflow_results.get("quality_checker", {}).get("quality_score"),
                    },
                )
            
            self.logger.info(f"🎉 工作流完成，任务ID: {task.task_id}")
            
            return {
                "status": "completed",
                "total_steps": total_steps,
                "results": workflow_results,
                "final_video_url": completion_payload.get("final_video_url") or final_url,
                "quality_score": workflow_results.get("quality_checker", {}).get("quality_score"),
                "persistence_status": "deferred",
                "workflow_state_id": wf_id
            }
            
        except Exception as e:
            # Workflow failed
            error_msg = f"Workflow failed: {str(e)}"

            try:
                await self._workflow_completion_adapter.publish_failed(
                    task=task,
                    workflow_id=wf_id,
                    error_message=error_msg,
                )
            except Exception as evt_err:
                self.logger.warning("Failed to publish workflow_failed event: %s", evt_err)
            if runtime_session is not None and runtime_session.status != WorkflowSessionStatus.FAILED.value:
                RuntimeSessionService.mark_session_failed_sync(
                    db,
                    runtime_session,
                    error_message=error_msg,
                    task=task,
                )
            
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

    async def _decide_next_step_llm(self, current_agent: AgentType, workflow_id: str) -> str:
        """Use a lightweight LLM + orchestrator_control tool to decide next step.
        Returns: 'proceed_next' | 'repeat_agent' | 'halt_workflow'
        """
        # Build observation (concise, facts-only) from MAS WM (SoT)
        try:
            from .adapters.state.agent_outputs import assess_agent_delivery
            from .adapters.state.mas_state import build_mas_state_view

            delivery = assess_agent_delivery(str(workflow_id), current_agent, service=self.short_term_service)
            facts_summary = build_mas_state_view(str(workflow_id), service=self.short_term_service)
        except Exception:
            delivery = {}
            facts_summary = {}

        meta = {"workflow_id": str(workflow_id), "facts_summary": facts_summary}
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
    
    # WorkflowStatus 已移除；active-path live status now comes from runtime view only.
    
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

    def _build_execution_queue(
        self,
        task_specs: Dict[AgentType, Dict[str, Any]],
        *,
        candidate_agents: Optional[List[AgentType]] = None,
    ) -> List[AgentType]:
        return OrchestrationQueuePolicy.build_execution_queue(
            task_specs=task_specs,
            candidate_agents=candidate_agents,
        )

    def _build_standby_agents(
        self,
        task_specs: Dict[AgentType, Dict[str, Any]],
        *,
        candidate_agents: Optional[List[AgentType]] = None,
    ) -> List[AgentType]:
        return OrchestrationQueuePolicy.build_standby_agents(
            task_specs=task_specs,
            candidate_agents=candidate_agents,
        )

    @staticmethod
    def _current_execution_id() -> Optional[str]:
        try:
            exec_state = execution_context_var.get()
            return getattr(exec_state, "id", None) if exec_state else None
        except Exception:
            return None

    async def _evaluate_runtime_boundary_cycle(
        self,
        *,
        workflow_state_id: str,
        current_agent: AgentType,
        agent_output: Dict[str, Any],
        audio_contract: Dict[str, Any],
        candidate_agents: List[AgentType],
        standby_agents: List[AgentType],
        replan_count: int,
        max_replans: int,
        current_index: int,
        execution_queue: List[AgentType],
        task_specs: Dict[AgentType, Dict[str, Any]],
        conditional_task_specs: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        try:
            execution_id = self._current_execution_id()
            report = self._orchestration_protocol.build_subagent_report(
                workflow_state_id=workflow_state_id,
                agent_type=current_agent,
                agent_output=agent_output,
                execution_id=execution_id,
            )
            control_plane = self._get_orchestration_control_plane()
            decision_request = control_plane.open_runtime_decision(
                workflow_state_id=workflow_state_id,
                current_agent=current_agent,
                standby_agents=standby_agents,
                report=report,
                audio_contract=dict(audio_contract or {}),
                replan_count=replan_count,
                max_replans=max_replans,
                execution_id=execution_id,
            )
            if not isinstance(decision_request, dict) or not decision_request:
                raise OrchestrationControlPlaneError(
                    "open_runtime_decision must return explicit envelope"
                )
            request_status = str(decision_request.get("status") or "").strip()
            if request_status == "no_gate":
                return {
                    "runtime_decision": {},
                    "apply_result": dict(decision_request.get("apply_result") or {}),
                    "decision_ack": dict(decision_request.get("decision_ack") or {}),
                }
            if request_status != "ready":
                raise OrchestrationControlPlaneError(
                    f"Unsupported runtime decision envelope status: {request_status or '<empty>'}"
                )
            payload = decision_request.get("decision_request")
            if not isinstance(payload, dict) or not payload:
                raise OrchestrationControlPlaneError(
                    "ready runtime decision envelope missing decision_request"
                )
            runtime_decision = await self._llm_decide_runtime_decision(
                workflow_state_id=workflow_state_id,
                current_agent=current_agent,
                standby_agents=standby_agents,
                report=payload.get("report") or {},
                gate_events=payload.get("gate_events") or [],
                replan_count=replan_count,
                max_replans=max_replans,
            )
            apply_response = control_plane.apply_runtime_decision(
                workflow_state_id=workflow_state_id,
                current_agent=current_agent,
                current_index=current_index,
                runtime_decision=runtime_decision,
                execution_queue=execution_queue,
                task_specs=task_specs,
                candidate_agents=list(candidate_agents),
                conditional_task_specs=conditional_task_specs,
                standby_agents=standby_agents,
                replan_count=replan_count,
            )
            apply_result = apply_response.get("apply_result") or {}
            decision_ack = apply_response.get("decision_ack") or {}
            return {
                "runtime_decision": runtime_decision,
                "apply_result": apply_result,
                "decision_ack": decision_ack,
            }
        except OrchestrationProtocolError as exc:
            raise AgentError(f"Runtime protocol violated: {exc}") from exc
        except (OrchestrationControlPlaneError, OrchestrationRuntimeControllerError) as exc:
            raise AgentError(f"Runtime control-plane violated: {exc}") from exc

    @staticmethod
    def _deserialize_agent_pool(raw_pool: Any) -> List[AgentType]:
        parsed: List[AgentType] = []
        if not isinstance(raw_pool, list):
            return parsed
        for item in raw_pool:
            try:
                parsed.append(AgentType(str(item)))
            except Exception:
                continue
        return parsed

    async def _llm_decide_runtime_decision(
        self,
        *,
        workflow_state_id: str,
        current_agent: AgentType,
        standby_agents: List[AgentType],
        report: Dict[str, Any],
        gate_events: List[Dict[str, Any]],
        replan_count: int,
        max_replans: int,
    ) -> Dict[str, Any]:
        if not gate_events:
            return {"action": "continue", "reason": "no_runtime_gate_event", "facts": {"report": report or {}}}
        if not standby_agents:
            return {
                "action": "continue",
                "reason": "standby_pool_empty",
                "facts": {
                    "report": report or {},
                    "gate_events": list(gate_events or []),
                },
            }

        llm = self.get_llm("plan")
        messages = [
            {
                "role": "system",
                "content": (
                    "你是多智能体编排器的运行时调整决策器。"
                    "必须仅输出 JSON，对当前子智能体回报和节点边界 gate 结果做下一步决策。"
                    "允许动作只有：continue、activate_from_standby、abort。"
                    "如果选择 activate_from_standby，target_agent 必须来自 standby_candidates。"
                    "不要发明新的 agent，也不要输出工具调用。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "workflow_id": str(workflow_state_id or ""),
                        "current_agent": current_agent.value,
                        "report": dict(report or {}),
                        "standby_candidates": [agent.value for agent in standby_agents],
                        "gate_events": list(gate_events or []),
                        "replan_budget": {
                            "used": int(replan_count),
                            "max": int(max_replans),
                        },
                    },
                    ensure_ascii=False,
                ),
            },
        ]
        try:
            response = await llm.chat_completion(
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=getattr(settings, "LLM_MAX_TOKENS_STANDARD", 1024),
            )
            data = json.loads((response.get("content") or "{}").strip() or "{}")
        except Exception as exc:
            raise AgentError(f"Runtime replan LLM decision failed: {exc}") from exc

        action_raw = data.get("action")
        if not isinstance(action_raw, str) or not action_raw.strip():
            raise AgentError("Runtime replan missing action")
        action = action_raw.strip().lower()
        reason = str(data.get("reason") or data.get("rationale") or "llm_runtime_replan").strip()
        target_raw = str(data.get("target_agent") or "").strip()
        allowed_targets = {agent.value: agent for agent in standby_agents}

        if action not in {"continue", "activate_from_standby", "abort"}:
            raise AgentError(f"Runtime replan returned invalid action: {action}")

        if action == "activate_from_standby":
            target_agent = allowed_targets.get(target_raw)
            if target_agent is None:
                raise AgentError(
                    f"Runtime replan returned invalid target_agent: {target_raw or '<empty>'}"
                )
            if replan_count >= max(0, int(max_replans)):
                return {
                    "action": "abort",
                    "reason": "replan_budget_exhausted",
                    "facts": {
                        "report": report,
                        "gate_events": gate_events,
                        "llm_output": data,
                    },
                }
            return {
                "action": "activate_from_standby",
                "target_agent": target_agent,
                "reason": reason or "llm_runtime_replan_activation",
                "facts": {
                    "report": report,
                    "gate_events": gate_events,
                    "llm_output": data,
                },
            }

        if action == "abort":
            return {
                "action": "abort",
                "reason": reason or "llm_runtime_replan_abort",
                "facts": {
                    "report": report,
                    "gate_events": gate_events,
                    "llm_output": data,
                },
            }

        return {
            "action": "continue",
            "reason": reason or "llm_runtime_replan_continue",
            "facts": {
                "report": report,
                "gate_events": gate_events,
                "llm_output": data,
            },
        }

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

    def _emit_pre_dispatch_diagnostics(self, agent_type: AgentType, workflow_state_id: str) -> None:
        if agent_type == AgentType.AUDIO_GENERATOR:
            try:
                contract = read_shared_fact(
                    workflow_state_id,
                    "workflow.contract.audio",
                    {},
                    service=self.short_term_service,
                ) or {}
                self.logger.info(
                    "AUDIO_AGENT_DISPATCH: workflow_id=%s policy=%s allow_silence=%s need_global_bgm=%s need_voiceover=%s",
                    workflow_state_id,
                    contract.get("policy") if isinstance(contract, dict) else None,
                    bool((contract or {}).get("allow_silence")) if isinstance(contract, dict) else None,
                    bool((contract or {}).get("need_global_bgm")) if isinstance(contract, dict) else None,
                    bool((contract or {}).get("need_voiceover")) if isinstance(contract, dict) else None,
                )
                self._last_audio_route_payload = {}
            except Exception as route_err:
                self.logger.warning("AUDIO_ORCHESTRATION diagnostics failed: %s", route_err)

    async def _prepare_agent_context(
        self,
        workflow_data: Dict[str, Any],
        agent_type: AgentType,
        workflow_id: str,
        *,
        runtime_input_payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
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
            boundary_context = self._get_context_contract_assembler().assemble_agent_context(
                agent_type=agent_type,
                workflow_state_id=workflow_id,
                workflow_data=workflow_data,
                runtime_input_payload=runtime_input_payload,
            )
            if isinstance(boundary_context, dict):
                assembler_diagnostics = boundary_context.pop("_assembler_diagnostics", None)
                if isinstance(assembler_diagnostics, dict):
                    for name, receipt in assembler_diagnostics.items():
                        if not isinstance(receipt, dict):
                            continue
                        status = str(receipt.get("status") or "").strip().lower()
                        if status and status != "resolved":
                            self.logger.warning(
                                "Boundary assembly fallback for %s on %s: %s",
                                agent_type.value,
                                name,
                                receipt,
                            )
                for key, value in boundary_context.items():
                    if value:
                        agent_input[key] = value

            if agent_type in [AgentType.IMAGE_GENERATOR, AgentType.VIDEO_GENERATOR, AgentType.AUDIO_GENERATOR]:
                overall_guidance = workflow_data.get("creative_guidance")
                if overall_guidance:
                    agent_input["creative_guidance"] = overall_guidance
                scene_guidances = workflow_data.get("scene_guidances")
                if scene_guidances:
                    agent_input["scene_guidances"] = scene_guidances

            return agent_input

        except AgentError:
            raise
        except Exception as e:
            self.logger.error(
                "❌ Failed to prepare agent context for %s: %s",
                agent_type.value,
                e,
            )
            raise AgentError(
                f"Failed to prepare agent context for {agent_type.value}: {e}"
            ) from e

    async def _llm_decompose_tasks(
        self,
        workflow_data: Dict[str, Any],
        workflow_id: str,
        candidate_agents: List[AgentType],
    ) -> Tuple[Dict[AgentType, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
        """LLM 生成 per-agent assignment contract，缺失 expected coverage 时显式失败。"""
        try:
            if not isinstance(candidate_agents, list) or not candidate_agents:
                raise ValueError("LLM task decomposition requires explicit candidate_agents")
            user_prompt = workflow_data.get("user_prompt") or workflow_data.get("prompt") or ""
            page_params = {
                "duration": workflow_data.get("duration"),
                "resolution": workflow_data.get("resolution"),
                "target_resolution": workflow_data.get("target_resolution"),
            }
            available_agents = [atype.value for atype in candidate_agents if isinstance(atype, AgentType)]
            pm = self.prompt_manager
            try:
                agent_sys = self.get_system_instructions() or {}
                pr = agent_sys.get("primary_role") or "工作流编排器"
            except Exception:
                pr = "工作流编排器"
            system_text = pm.render_template(
                "agents/orchestrator",
                "decomposition_system",
                variables={"primary_role": pr},
                use_cache=True,
                auto_reload=False,
            )
            user_text = pm.render_template(
                "agents/orchestrator",
                "decomposition_user",
                variables={
                    "user_prompt": str(user_prompt),
                    "page_params_json": json.dumps(page_params, ensure_ascii=False),
                    "candidate_agents_json": json.dumps(available_agents, ensure_ascii=False),
                    "agent_catalog_json": json.dumps(
                        self._planning_agent_catalog(), ensure_ascii=False
                    ),
                    "runtime_constraints_json": json.dumps(
                        {
                            "audio_contract": workflow_data.get("audio_contract") or {},
                            "audio_capability": workflow_data.get("audio_capability") or {},
                            "task_traits": self._extract_planning_task_traits(workflow_data),
                            "workflow_state_id": workflow_id,
                        },
                        ensure_ascii=False,
                    ),
                },
                use_cache=True,
                auto_reload=False,
            )
            llm = self.get_llm("plan")
            resp = await llm.chat_completion(
                messages=[
                    {"role": "system", "content": system_text},
                    {"role": "user", "content": user_text},
                ],
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
            expected_agents = [
                atype
                for atype in list(candidate_agents)
                if isinstance(atype, AgentType)
            ]
            expected_agent_set = set(expected_agents)
            unexpected_agents: List[str] = []
            if isinstance(agents, list):
                for item in agents:
                    if not isinstance(item, dict):
                        continue
                    atype = self._parse_agent_type(item.get("agent"))
                    if atype is None:
                        continue
                    if atype not in expected_agent_set:
                        unexpected_agents.append(atype.value)
                        continue
                    run_flag = item.get("run")
                    mission = str(item.get("mission") or "").strip()
                    deliverable = str(item.get("deliverable") or "").strip()
                    if not mission:
                        raise ValueError(
                            f"LLM task decomposition missing mission for agent: {atype.value}"
                        )
                    if not deliverable:
                        raise ValueError(
                            f"LLM task decomposition missing deliverable for agent: {atype.value}"
                        )
                    spec = {
                        "agent": atype.value,
                        "mission": mission,
                        "deliverable": deliverable,
                        "constraints": self._normalize_assignment_constraints(
                            item.get("constraints")
                        ),
                        "order": item.get("order"),
                        "runtime_hints": self._normalize_runtime_hints(
                            item.get("runtime_hints")
                        ),
                        "run": bool(run_flag) if run_flag is not None else True,
                        "fallback_used": False,
                    }
                    task_map[atype] = spec
            if unexpected_agents:
                raise ValueError(
                    "LLM task decomposition returned task_specs for non-candidate agents: "
                    + ", ".join(sorted(set(unexpected_agents)))
                )
            missing_agents = [
                atype.value for atype in expected_agents if not isinstance(task_map.get(atype), dict)
            ]
            if missing_agents:
                raise ValueError(
                    "LLM task decomposition missing task_specs for agents: "
                    + ", ".join(missing_agents)
                )
            conditional_tasks = data.get("conditional_tasks") if isinstance(data, dict) else None
            if conditional_tasks is not None and not isinstance(conditional_tasks, list):
                raise ValueError("LLM task decomposition conditional_tasks must be list when provided")
            for item in conditional_tasks or []:
                if not isinstance(item, dict):
                    continue
                task_id = str(item.get("task_id") or "").strip()
                if not task_id:
                    continue
                atype = self._parse_agent_type(item.get("agent"))
                if atype is None:
                    continue
                if atype not in expected_agent_set:
                    raise ValueError(
                        "LLM task decomposition returned conditional_task for non-candidate agent: "
                        f"{atype.value}"
                    )
                mission = str(item.get("mission") or "").strip()
                deliverable = str(item.get("deliverable") or "").strip()
                if not mission:
                    raise ValueError(
                        f"LLM task decomposition missing mission for conditional task: {task_id}"
                    )
                if not deliverable:
                    raise ValueError(
                        f"LLM task decomposition missing deliverable for conditional task: {task_id}"
                    )
                spec = {
                    "agent": atype.value,
                    "mission": mission,
                    "deliverable": deliverable,
                    "constraints": self._normalize_assignment_constraints(
                        item.get("constraints")
                    ),
                    "trigger": item.get("trigger"),
                    "runtime_hints": self._normalize_runtime_hints(
                        item.get("runtime_hints")
                    ),
                    "fallback_used": False,
                }
                conditional_task_specs[task_id] = spec
            return task_map, conditional_task_specs
        except Exception as e:
            try:
                self.logger.error("LLM task decomposition failed: %s (required)", e)
            except Exception:
                pass
            raise AgentError(f"LLM task decomposition is required but failed: {e}") from e
