"""
Orchestrator Agent - Coordinates the entire video generation workflow.
"""
import asyncio
import json
import logging
import os
import uuid
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..core.config import settings
from ..core.prompt_manager import get_prompt_manager
from ..core.video_config_manager import get_video_config
from ..domain import (
    AgentExecutionRequest,
    AgentExecutionResult,
    AgentTaskReference,
    AgentType,
    JsonObjectPayload,
    WorkflowNodeStatus,
    WorkflowSessionStatus,
)
from ..events.execution import execution_context_var
from ..services.audio_delivery_gate_evaluator import AudioDeliveryGateEvaluator
from ..services.context_assembler import ContextContractAssembler
from ..services.context_reference_ports import (
    SceneInfoReferencePreparationError,
    SceneInfoReferencePreparationPort,
)
from ..services.execution_host_lease import (
    activate_current_attempt_keepalive,
    deactivate_current_attempt_keepalive,
)
from ..services.memory_provider import MemoryServices
from ..services.orchestration_control_plane import (
    OrchestrationControlPlane,
    OrchestrationControlPlaneError,
)
from ..services.orchestration_observation_adapter import OrchestrationObservationAdapter
from ..services.orchestration_protocol import OrchestrationProtocol, OrchestrationProtocolError
from ..services.orchestration_queue_policy import OrchestrationQueuePolicy
from ..services.orchestration_runtime_controller import (
    OrchestrationRuntimeController,
    OrchestrationRuntimeControllerError,
)
from ..services.orchestration_runtime_decision import RuntimeAction, RuntimeDecision
from ..services.orchestration_runtime_ports import (
    OrchestrationRuntimeResumeBootstrapError,
    OrchestrationRuntimeResumePort,
    OrchestrationRuntimeTransitionPort,
)
from ..services.orchestration_state_adapter import OrchestrationStateAdapter
from ..services.published_deliverable_service import get_published_deliverable_ref
from ..services.script_review_contract import get_script_review_contract
from ..services.video_composer_execution_contract import build_video_composer_execution_contract
from ..services.video_execution_contract import build_video_generation_execution_contract
from ..services.video_metadata_service import (
    merge_video_metadata,
    normalize_video_metadata,
    probe_local_video_metadata_sync,
)
from ..services.workflow_completion_adapter import WorkflowCompletionAdapter
from .audio_generator import AudioGeneratorAgent
from .base import AgentError, BaseAgent
from .concept_planner import ConceptPlannerAgent
from .image_generator import ImageGeneratorAgent
from .quality_checker import QualityCheckerAgent
from .script_writer import ScriptWriterAgent
from .tools.tool_registry import get_tool_registry
from .utils.artifacts import evaluate_scene_output_acceptance
from .utils.media_runtime import build_local_public_url

# legacy WM singleton removed - use injected self._memory_services.short_term
from .utils.memory_helpers import (
    agent_scope,
    get_mas_working_memory,
    mas_scope,
    read_shared_fact,
    write_shared_fact,
)
from .video_composer import VideoComposerAgent
from .video_generator import VideoGeneratorAgent
from .voice_synthesizer import VoiceSynthesizerAgent


@dataclass(frozen=True)
class _RuntimeSuccessBoundaryOutcome:
    standby_agents: Tuple[AgentType, ...]
    replan_count: int
    gate_response: Optional[Dict[str, Any]] = None
    attempt_completion_required: bool = False
    attempt_completed: bool = False
    output_accepted: bool = True
    attempt_abandoned: bool = False


class _OrchestrationBoundaryError(AgentError):
    """Typed orchestration failure retained through runtime diagnostics."""

    def __init__(self, message: str, *, reason_code: str) -> None:
        self.reason_code = str(reason_code)
        super().__init__(message)


class _RuntimeRetryRequested(_OrchestrationBoundaryError):
    """The runtime disposition explicitly selected another attempt."""

    def __init__(self, message: str, *, replan_count: int) -> None:
        if type(replan_count) is not int or replan_count < 0:
            raise ValueError("replan_count must be a non-negative integer")
        self.replan_count = replan_count
        super().__init__(message, reason_code="runtime_retry_requested")


class OrchestratorAgent(BaseAgent):
    """
    Orchestrator Agent manages the complete video generation workflow
    by coordinating all specialized agents in the correct order
    """

    _PLANNING_RUNTIME_IDENTITY_KEYS = {
        "workflow_state_id",
        "workflow_id",
        "task_id",
        "runtime_session_id",
        "session_id",
        "attempt_id",
        "lease_token",
    }

    AGENT_EXECUTION_MODE = "mas_control_plane"

    def __init__(
        self,
        memory_services: Optional[MemoryServices] = None,
        *,
        runtime_transition_port: OrchestrationRuntimeTransitionPort,
        runtime_resume_port: OrchestrationRuntimeResumePort,
        scene_info_reference_port: SceneInfoReferencePreparationPort,
    ):
        import os

        from .utils.llm_policy import LLMPolicyManager

        policy_file = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "config", "llm_policies.yaml"
        )
        self._llm_policy = LLMPolicyManager(policy_file)
        if memory_services is None:
            raise ValueError("memory_services is required for OrchestratorAgent")
        self._memory_services = memory_services
        self._runtime_transition_port = runtime_transition_port
        self._runtime_resume_port = runtime_resume_port
        self._scene_info_reference_port = scene_info_reference_port
        self._audio_delivery_gate = AudioDeliveryGateEvaluator(
            memory_services=self._memory_services
        )
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
            timeout_seconds=getattr(settings, "ORCHESTRATOR_TIMEOUT_SECONDS", 1800),
            max_retries=1,
            llms=self._llm_policy.build_llms_for_agent("orchestrator"),
            memory_services=self._memory_services,
        )

        # Initialize all specialized agents
        self.agents = {
            AgentType.CONCEPT_PLANNER: ConceptPlannerAgent(
                llms=self._llm_policy.build_llms_for_agent("concept_planner"),
                memory_services=self._memory_services,
            ),
            AgentType.SCRIPT_WRITER: ScriptWriterAgent(
                llms=self._llm_policy.build_llms_for_agent("script_writer"),
                memory_services=self._memory_services,
            ),
            AgentType.VOICE_SYNTHESIZER: VoiceSynthesizerAgent(
                llms=self._llm_policy.build_llms_for_agent("voice_synthesizer"),
                memory_services=self._memory_services,
            ),
            AgentType.IMAGE_GENERATOR: ImageGeneratorAgent(
                llms=self._llm_policy.build_llms_for_agent("image_generator"),
                memory_services=self._memory_services,
            ),
            AgentType.VIDEO_GENERATOR: VideoGeneratorAgent(
                llms=self._llm_policy.build_llms_for_agent("video_generator"),
                memory_services=self._memory_services,
            ),
            AgentType.AUDIO_GENERATOR: AudioGeneratorAgent(
                llms=self._llm_policy.build_llms_for_agent("audio_generator"),
                memory_services=self._memory_services,
            ),
            AgentType.VIDEO_COMPOSER: VideoComposerAgent(
                llms=self._llm_policy.build_llms_for_agent("video_composer"),
                memory_services=self._memory_services,
            ),
            AgentType.QUALITY_CHECKER: QualityCheckerAgent(
                llms=self._llm_policy.build_llms_for_agent("quality_checker"),
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
                        provider = getattr(
                            handle._service, "get_provider_name", lambda: "unknown"
                        )()
                        model = getattr(handle, "_model", None) or "default"
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
    def _parse_agent_type(value: Any) -> Optional[AgentType]:
        if isinstance(value, AgentType):
            return value
        if not isinstance(value, str):
            return None
        try:
            return AgentType(value)
        except ValueError:
            return None

    def _registered_agents(self) -> List[AgentType]:
        agents = getattr(self, "agents", {}) or {}
        return [agent_type for agent_type in agents.keys() if isinstance(agent_type, AgentType)]

    @staticmethod
    def _agent_requires_approved_script_input(agent_type: AgentType) -> bool:
        return OrchestrationQueuePolicy.requires_approved_script_input(agent_type)

    @staticmethod
    def _has_approved_script_runtime_input(runtime_input_payload: Optional[Dict[str, Any]]) -> bool:
        ref = get_published_deliverable_ref(runtime_input_payload, node_key="script")
        return isinstance(ref, dict) and ref.get("is_approved") is True

    def _ensure_dispatch_prerequisites(
        self,
        *,
        agent_type: AgentType,
        workflow_state_id: str,
        runtime_input_payload: Optional[Dict[str, Any]],
    ) -> None:
        if not self._agent_requires_approved_script_input(agent_type):
            return
        if self._has_approved_script_runtime_input(runtime_input_payload):
            return
        raise AgentError(
            "Script prerequisite not satisfied for dispatch: "
            f"workflow_id={workflow_state_id} agent={agent_type.value} "
            "status=script_prerequisite_not_satisfied"
        )

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

    @classmethod
    def _sanitize_planning_audio_contract(cls, value: Any) -> Dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        return {
            key: item
            for key, item in dict(value).items()
            if key not in cls._PLANNING_RUNTIME_IDENTITY_KEYS
        }

    @staticmethod
    def _normalize_runtime_hints(value: Any) -> Dict[str, Any]:
        return dict(value) if isinstance(value, dict) else {}

    @classmethod
    def _resolve_task_runtime_hints(cls, task_spec: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not isinstance(task_spec, dict):
            return {}
        return cls._normalize_runtime_hints(task_spec.get("runtime_hints"))

    @staticmethod
    def _build_agent_execution_contract(
        *,
        agent_type: AgentType,
        workflow_state_id: str,
        runtime_hints: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if agent_type == AgentType.VIDEO_GENERATOR:
            generate_audio = None
            if isinstance(runtime_hints, dict) and "generate_audio" in runtime_hints:
                candidate = runtime_hints.get("generate_audio")
                if type(candidate) is not bool:
                    raise AgentError("video_generator runtime_hints.generate_audio must be boolean")
                generate_audio = candidate
            return build_video_generation_execution_contract(
                workflow_state_id=workflow_state_id,
                generate_audio=generate_audio,
            )

        if agent_type == AgentType.VIDEO_COMPOSER:
            try:
                if isinstance(runtime_hints, dict):
                    legacy_keys = [
                        key
                        for key in ("add_bgm", "add_voiceover", "compose_requested")
                        if runtime_hints.get(key) is not None
                    ]
                    if legacy_keys:
                        raise AgentError(
                            "Legacy video_composer runtime overrides are no longer supported; "
                            f"use compose_mode instead (got: {', '.join(legacy_keys)})"
                        )
                compose_mode = "compose"
                if (
                    isinstance(runtime_hints, dict)
                    and runtime_hints.get("compose_mode") is not None
                ):
                    compose_mode = runtime_hints.get("compose_mode")
                return build_video_composer_execution_contract(
                    workflow_state_id=workflow_state_id,
                    compose_mode=compose_mode,
                )
            except ValueError as exc:
                raise AgentError(f"Invalid video_composer execution boundary: {exc}") from exc

        return {}

    @staticmethod
    def _build_task_assignment(
        *,
        agent_type: AgentType,
        task_specs: Dict[AgentType, Dict[str, Any]],
    ) -> Dict[str, Any]:
        task_spec = task_specs.get(agent_type) if isinstance(task_specs, dict) else None
        if not isinstance(task_spec, dict):
            raise AgentError(f"Missing task_spec for scheduled agent: {agent_type.value}")
        return dict(task_spec)

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

    def _get_orchestration_runtime_transition_facade(
        self,
    ) -> OrchestrationRuntimeTransitionPort:
        port = getattr(self, "_runtime_transition_port", None) or getattr(
            self,
            "_orchestration_runtime_transition_facade",
            None,
        )
        if port is None:
            raise AgentError("runtime_transition_port is required")
        return port

    def _get_orchestration_runtime_resume_bootstrap_facade(
        self,
    ) -> OrchestrationRuntimeResumePort:
        port = getattr(self, "_runtime_resume_port", None) or getattr(
            self,
            "_orchestration_runtime_resume_bootstrap_facade",
            None,
        )
        if port is None:
            raise AgentError("runtime_resume_port is required")
        return port

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
        pm = getattr(self, "prompt_manager", None) or get_prompt_manager()
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
                        "audio_contract": self._sanitize_planning_audio_contract(
                            workflow_data.get("audio_contract")
                        ),
                        "audio_capability": workflow_data.get("audio_capability") or {},
                    },
                    ensure_ascii=False,
                ),
            },
            use_cache=True,
            auto_reload=False,
        )
        try:
            self.logger.info(
                "ORCH_PLAN_CANDIDATE_INPUT workflow=%s system=%s user=%s",
                workflow_id,
                system_text,
                user_text,
            )
        except Exception:
            pass
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
            self.logger.info(
                "ORCH_PLAN_CANDIDATE_OUTPUT_RAW workflow=%s content=%s",
                workflow_id,
                content,
            )
        except Exception:
            pass

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
                "LLM candidate selection returned unknown agents: " + ", ".join(unknown_agents)
            )
        if not candidate_agents:
            raise AgentError("LLM candidate selection produced no valid candidate agents")
        rationale = (
            str(data.get("selection_rationale") or "").strip() if isinstance(data, dict) else ""
        )
        try:
            self.logger.info(
                "ORCH_PLAN_CANDIDATE_OUTPUT_NORMALIZED workflow=%s candidate_agents=%s rationale=%s",
                workflow_id,
                json.dumps([agent.value for agent in candidate_agents], ensure_ascii=False),
                rationale,
            )
        except Exception:
            pass
        return candidate_agents, rationale

    async def _execute_impl(
        self,
        request: AgentExecutionRequest,
    ) -> Dict[str, Any]:
        """Execute the complete video generation workflow using Shared Working Memory"""

        task = request.task
        input_data = request.input_data.to_dict()
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
        except AgentError:
            raise
        except Exception as route_err:
            raise AgentError(
                f"Failed to initialize orchestration context: {route_err}"
            ) from route_err

        runtime_resume_bootstrap = self._get_orchestration_runtime_resume_bootstrap_facade()
        try:
            runtime_resume_context = runtime_resume_bootstrap.resolve_runtime_resume_context(
                task=task,
            )
        except OrchestrationRuntimeResumeBootstrapError as exc:
            raise AgentError(str(exc)) from exc
        runtime_session_id = runtime_resume_context.runtime_session_id
        runtime_session_status = runtime_resume_context.runtime_session_status
        script_gate_id = runtime_resume_context.script_gate_id
        script_resume_action = runtime_resume_context.script_resume_action
        if script_gate_id is not None and not runtime_resume_context.latest_script_decision_exists:
            return {
                "status": "waiting_gate",
                "session_id": runtime_session_id,
                "gate_id": script_gate_id,
                "node_key": "script",
            }

        runtime_input_payload = dict(runtime_resume_context.runtime_input_payload or {})
        workflow_data = runtime_input_payload.copy() if runtime_input_payload else input_data.copy()
        workflow_data.setdefault(
            "resolution", input_data.get("resolution") or settings.DEFAULT_VIDEO_RESOLUTION
        )
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
        review_contract = get_script_review_contract(runtime_input_payload)
        if (
            script_resume_action in {"revise", "replan"}
            and isinstance(review_contract, dict)
            and review_contract
        ):
            workflow_data["script_review_contract"] = dict(review_contract)
        else:
            workflow_data.pop("script_review_contract", None)

        runtime_resume_checkpoint = runtime_resume_context.runtime_resume_checkpoint
        resume_anchor_agent = runtime_resume_context.resume_anchor_agent

        workflow_results: Dict[str, Any] = {}
        if script_resume_action in {"approve", "revise"}:
            self.logger.info(
                "ORCH_PLAN_MODE workflow=%s mode=resume_script action=%s",
                wf_id,
                script_resume_action,
            )
            try:
                resume_bundle = runtime_resume_bootstrap.load_authoritative_resume_task_specs(
                    runtime_session_id=runtime_session_id,
                    resume_action=script_resume_action,
                )
            except OrchestrationRuntimeResumeBootstrapError as exc:
                raise AgentError(str(exc)) from exc
            task_specs = resume_bundle.task_specs
            _conditional_task_specs = resume_bundle.conditional_task_specs
            candidate_agents = resume_bundle.candidate_agents
            if script_resume_action == "approve":
                skip_agents.update({AgentType.CONCEPT_PLANNER, AgentType.SCRIPT_WRITER})
                runtime_resume_bootstrap.consume_script_approval_continuation(
                    runtime_session_id=runtime_session_id,
                    task=task,
                )
            else:
                try:
                    runtime_resume_bootstrap.project_script_revision_context(
                        runtime_session_id=runtime_session_id,
                        workflow_state_id=wf_id,
                        resume_action=script_resume_action,
                    )
                except OrchestrationRuntimeResumeBootstrapError as exc:
                    raise AgentError(str(exc)) from exc
                skip_agents.add(AgentType.CONCEPT_PLANNER)
            execution_queue = self._build_execution_queue(
                task_specs, candidate_agents=list(candidate_agents)
            )
            standby_agents = self._build_standby_agents(
                task_specs, candidate_agents=list(candidate_agents)
            )
        elif runtime_resume_checkpoint is not None:
            if resume_anchor_agent is None:
                raise AgentError(
                    "Runtime continuation checkpoint is missing a dispatchable agent anchor"
                )
            self.logger.info(
                "ORCH_PLAN_MODE workflow=%s mode=resume_checkpoint anchor=%s",
                wf_id,
                resume_anchor_agent.value if isinstance(resume_anchor_agent, AgentType) else "",
            )
            (
                task_specs,
                _conditional_task_specs,
                candidate_agents,
            ) = self._orchestration_state.checkpoint_to_task_specs(
                runtime_resume_checkpoint,
                require_decision_id=False,
            )
            execution_queue = self._build_execution_queue(
                task_specs, candidate_agents=list(candidate_agents)
            )
            if resume_anchor_agent not in execution_queue:
                raise AgentError(
                    f"Runtime continuation anchor {resume_anchor_agent.value} is not dispatchable from persisted task_specs"
                )
            execution_queue = execution_queue[execution_queue.index(resume_anchor_agent) :]
            standby_agents = self._build_standby_agents(
                task_specs, candidate_agents=list(candidate_agents)
            )
        else:
            self.logger.info("ORCH_PLAN_MODE workflow=%s mode=fresh", wf_id)
            candidate_agents, _selection_rationale = await self._llm_select_candidate_agents(
                workflow_data=workflow_data,
                workflow_id=wf_id,
            )

            # 任务分解（LLM → per-agent 指令），失败则回退
            task_specs, _conditional_task_specs = await self._llm_decompose_tasks(
                workflow_data,
                wf_id,
                candidate_agents=list(candidate_agents),
            )

            execution_queue = self._build_execution_queue(
                task_specs, candidate_agents=list(candidate_agents)
            )
            standby_agents = self._build_standby_agents(
                task_specs, candidate_agents=list(candidate_agents)
            )
        try:
            self.logger.info(
                "ORCH_PLAN_QUEUE workflow=%s candidate_agents=%s execution_queue=%s standby_agents=%s",
                wf_id,
                json.dumps([agent.value for agent in candidate_agents], ensure_ascii=False),
                json.dumps([agent.value for agent in execution_queue], ensure_ascii=False),
                json.dumps([agent.value for agent in standby_agents], ensure_ascii=False),
            )
        except Exception:
            pass
        replan_count = 0
        max_replans = int(getattr(settings, "ORCHESTRATOR_MAX_REPLAN_ACTIVATIONS", 2))
        total_steps = len(execution_queue)
        script_trigger_reason = (
            script_resume_action if script_resume_action in {"revise", "replan"} else "initial"
        )
        if runtime_resume_checkpoint is not None and resume_anchor_agent == AgentType.SCRIPT_WRITER:
            script_trigger_reason = "resume"
        script_requested_by = runtime_resume_context.latest_script_decision_actor_type or "system"
        current_runtime_node_key: Optional[str] = None
        current_attempt_id: Optional[int] = None
        current_attempt_trigger_reason = ""
        current_attempt_lease_token: Optional[str] = None
        current_attempt_keepalive_active = False

        def _build_execution_host_keepalive_diagnostic(
            *,
            node_key: str,
            attempt_id: int,
            state: str,
            reason_code: str,
            message: str,
        ) -> Dict[str, Any]:
            return {
                "code": "execution_host_keepalive",
                "node_key": str(node_key or "").strip() or None,
                "attempt_id": int(attempt_id),
                "state": str(state or "").strip().lower() or "failed",
                "reason_code": str(reason_code or "").strip().lower() or "unknown",
                "message": str(message or "").strip(),
                "captured_at": datetime.now(timezone.utc).isoformat(),
            }

        def _activate_runtime_attempt_keepalive_or_fail() -> bool:
            nonlocal current_runtime_node_key, current_attempt_id, current_attempt_lease_token

            if (
                current_runtime_node_key is None
                or current_attempt_id is None
                or current_attempt_lease_token is None
            ):
                raise AgentError("Runtime attempt bootstrap returned an incomplete lease scope")

            activated = activate_current_attempt_keepalive(
                runtime_session_id=runtime_session_id,
                attempt_id=current_attempt_id,
                lease_token=current_attempt_lease_token,
            )
            if activated:
                return True

            message = "Execution host keepalive unavailable for leased runtime attempt"
            try:
                self._get_orchestration_runtime_transition_facade().fail_runtime_attempt(
                    runtime_session_id=runtime_session_id,
                    node_key=current_runtime_node_key,
                    attempt_id=current_attempt_id,
                    error_message=message,
                    lease_token=current_attempt_lease_token,
                    diagnostics=[
                        _build_execution_host_keepalive_diagnostic(
                            node_key=current_runtime_node_key,
                            attempt_id=current_attempt_id,
                            state="activation_failed",
                            reason_code="keepalive_unavailable",
                            message=message,
                        )
                    ],
                )
            finally:
                current_runtime_node_key = None
                current_attempt_id = None
                current_attempt_lease_token = None

            raise AgentError(message)

        def _retire_runtime_attempt_scope(
            *,
            reason: str,
            preserve_completed_attempt: bool = False,
        ) -> Optional[Dict[str, Any]]:
            nonlocal current_runtime_node_key, current_attempt_id
            nonlocal current_attempt_trigger_reason, current_attempt_lease_token
            nonlocal current_attempt_keepalive_active

            retired_context: Optional[Dict[str, Any]] = None
            if (
                preserve_completed_attempt
                and current_runtime_node_key is not None
                and current_attempt_id is not None
            ):
                retired_context = {
                    "node_key": current_runtime_node_key,
                    "attempt_id": int(current_attempt_id),
                }
            if current_attempt_keepalive_active:
                deactivate_current_attempt_keepalive(reason=reason)
                current_attempt_keepalive_active = False
            current_runtime_node_key = None
            current_attempt_id = None
            current_attempt_trigger_reason = ""
            current_attempt_lease_token = None
            return retired_context

        try:
            for step_index, agent_type in enumerate(execution_queue):
                total_steps = max(len(execution_queue), 1)
                agent = self.agents[agent_type]
                current_runtime_node_key = None
                current_attempt_id = None
                current_attempt_trigger_reason = ""
                current_attempt_lease_token = None
                current_attempt_keepalive_active = False
                retired_completed_attempt_context: Optional[Dict[str, Any]] = None
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
                    spec_run = (
                        task_specs.get(agent_type, {}).get("run")
                        if isinstance(task_specs, dict)
                        else None
                    )
                    if spec_run is False:
                        self.logger.info(f"⏭️ Skipping {agent.agent_name} (directive run=false)")
                        continue
                except Exception:
                    pass

                if runtime_session_id is not None:
                    self._ensure_dispatch_prerequisites(
                        agent_type=agent_type,
                        workflow_state_id=wf_id,
                        runtime_input_payload=runtime_input_payload,
                    )

                self._emit_pre_dispatch_diagnostics(agent_type, wf_id)
                if runtime_session_id is not None:
                    try:
                        attempt_bootstrap = runtime_resume_bootstrap.start_runtime_attempt(
                            runtime_session_id=runtime_session_id,
                            task=task,
                            current_agent_type=agent_type,
                            workflow_state_id=wf_id,
                            task_specs=task_specs,
                            conditional_task_specs=_conditional_task_specs,
                            candidate_agents=list(candidate_agents),
                            script_trigger_reason=script_trigger_reason,
                            script_requested_by=script_requested_by,
                            resume_anchor_agent=resume_anchor_agent,
                        )
                    except OrchestrationRuntimeResumeBootstrapError as exc:
                        raise AgentError(str(exc)) from exc
                    current_runtime_node_key = attempt_bootstrap.node_key
                    current_attempt_id = attempt_bootstrap.attempt_id
                    current_attempt_trigger_reason = attempt_bootstrap.trigger_reason
                    current_attempt_lease_token = attempt_bootstrap.lease_token
                    current_attempt_keepalive_active = _activate_runtime_attempt_keepalive_or_fail()

                # Update progress
                progress_percentage = int((step_index / total_steps) * 90)  # 为持久化预留10%
                current_step = f"Executing {agent.agent_name}"

                await self._update_progress(progress_percentage, current_step)
                self.logger.info(
                    f"Starting workflow step {step_index + 1}/{total_steps}: {agent.agent_name}"
                )

                try:
                    # Prepare agent input with creative context (if available)
                    self.logger.info(f"🧠 DEBUG: Preparing context for {agent_type.value}")
                    agent_input = await self._prepare_scheduled_agent_input(
                        workflow_data=workflow_data,
                        agent_type=agent_type,
                        workflow_id=wf_id,
                        task_specs=task_specs,
                        runtime_input_payload=runtime_input_payload,
                    )

                    # Debug: Check if context contains creative guidance
                    if agent_type in [AgentType.IMAGE_GENERATOR, AgentType.VIDEO_GENERATOR]:
                        has_creative_guidance = "creative_guidance" in agent_input
                        scene_guidances_count = len(agent_input.get("scene_guidances", {}))
                        self.logger.info(
                            f"🧠 DEBUG: {agent_type.value} context - creative_guidance: {has_creative_guidance}, scene_guidances: {scene_guidances_count}"
                        )

                    # Hard gate: quality_checker requires a final video deliverable in MAS SoT.
                    if agent_type == AgentType.QUALITY_CHECKER:
                        try:
                            from .adapters.state.agent_outputs import assess_final_video_ready

                            delivery = assess_final_video_ready(
                                str(wf_id), service=self.short_term_service
                            )
                            if not delivery.get("ready"):
                                raise AgentError(
                                    "Cannot run quality_checker: project.final_video missing in MAS WM"
                                )
                        except AgentError:
                            raise
                        except Exception as err:
                            raise AgentError(
                                f"Cannot run quality_checker: final_video check failed: {err}"
                            ) from err

                    agent_output, success_boundary = await self._execute_agent_success_path(
                        agent=agent,
                        request=AgentExecutionRequest(
                            task=task,
                            agent_type=agent_type.value,
                            input_data=JsonObjectPayload.from_mapping(
                                agent_input,
                                field_path=f"agent_input.{agent_type.value}",
                            ),
                            workflow_state_id=wf_id,
                            execution_order=step_index + 1,
                        ),
                        workflow_state_id=wf_id,
                        workflow_results=workflow_results,
                        workflow_data=workflow_data,
                        current_agent=agent_type,
                        audio_contract=dict(audio_contract or {}),
                        candidate_agents=list(candidate_agents),
                        standby_agents=standby_agents,
                        replan_count=replan_count,
                        max_replans=max_replans,
                        current_index=step_index,
                        execution_queue=execution_queue,
                        task_specs=task_specs,
                        conditional_task_specs=_conditional_task_specs,
                        runtime_session_id=runtime_session_id,
                        runtime_node_key=current_runtime_node_key,
                        attempt_id=current_attempt_id,
                        lease_token=current_attempt_lease_token,
                        attempt_trigger_reason=current_attempt_trigger_reason,
                        script_trigger_reason=script_trigger_reason,
                    )
                    standby_agents = list(success_boundary.standby_agents)
                    replan_count = success_boundary.replan_count
                    if success_boundary.attempt_abandoned:
                        _retire_runtime_attempt_scope(reason="attempt_abandoned_for_replan")
                    if not success_boundary.output_accepted:
                        continue
                    if success_boundary.attempt_completed:
                        retired_completed_attempt_context = _retire_runtime_attempt_scope(
                            reason="attempt_completed",
                            preserve_completed_attempt=True,
                        )
                    if success_boundary.gate_response is not None:
                        return success_boundary.gate_response

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
                        bucket = (
                            shared.get(f"scene_outputs.{tracked_kind}", {})
                            if shared is not None
                            else {}
                        )
                        committed = len(bucket) if isinstance(bucket, dict) else 0
                        extra: Dict[str, Any] = {}
                        if tracked_kind == "audio":
                            try:
                                bgm = (
                                    shared.get("project.background_music", {})
                                    if shared is not None
                                    else {}
                                )
                                extra["project_background_music"] = bool(
                                    isinstance(bgm, dict)
                                    and (
                                        str(bgm.get("audio_path") or "").strip()
                                        or str(bgm.get("audio_url") or "").strip()
                                    )
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

                    self.logger.info(
                        f"Completed workflow step {step_index + 1}/{total_steps}: {agent.agent_name}"
                    )

                except Exception as e:
                    if (
                        runtime_session_id is not None
                        and current_runtime_node_key is not None
                        and current_attempt_id is not None
                    ):
                        stage_diagnostic = {
                            "code": f"{current_runtime_node_key}_stage_failed",
                            "stage": current_runtime_node_key,
                            "message": str(e),
                        }
                        failure_reason_code = str(getattr(e, "reason_code", None) or "").strip()
                        if failure_reason_code:
                            stage_diagnostic["reason_code"] = failure_reason_code
                        self._get_orchestration_runtime_transition_facade().fail_runtime_attempt(
                            runtime_session_id=runtime_session_id,
                            node_key=current_runtime_node_key,
                            attempt_id=current_attempt_id,
                            error_message=str(e),
                            lease_token=current_attempt_lease_token,
                            diagnostics=[stage_diagnostic],
                        )
                        _retire_runtime_attempt_scope(reason="attempt_failed")
                    elif (
                        runtime_session_id is not None
                        and retired_completed_attempt_context is not None
                    ):
                        try:
                            self._get_orchestration_runtime_transition_facade().upsert_runtime_attempt_diagnostic(
                                runtime_session_id=runtime_session_id,
                                attempt_id=int(retired_completed_attempt_context["attempt_id"]),
                                diagnostic={
                                    "code": f"{retired_completed_attempt_context['node_key']}_stage_failed",
                                    "attempt_id": int(
                                        retired_completed_attempt_context["attempt_id"]
                                    ),
                                    "stage": retired_completed_attempt_context["node_key"],
                                    "state": "post_completion_failure",
                                    "reason_code": "post_completion_control_plane_failure",
                                    "message": str(e),
                                },
                            )
                        except Exception as diag_err:
                            self.logger.warning(
                                "Failed to persist post-completion runtime diagnostic for session=%s attempt=%s: %s",
                                runtime_session_id,
                                retired_completed_attempt_context.get("attempt_id"),
                                diag_err,
                            )
                        finally:
                            retired_completed_attempt_context = None
                    error_msg = (
                        f"Workflow failed at step {step_index + 1} ({agent.agent_name}): {str(e)}"
                    )
                    self.logger.error(error_msg)

                    if isinstance(e, _RuntimeRetryRequested):
                        replan_count = e.replan_count
                        self.logger.info(f"Retrying step {step_index + 1}: {agent.agent_name}")
                        retry_trigger_reason = (
                            script_trigger_reason
                            if agent_type == AgentType.SCRIPT_WRITER
                            and script_trigger_reason in {"revise", "replan"}
                            else "retry"
                        )
                        if runtime_session_id is not None:
                            try:
                                attempt_bootstrap = runtime_resume_bootstrap.start_runtime_attempt(
                                    runtime_session_id=runtime_session_id,
                                    task=task,
                                    current_agent_type=agent_type,
                                    workflow_state_id=wf_id,
                                    task_specs=task_specs,
                                    conditional_task_specs=_conditional_task_specs,
                                    candidate_agents=list(candidate_agents),
                                    script_trigger_reason=script_trigger_reason,
                                    script_requested_by=script_requested_by,
                                    resume_anchor_agent=resume_anchor_agent,
                                    trigger_reason_override=retry_trigger_reason,
                                )
                            except OrchestrationRuntimeResumeBootstrapError as exc:
                                raise AgentError(str(exc)) from exc
                            current_runtime_node_key = attempt_bootstrap.node_key
                            current_attempt_id = attempt_bootstrap.attempt_id
                            current_attempt_trigger_reason = attempt_bootstrap.trigger_reason
                            current_attempt_lease_token = attempt_bootstrap.lease_token
                            current_attempt_keepalive_active = (
                                _activate_runtime_attempt_keepalive_or_fail()
                            )
                        try:
                            agent_input = await self._prepare_scheduled_agent_input(
                                workflow_data=workflow_data,
                                agent_type=agent_type,
                                workflow_id=wf_id,
                                task_specs=task_specs,
                                runtime_input_payload=runtime_input_payload,
                            )
                        except Exception as retry_input_err:
                            self._fail_retry_runtime_attempt(
                                runtime_session_id=runtime_session_id,
                                runtime_node_key=current_runtime_node_key,
                                attempt_id=current_attempt_id,
                                lease_token=current_attempt_lease_token,
                                error=retry_input_err,
                                diagnostic_code=(
                                    f"{current_runtime_node_key}_retry_input_failed"
                                    if current_runtime_node_key
                                    else "retry_input_failed"
                                ),
                            )
                            raise
                        agent_output, success_boundary = await self._execute_agent_success_path(
                            agent=agent,
                            request=AgentExecutionRequest(
                                task=task,
                                agent_type=agent_type.value,
                                input_data=JsonObjectPayload.from_mapping(
                                    agent_input,
                                    field_path=f"agent_input.{agent_type.value}",
                                ),
                                workflow_state_id=wf_id,
                                execution_order=step_index + 1,
                            ),
                            workflow_state_id=wf_id,
                            workflow_results=workflow_results,
                            workflow_data=workflow_data,
                            current_agent=agent_type,
                            audio_contract=dict(audio_contract or {}),
                            candidate_agents=list(candidate_agents),
                            standby_agents=standby_agents,
                            replan_count=replan_count,
                            max_replans=max_replans,
                            current_index=step_index,
                            execution_queue=execution_queue,
                            task_specs=task_specs,
                            conditional_task_specs=_conditional_task_specs,
                            runtime_session_id=runtime_session_id,
                            runtime_node_key=current_runtime_node_key,
                            attempt_id=current_attempt_id,
                            lease_token=current_attempt_lease_token,
                            attempt_trigger_reason=current_attempt_trigger_reason,
                            script_trigger_reason=retry_trigger_reason,
                            fail_runtime_attempt_on_error=True,
                        )
                        standby_agents = list(success_boundary.standby_agents)
                        replan_count = success_boundary.replan_count
                        if success_boundary.attempt_abandoned:
                            _retire_runtime_attempt_scope(
                                reason="retry_attempt_abandoned_for_replan"
                            )
                        if not success_boundary.output_accepted:
                            continue
                        if success_boundary.attempt_completed:
                            retired_completed_attempt_context = _retire_runtime_attempt_scope(
                                reason="retry_attempt_completed",
                                preserve_completed_attempt=True,
                            )
                        if success_boundary.gate_response is not None:
                            return success_boundary.gate_response
                        continue

                    # 不重试：标记失败并通知
                    raise AgentError(error_msg) from e
                finally:
                    if current_attempt_keepalive_active:
                        deactivate_current_attempt_keepalive(reason="attempt_scope_exit")
                        current_attempt_keepalive_active = False

            # Workflow completed successfully
            await self._update_progress(90, "Workflow completed, dispatching completion event")

            # 发布完成事件（监听器异步落库），不再同步持久化
            persistence_payload = self._workflow_completion_adapter.build_persistence_payload(
                str(wf_id)
            )
            final_url = str(persistence_payload.get("final_video_url") or "").strip()
            final_path = str(persistence_payload.get("final_video_path") or "").strip()
            if workflow_results.get(AgentType.VIDEO_COMPOSER.value) and not (
                final_url or final_path
            ):
                raise AgentError(
                    "Workflow completed without authoritative project.final_video; "
                    "runtime summary and persistence projection would diverge"
                )

            quality_result = workflow_results.get("quality_checker")
            quality_result = quality_result if isinstance(quality_result, dict) else {}
            quality_score = quality_result.get("quality_score")
            if runtime_session_id is None:
                raise AgentError("Workflow completion has no runtime terminal authority")
            self._get_orchestration_runtime_transition_facade().mark_runtime_session_completed(
                runtime_session_id=runtime_session_id,
                task_id=task.task_id,
                summary_output=self._workflow_completion_adapter.build_runtime_summary_output(
                    final_video_url=final_url,
                    final_video_path=final_path,
                    results=workflow_results,
                    quality_score=quality_score,
                ),
            )
            runtime_session_status = WorkflowSessionStatus.COMPLETED.value

            completion_payload: Dict[str, Any] = {}
            persistence_status = "event_published"
            projection_error: Optional[str] = None
            try:
                completion_payload = await self._workflow_completion_adapter.publish_completed(
                    task=task,
                    workflow_id=wf_id,
                    persistence_payload=persistence_payload,
                    results=workflow_results,
                    quality_score=quality_score,
                    runtime_session_id=runtime_session_id,
                    runtime_terminal_committed=True,
                )
            except Exception as event_error:
                persistence_status = "event_publish_failed"
                projection_error = str(event_error)
                self.logger.error(
                    "Runtime terminal committed but completion projection failed for session=%s: %s",
                    runtime_session_id,
                    event_error,
                )

            self.logger.info(f"🎉 工作流完成，任务ID: {task.task_id}")

            return {
                "status": "completed",
                "total_steps": total_steps,
                "results": workflow_results,
                "final_video_url": final_url,
                "final_video_path": final_path,
                "quality_score": quality_score,
                "role_continuity_diagnostics": completion_payload.get(
                    "role_continuity_diagnostics"
                ),
                "persistence_status": persistence_status,
                "projection_error": projection_error,
                "workflow_state_id": wf_id,
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
            if runtime_session_id is not None and runtime_session_status not in {
                WorkflowSessionStatus.COMPLETED.value,
                WorkflowSessionStatus.FAILED.value,
            }:
                self._get_orchestration_runtime_transition_facade().mark_runtime_session_failed(
                    runtime_session_id=runtime_session_id,
                    task_id=task.task_id,
                    error_message=error_msg,
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

        def _decision_error(reason_code: str, message: str) -> AgentError:
            return AgentError(
                "orchestrator_decision_failed " f"reason_code={reason_code}: {message}"
            )

        # Build observation (concise, facts-only) from MAS WM (SoT)
        try:
            from .adapters.state.agent_outputs import assess_agent_delivery
            from .adapters.state.mas_state import build_mas_state_view

            delivery = assess_agent_delivery(
                str(workflow_id), current_agent, service=self.short_term_service
            )
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
        pm = getattr(self, "prompt_manager", None) or get_prompt_manager()
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
        model_name = getattr(settings, "ORCHESTRATOR_DECISION_MODEL", "glm-4.5-air")
        result = await self.llm_function_call(
            messages=[sys_msg, user_msg],
            context_description="Workflow step decision",
            model=model_name,
            temperature=0.2,
            # 统一使用结构化 JSON 回执，降低长尾解析风险
            response_format={"type": "json_object"},
        )

        if not isinstance(result, dict):
            raise _decision_error(
                "orchestrator_decision_invalid_envelope",
                "llm_function_call returned a non-dict result",
            )

        approach = str(result.get("approach") or "").strip()
        if approach == "function_call_plan":
            tool_calls = result.get("tool_calls")
            if not isinstance(tool_calls, list) or not tool_calls:
                raise _decision_error(
                    "orchestrator_decision_missing",
                    "function_call_plan returned no control tool calls",
                )
            exec_res = await self.execute_tool_calls(tool_calls)  # 执行控制动作
            if not isinstance(exec_res, list) or not exec_res:
                raise _decision_error(
                    "orchestrator_decision_tool_failed",
                    "control tool execution returned no result",
                )
            failed_calls: List[str] = []
            for call in exec_res:
                if not isinstance(call, dict):
                    failed_calls.append("non_dict_result")
                    continue
                tool_name = call.get("tool") or ""
                if tool_name == "orchestrator_control_repeat_agent" and call.get("success"):
                    return "repeat_agent"
                if tool_name == "orchestrator_control_halt_workflow" and call.get("success"):
                    return "halt_workflow"
                if tool_name == "orchestrator_control_proceed_next" and call.get("success"):
                    return "proceed_next"
                if not call.get("success"):
                    failed_calls.append(
                        f"{tool_name or '<unknown>'}:{call.get('error') or 'failed'}"
                    )
            if failed_calls:
                raise _decision_error(
                    "orchestrator_decision_tool_failed",
                    "; ".join(failed_calls),
                )
            raise _decision_error(
                "orchestrator_decision_unsupported_tool_result",
                "control tool execution returned no recognized successful decision",
            )
        # 无工具可用：尝试解析严格 JSON 文本决策
        if approach == "text_response":
            try:
                content = (result.get("content") or "").strip()
                import json as _json

                if not content:
                    raise _decision_error(
                        "orchestrator_decision_missing",
                        "text_response returned empty content",
                    )
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
                if decision:
                    raise _decision_error(
                        "orchestrator_decision_invalid_action",
                        f"unsupported decision: {decision}",
                    )
                raise _decision_error(
                    "orchestrator_decision_missing",
                    "text_response JSON did not include a supported decision",
                )
            except AgentError:
                raise
            except Exception as exc:
                raise _decision_error(
                    "orchestrator_decision_parse_failed",
                    str(exc),
                ) from exc
        raise _decision_error(
            "orchestrator_decision_missing",
            f"unsupported or missing decision approach: {approach or '<empty>'}",
        )

    # WorkflowStatus 已移除；active-path live status now comes from runtime view only.

    def _is_image_step_completed(self, workflow_id: str) -> bool:
        """Gate condition for image generation step completion."""
        contract = evaluate_scene_output_acceptance(
            kind="image",
            workflow_id=str(workflow_id),
            agent_memory=None,
            service=self.short_term_service,
        )
        if contract.get("accepted") is True:
            return True
        self.logger.warning(
            "Image step not completed by scene-output acceptance contract: %s",
            {
                "reason_code": contract.get("reason_code"),
                "expected_scene_numbers": contract.get("expected_scene_numbers"),
                "accepted_scene_numbers": contract.get("accepted_scene_numbers"),
                "missing_scene_numbers": contract.get("missing_scene_numbers"),
                "failed_scene_numbers": contract.get("failed_scene_numbers"),
                "rejected_scene_outputs": contract.get("rejected_scene_outputs"),
            },
        )
        return False

    def _is_video_step_completed(self, workflow_id: str) -> bool:
        """Gate condition for video generation step completion."""
        contract = evaluate_scene_output_acceptance(
            kind="video",
            workflow_id=str(workflow_id),
            agent_memory=None,
            service=self.short_term_service,
        )
        if contract.get("accepted") is True:
            return True
        self.logger.warning(
            "Video step not completed by scene-output acceptance contract: %s",
            {
                "reason_code": contract.get("reason_code"),
                "expected_scene_numbers": contract.get("expected_scene_numbers"),
                "accepted_scene_numbers": contract.get("accepted_scene_numbers"),
                "missing_scene_numbers": contract.get("missing_scene_numbers"),
                "failed_scene_numbers": contract.get("failed_scene_numbers"),
                "rejected_scene_outputs": contract.get("rejected_scene_outputs"),
            },
        )
        return False

    def _store_composer_outputs(
        self,
        workflow_id: str,
        agent_output: Dict[str, Any],
    ) -> Callable[[], None]:
        wf_id = str(workflow_id or "")
        if not wf_id or not isinstance(agent_output, dict):
            return lambda: None
        final_path = str(agent_output.get("final_video_path") or "").strip()
        final_url = str(agent_output.get("final_video_url") or "").strip()
        mix_receipt = agent_output.get("mix_receipt")
        if not (final_path or final_url or isinstance(mix_receipt, dict)):
            return lambda: None
        facts: Dict[str, Any] = {}
        if final_path or final_url:
            resolved_final_url = final_url or build_local_public_url(final_path)
            seed_metadata = normalize_video_metadata(agent_output.get("metadata", {}))
            probed_metadata = probe_local_video_metadata_sync(final_path) if final_path else {}
            final_video_metadata = merge_video_metadata(
                seed_metadata,
                probed_metadata,
                overwrite_non_empty=True,
            )
            payload = {
                "path": final_path,
                "url": resolved_final_url,
                "storage": {
                    "provider": "local",
                    "url": resolved_final_url,
                    "skipped": True,
                },
            }
            if isinstance(final_video_metadata, dict) and final_video_metadata:
                payload["metadata"] = dict(final_video_metadata)
            facts["project.final_video"] = payload
        if isinstance(mix_receipt, dict) and mix_receipt:
            facts["project.final_video_mix"] = dict(mix_receipt)

        shared = None
        previous_facts: Dict[str, Tuple[bool, Any]] = {}

        def _rollback() -> None:
            if shared is None:
                return
            for key, (existed, previous_value) in previous_facts.items():
                if existed:
                    shared.put(key, deepcopy(previous_value))
                else:
                    shared.delete(key)

        try:
            shared = get_mas_working_memory(wf_id, service=self.short_term_service)
            existing_keys = set(shared.list_keys())
            previous_facts = {
                key: (key in existing_keys, deepcopy(shared.get(key))) for key in facts
            }
            for key, value in facts.items():
                shared.put(key, value)
        except Exception as exc:
            try:
                _rollback()
            except Exception as rollback_exc:
                self.logger.error(
                    "Failed to roll back composer output publication: %s",
                    rollback_exc,
                    exc_info=True,
                )
            self.logger.error("❌ Failed to store composer outputs: %s", exc, exc_info=True)
            raise _OrchestrationBoundaryError(
                f"Authoritative composer publication failed: {exc}",
                reason_code="authoritative_publication_failed",
            ) from exc
        return _rollback

    def _record_agent_output(
        self,
        *,
        workflow_id: str,
        agent_type: AgentType,
        workflow_results: Dict[str, Any],
        workflow_data: Dict[str, Any],
        agent_output: Dict[str, Any],
    ) -> Callable[[], None]:
        previous_results = dict(workflow_results)
        previous_data = dict(workflow_data)
        composer_rollback: Callable[[], None] = lambda: None

        def _restore_local_maps() -> None:
            workflow_results.clear()
            workflow_results.update(previous_results)
            workflow_data.clear()
            workflow_data.update(previous_data)

        try:
            if agent_type == AgentType.VIDEO_COMPOSER:
                rollback_candidate = self._store_composer_outputs(workflow_id, agent_output)
                if callable(rollback_candidate):
                    composer_rollback = rollback_candidate
            workflow_results[agent_type.value] = agent_output
            workflow_data.update(agent_output)
        except Exception:
            _restore_local_maps()
            try:
                composer_rollback()
            except Exception as rollback_exc:
                self.logger.error(
                    "Failed to roll back authoritative composer publication: %s",
                    rollback_exc,
                    exc_info=True,
                )
            raise

        def _rollback() -> None:
            _restore_local_maps()
            composer_rollback()

        return _rollback

    async def _execute_agent_success_path(
        self,
        *,
        agent: BaseAgent,
        request: AgentExecutionRequest,
        workflow_state_id: str,
        workflow_results: Dict[str, Any],
        workflow_data: Dict[str, Any],
        current_agent: AgentType,
        audio_contract: Dict[str, Any],
        candidate_agents: List[AgentType],
        standby_agents: List[AgentType],
        replan_count: int,
        max_replans: int,
        current_index: int,
        execution_queue: List[AgentType],
        task_specs: Dict[AgentType, Dict[str, Any]],
        conditional_task_specs: Dict[str, Dict[str, Any]],
        runtime_session_id: Optional[int],
        runtime_node_key: Optional[str],
        attempt_id: Optional[int],
        lease_token: Optional[str],
        attempt_trigger_reason: str,
        script_trigger_reason: str,
        fail_runtime_attempt_on_error: bool = False,
    ) -> Tuple[Dict[str, Any], _RuntimeSuccessBoundaryOutcome]:
        try:
            try:
                agent_result = await agent.execute(request)
            except Exception as agent_error:
                failure_observation = (
                    self._orchestration_protocol.build_agent_execution_failure_observation(
                        workflow_state_id=workflow_state_id,
                        agent_type=current_agent,
                        error=agent_error,
                        execution_id=self._current_execution_id(),
                    )
                )
                runtime_cycle = await self._evaluate_runtime_boundary_cycle(
                    workflow_state_id=workflow_state_id,
                    current_agent=current_agent,
                    agent_result=None,
                    normalized_report=failure_observation,
                    audio_contract=dict(audio_contract or {}),
                    candidate_agents=list(candidate_agents),
                    standby_agents=list(standby_agents),
                    replan_count=replan_count,
                    max_replans=max_replans,
                    current_index=current_index,
                    execution_queue=execution_queue,
                    task_specs=task_specs,
                    conditional_task_specs=conditional_task_specs,
                )
                failure_outcome = self._apply_runtime_cycle_outcome(
                    normalized_report=failure_observation,
                    runtime_cycle=runtime_cycle,
                    standby_agents=standby_agents,
                    replan_count=replan_count,
                    execution_queue=execution_queue,
                    task_specs=task_specs,
                    runtime_session_id=runtime_session_id,
                    runtime_node_key=runtime_node_key,
                    attempt_id=attempt_id,
                    lease_token=lease_token,
                )
                if failure_outcome.output_accepted:
                    raise _OrchestrationBoundaryError(
                        "Agent execution failure cannot authorize output publication",
                        reason_code="runtime_failure_publication_invalid",
                    )
                return {}, failure_outcome
            agent_output = agent_result.output_data.to_dict()
            try:
                normalized_report = self._orchestration_protocol.build_subagent_report(
                    workflow_state_id=workflow_state_id,
                    agent_type=current_agent,
                    agent_result=agent_result,
                    execution_id=self._current_execution_id(),
                )
            except OrchestrationProtocolError as exc:
                raise _OrchestrationBoundaryError(
                    f"Runtime protocol violated: {exc}",
                    reason_code=exc.reason_code,
                ) from exc
            success_boundary = await self._finalize_successful_agent_runtime_boundary(
                workflow_state_id=workflow_state_id,
                task_id=request.task.task_id,
                current_agent=current_agent,
                agent_result=agent_result,
                normalized_report=normalized_report,
                agent_output=agent_output,
                audio_contract=audio_contract,
                candidate_agents=candidate_agents,
                standby_agents=standby_agents,
                replan_count=replan_count,
                max_replans=max_replans,
                current_index=current_index,
                execution_queue=execution_queue,
                task_specs=task_specs,
                conditional_task_specs=conditional_task_specs,
                runtime_session_id=runtime_session_id,
                runtime_node_key=runtime_node_key,
                attempt_id=attempt_id,
                lease_token=lease_token,
                attempt_trigger_reason=attempt_trigger_reason,
                script_trigger_reason=script_trigger_reason,
            )
            if not success_boundary.output_accepted:
                return {}, success_boundary
            rollback_publication = self._record_agent_output(
                workflow_id=workflow_state_id,
                agent_type=current_agent,
                workflow_results=workflow_results,
                workflow_data=workflow_data,
                agent_output=agent_output,
            )
            try:
                success_boundary = self._complete_successful_runtime_attempt(
                    success_boundary=success_boundary,
                    runtime_session_id=runtime_session_id,
                    runtime_node_key=runtime_node_key,
                    attempt_id=attempt_id,
                    lease_token=lease_token,
                )
            except Exception:
                try:
                    rollback_publication()
                except Exception as rollback_exc:
                    self.logger.error(
                        "Failed to roll back output publication after runtime completion error: %s",
                        rollback_exc,
                        exc_info=True,
                    )
                raise
            return agent_output, success_boundary
        except Exception as exc:
            if fail_runtime_attempt_on_error:
                self._fail_retry_runtime_attempt(
                    runtime_session_id=runtime_session_id,
                    runtime_node_key=runtime_node_key,
                    attempt_id=attempt_id,
                    lease_token=lease_token,
                    error=exc,
                    diagnostic_code=(
                        f"{runtime_node_key}_retry_failed" if runtime_node_key else "retry_failed"
                    ),
                )
            raise

    def _fail_retry_runtime_attempt(
        self,
        *,
        runtime_session_id: Optional[int],
        runtime_node_key: Optional[str],
        attempt_id: Optional[int],
        lease_token: Optional[str],
        error: Exception,
        diagnostic_code: str,
    ) -> None:
        if runtime_session_id is None or runtime_node_key is None or attempt_id is None:
            return
        self._get_orchestration_runtime_transition_facade().fail_runtime_attempt(
            runtime_session_id=runtime_session_id,
            node_key=runtime_node_key,
            attempt_id=attempt_id,
            error_message=str(error),
            lease_token=lease_token,
            diagnostics=[
                {
                    "code": diagnostic_code,
                    "stage": runtime_node_key,
                    "message": str(error),
                    **(
                        {"reason_code": str(error.reason_code)}
                        if getattr(error, "reason_code", None)
                        else {}
                    ),
                }
            ],
        )

    def _apply_runtime_cycle_outcome(
        self,
        *,
        normalized_report: Dict[str, Any],
        runtime_cycle: Dict[str, Any],
        standby_agents: List[AgentType],
        replan_count: int,
        execution_queue: List[AgentType],
        task_specs: Dict[AgentType, Dict[str, Any]],
        runtime_session_id: Optional[int],
        runtime_node_key: Optional[str],
        attempt_id: Optional[int],
        lease_token: Optional[str],
    ) -> _RuntimeSuccessBoundaryOutcome:
        runtime_decision = runtime_cycle.get("runtime_decision") or {}
        apply_result = runtime_cycle.get("apply_result") or {}
        apply_status = apply_result.get("status")
        report_status = normalized_report.get("status")
        replan_reason = runtime_decision.get("reason") or apply_result.get("reason")
        if not isinstance(replan_reason, str) or not replan_reason:
            raise _OrchestrationBoundaryError(
                "Runtime apply result missing reason",
                reason_code="runtime_apply_reason_missing",
            )
        updated_standby_agents = list(standby_agents)
        updated_replan_count = replan_count
        output_accepted = True
        attempt_abandoned = False

        if apply_status == "activated":
            target_agent = apply_result.get("target_agent")
            updated_queue = apply_result.get("execution_queue")
            if not isinstance(updated_queue, list) or any(
                not isinstance(candidate, AgentType) for candidate in updated_queue
            ):
                raise _OrchestrationBoundaryError(
                    "Runtime apply_result execution_queue must be list[AgentType]",
                    reason_code="runtime_apply_execution_queue_invalid",
                )
            execution_queue[:] = list(updated_queue)
            updated_task_specs = apply_result.get("task_specs")
            if not isinstance(updated_task_specs, dict):
                raise _OrchestrationBoundaryError(
                    "Runtime apply_result task_specs must be a dict",
                    reason_code="runtime_apply_task_specs_invalid",
                )
            task_specs.clear()
            task_specs.update(updated_task_specs)
            raw_standby_agents = apply_result.get("standby_agents")
            if not isinstance(raw_standby_agents, list) or any(
                not isinstance(candidate, AgentType) for candidate in raw_standby_agents
            ):
                raise _OrchestrationBoundaryError(
                    "Runtime apply_result standby_agents must be list[AgentType]",
                    reason_code="runtime_apply_standby_agents_invalid",
                )
            updated_standby_agents = list(raw_standby_agents)
            raw_replan_count = apply_result.get("replan_count")
            if type(raw_replan_count) is not int:
                raise _OrchestrationBoundaryError(
                    "Runtime apply_result replan_count must be an integer",
                    reason_code="runtime_apply_replan_count_invalid",
                )
            updated_replan_count = raw_replan_count
            self.logger.info(
                "ADAPTIVE_REPLAN action=activate_from_standby target=%s reason=%s "
                "queue_changed=%s count=%s",
                target_agent.value if isinstance(target_agent, AgentType) else target_agent,
                replan_reason,
                bool(apply_result.get("queue_changed")),
                updated_replan_count,
            )
            if report_status != "completed":
                output_accepted = False
                if runtime_session_id is not None:
                    if (
                        runtime_node_key is None
                        or attempt_id is None
                        or not isinstance(lease_token, str)
                        or not lease_token
                    ):
                        raise AgentError(
                            "Runtime standby activation requires an active node, attempt, and lease"
                        )
                    self._get_orchestration_runtime_transition_facade().abandon_runtime_attempt_for_replan(
                        runtime_session_id=runtime_session_id,
                        node_key=runtime_node_key,
                        attempt_id=attempt_id,
                        lease_token=lease_token,
                        reason=replan_reason,
                    )
                    attempt_abandoned = True
        elif apply_status == "retry":
            raw_replan_count = apply_result.get("replan_count")
            if type(raw_replan_count) is not int:
                raise _OrchestrationBoundaryError(
                    "Runtime retry result missing integer replan_count",
                    reason_code="runtime_retry_replan_count_invalid",
                )
            raise _RuntimeRetryRequested(
                f"Runtime disposition requested retry: {replan_reason}",
                replan_count=raw_replan_count,
            )
        elif apply_status == "accepted_with_gaps":
            if report_status != "partial":
                raise AgentError("Runtime disposition accept_with_gaps requires a partial report")
        elif apply_status == "abort":
            raise AgentError(f"Workflow halted by runtime decision: {replan_reason}")
        elif apply_status == "continue":
            if report_status != "completed":
                raise _OrchestrationBoundaryError(
                    "Non-success report cannot continue without an explicit disposition",
                    reason_code="runtime_non_success_continue_invalid",
                )
        else:
            raise _OrchestrationBoundaryError(
                f"Unsupported runtime apply status: {apply_status!r}",
                reason_code="runtime_apply_status_invalid",
            )

        decision_ack = runtime_cycle.get("decision_ack") or {}
        self.logger.debug(
            "RUNTIME_DECISION_ACK %s",
            json.dumps(decision_ack, ensure_ascii=False),
        )
        return _RuntimeSuccessBoundaryOutcome(
            standby_agents=tuple(updated_standby_agents),
            replan_count=updated_replan_count,
            output_accepted=output_accepted,
            attempt_abandoned=attempt_abandoned,
        )

    async def _finalize_successful_agent_runtime_boundary(
        self,
        *,
        workflow_state_id: str,
        task_id: str,
        current_agent: AgentType,
        agent_result: AgentExecutionResult,
        normalized_report: Dict[str, Any],
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
        runtime_session_id: Optional[int],
        runtime_node_key: Optional[str],
        attempt_id: Optional[int],
        lease_token: Optional[str],
        attempt_trigger_reason: str,
        script_trigger_reason: str,
    ) -> _RuntimeSuccessBoundaryOutcome:
        try:
            runtime_cycle = await self._evaluate_runtime_boundary_cycle(
                workflow_state_id=workflow_state_id,
                current_agent=current_agent,
                agent_result=agent_result,
                normalized_report=normalized_report,
                audio_contract=dict(audio_contract or {}),
                candidate_agents=list(candidate_agents),
                standby_agents=list(standby_agents),
                replan_count=replan_count,
                max_replans=max_replans,
                current_index=current_index,
                execution_queue=execution_queue,
                task_specs=task_specs,
                conditional_task_specs=conditional_task_specs,
            )
            outcome = self._apply_runtime_cycle_outcome(
                normalized_report=normalized_report,
                runtime_cycle=runtime_cycle,
                standby_agents=standby_agents,
                replan_count=replan_count,
                execution_queue=execution_queue,
                task_specs=task_specs,
                runtime_session_id=runtime_session_id,
                runtime_node_key=runtime_node_key,
                attempt_id=attempt_id,
                lease_token=lease_token,
            )
        except AgentError:
            raise
        except Exception as replan_err:
            raise AgentError(f"Runtime decision evaluation failed: {replan_err}") from replan_err

        if not outcome.output_accepted:
            return outcome
        if runtime_session_id is None:
            return outcome
        if runtime_node_key is None or attempt_id is None or not str(lease_token or "").strip():
            raise AgentError("Runtime success boundary requires an active node, attempt, and lease")

        transition_port = self._get_orchestration_runtime_transition_facade()
        if current_agent == AgentType.SCRIPT_WRITER:
            gate_response = transition_port.open_script_review_gate(
                runtime_session_id=runtime_session_id,
                task_id=task_id,
                workflow_id=workflow_state_id,
                script_attempt_id=attempt_id,
                lease_token=lease_token,
                trigger_reason=attempt_trigger_reason or script_trigger_reason,
                script_output=dict(agent_output),
                task_specs=task_specs,
                conditional_task_specs=conditional_task_specs,
                candidate_agents=list(candidate_agents),
            )
            return _RuntimeSuccessBoundaryOutcome(
                standby_agents=outcome.standby_agents,
                replan_count=outcome.replan_count,
                gate_response=gate_response,
            )

        return _RuntimeSuccessBoundaryOutcome(
            standby_agents=outcome.standby_agents,
            replan_count=outcome.replan_count,
            attempt_completion_required=True,
        )

    def _complete_successful_runtime_attempt(
        self,
        *,
        success_boundary: _RuntimeSuccessBoundaryOutcome,
        runtime_session_id: Optional[int],
        runtime_node_key: Optional[str],
        attempt_id: Optional[int],
        lease_token: Optional[str],
    ) -> _RuntimeSuccessBoundaryOutcome:
        if not success_boundary.attempt_completion_required:
            return success_boundary
        if runtime_session_id is None:
            raise AgentError("Runtime attempt completion requires a runtime session")
        if runtime_node_key is None or attempt_id is None or not str(lease_token or "").strip():
            raise AgentError(
                "Runtime attempt completion requires an active node, attempt, and lease"
            )
        self._get_orchestration_runtime_transition_facade().complete_runtime_attempt(
            runtime_session_id=runtime_session_id,
            node_key=runtime_node_key,
            attempt_id=attempt_id,
            lease_token=lease_token,
            node_status=WorkflowNodeStatus.COMPLETED.value,
        )
        return _RuntimeSuccessBoundaryOutcome(
            standby_agents=success_boundary.standby_agents,
            replan_count=success_boundary.replan_count,
            gate_response=success_boundary.gate_response,
            attempt_completed=True,
            output_accepted=success_boundary.output_accepted,
            attempt_abandoned=success_boundary.attempt_abandoned,
        )

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
        agent_result: Optional[AgentExecutionResult],
        normalized_report: Optional[Dict[str, Any]] = None,
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
            report = (
                dict(normalized_report)
                if normalized_report is not None
                else self._orchestration_protocol.build_subagent_report(
                    workflow_state_id=workflow_state_id,
                    agent_type=current_agent,
                    agent_result=agent_result,
                    execution_id=execution_id,
                )
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
            raise _OrchestrationBoundaryError(
                f"Runtime protocol violated: {exc}",
                reason_code=exc.reason_code,
            ) from exc
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
    ) -> RuntimeDecision:
        if type(replan_count) is not int or replan_count < 0:
            raise AgentError("Runtime replan count must be a non-negative integer")
        if type(max_replans) is not int or max_replans < 0:
            raise AgentError("Runtime replan max must be a non-negative integer")
        report_status = report.get("status") if isinstance(report, dict) else None
        if report_status not in {"completed", "partial", "failed"}:
            raise AgentError("Runtime replan report missing canonical status")

        llm = self.get_llm("plan")
        pm = getattr(self, "prompt_manager", None) or get_prompt_manager()
        try:
            agent_sys = self.get_system_instructions() or {}
            pr = agent_sys.get("primary_role") or "工作流编排器"
        except Exception:
            pr = "工作流编排器"
        system_text = pm.render_template(
            "agents/orchestrator",
            "runtime_decision_system",
            variables={"primary_role": pr},
            use_cache=True,
            auto_reload=False,
        )
        user_text = pm.render_template(
            "agents/orchestrator",
            "runtime_decision_user",
            variables={
                "workflow_id": str(workflow_state_id or ""),
                "current_agent": current_agent.value,
                "report_json": json.dumps(dict(report or {}), ensure_ascii=False),
                "standby_candidates_json": json.dumps(
                    [agent.value for agent in standby_agents], ensure_ascii=False
                ),
                "gate_events_json": json.dumps(list(gate_events or []), ensure_ascii=False),
                "replan_budget_json": json.dumps(
                    {
                        "used": replan_count,
                        "max": max_replans,
                    },
                    ensure_ascii=False,
                ),
            },
            use_cache=True,
            auto_reload=False,
        )
        messages = [
            {
                "role": "system",
                "content": system_text,
            },
            {
                "role": "user",
                "content": user_text,
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

        if not isinstance(data, dict):
            raise AgentError("Runtime replan response must be a JSON object")
        action = data.get("action")
        if not isinstance(action, str) or not action:
            raise AgentError("Runtime replan missing action")
        if action != action.strip():
            raise AgentError("Runtime replan action must be canonical")
        reason = data.get("reason")
        if not isinstance(reason, str) or not reason or reason != reason.strip():
            raise AgentError("Runtime replan missing canonical reason")
        target_raw = data.get("target_agent")
        allowed_targets = {agent.value: agent for agent in standby_agents}

        try:
            runtime_action = RuntimeAction(action)
        except ValueError:
            raise AgentError(f"Runtime replan returned invalid action: {action}")

        allowed_actions_by_status = {
            "completed": {
                RuntimeAction.CONTINUE,
                RuntimeAction.ACTIVATE_FROM_STANDBY,
                RuntimeAction.ABORT,
            },
            "partial": {
                RuntimeAction.RETRY_CURRENT,
                RuntimeAction.ACTIVATE_FROM_STANDBY,
                RuntimeAction.ACCEPT_WITH_GAPS,
                RuntimeAction.ABORT,
            },
            "failed": {
                RuntimeAction.RETRY_CURRENT,
                RuntimeAction.ACTIVATE_FROM_STANDBY,
                RuntimeAction.ABORT,
            },
        }
        if runtime_action not in allowed_actions_by_status[report_status]:
            if report_status == "failed" and runtime_action is RuntimeAction.ACCEPT_WITH_GAPS:
                raise AgentError("Runtime replan failed report cannot be accepted")
            raise AgentError(
                f"Runtime replan action {action} is invalid for report status {report_status}"
            )

        if runtime_action is not RuntimeAction.ACTIVATE_FROM_STANDBY and "target_agent" in data:
            raise AgentError("Runtime replan target_agent is only valid for standby activation")

        if runtime_action is RuntimeAction.ACCEPT_WITH_GAPS:
            reflection = report.get("reflection")
            reported_gaps = (
                reflection.get("reported_gaps") if isinstance(reflection, dict) else None
            )
            if (
                not isinstance(reported_gaps, list)
                or not reported_gaps
                or any(
                    not isinstance(gap, str) or not gap or gap != gap.strip()
                    for gap in reported_gaps
                )
            ):
                raise AgentError(
                    "Runtime replan partial acceptance requires explicit reported_gaps"
                )

        if (
            runtime_action
            in {
                RuntimeAction.RETRY_CURRENT,
                RuntimeAction.ACTIVATE_FROM_STANDBY,
            }
            and replan_count >= max_replans
        ):
            raise AgentError("Runtime replan budget exhausted")

        task_id = data.get("task_id")
        if task_id is not None and (
            type(task_id) is not str or not task_id or task_id != task_id.strip()
        ):
            raise AgentError("Runtime replan task_id must be canonical when provided")
        if runtime_action is not RuntimeAction.ACTIVATE_FROM_STANDBY and task_id is not None:
            raise AgentError("Runtime replan task_id is only valid for standby activation")

        facts = {
            "report": report,
            "gate_events": gate_events,
            "llm_output": data,
        }
        if runtime_action is RuntimeAction.ACTIVATE_FROM_STANDBY:
            if (
                not isinstance(target_raw, str)
                or not target_raw
                or target_raw != target_raw.strip()
            ):
                raise AgentError(
                    "Runtime replan activate_from_standby missing canonical target_agent"
                )
            target_agent = allowed_targets.get(target_raw)
            if target_agent is None:
                raise AgentError(
                    f"Runtime replan returned invalid target_agent: {target_raw or '<empty>'}"
                )
            return RuntimeDecision(
                action=runtime_action,
                target_agent=target_agent,
                task_id=task_id,
                reason=reason,
                facts=facts,
            )

        return RuntimeDecision(
            action=runtime_action,
            reason=reason,
            facts=facts,
        )

    def _get_video_audio_capability(self) -> Dict[str, Any]:
        """Read current provider audio capability from video config manager."""
        try:
            provider_cfg = self.video_config.get_current_provider_config()
            provider = getattr(provider_cfg, "provider_name", None)
            supports_native_audio = getattr(provider_cfg, "supports_native_audio", None)
            native_audio_param_name = getattr(
                provider_cfg,
                "native_audio_param_name",
                None,
            )
            native_audio_default_enabled = getattr(
                provider_cfg,
                "native_audio_default_enabled",
                None,
            )
            if type(provider) is not str or not provider or provider != provider.strip():
                raise ValueError("provider_name must be a canonical non-empty string")
            if type(supports_native_audio) is not bool:
                raise ValueError("supports_native_audio must be boolean")
            if (
                type(native_audio_param_name) is not str
                or not native_audio_param_name
                or native_audio_param_name != native_audio_param_name.strip()
            ):
                raise ValueError("native_audio_param_name must be a canonical non-empty string")
            if (
                native_audio_default_enabled is not None
                and type(native_audio_default_enabled) is not bool
            ):
                raise ValueError("native_audio_default_enabled must be boolean or null")
            return {
                "provider": provider,
                "supports_native_audio": supports_native_audio,
                "native_audio_param_name": native_audio_param_name,
                "native_audio_default_enabled": native_audio_default_enabled,
            }
        except Exception as exc:
            raise _OrchestrationBoundaryError(
                f"video_audio_capability_unavailable: {exc}",
                reason_code="video_audio_capability_unavailable",
            ) from exc

    def _emit_pre_dispatch_diagnostics(self, agent_type: AgentType, workflow_state_id: str) -> None:
        if agent_type == AgentType.AUDIO_GENERATOR:
            try:
                contract = (
                    read_shared_fact(
                        workflow_state_id,
                        "workflow.contract.audio",
                        {},
                        service=self.short_term_service,
                    )
                    or {}
                )
                self.logger.info(
                    "AUDIO_AGENT_DISPATCH: workflow_id=%s policy=%s allow_silence=%s need_global_bgm=%s need_voiceover=%s",
                    workflow_state_id,
                    contract.get("policy") if isinstance(contract, dict) else None,
                    bool((contract or {}).get("allow_silence"))
                    if isinstance(contract, dict)
                    else None,
                    bool((contract or {}).get("need_global_bgm"))
                    if isinstance(contract, dict)
                    else None,
                    bool((contract or {}).get("need_voiceover"))
                    if isinstance(contract, dict)
                    else None,
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
        execution_contract: Optional[Dict[str, Any]] = None,
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
            scene_info_refs: Dict[str, str] = {}
            if agent_type in {AgentType.IMAGE_GENERATOR, AgentType.VIDEO_GENERATOR}:
                try:
                    scene_info_refs[agent_type.value] = self._scene_info_reference_port.prepare(
                        workflow_state_id=workflow_id,
                        agent_type=agent_type,
                        runtime_input_payload=dict(runtime_input_payload or {}),
                    )
                except SceneInfoReferencePreparationError as exc:
                    raise AgentError(
                        "Scene info reference preparation failed: "
                        f"reason_code={exc.reason_code} detail={exc}"
                    ) from exc
            boundary_context = self._get_context_contract_assembler().assemble_agent_context(
                agent_type=agent_type,
                workflow_state_id=workflow_id,
                workflow_data=workflow_data,
                runtime_input_payload=runtime_input_payload,
                execution_contract=execution_contract,
                scene_info_refs=scene_info_refs,
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

            if agent_type in [
                AgentType.IMAGE_GENERATOR,
                AgentType.VIDEO_GENERATOR,
                AgentType.AUDIO_GENERATOR,
            ]:
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
            raise AgentError(f"Failed to prepare agent context for {agent_type.value}: {e}") from e

    async def _prepare_scheduled_agent_input(
        self,
        *,
        workflow_data: Dict[str, Any],
        agent_type: AgentType,
        workflow_id: str,
        task_specs: Dict[AgentType, Dict[str, Any]],
        runtime_input_payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        task_assignment = self._build_task_assignment(
            agent_type=agent_type,
            task_specs=task_specs,
        )
        runtime_hints = self._resolve_task_runtime_hints(task_assignment)
        execution_contract = self._build_agent_execution_contract(
            agent_type=agent_type,
            workflow_state_id=workflow_id,
            runtime_hints=runtime_hints,
        )
        agent_input = await self._prepare_agent_context(
            workflow_data,
            agent_type,
            workflow_id,
            runtime_input_payload=runtime_input_payload,
            execution_contract=execution_contract,
        )
        if isinstance(execution_contract, dict) and execution_contract:
            agent_input["execution_contract"] = execution_contract
        agent_input["task"] = task_assignment
        return agent_input

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
            available_agents = [
                atype.value for atype in candidate_agents if isinstance(atype, AgentType)
            ]
            pm = getattr(self, "prompt_manager", None) or get_prompt_manager()
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
                            "audio_contract": self._sanitize_planning_audio_contract(
                                workflow_data.get("audio_contract")
                            ),
                            "audio_capability": workflow_data.get("audio_capability") or {},
                            "task_traits": self._extract_planning_task_traits(workflow_data),
                        },
                        ensure_ascii=False,
                    ),
                },
                use_cache=True,
                auto_reload=False,
            )
            try:
                self.logger.info(
                    "ORCH_PLAN_DECOMP_INPUT workflow=%s system=%s user=%s",
                    workflow_id,
                    system_text,
                    user_text,
                )
            except Exception:
                pass
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
            try:
                self.logger.info(
                    "ORCH_PLAN_DECOMP_OUTPUT_RAW workflow=%s content=%s",
                    workflow_id,
                    content,
                )
            except Exception:
                pass
            data = json.loads(content)
            agents = data.get("agents") if isinstance(data, dict) else None
            task_map: Dict[AgentType, Dict[str, Any]] = {}
            conditional_task_specs: Dict[str, Dict[str, Any]] = {}
            expected_agents = [
                atype for atype in list(candidate_agents) if isinstance(atype, AgentType)
            ]
            expected_agent_set = set(expected_agents)
            unexpected_agents: List[str] = []
            if isinstance(agents, list):
                for index, item in enumerate(agents):
                    if not isinstance(item, dict):
                        raise ValueError(
                            f"LLM task decomposition agents[{index}] must be an object"
                        )
                    spec = OrchestrationStateAdapter.parse_primary_task_spec_payload(
                        spec=item,
                        require_explicit_agent=True,
                        field_path=f"task_decomposition.agents[{index}]",
                    )
                    atype = AgentType(spec["agent"])
                    if atype not in expected_agent_set:
                        unexpected_agents.append(atype.value)
                        continue
                    if not spec["mission"].strip():
                        raise ValueError(
                            f"LLM task decomposition missing mission for agent: {atype.value}"
                        )
                    if not spec["deliverable"].strip():
                        raise ValueError(
                            f"LLM task decomposition missing deliverable for agent: {atype.value}"
                        )
                    spec["fallback_used"] = False
                    task_map[atype] = spec
            if unexpected_agents:
                raise ValueError(
                    "LLM task decomposition returned task_specs for non-candidate agents: "
                    + ", ".join(sorted(set(unexpected_agents)))
                )
            missing_agents = [
                atype.value
                for atype in expected_agents
                if not isinstance(task_map.get(atype), dict)
            ]
            if missing_agents:
                raise ValueError(
                    "LLM task decomposition missing task_specs for agents: "
                    + ", ".join(missing_agents)
                )
            conditional_tasks = data.get("conditional_tasks") if isinstance(data, dict) else None
            if conditional_tasks is not None and not isinstance(conditional_tasks, list):
                raise ValueError(
                    "LLM task decomposition conditional_tasks must be list when provided"
                )
            for index, item in enumerate(conditional_tasks or []):
                if not isinstance(item, dict):
                    raise ValueError(
                        f"LLM task decomposition conditional_tasks[{index}] must be an object"
                    )
                task_id = item.get("task_id")
                if not isinstance(task_id, str) or not task_id or task_id != task_id.strip():
                    raise ValueError(
                        f"LLM task decomposition conditional_tasks[{index}].task_id "
                        "must be a canonical string"
                    )
                spec = OrchestrationStateAdapter.parse_conditional_task_spec_payload(
                    spec={key: value for key, value in item.items() if key != "task_id"},
                    field_path=f"task_decomposition.conditional_tasks[{index}]",
                )
                atype = AgentType(spec["agent"])
                if atype not in expected_agent_set:
                    raise ValueError(
                        "LLM task decomposition returned conditional_task for non-candidate agent: "
                        f"{atype.value}"
                    )
                if not isinstance(spec.get("mission"), str) or not spec["mission"].strip():
                    raise ValueError(
                        f"LLM task decomposition missing mission for conditional task: {task_id}"
                    )
                if not isinstance(spec.get("deliverable"), str) or not spec["deliverable"].strip():
                    raise ValueError(
                        f"LLM task decomposition missing deliverable for conditional task: {task_id}"
                    )
                spec["fallback_used"] = False
                conditional_task_specs[task_id] = spec
            try:
                normalized_task_map = {
                    agent_type.value: dict(spec) for agent_type, spec in task_map.items()
                }
                self.logger.info(
                    "ORCH_PLAN_DECOMP_OUTPUT_NORMALIZED workflow=%s task_specs=%s conditional_task_specs=%s",
                    workflow_id,
                    json.dumps(normalized_task_map, ensure_ascii=False),
                    json.dumps(conditional_task_specs, ensure_ascii=False),
                )
            except Exception:
                pass
            return task_map, conditional_task_specs
        except Exception as e:
            try:
                self.logger.error("LLM task decomposition failed: %s (required)", e)
            except Exception:
                pass
            raise AgentError(f"LLM task decomposition is required but failed: {e}") from e
