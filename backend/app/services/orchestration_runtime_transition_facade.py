"""
Orchestration-facing facade for post-execution runtime control-plane transitions.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..core.database import SessionLocal as SyncSessionLocal
from ..models import AgentType, Task
from .context_assembler import ContextContractAssembler
from .orchestration_state_adapter import OrchestrationStateAdapter
from .runtime_session_service import RuntimeSessionService


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
        task_db_id: Optional[int] = None,
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
            if task_db_id is not None:
                runtime_task = runtime_db.query(Task).filter(Task.id == int(task_db_id)).first()
                if runtime_task is None:
                    raise OrchestrationRuntimeTransitionError(
                        f"Task {task_db_id} missing during runtime control-plane transition"
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
        self._run_with_fresh_runtime_control_plane_session(
            runtime_session_id=runtime_session_id,
            action=lambda runtime_db, fresh_runtime_session, _runtime_task: RuntimeSessionService.complete_node_attempt_sync(
                runtime_db,
                fresh_runtime_session,
                node_key=node_key,
                attempt_id=attempt_id,
                lease_token=lease_token,
                node_status=node_status,
            ),
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
        self._run_with_fresh_runtime_control_plane_session(
            runtime_session_id=runtime_session_id,
            action=lambda runtime_db, fresh_runtime_session, _runtime_task: RuntimeSessionService.fail_node_attempt_sync(
                runtime_db,
                fresh_runtime_session,
                node_key=node_key,
                attempt_id=attempt_id,
                error_message=error_message,
                lease_token=lease_token,
                diagnostics=diagnostics,
            ),
        )

    def upsert_runtime_attempt_diagnostic(
        self,
        *,
        runtime_session_id: int,
        attempt_id: int,
        diagnostic: Dict[str, Any],
    ) -> None:
        self._run_with_fresh_runtime_control_plane_session(
            runtime_session_id=runtime_session_id,
            action=lambda runtime_db, fresh_runtime_session, _runtime_task: RuntimeSessionService.upsert_attempt_node_diagnostic_sync(
                runtime_db,
                fresh_runtime_session,
                attempt_id=attempt_id,
                diagnostic=diagnostic,
            ),
        )

    def open_script_review_gate(
        self,
        *,
        runtime_session_id: int,
        task_db_id: int,
        workflow_id: str,
        script_attempt_id: int,
        lease_token: Optional[str],
        trigger_reason: str,
        script_output: Dict[str, Any],
        task_specs: Dict[AgentType, Dict[str, Any]],
        conditional_task_specs: Dict[str, Dict[str, Any]],
        candidate_agents: List[AgentType],
    ) -> Dict[str, Any]:
        def _open_gate(runtime_db: Session, runtime_session: Any, runtime_task: Optional[Task]) -> Dict[str, Any]:
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
            gate = RuntimeSessionService.complete_script_attempt_and_open_review_gate_sync(
                runtime_db,
                runtime_session,
                task=runtime_task,
                workflow_state_id=workflow_id,
                attempt_id=script_attempt_id,
                trigger_reason=trigger_reason,
                script_output=script_output,
                artifact_ref=dict(boundary.get("artifact_ref") or {}),
                script_preview_text=str(boundary.get("script_preview_text") or ""),
                lease_token=lease_token,
                continuation_checkpoint=continuation_checkpoint,
            )
            return {
                "status": "waiting_gate",
                "session_id": runtime_session.id,
                "gate_id": gate.id,
                "node_key": "script",
            }

        return self._run_with_fresh_runtime_control_plane_session(
            runtime_session_id=runtime_session_id,
            task_db_id=task_db_id,
            action=_open_gate,
        )

    def mark_runtime_session_completed(
        self,
        *,
        runtime_session_id: int,
        task_db_id: int,
        summary_output: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._run_with_fresh_runtime_control_plane_session(
            runtime_session_id=runtime_session_id,
            task_db_id=task_db_id,
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
        task_db_id: int,
        error_message: str,
    ) -> None:
        self._run_with_fresh_runtime_control_plane_session(
            runtime_session_id=runtime_session_id,
            task_db_id=task_db_id,
            action=lambda runtime_db, fresh_runtime_session, runtime_task: RuntimeSessionService.mark_session_failed_sync(
                runtime_db,
                fresh_runtime_session,
                error_message=error_message,
                task=runtime_task,
            ),
        )
