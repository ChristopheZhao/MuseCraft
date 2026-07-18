"""
Orchestration-facing facade for post-execution runtime control-plane transitions.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any, Dict, List, Optional, TypeVar

from sqlalchemy.orm import Session

from ..core.database import SessionLocal as SyncSessionLocal
from ..domain import (
    AgentType,
    JsonObjectPayload,
    RuntimeSessionRecord,
    RuntimeStoreError,
    RuntimeStoreReason,
    RuntimeTaskTransition,
    TaskStatus,
    WorkflowGateStatus,
    WorkflowNodeStatus,
)
from ..infrastructure import SqlAlchemyRuntimeAttemptStore
from .context_assembler import ContextContractAssembler
from .orchestration_state_adapter import OrchestrationStateAdapter
from .published_deliverable_service import (
    build_deliverable_ref,
    clear_published_deliverable_ref,
    discard_published_payload,
)
from .runtime_attempt_control_plane import RuntimeAttemptControlPlane
from .runtime_gate_control_plane import RuntimeGateControlPlane
from .runtime_published_deliverable_control_plane import RuntimePublishedDeliverableControlPlane
from .runtime_session_control_plane import RuntimeSessionControlPlane
from .script_review_contract import get_script_review_contract, set_script_review_contract


class OrchestrationRuntimeTransitionError(RuntimeError):
    """Raised when orchestration-facing runtime transition contracts fail."""


TransitionResult = TypeVar("TransitionResult")


class OrchestrationRuntimeTransitionFacade:
    """Executes post-execution runtime transitions without making orchestrator own runtime truth."""

    _PAYLOAD_COMPENSATION_INFO_KEY = "runtime_published_payload_compensation_ref"

    def __init__(
        self,
        *,
        context_contract_assembler: ContextContractAssembler,
        orchestration_state: OrchestrationStateAdapter,
        session_factory: Callable[[], Session] = SyncSessionLocal,
    ) -> None:
        self._context_contract_assembler = context_contract_assembler
        self._orchestration_state = orchestration_state
        self._session_factory = session_factory

    def _run_with_fresh_runtime_control_plane_session(
        self,
        *,
        runtime_session_id: int,
        task_id: Optional[str] = None,
        action: Callable[
            [Session, SqlAlchemyRuntimeAttemptStore, RuntimeSessionRecord],
            TransitionResult,
        ],
    ) -> TransitionResult:
        runtime_db = self._session_factory()
        try:
            store = SqlAlchemyRuntimeAttemptStore(runtime_db)
            fresh_runtime_session = store.load_session(runtime_session_id)
            if fresh_runtime_session is None:
                raise OrchestrationRuntimeTransitionError(
                    f"Runtime session {runtime_session_id} missing during control-plane transition"
                )
            if task_id is not None and fresh_runtime_session.task_id != str(task_id):
                raise OrchestrationRuntimeTransitionError(
                    f"Runtime session {runtime_session_id} does not belong to task {task_id}"
                )

            result = action(runtime_db, store, fresh_runtime_session)
            runtime_db.info.pop(self._PAYLOAD_COMPENSATION_INFO_KEY, None)
            return result
        except Exception as transition_error:
            runtime_db.rollback()
            payload_ref = runtime_db.info.pop(self._PAYLOAD_COMPENSATION_INFO_KEY, None)
            if isinstance(payload_ref, str) and payload_ref:
                try:
                    discard_published_payload(payload_ref)
                except Exception as cleanup_error:
                    raise OrchestrationRuntimeTransitionError(
                        "Runtime transition and payload cleanup both failed: "
                        f"transition={type(transition_error).__name__}; "
                        f"cleanup={type(cleanup_error).__name__}"
                    ) from cleanup_error
            raise
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

        def _complete(
            runtime_db: Session,
            store: SqlAlchemyRuntimeAttemptStore,
            _runtime_session: RuntimeSessionRecord,
        ) -> None:
            control_plane = RuntimeAttemptControlPlane(store)
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

        def _fail(
            runtime_db: Session,
            store: SqlAlchemyRuntimeAttemptStore,
            _runtime_session: RuntimeSessionRecord,
        ) -> None:
            control_plane = RuntimeAttemptControlPlane(store)
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

        def _upsert(
            runtime_db: Session,
            store: SqlAlchemyRuntimeAttemptStore,
            _runtime_session: RuntimeSessionRecord,
        ) -> None:
            RuntimeAttemptControlPlane(store).upsert_diagnostic(
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
            runtime_db: Session,
            store: SqlAlchemyRuntimeAttemptStore,
            runtime_session: RuntimeSessionRecord,
        ) -> Dict[str, Any]:
            draft = self._context_contract_assembler.build_script_review_boundary_draft(
                workflow_state_id=workflow_id,
                script_output=script_output,
            )
            draft_payload = draft.get("payload")
            draft_summary = draft.get("summary")
            if not isinstance(draft_payload, dict) or not isinstance(draft_summary, dict):
                raise OrchestrationRuntimeTransitionError(
                    "Script review boundary draft is missing typed payload or summary"
                )
            deliverable = RuntimePublishedDeliverableControlPlane(store).publish_script(
                session_id=runtime_session_id,
                workflow_id=workflow_id,
                attempt_id=script_attempt_id,
                payload=JsonObjectPayload.from_mapping(
                    draft_payload,
                    field_path="script_review.deliverable_payload",
                ),
                summary=JsonObjectPayload.from_mapping(
                    draft_summary,
                    field_path="script_review.deliverable_summary",
                ),
            )
            runtime_db.info[self._PAYLOAD_COMPENSATION_INFO_KEY] = deliverable.payload_ref
            continuation_checkpoint = self._orchestration_state.build_continuation_checkpoint(
                task_specs=task_specs,
                conditional_task_specs=conditional_task_specs,
                candidate_agents=list(candidate_agents),
                anchor_type=OrchestrationStateAdapter.CONTINUATION_ANCHOR_GATE_DECISION,
                node_key="script",
                attempt_id=script_attempt_id,
                decision_id=None,
            )
            artifact_ref = JsonObjectPayload.from_mapping(
                build_deliverable_ref(deliverable),
                field_path="script_review.artifact_ref",
            )
            continuation_payload = JsonObjectPayload.from_mapping(
                continuation_checkpoint,
                field_path="script_review.continuation_checkpoint",
            )
            normalized_input_payload = runtime_session.input_payload.to_dict()
            review_contract = get_script_review_contract(normalized_input_payload) or {}
            target_input_payload = clear_published_deliverable_ref(
                set_script_review_contract(normalized_input_payload, None),
                node_key="script",
            )

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
            script_preview_text = str(draft.get("script_preview_text") or "")
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
                    task_id=runtime_session.task_id,
                    expected_status=runtime_session.task_status,
                    target_status=TaskStatus.IN_PROGRESS,
                    progress_step="Waiting for script approval",
                    progress_percentage=35,
                    requires_human_review=True,
                ),
            )
            runtime_db.commit()
            runtime_db.info.pop(self._PAYLOAD_COMPENSATION_INFO_KEY, None)
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
        normalized_summary = JsonObjectPayload.from_mapping(
            summary_output or {},
            field_path="runtime_session.completion_summary",
        )
        runtime_db = self._session_factory()
        try:
            store = SqlAlchemyRuntimeAttemptStore(runtime_db)
            session = store.load_session(runtime_session_id)
            if session is None:
                raise OrchestrationRuntimeTransitionError(
                    f"Runtime session {runtime_session_id} missing during completion"
                )
            if session.task_id != str(task_id):
                raise OrchestrationRuntimeTransitionError(
                    f"Runtime session {runtime_session_id} does not belong to task {task_id}"
                )
            RuntimeSessionControlPlane(store).mark_completed(
                runtime_session_id,
                summary_output=normalized_summary,
            )
            runtime_db.commit()
        except Exception:
            runtime_db.rollback()
            raise
        finally:
            runtime_db.close()

    def mark_runtime_session_failed(
        self,
        *,
        runtime_session_id: int,
        task_id: str,
        error_message: str,
    ) -> None:
        runtime_db = self._session_factory()
        try:
            store = SqlAlchemyRuntimeAttemptStore(runtime_db)
            session = store.load_session(runtime_session_id)
            if session is None:
                raise OrchestrationRuntimeTransitionError(
                    f"Runtime session {runtime_session_id} missing during failure transition"
                )
            if session.task_id != str(task_id):
                raise OrchestrationRuntimeTransitionError(
                    f"Runtime session {runtime_session_id} does not belong to task {task_id}"
                )
            RuntimeSessionControlPlane(store).mark_failed(
                runtime_session_id,
                error_message=error_message,
            )
            runtime_db.commit()
        except Exception:
            runtime_db.rollback()
            raise
        finally:
            runtime_db.close()
