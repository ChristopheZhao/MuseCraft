"""
Orchestration-facing facade for post-execution runtime control-plane transitions.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..core.database import SessionLocal as SyncSessionLocal
from ..domain import (
    AgentType,
    JsonObjectPayload,
    RuntimeStoreError,
    RuntimeStoreReason,
    RuntimeTaskTransition,
    TaskStatus,
    WorkflowGateStatus,
    WorkflowNodeStatus,
)
from ..infrastructure import SqlAlchemyRuntimeAttemptStore
from ..models import Task
from .context_assembler import ContextContractAssembler
from .orchestration_state_adapter import OrchestrationStateAdapter
from .published_deliverable_service import clear_published_deliverable_ref
from .runtime_attempt_control_plane import RuntimeAttemptControlPlane
from .runtime_gate_control_plane import RuntimeGateControlPlane
from .runtime_session_service import RuntimeSessionService
from .script_review_contract import get_script_review_contract, set_script_review_contract


class OrchestrationRuntimeTransitionError(RuntimeError):
    """Raised when orchestration-facing runtime transition contracts fail."""


class OrchestrationRuntimeTransitionFacade:
    """Executes post-execution runtime transitions without making orchestrator own runtime truth."""

    def __init__(
        self,
        *,
        context_contract_assembler: ContextContractAssembler,
        orchestration_state: OrchestrationStateAdapter,
        session_factory=SyncSessionLocal,
    ) -> None:
        self._context_contract_assembler = context_contract_assembler
        self._orchestration_state = orchestration_state
        self._session_factory = session_factory

    def _run_with_fresh_runtime_control_plane_session(
        self,
        *,
        runtime_session_id: int,
        task_id: Optional[str] = None,
        action,
    ) -> Any:
        runtime_db = self._session_factory()
        try:
            fresh_runtime_session = RuntimeSessionService.get_session_by_id_sync(
                runtime_db,
                runtime_session_id,
            )
            if fresh_runtime_session is None:
                raise OrchestrationRuntimeTransitionError(
                    f"Runtime session {runtime_session_id} missing during control-plane transition"
                )

            runtime_task = None
            if task_id is not None:
                runtime_task = runtime_db.query(Task).filter(Task.task_id == str(task_id)).first()
                if runtime_task is None:
                    raise OrchestrationRuntimeTransitionError(
                        f"Task {task_id} missing during runtime control-plane transition"
                    )

            return action(runtime_db, fresh_runtime_session, runtime_task)
        finally:
            runtime_db.close()

    def complete_runtime_attempt(
        self,
        *,
        runtime_session_id: int,
        node_key: str,
        attempt_id: int,
        lease_token: Optional[str],
        node_status: str,
    ) -> None:
        try:
            target_node_status = WorkflowNodeStatus(node_status)
        except ValueError as exc:
            raise OrchestrationRuntimeTransitionError(
                f"Unsupported runtime node completion status: {node_status!r}"
            ) from exc

        def _complete(runtime_db: Session, _runtime_session: Any, _runtime_task: Any) -> None:
            control_plane = RuntimeAttemptControlPlane(SqlAlchemyRuntimeAttemptStore(runtime_db))
            try:
                control_plane.complete_attempt(
                    session_id=runtime_session_id,
                    node_key=node_key,
                    attempt_id=attempt_id,
                    expected_lease_token=lease_token,
                    target_node_status=target_node_status,
                )
            except RuntimeStoreError as exc:
                if exc.reason_code not in {
                    RuntimeStoreReason.LEASE_CONFLICT,
                    RuntimeStoreReason.STATE_CONFLICT,
                }:
                    raise
                diagnostic = control_plane.transition_validation_diagnostic(
                    session_id=runtime_session_id,
                    node_key=node_key,
                    attempt_id=attempt_id,
                    validation_error=exc,
                    diagnostic_code=("execution_host_keepalive_completion_validation_failed"),
                )
                control_plane.upsert_diagnostic(
                    session_id=runtime_session_id,
                    attempt_id=attempt_id,
                    diagnostic=diagnostic,
                )
                runtime_db.commit()
                raise
            runtime_db.commit()

        self._run_with_fresh_runtime_control_plane_session(
            runtime_session_id=runtime_session_id,
            action=_complete,
        )

    def fail_runtime_attempt(
        self,
        *,
        runtime_session_id: int,
        node_key: str,
        attempt_id: int,
        error_message: str,
        lease_token: Optional[str],
        diagnostics: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        normalized_diagnostics = tuple(
            JsonObjectPayload.from_mapping(
                diagnostic,
                field_path=f"runtime_attempt.failure_diagnostics[{index}]",
            )
            for index, diagnostic in enumerate(diagnostics or [])
        )

        def _fail(runtime_db: Session, _runtime_session: Any, _runtime_task: Any) -> None:
            control_plane = RuntimeAttemptControlPlane(SqlAlchemyRuntimeAttemptStore(runtime_db))
            try:
                control_plane.fail_attempt(
                    session_id=runtime_session_id,
                    node_key=node_key,
                    attempt_id=attempt_id,
                    expected_lease_token=lease_token,
                    error_message=error_message,
                    diagnostics=normalized_diagnostics,
                )
            except RuntimeStoreError as exc:
                if exc.reason_code not in {
                    RuntimeStoreReason.LEASE_CONFLICT,
                    RuntimeStoreReason.STATE_CONFLICT,
                }:
                    raise
                diagnostic = control_plane.transition_validation_diagnostic(
                    session_id=runtime_session_id,
                    node_key=node_key,
                    attempt_id=attempt_id,
                    validation_error=exc,
                    diagnostic_code="execution_host_keepalive_failure_validation_failed",
                )
                control_plane.upsert_diagnostic(
                    session_id=runtime_session_id,
                    attempt_id=attempt_id,
                    diagnostic=diagnostic,
                )
                runtime_db.commit()
                raise
            runtime_db.commit()

        self._run_with_fresh_runtime_control_plane_session(
            runtime_session_id=runtime_session_id,
            action=_fail,
        )

    def upsert_runtime_attempt_diagnostic(
        self,
        *,
        runtime_session_id: int,
        attempt_id: int,
        diagnostic: Dict[str, Any],
    ) -> None:
        normalized_diagnostic = JsonObjectPayload.from_mapping(
            diagnostic,
            field_path="runtime_attempt.diagnostic",
        )

        def _upsert(runtime_db: Session, _runtime_session: Any, _runtime_task: Any) -> None:
            RuntimeAttemptControlPlane(SqlAlchemyRuntimeAttemptStore(runtime_db)).upsert_diagnostic(
                session_id=runtime_session_id,
                attempt_id=attempt_id,
                diagnostic=normalized_diagnostic,
            )
            runtime_db.commit()

        self._run_with_fresh_runtime_control_plane_session(
            runtime_session_id=runtime_session_id,
            action=_upsert,
        )

    def open_script_review_gate(
        self,
        *,
        runtime_session_id: int,
        task_id: str,
        workflow_id: str,
        script_attempt_id: int,
        lease_token: Optional[str],
        trigger_reason: str,
        script_output: Dict[str, Any],
        task_specs: Dict[AgentType, Dict[str, Any]],
        conditional_task_specs: Dict[str, Dict[str, Any]],
        candidate_agents: List[AgentType],
    ) -> Dict[str, Any]:
        def _open_gate(
            runtime_db: Session, runtime_session: Any, runtime_task: Optional[Task]
        ) -> Dict[str, Any]:
            if runtime_task is None:
                raise OrchestrationRuntimeTransitionError(
                    f"Task {task_id} missing while opening the script review gate"
                )
            boundary = self._context_contract_assembler.publish_script_review_boundary_sync(
                db=runtime_db,
                session=runtime_session,
                workflow_state_id=workflow_id,
                attempt_id=script_attempt_id,
                script_output=script_output,
            )
            continuation_checkpoint = self._orchestration_state.build_continuation_checkpoint(
                task_specs=task_specs,
                conditional_task_specs=conditional_task_specs,
                candidate_agents=list(candidate_agents),
                anchor_type=OrchestrationStateAdapter.CONTINUATION_ANCHOR_GATE_DECISION,
                node_key="script",
                attempt_id=script_attempt_id,
                decision_id=None,
            )
            artifact_ref_value = boundary.get("artifact_ref")
            if not isinstance(artifact_ref_value, dict):
                raise OrchestrationRuntimeTransitionError(
                    "Script review boundary missing typed artifact_ref"
                )
            artifact_ref = JsonObjectPayload.from_mapping(
                artifact_ref_value,
                field_path="script_review.artifact_ref",
            )
            continuation_payload = JsonObjectPayload.from_mapping(
                continuation_checkpoint,
                field_path="script_review.continuation_checkpoint",
            )
            input_payload_value = runtime_session.input_payload
            if not isinstance(input_payload_value, dict):
                raise OrchestrationRuntimeTransitionError(
                    "Runtime session input_payload is not a JSON object"
                )
            normalized_input_payload = JsonObjectPayload.from_mapping(
                input_payload_value,
                field_path="script_review.session_input_payload",
            ).to_dict()
            review_contract = get_script_review_contract(normalized_input_payload) or {}
            target_input_payload = clear_published_deliverable_ref(
                set_script_review_contract(normalized_input_payload, None),
                node_key="script",
            )

            store = SqlAlchemyRuntimeAttemptStore(runtime_db)
            RuntimeAttemptControlPlane(store).complete_attempt(
                session_id=runtime_session_id,
                node_key="script",
                attempt_id=script_attempt_id,
                expected_lease_token=lease_token,
                target_node_status=WorkflowNodeStatus.RUNNING,
                output_artifacts=(artifact_ref,),
                metrics=JsonObjectPayload.from_mapping(
                    {
                        "trigger_reason": trigger_reason,
                        "scenes_generated": script_output.get("scenes_generated"),
                        "total_scenes": script_output.get("total_scenes"),
                        "review_contract_action": review_contract.get("action"),
                    },
                    field_path="script_review.attempt_metrics",
                ),
                continuation_checkpoint=continuation_payload,
                node_artifact_refs=(artifact_ref,),
                node_diagnostics=(),
            )
            try:
                current_task_status = TaskStatus(str(runtime_task.status))
            except ValueError as exc:
                raise OrchestrationRuntimeTransitionError(
                    f"Task {task_id} has unsupported status {runtime_task.status!r}"
                ) from exc
            script_preview_text = str(boundary.get("script_preview_text") or "")
            gate = RuntimeGateControlPlane(store).open_human_gate(
                session_id=runtime_session_id,
                node_key="script",
                attempt_id=script_attempt_id,
                gate_name="script_review",
                gate_type="human_review",
                contract_version="v1",
                scope=JsonObjectPayload.from_mapping(
                    {"scope_type": "episode", "scope_ref": str(workflow_id or "")},
                    field_path="script_review.gate_scope",
                ),
                artifact_refs=(artifact_ref,),
                facts=JsonObjectPayload.from_mapping(
                    {
                        "workflow_state_id": workflow_id,
                        "scenes_generated": script_output.get("scenes_generated"),
                        "total_scenes": script_output.get("total_scenes"),
                        "script_preview_text": script_preview_text,
                        "trigger_reason": trigger_reason,
                    },
                    field_path="script_review.gate_facts",
                ),
                allowed_actions=("approve", "revise", "replan"),
                recommended_action="approve",
                expected_lease_token=None,
                result_code=WorkflowGateStatus.AWAITING_HUMAN.value,
                reason_code=str(trigger_reason or "script_review_requested"),
                session_input_payload=JsonObjectPayload.from_mapping(
                    target_input_payload,
                    field_path="script_review.target_session_input_payload",
                ),
                node_artifact_refs=(artifact_ref,),
                node_diagnostics=(),
                task_transition=RuntimeTaskTransition(
                    task_id=str(runtime_task.task_id),
                    expected_status=current_task_status,
                    target_status=TaskStatus.IN_PROGRESS,
                    progress_step="Waiting for script approval",
                    progress_percentage=35,
                    requires_human_review=True,
                ),
            )
            runtime_db.commit()
            return {
                "status": "waiting_gate",
                "session_id": runtime_session_id,
                "gate_id": gate.gate_id,
                "node_key": "script",
            }

        return self._run_with_fresh_runtime_control_plane_session(
            runtime_session_id=runtime_session_id,
            task_id=task_id,
            action=_open_gate,
        )

    def mark_runtime_session_completed(
        self,
        *,
        runtime_session_id: int,
        task_id: str,
        summary_output: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._run_with_fresh_runtime_control_plane_session(
            runtime_session_id=runtime_session_id,
            task_id=task_id,
            action=lambda runtime_db, fresh_runtime_session, runtime_task: RuntimeSessionService.mark_session_completed_sync(
                runtime_db,
                fresh_runtime_session,
                task=runtime_task,
                summary_output=summary_output,
            ),
        )

    def mark_runtime_session_failed(
        self,
        *,
        runtime_session_id: int,
        task_id: str,
        error_message: str,
    ) -> None:
        self._run_with_fresh_runtime_control_plane_session(
            runtime_session_id=runtime_session_id,
            task_id=task_id,
            action=lambda runtime_db, fresh_runtime_session, runtime_task: RuntimeSessionService.mark_session_failed_sync(
                runtime_db,
                fresh_runtime_session,
                error_message=error_message,
                task=runtime_task,
            ),
        )
