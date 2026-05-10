"""
Orchestration-facing facade for pre-execution runtime resume/load/bootstrap choreography.

SQL/session boundary:
- this facade consumes the caller-owned current sync SQLAlchemy session only
- it must not open, replace, or close DB sessions
- RuntimeSessionService remains the sole owner of runtime persistence semantics
- fresh-session control-plane transitions stay in OrchestrationRuntimeTransitionFacade
"""
from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..models import AgentType, Task, WorkflowSessionStatus
from .orchestration_state_adapter import OrchestrationStateAdapter
from .published_deliverable_service import (
    PublishedDeliverableService,
    load_published_payload,
)
from .runtime_session_service import RuntimeSessionService


class OrchestrationRuntimeResumeBootstrapError(RuntimeError):
    """Raised when orchestration-facing runtime resume/bootstrap contracts fail."""


@dataclass(frozen=True)
class RuntimeResumeContext:
    runtime_session: Any
    script_gate: Any
    latest_script_decision: Any
    script_resume_action: str
    runtime_resume_checkpoint: Optional[Dict[str, Any]]
    resume_anchor_agent: Optional[AgentType]


@dataclass(frozen=True)
class RuntimeResumeTaskSpecBundle:
    task_specs: Dict[AgentType, Dict[str, Any]]
    conditional_task_specs: Dict[str, Dict[str, Any]]
    candidate_agents: List[AgentType]


@dataclass(frozen=True)
class RuntimeAttemptBootstrapResult:
    node_key: Optional[str]
    attempt_id: Optional[int]
    trigger_reason: str
    lease_token: Optional[str]


class OrchestrationRuntimeResumeBootstrapFacade:
    """Executes pre-execution resume/bootstrap choreography behind one orchestration-facing boundary."""

    _AGENT_TO_NODE_KEY = {
        AgentType.CONCEPT_PLANNER: "concept",
        AgentType.SCRIPT_WRITER: "script",
        AgentType.IMAGE_GENERATOR: "image",
        AgentType.VIDEO_GENERATOR: "video",
        AgentType.VOICE_SYNTHESIZER: "voice",
        AgentType.VIDEO_COMPOSER: "compose",
        AgentType.AUDIO_GENERATOR: "audio",
        AgentType.QUALITY_CHECKER: "quality",
    }

    def __init__(
        self,
        *,
        orchestration_state: OrchestrationStateAdapter,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._orchestration_state = orchestration_state
        self._logger = logger or logging.getLogger("orchestration_runtime_resume_bootstrap")

    @classmethod
    def _runtime_node_key_for_agent(cls, agent_type: AgentType) -> Optional[str]:
        return cls._AGENT_TO_NODE_KEY.get(agent_type)

    @classmethod
    def _agent_type_for_runtime_node_key(cls, node_key: str) -> Optional[AgentType]:
        normalized = str(node_key or "").strip().lower()
        if not normalized:
            return None
        for agent_type, mapped_key in cls._AGENT_TO_NODE_KEY.items():
            if mapped_key == normalized:
                return agent_type
        return None

    @staticmethod
    def _select_script_candidate_ref(gate: Any) -> Optional[Dict[str, Any]]:
        artifact_refs = getattr(gate, "artifact_refs", None)
        if not isinstance(artifact_refs, list):
            return None
        for ref in artifact_refs:
            if not isinstance(ref, dict):
                continue
            if str(ref.get("deliverable_type") or "").strip().lower() != "script":
                continue
            if not str(ref.get("payload_ref") or "").strip():
                continue
            return dict(ref)
        return None

    def project_script_revision_context(
        self,
        *,
        db: Session,
        runtime_session: Any,
        workflow_state_id: str,
        resume_action: str,
    ) -> Dict[str, Any]:
        """Restore agent-facing script facts for a control-plane revise resume."""

        normalized_action = str(resume_action or "").strip().lower()
        if normalized_action != "revise":
            return {
                "status": "skipped",
                "reason_code": "resume_action_not_revise",
                "resume_action": normalized_action,
            }
        if runtime_session is None:
            raise OrchestrationRuntimeResumeBootstrapError(
                "script_revision_context_missing: runtime_session_missing"
            )

        gate = RuntimeSessionService.get_latest_gate_for_node_sync(
            db,
            runtime_session.id,
            "script",
        )
        if gate is None:
            raise OrchestrationRuntimeResumeBootstrapError(
                "script_revision_context_missing: script_gate_missing"
            )

        ref = self._select_script_candidate_ref(gate)
        if ref is None:
            ref = PublishedDeliverableService.get_node_deliverable_ref_sync(
                db,
                session=runtime_session,
                node_key="script",
                attempt_id=getattr(gate, "attempt_id", None),
            )
        if not isinstance(ref, dict):
            raise OrchestrationRuntimeResumeBootstrapError(
                "script_revision_context_missing: candidate_deliverable_ref_missing"
            )

        payload = load_published_payload(ref.get("payload_ref"))
        if not isinstance(payload, dict):
            raise OrchestrationRuntimeResumeBootstrapError(
                "script_revision_context_missing: candidate_payload_unavailable"
            )

        try:
            receipt = self._orchestration_state.project_script_revision_facts(
                workflow_state_id=str(workflow_state_id),
                payload=payload,
                source="script_gate_candidate_deliverable",
            )
        except ValueError as exc:
            raise OrchestrationRuntimeResumeBootstrapError(str(exc)) from exc

        return {
            **dict(receipt),
            "gate_id": getattr(gate, "id", None),
            "attempt_id": getattr(gate, "attempt_id", None),
            "deliverable_id": ref.get("deliverable_id"),
        }

    def resolve_runtime_resume_context(
        self,
        *,
        db: Session,
        task: Task,
    ) -> RuntimeResumeContext:
        """Resolve resume inputs using the caller-owned current session; no fresh SQL session is created here."""
        if db is None:
            return RuntimeResumeContext(
                runtime_session=None,
                script_gate=None,
                latest_script_decision=None,
                script_resume_action="",
                runtime_resume_checkpoint=None,
                resume_anchor_agent=None,
            )

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

        script_resume_action = ""
        if (
            latest_decision is not None
            and runtime_session.status == WorkflowSessionStatus.RESUMING.value
        ):
            script_resume_action = str(latest_decision.action or "").strip().lower()

        runtime_resume_checkpoint: Optional[Dict[str, Any]] = None
        resume_anchor_agent: Optional[AgentType] = None
        if (
            runtime_session.status == WorkflowSessionStatus.RESUMING.value
            and not script_resume_action
        ):
            try:
                runtime_resume_checkpoint = RuntimeSessionService.load_active_continuation_sync(
                    db,
                    runtime_session,
                    expected_anchor_type=OrchestrationStateAdapter.CONTINUATION_ANCHOR_RUNTIME_CHECKPOINT,
                    require_decision_id=False,
                    require_resuming=True,
                )
            except ValueError as exc:
                raise OrchestrationRuntimeResumeBootstrapError(
                    f"Missing runtime continuation checkpoint for generic resume: {exc}"
                ) from exc
            resume_anchor_agent = self._agent_type_for_runtime_node_key(
                str(runtime_resume_checkpoint.get("node_key") or "")
            )
            if resume_anchor_agent is None:
                raise OrchestrationRuntimeResumeBootstrapError(
                    "Runtime continuation checkpoint cannot be mapped to a scheduled agent"
                )

        return RuntimeResumeContext(
            runtime_session=runtime_session,
            script_gate=script_gate,
            latest_script_decision=latest_decision,
            script_resume_action=script_resume_action,
            runtime_resume_checkpoint=runtime_resume_checkpoint,
            resume_anchor_agent=resume_anchor_agent,
        )

    def load_authoritative_resume_task_specs(
        self,
        *,
        db: Session,
        runtime_session: Any,
        resume_action: str,
    ) -> RuntimeResumeTaskSpecBundle:
        """Load persisted continuation specs through RuntimeSessionService on the caller-owned current session."""
        checkpoint = RuntimeSessionService.load_active_script_continuation_sync(
            db,
            runtime_session,
            node_key="script",
        )
        (
            task_specs,
            conditional_task_specs,
            candidate_agents,
        ) = self._orchestration_state.checkpoint_to_task_specs(
            checkpoint=checkpoint,
            require_decision_id=True,
        )
        if not task_specs:
            raise OrchestrationRuntimeResumeBootstrapError(
                f"Missing persisted continuation task_specs for resume action: {resume_action or '<empty>'}"
            )
        if resume_action in {"approve", "revise"} and AgentType.SCRIPT_WRITER not in task_specs:
            raise OrchestrationRuntimeResumeBootstrapError(
                f"Persisted continuation task_specs missing script_writer for resume action: {resume_action}"
            )
        if not candidate_agents:
            raise OrchestrationRuntimeResumeBootstrapError(
                f"Persisted continuation task_specs produced empty candidate pool for resume action: {resume_action or '<empty>'}"
            )
        return RuntimeResumeTaskSpecBundle(
            task_specs=task_specs,
            conditional_task_specs=conditional_task_specs,
            candidate_agents=list(candidate_agents),
        )

    def start_runtime_attempt(
        self,
        *,
        db: Session,
        runtime_session: Any,
        task: Task,
        current_agent_type: AgentType,
        workflow_state_id: str,
        task_specs: Dict[AgentType, Dict[str, Any]],
        conditional_task_specs: Dict[str, Dict[str, Any]],
        candidate_agents: List[AgentType],
        script_trigger_reason: str,
        script_requested_by: str,
        resume_anchor_agent: Optional[AgentType],
        trigger_reason_override: Optional[str] = None,
    ) -> RuntimeAttemptBootstrapResult:
        """Bootstrap the attempt on the caller-owned current session; fresh-session semantics stay out of this seam."""
        if runtime_session is None:
            return RuntimeAttemptBootstrapResult(
                node_key=None,
                attempt_id=None,
                trigger_reason="",
                lease_token=None,
            )

        runtime_node_key = self._runtime_node_key_for_agent(current_agent_type)
        if runtime_node_key is None:
            return RuntimeAttemptBootstrapResult(
                node_key=None,
                attempt_id=None,
                trigger_reason="",
                lease_token=None,
            )

        if trigger_reason_override is not None:
            effective_trigger_reason = str(trigger_reason_override or "").strip().lower() or "retry"
        elif current_agent_type == AgentType.SCRIPT_WRITER and script_trigger_reason in {
            "revise",
            "replan",
        }:
            effective_trigger_reason = script_trigger_reason
        elif resume_anchor_agent == current_agent_type:
            effective_trigger_reason = "resume"
        else:
            effective_trigger_reason = "initial"

        requested_by = (
            script_requested_by if current_agent_type == AgentType.SCRIPT_WRITER else "system"
        )
        progress_step = (
            "Generating script" if current_agent_type == AgentType.SCRIPT_WRITER else None
        )
        progress_percentage = 15 if current_agent_type == AgentType.SCRIPT_WRITER else None
        attempt = RuntimeSessionService.start_node_attempt_sync(
            db,
            runtime_session,
            node_key=runtime_node_key,
            trigger_reason=effective_trigger_reason,
            requested_by=requested_by,
            input_contract={"stage": runtime_node_key, "workflow_state_id": workflow_state_id},
            task=task,
            progress_step=progress_step,
            progress_percentage=progress_percentage,
        )
        continuation_checkpoint = self._orchestration_state.build_continuation_checkpoint(
            task_specs=task_specs,
            conditional_task_specs=conditional_task_specs,
            candidate_agents=list(candidate_agents),
            anchor_type=OrchestrationStateAdapter.CONTINUATION_ANCHOR_RUNTIME_CHECKPOINT,
            node_key=runtime_node_key,
            attempt_id=attempt.id,
            decision_id=None,
        )
        RuntimeSessionService.bind_attempt_continuation_checkpoint_sync(
            db,
            runtime_session,
            attempt_id=attempt.id,
            continuation_checkpoint=continuation_checkpoint,
        )
        leased_attempt = RuntimeSessionService.grant_attempt_lease_sync(
            db,
            runtime_session,
            attempt_id=attempt.id,
            lease_owner=f"orchestrator:{workflow_state_id}:{runtime_node_key}",
        )
        try:
            RuntimeSessionService.clear_node_diagnostic_codes_sync(
                db,
                runtime_session,
                node_key=runtime_node_key,
                codes=[
                    "execution_host_keepalive",
                    "execution_host_keepalive_activation_requested",
                    "execution_host_keepalive_first_heartbeat_ack",
                    "execution_host_keepalive_heartbeat_begin",
                    "execution_host_keepalive_heartbeat_end",
                    "execution_host_keepalive_deactivated",
                    "execution_host_keepalive_completion_validation_failed",
                ],
            )
        except Exception as diag_err:
            self._logger.warning(
                "Failed to clear execution host keepalive diagnostics for session=%s node=%s: %s",
                getattr(runtime_session, "id", None),
                runtime_node_key,
                diag_err,
            )
        return RuntimeAttemptBootstrapResult(
            node_key=runtime_node_key,
            attempt_id=attempt.id,
            trigger_reason=effective_trigger_reason,
            lease_token=str(leased_attempt.lease_token or "").strip() or None,
        )
