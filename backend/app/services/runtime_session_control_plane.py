"""Control-plane ownership for runtime session lifecycle transitions."""

from __future__ import annotations

from ..domain import (
    JsonObjectPayload,
    RuntimeSessionAttemptTransition,
    RuntimeSessionNodeTransition,
    RuntimeSessionRecord,
    RuntimeSessionStore,
    RuntimeSessionTransitionCommand,
    RuntimeStoreError,
    RuntimeStoreReason,
    RuntimeTaskTransition,
    TaskStatus,
    WorkflowAttemptStatus,
    WorkflowNodeStatus,
    WorkflowSessionStatus,
)
from .runtime_read_model_service import RuntimeReadModelService


class RuntimeSessionControlPlane:
    """Selects session/node/attempt/task outcomes before persistence."""

    def __init__(self, store: RuntimeSessionStore) -> None:
        self._store = store

    def mark_running(self, session_id: int) -> RuntimeSessionRecord:
        session = self._session(session_id, operation="mark_runtime_session_running")
        if session.status is not WorkflowSessionStatus.QUEUED:
            self._state_conflict(
                operation="mark_runtime_session_running",
                message=f"runtime session {session_id} is not queued",
            )
        nodes = self._nodes(session_id, operation="mark_runtime_session_running")
        first_node = nodes[0]
        node_transitions: tuple[RuntimeSessionNodeTransition, ...] = ()
        if first_node.status is WorkflowNodeStatus.QUEUED:
            node_transitions = (
                RuntimeSessionNodeTransition(
                    node_key=first_node.node_key,
                    expected_status=first_node.status,
                    target_status=WorkflowNodeStatus.RUNNING,
                ),
            )
        return self._store.transition_session(
            RuntimeSessionTransitionCommand(
                session_id=session_id,
                expected_statuses=(session.status,),
                target_status=WorkflowSessionStatus.RUNNING,
                expected_current_node_key=session.current_node_key,
                expected_current_attempt_id=session.current_attempt_id,
                target_current_node_key=session.current_node_key or first_node.node_key,
                target_current_attempt_id=session.current_attempt_id,
                node_transitions=node_transitions,
                clear_error_message=True,
                task_transition=self._task_transition(
                    session,
                    target_status=TaskStatus.IN_PROGRESS,
                    clear_error_message=True,
                ),
            )
        )

    def mark_resuming(self, session_id: int) -> RuntimeSessionRecord:
        operation = "mark_runtime_session_resuming"
        model = RuntimeReadModelService(self._store).load_for_session(session_id)
        if model is None:
            self._not_found(operation=operation, session_id=session_id)
        assert model is not None
        resume_control = model.resume_control
        resume_control_data = resume_control.to_dict() if resume_control is not None else None
        if resume_control_data is None or resume_control_data.get("can_resume") is not True:
            reason_code = (
                str(resume_control_data.get("reason_code") or "resume_not_available")
                if resume_control_data is not None
                else "resume_not_available"
            )
            self._state_conflict(
                operation=operation,
                message=f"runtime session {session_id} cannot resume: {reason_code}",
            )

        session = model.session
        attempt = self._current_attempt(session, operation=operation)
        node = self._current_node(session, model.nodes, operation=operation)
        attempt_transition = RuntimeSessionAttemptTransition(
            attempt_id=attempt.attempt_id,
            expected_status=attempt.status,
            target_status=(
                WorkflowAttemptStatus.ABORTED
                if attempt.status is WorkflowAttemptStatus.RUNNING
                else attempt.status
            ),
            clear_lease=True,
        )
        node_transitions: tuple[RuntimeSessionNodeTransition, ...] = ()
        if node.status is WorkflowNodeStatus.RUNNING:
            node_transitions = (
                RuntimeSessionNodeTransition(
                    node_key=node.node_key,
                    expected_status=node.status,
                    target_status=WorkflowNodeStatus.STALE,
                ),
            )
        return self._store.transition_session(
            RuntimeSessionTransitionCommand(
                session_id=session_id,
                expected_statuses=(session.status,),
                target_status=WorkflowSessionStatus.RESUMING,
                expected_current_node_key=session.current_node_key,
                expected_current_attempt_id=session.current_attempt_id,
                target_current_node_key=session.current_node_key,
                target_current_attempt_id=session.current_attempt_id,
                node_transitions=node_transitions,
                attempt_transition=attempt_transition,
                clear_error_message=True,
                task_transition=self._task_transition(
                    session,
                    target_status=TaskStatus.IN_PROGRESS,
                    clear_error_message=True,
                ),
            )
        )

    def abandon_current_attempt_for_replan(
        self,
        session_id: int,
        *,
        node_key: str,
        attempt_id: int,
        expected_lease_token: str,
        reason: str,
    ) -> RuntimeSessionRecord:
        operation = "abandon_runtime_attempt_for_replan"
        normalized_reason = str(reason or "").strip()
        if not normalized_reason:
            raise ValueError("reason must be a non-empty string")
        session = self._session(session_id, operation=operation)
        self._require_non_terminal(session, operation=operation)
        nodes = self._nodes(session_id, operation=operation)
        node = self._current_node(session, nodes, operation=operation)
        attempt = self._current_attempt(session, operation=operation)
        if node.node_key != node_key or attempt.attempt_id != attempt_id:
            self._state_conflict(
                operation=operation,
                message="runtime replan anchor changed before attempt abandonment",
            )
        if attempt.lease_token != expected_lease_token:
            self._state_conflict(
                operation=operation,
                message="runtime replan lease changed before attempt abandonment",
            )
        if node.status is not WorkflowNodeStatus.RUNNING:
            self._state_conflict(
                operation=operation,
                message=(f"runtime node {node.node_key} must be running before standby replan"),
            )
        if attempt.status is not WorkflowAttemptStatus.RUNNING:
            self._state_conflict(
                operation=operation,
                message=(
                    f"runtime attempt {attempt.attempt_id} must be running before standby replan"
                ),
            )
        return self._store.transition_session(
            RuntimeSessionTransitionCommand(
                session_id=session_id,
                expected_statuses=(session.status,),
                target_status=session.status,
                expected_current_node_key=session.current_node_key,
                expected_current_attempt_id=session.current_attempt_id,
                target_current_node_key=session.current_node_key,
                target_current_attempt_id=session.current_attempt_id,
                node_transitions=(
                    RuntimeSessionNodeTransition(
                        node_key=node.node_key,
                        expected_status=node.status,
                        target_status=WorkflowNodeStatus.SKIPPED,
                    ),
                ),
                attempt_transition=RuntimeSessionAttemptTransition(
                    attempt_id=attempt.attempt_id,
                    expected_status=attempt.status,
                    target_status=WorkflowAttemptStatus.ABORTED,
                    clear_lease=True,
                    error_code="runtime_replan_activated",
                    error_message=normalized_reason,
                ),
                clear_error_message=True,
                task_transition=self._task_transition(
                    session,
                    target_status=TaskStatus.IN_PROGRESS,
                    clear_error_message=True,
                ),
            )
        )

    def mark_completed(
        self,
        session_id: int,
        *,
        summary_output: JsonObjectPayload,
    ) -> RuntimeSessionRecord:
        operation = "mark_runtime_session_completed"
        session = self._session(session_id, operation=operation)
        self._require_non_terminal(session, operation=operation)
        nodes = self._nodes(session_id, operation=operation)
        if any(node.status is WorkflowNodeStatus.FAILED for node in nodes):
            self._state_conflict(
                operation=operation,
                message=f"runtime session {session_id} contains a failed node",
            )

        node_transitions: list[RuntimeSessionNodeTransition] = []
        final_statuses: list[tuple[str, WorkflowNodeStatus]] = []
        for node in nodes:
            if node.status in {WorkflowNodeStatus.COMPLETED, WorkflowNodeStatus.SKIPPED}:
                target_status = node.status
            elif node.status in {WorkflowNodeStatus.QUEUED, WorkflowNodeStatus.STALE}:
                target_status = WorkflowNodeStatus.SKIPPED
            else:
                target_status = WorkflowNodeStatus.COMPLETED
            final_statuses.append((node.node_key, target_status))
            if target_status is not node.status:
                node_transitions.append(
                    RuntimeSessionNodeTransition(
                        node_key=node.node_key,
                        expected_status=node.status,
                        target_status=target_status,
                    )
                )

        attempt_transition = self._completion_attempt_transition(session, operation=operation)
        visited_node_keys = [
            node_key
            for node_key, status in final_statuses
            if status is not WorkflowNodeStatus.SKIPPED
        ]
        return self._store.transition_session(
            RuntimeSessionTransitionCommand(
                session_id=session_id,
                expected_statuses=(session.status,),
                target_status=WorkflowSessionStatus.COMPLETED,
                expected_current_node_key=session.current_node_key,
                expected_current_attempt_id=session.current_attempt_id,
                target_current_node_key=(
                    visited_node_keys[-1] if visited_node_keys else session.current_node_key
                ),
                target_current_attempt_id=session.current_attempt_id,
                node_transitions=tuple(node_transitions),
                attempt_transition=attempt_transition,
                summary_output=summary_output,
                clear_error_message=True,
                task_transition=self._task_transition(
                    session,
                    target_status=TaskStatus.COMPLETED,
                    progress_step="Completed",
                    progress_percentage=100,
                    clear_error_message=True,
                    requires_human_review=False,
                ),
            )
        )

    def mark_failed(self, session_id: int, *, error_message: str) -> RuntimeSessionRecord:
        operation = "mark_runtime_session_failed"
        normalized_error = str(error_message or "").strip()
        if not normalized_error:
            raise ValueError("error_message must be a non-empty string")
        session = self._session(session_id, operation=operation)
        self._require_non_terminal(session, operation=operation)
        nodes = self._nodes(session_id, operation=operation)
        node_transitions: tuple[RuntimeSessionNodeTransition, ...] = ()
        if session.current_node_key is not None:
            node = self._current_node(session, nodes, operation=operation)
            if node.status is not WorkflowNodeStatus.FAILED:
                node_transitions = (
                    RuntimeSessionNodeTransition(
                        node_key=node.node_key,
                        expected_status=node.status,
                        target_status=WorkflowNodeStatus.FAILED,
                    ),
                )
        attempt_transition = self._failure_attempt_transition(
            session,
            operation=operation,
            error_message=normalized_error,
        )
        return self._store.transition_session(
            RuntimeSessionTransitionCommand(
                session_id=session_id,
                expected_statuses=(session.status,),
                target_status=WorkflowSessionStatus.FAILED,
                expected_current_node_key=session.current_node_key,
                expected_current_attempt_id=session.current_attempt_id,
                target_current_node_key=session.current_node_key,
                target_current_attempt_id=session.current_attempt_id,
                node_transitions=node_transitions,
                attempt_transition=attempt_transition,
                error_message=normalized_error,
                task_transition=self._task_transition(
                    session,
                    target_status=TaskStatus.FAILED,
                    error_message=normalized_error,
                    requires_human_review=False,
                ),
            )
        )

    def mark_cancelled(self, session_id: int) -> RuntimeSessionRecord:
        operation = "mark_runtime_session_cancelled"
        session = self._session(session_id, operation=operation)
        self._require_non_terminal(session, operation=operation)
        nodes = self._nodes(session_id, operation=operation)
        node_transitions = tuple(
            RuntimeSessionNodeTransition(
                node_key=node.node_key,
                expected_status=node.status,
                target_status=WorkflowNodeStatus.SKIPPED,
            )
            for node in nodes
            if node.status
            not in {
                WorkflowNodeStatus.COMPLETED,
                WorkflowNodeStatus.FAILED,
                WorkflowNodeStatus.SKIPPED,
            }
        )
        attempt_transition = self._cancel_attempt_transition(session, operation=operation)
        return self._store.transition_session(
            RuntimeSessionTransitionCommand(
                session_id=session_id,
                expected_statuses=(session.status,),
                target_status=WorkflowSessionStatus.CANCELLED,
                expected_current_node_key=session.current_node_key,
                expected_current_attempt_id=session.current_attempt_id,
                target_current_node_key=session.current_node_key,
                target_current_attempt_id=session.current_attempt_id,
                node_transitions=node_transitions,
                attempt_transition=attempt_transition,
                clear_error_message=True,
                task_transition=self._task_transition(
                    session,
                    target_status=TaskStatus.CANCELLED,
                    clear_error_message=True,
                    requires_human_review=False,
                ),
            )
        )

    def _completion_attempt_transition(
        self,
        session: RuntimeSessionRecord,
        *,
        operation: str,
    ) -> RuntimeSessionAttemptTransition | None:
        if session.current_attempt_id is None:
            return None
        attempt = self._current_attempt(session, operation=operation)
        if attempt.status in {WorkflowAttemptStatus.FAILED, WorkflowAttemptStatus.ABORTED}:
            self._state_conflict(
                operation=operation,
                message=(
                    f"runtime session {session.session_id} current attempt "
                    f"is {attempt.status.value}"
                ),
            )
        return RuntimeSessionAttemptTransition(
            attempt_id=attempt.attempt_id,
            expected_status=attempt.status,
            target_status=(
                WorkflowAttemptStatus.SUCCEEDED
                if attempt.status is WorkflowAttemptStatus.RUNNING
                else attempt.status
            ),
            clear_lease=True,
        )

    def _failure_attempt_transition(
        self,
        session: RuntimeSessionRecord,
        *,
        operation: str,
        error_message: str,
    ) -> RuntimeSessionAttemptTransition | None:
        if session.current_attempt_id is None:
            return None
        attempt = self._current_attempt(session, operation=operation)
        return RuntimeSessionAttemptTransition(
            attempt_id=attempt.attempt_id,
            expected_status=attempt.status,
            target_status=(
                WorkflowAttemptStatus.FAILED
                if attempt.status is WorkflowAttemptStatus.RUNNING
                else attempt.status
            ),
            clear_lease=True,
            error_code=(
                "runtime_session_failed"
                if attempt.status is WorkflowAttemptStatus.RUNNING
                else None
            ),
            error_message=(
                error_message if attempt.status is WorkflowAttemptStatus.RUNNING else None
            ),
        )

    def _cancel_attempt_transition(
        self,
        session: RuntimeSessionRecord,
        *,
        operation: str,
    ) -> RuntimeSessionAttemptTransition | None:
        if session.current_attempt_id is None:
            return None
        attempt = self._current_attempt(session, operation=operation)
        return RuntimeSessionAttemptTransition(
            attempt_id=attempt.attempt_id,
            expected_status=attempt.status,
            target_status=(
                WorkflowAttemptStatus.ABORTED
                if attempt.status is WorkflowAttemptStatus.RUNNING
                else attempt.status
            ),
            clear_lease=True,
        )

    def _session(self, session_id: int, *, operation: str) -> RuntimeSessionRecord:
        session = self._store.load_session(session_id)
        if session is None:
            self._not_found(operation=operation, session_id=session_id)
        assert session is not None
        return session

    def _nodes(self, session_id: int, *, operation: str):
        nodes = self._store.load_nodes(session_id)
        if not nodes:
            raise RuntimeStoreError(
                reason_code=RuntimeStoreReason.INTEGRITY_ERROR,
                operation=operation,
                message=f"runtime session {session_id} has no workflow nodes",
            )
        return nodes

    def _current_attempt(self, session: RuntimeSessionRecord, *, operation: str):
        if session.current_attempt_id is None:
            raise RuntimeStoreError(
                reason_code=RuntimeStoreReason.INTEGRITY_ERROR,
                operation=operation,
                message=f"runtime session {session.session_id} has no current attempt anchor",
            )
        attempt = self._store.load_attempt(session.session_id, session.current_attempt_id)
        if attempt is None:
            raise RuntimeStoreError(
                reason_code=RuntimeStoreReason.INTEGRITY_ERROR,
                operation=operation,
                message=(
                    f"runtime session {session.session_id} current attempt "
                    f"{session.current_attempt_id} is missing"
                ),
            )
        return attempt

    @staticmethod
    def _current_node(session, nodes, *, operation: str):
        if session.current_node_key is not None:
            for node in nodes:
                if node.node_key == session.current_node_key:
                    return node
        raise RuntimeStoreError(
            reason_code=RuntimeStoreReason.INTEGRITY_ERROR,
            operation=operation,
            message=f"runtime session {session.session_id} current node anchor is missing",
        )

    @staticmethod
    def _require_non_terminal(session: RuntimeSessionRecord, *, operation: str) -> None:
        if session.status in {
            WorkflowSessionStatus.COMPLETED,
            WorkflowSessionStatus.FAILED,
            WorkflowSessionStatus.CANCELLED,
        }:
            RuntimeSessionControlPlane._state_conflict(
                operation=operation,
                message=(
                    f"runtime session {session.session_id} is already terminal: "
                    f"{session.status.value}"
                ),
            )

    @staticmethod
    def _task_transition(
        session: RuntimeSessionRecord,
        *,
        target_status: TaskStatus,
        progress_step: str | None = None,
        progress_percentage: int | None = None,
        error_message: str | None = None,
        clear_error_message: bool = False,
        requires_human_review: bool | None = None,
    ) -> RuntimeTaskTransition:
        return RuntimeTaskTransition(
            task_id=session.task_id,
            expected_status=session.task_status,
            target_status=target_status,
            progress_step=progress_step,
            progress_percentage=progress_percentage,
            error_message=error_message,
            clear_error_message=clear_error_message,
            requires_human_review=requires_human_review,
        )

    @staticmethod
    def _not_found(*, operation: str, session_id: int) -> None:
        raise RuntimeStoreError(
            reason_code=RuntimeStoreReason.RECORD_NOT_FOUND,
            operation=operation,
            message=f"runtime session {session_id} was not found",
        )

    @staticmethod
    def _state_conflict(*, operation: str, message: str) -> None:
        raise RuntimeStoreError(
            reason_code=RuntimeStoreReason.STATE_CONFLICT,
            operation=operation,
            message=message,
        )
