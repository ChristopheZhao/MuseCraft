"""SQLAlchemy adapter for runtime attempt persistence capabilities."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from enum import Enum
from types import TracebackType
from typing import TypeVar, cast

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from ..domain import (
    JsonObjectPayload,
    RuntimeAttemptCompletionCommand,
    RuntimeAttemptFailureCommand,
    RuntimeAttemptHeartbeatCommand,
    RuntimeAttemptLeaseCommand,
    RuntimeAttemptRecord,
    RuntimeAttemptReleaseCommand,
    RuntimeAttemptStartCommand,
    RuntimeContinuationBindCommand,
    RuntimeGateDecisionApplyCommand,
    RuntimeGateDecisionCreateCommand,
    RuntimeGateDecisionRecord,
    RuntimeGateOpenCommand,
    RuntimeGateRecord,
    RuntimeNodeRecord,
    RuntimePublishedDeliverableApprovalCommand,
    RuntimePublishedDeliverableRecord,
    RuntimePublishedDeliverableWrite,
    RuntimeSessionRecord,
    RuntimeSessionTransitionCommand,
    RuntimeStoreError,
    RuntimeStoreReason,
    RuntimeTaskTransition,
    TaskStatus,
    WorkflowAttemptStatus,
    WorkflowGateStatus,
    WorkflowNodeStatus,
    WorkflowSessionStatus,
)
from ..models import (
    Task,
    WorkflowGate,
    WorkflowGateDecision,
    WorkflowNodeAttempt,
    WorkflowNodeState,
    WorkflowPublishedDeliverable,
    WorkflowSession,
)

StatusT = TypeVar("StatusT", bound=Enum)
SessionFactory = Callable[[], Session]


def _error(
    *,
    reason_code: RuntimeStoreReason,
    operation: str,
    message: str,
) -> RuntimeStoreError:
    return RuntimeStoreError(
        reason_code=reason_code,
        operation=operation,
        message=message,
    )


def _status(
    enum_type: type[StatusT],
    raw_value: object,
    *,
    operation: str,
    field_path: str,
) -> StatusT:
    if not isinstance(raw_value, str):
        raise _error(
            reason_code=RuntimeStoreReason.INTEGRITY_ERROR,
            operation=operation,
            message=f"{field_path} must contain a string enum value",
        )
    try:
        return enum_type(raw_value)
    except ValueError as exc:
        raise _error(
            reason_code=RuntimeStoreReason.INTEGRITY_ERROR,
            operation=operation,
            message=f"{field_path} contains unsupported value {raw_value!r}",
        ) from exc


def _payload(raw_value: object, *, operation: str, field_path: str) -> JsonObjectPayload:
    if raw_value is None:
        return JsonObjectPayload.empty()
    if not isinstance(raw_value, Mapping):
        raise _error(
            reason_code=RuntimeStoreReason.INTEGRITY_ERROR,
            operation=operation,
            message=f"{field_path} must contain a JSON object",
        )
    try:
        return JsonObjectPayload.from_mapping(
            cast(Mapping[str, object], raw_value),
            field_path=field_path,
        )
    except (TypeError, ValueError) as exc:
        raise _error(
            reason_code=RuntimeStoreReason.INTEGRITY_ERROR,
            operation=operation,
            message=f"{field_path} contains an invalid JSON object",
        ) from exc


def _payloads(
    raw_value: object,
    *,
    operation: str,
    field_path: str,
) -> tuple[JsonObjectPayload, ...]:
    if raw_value is None:
        return ()
    if not isinstance(raw_value, Sequence) or isinstance(raw_value, (str, bytes)):
        raise _error(
            reason_code=RuntimeStoreReason.INTEGRITY_ERROR,
            operation=operation,
            message=f"{field_path} must contain a JSON object array",
        )
    return tuple(
        _payload(item, operation=operation, field_path=f"{field_path}[{index}]")
        for index, item in enumerate(raw_value)
    )


def _strings(
    raw_value: object,
    *,
    operation: str,
    field_path: str,
) -> tuple[str, ...]:
    if raw_value is None:
        return ()
    if not isinstance(raw_value, Sequence) or isinstance(raw_value, (str, bytes)):
        raise _error(
            reason_code=RuntimeStoreReason.INTEGRITY_ERROR,
            operation=operation,
            message=f"{field_path} must contain a string array",
        )
    normalized: list[str] = []
    for index, item in enumerate(raw_value):
        if not isinstance(item, str) or not item.strip():
            raise _error(
                reason_code=RuntimeStoreReason.INTEGRITY_ERROR,
                operation=operation,
                message=f"{field_path}[{index}] must contain a non-empty string",
            )
        normalized.append(item.strip())
    return tuple(normalized)


def _utc(value: datetime, *, operation: str, field_path: str) -> datetime:
    if not isinstance(value, datetime):
        raise _error(
            reason_code=RuntimeStoreReason.INTEGRITY_ERROR,
            operation=operation,
            message=f"{field_path} must be a datetime",
        )
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class SqlAlchemyRuntimeAttemptStore:
    """Maps SQL rows to immutable attempt records without committing transactions."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def _task_for_session(
        self,
        session: WorkflowSession,
        *,
        operation: str,
        lock: bool = False,
    ) -> Task:
        statement = select(Task).where(Task.id == session.task_db_id)
        if lock:
            statement = statement.with_for_update()
        task = self._db.execute(statement).scalar_one_or_none()
        if task is None:
            raise _error(
                reason_code=RuntimeStoreReason.INTEGRITY_ERROR,
                operation=operation,
                message=f"runtime session {session.id} references a missing task",
            )
        return task

    def _locked_session(self, session_id: int, *, operation: str) -> WorkflowSession:
        session = self._db.execute(
            select(WorkflowSession)
            .where(WorkflowSession.id == session_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).scalar_one_or_none()
        if session is None:
            raise _error(
                reason_code=RuntimeStoreReason.RECORD_NOT_FOUND,
                operation=operation,
                message=f"runtime session {session_id} was not found",
            )
        return session

    def _locked_node(
        self,
        session_id: int,
        node_key: str,
        *,
        operation: str,
    ) -> WorkflowNodeState:
        node = self._db.execute(
            select(WorkflowNodeState)
            .where(
                WorkflowNodeState.session_id == session_id,
                WorkflowNodeState.node_key == node_key,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        ).scalar_one_or_none()
        if node is None:
            raise _error(
                reason_code=RuntimeStoreReason.RECORD_NOT_FOUND,
                operation=operation,
                message=f"runtime node {node_key!r} was not found in session {session_id}",
            )
        return node

    def _locked_attempt(
        self,
        session_id: int,
        attempt_id: int,
        *,
        operation: str,
    ) -> WorkflowNodeAttempt:
        attempt = self._db.execute(
            select(WorkflowNodeAttempt)
            .where(
                WorkflowNodeAttempt.id == attempt_id,
                WorkflowNodeAttempt.session_id == session_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        ).scalar_one_or_none()
        if attempt is None:
            raise _error(
                reason_code=RuntimeStoreReason.RECORD_NOT_FOUND,
                operation=operation,
                message=f"runtime attempt {attempt_id} was not found in session {session_id}",
            )
        return attempt

    def _locked_gate(
        self,
        session_id: int,
        gate_id: int,
        *,
        operation: str,
    ) -> WorkflowGate:
        gate = self._db.execute(
            select(WorkflowGate)
            .where(
                WorkflowGate.id == gate_id,
                WorkflowGate.session_id == session_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        ).scalar_one_or_none()
        if gate is None:
            raise _error(
                reason_code=RuntimeStoreReason.RECORD_NOT_FOUND,
                operation=operation,
                message=f"runtime gate {gate_id} was not found in session {session_id}",
            )
        return gate

    def _session_record(
        self,
        session: WorkflowSession,
        *,
        operation: str,
    ) -> RuntimeSessionRecord:
        task = self._task_for_session(session, operation=operation)
        return RuntimeSessionRecord(
            session_id=cast(int, session.id),
            task_id=cast(str, task.task_id),
            task_status=_status(
                TaskStatus,
                task.status,
                operation=operation,
                field_path="tasks.status",
            ),
            mode=cast(str, session.mode),
            status=_status(
                WorkflowSessionStatus,
                session.status,
                operation=operation,
                field_path="workflow_sessions.status",
            ),
            project_id=cast(str | None, session.project_id),
            episode_id=cast(str | None, session.episode_id),
            shared_memory_id=cast(str | None, session.shared_memory_id),
            current_node_key=cast(str | None, session.current_node_key),
            current_attempt_id=cast(int | None, session.current_attempt_id),
            input_payload=_payload(
                session.input_payload,
                operation=operation,
                field_path="workflow_sessions.input_payload",
            ),
            gate_policy=_payload(
                session.gate_policy,
                operation=operation,
                field_path="workflow_sessions.gate_policy",
            ),
            summary_output=_payload(
                session.summary_output,
                operation=operation,
                field_path="workflow_sessions.summary_output",
            ),
            error_message=cast(str | None, session.error_message),
            created_at=cast(datetime | None, session.created_at),
            updated_at=cast(datetime | None, session.updated_at),
        )

    @staticmethod
    def _node_record(node: WorkflowNodeState, *, operation: str) -> RuntimeNodeRecord:
        return RuntimeNodeRecord(
            node_id=cast(int, node.id),
            session_id=cast(int, node.session_id),
            node_key=cast(str, node.node_key),
            node_type=cast(str, node.node_type),
            order_index=cast(int, node.order_index),
            scope_type=cast(str, node.scope_type),
            status=_status(
                WorkflowNodeStatus,
                node.status,
                operation=operation,
                field_path="workflow_node_states.status",
            ),
            scope_ref=cast(str | None, node.scope_ref),
            revision_index=cast(int, node.revision_index),
            gate_required=bool(node.gate_required),
            last_gate_id=cast(int | None, node.last_gate_id),
            artifact_refs=_payloads(
                node.artifact_refs,
                operation=operation,
                field_path="workflow_node_states.artifact_refs",
            ),
            diagnostics=_payloads(
                node.diagnostics,
                operation=operation,
                field_path="workflow_node_states.diagnostics",
            ),
        )

    @staticmethod
    def _attempt_record(
        attempt: WorkflowNodeAttempt,
        *,
        operation: str,
    ) -> RuntimeAttemptRecord:
        last_heartbeat = cast(datetime | None, attempt.last_heartbeat_at)
        lease_expires = cast(datetime | None, attempt.lease_expires_at)
        return RuntimeAttemptRecord(
            attempt_id=cast(int, attempt.id),
            session_id=cast(int, attempt.session_id),
            node_id=cast(int, attempt.node_id),
            attempt_no=cast(int, attempt.attempt_no),
            trigger_reason=cast(str, attempt.trigger_reason),
            requested_by=cast(str, attempt.requested_by),
            status=_status(
                WorkflowAttemptStatus,
                attempt.status,
                operation=operation,
                field_path="workflow_node_attempts.status",
            ),
            input_contract=_payload(
                attempt.input_contract,
                operation=operation,
                field_path="workflow_node_attempts.input_contract",
            ),
            continuation_checkpoint=(
                _payload(
                    attempt.continuation_checkpoint,
                    operation=operation,
                    field_path="workflow_node_attempts.continuation_checkpoint",
                )
                if attempt.continuation_checkpoint is not None
                else None
            ),
            output_artifacts=_payloads(
                attempt.output_artifacts,
                operation=operation,
                field_path="workflow_node_attempts.output_artifacts",
            ),
            metrics=_payload(
                attempt.metrics,
                operation=operation,
                field_path="workflow_node_attempts.metrics",
            ),
            error_code=cast(str | None, attempt.error_code),
            error_message=cast(str | None, attempt.error_message),
            lease_token=cast(str | None, attempt.lease_token),
            lease_owner=cast(str | None, attempt.lease_owner),
            last_heartbeat_at=(
                _utc(
                    last_heartbeat,
                    operation=operation,
                    field_path="workflow_node_attempts.last_heartbeat_at",
                )
                if last_heartbeat is not None
                else None
            ),
            lease_expires_at=(
                _utc(
                    lease_expires,
                    operation=operation,
                    field_path="workflow_node_attempts.lease_expires_at",
                )
                if lease_expires is not None
                else None
            ),
        )

    @staticmethod
    def _gate_record(gate: WorkflowGate, *, operation: str) -> RuntimeGateRecord:
        return RuntimeGateRecord(
            gate_id=cast(int, gate.id),
            session_id=cast(int, gate.session_id),
            node_id=cast(int, gate.node_id),
            attempt_id=cast(int | None, gate.attempt_id),
            gate_name=cast(str, gate.gate_name),
            gate_type=cast(str, gate.gate_type),
            status=_status(
                WorkflowGateStatus,
                gate.status,
                operation=operation,
                field_path="workflow_gates.status",
            ),
            contract_version=cast(str, gate.contract_version),
            scope=_payload(
                gate.scope,
                operation=operation,
                field_path="workflow_gates.scope",
            ),
            artifact_refs=_payloads(
                gate.artifact_refs,
                operation=operation,
                field_path="workflow_gates.artifact_refs",
            ),
            facts=_payload(
                gate.facts,
                operation=operation,
                field_path="workflow_gates.facts",
            ),
            result_code=cast(str | None, gate.result_code),
            reason_code=cast(str | None, gate.reason_code),
            diagnostics=_payloads(
                gate.diagnostics,
                operation=operation,
                field_path="workflow_gates.diagnostics",
            ),
            allowed_actions=_strings(
                gate.allowed_actions,
                operation=operation,
                field_path="workflow_gates.allowed_actions",
            ),
            recommended_action=cast(str | None, gate.recommended_action),
            created_at=cast(datetime | None, gate.created_at),
            updated_at=cast(datetime | None, gate.updated_at),
        )

    @staticmethod
    def _gate_decision_record(
        decision: WorkflowGateDecision,
        *,
        operation: str,
    ) -> RuntimeGateDecisionRecord:
        return RuntimeGateDecisionRecord(
            decision_id=cast(int, decision.id),
            gate_id=cast(int, decision.gate_id),
            session_id=cast(int, decision.session_id),
            node_id=cast(int, decision.node_id),
            action=cast(str, decision.action),
            actor_type=cast(str, decision.actor_type),
            actor_id=cast(str | None, decision.actor_id),
            feedback_text=cast(str | None, decision.feedback_text),
            structured_constraints=_payload(
                decision.structured_constraints,
                operation=operation,
                field_path="workflow_gate_decisions.structured_constraints",
            ),
            invalidation_scope=cast(str, decision.invalidation_scope),
            created_at=cast(datetime | None, decision.created_at),
            updated_at=cast(datetime | None, decision.updated_at),
        )

    @staticmethod
    def _published_deliverable_record(
        deliverable: WorkflowPublishedDeliverable,
        *,
        operation: str,
    ) -> RuntimePublishedDeliverableRecord:
        return RuntimePublishedDeliverableRecord(
            deliverable_id=cast(int, deliverable.id),
            session_id=cast(int, deliverable.session_id),
            node_id=cast(int, deliverable.node_id),
            attempt_id=cast(int, deliverable.attempt_id),
            deliverable_type=cast(str, deliverable.deliverable_type),
            scope_type=cast(str, deliverable.scope_type),
            revision_no=cast(int, deliverable.revision_no),
            payload_ref=cast(str, deliverable.payload_ref),
            scope_id=cast(str | None, deliverable.scope_id),
            summary=_payload(
                deliverable.summary,
                operation=operation,
                field_path="workflow_published_deliverables.summary",
            ),
            is_candidate=bool(deliverable.is_candidate),
            is_approved=bool(deliverable.is_approved),
        )

    def _apply_task_transition(
        self,
        session: WorkflowSession,
        transition: RuntimeTaskTransition | None,
        *,
        operation: str,
    ) -> None:
        if transition is None:
            return
        task = self._task_for_session(session, operation=operation, lock=True)
        if task.task_id != transition.task_id:
            raise _error(
                reason_code=RuntimeStoreReason.STATE_CONFLICT,
                operation=operation,
                message="task transition does not belong to the runtime session",
            )
        if (
            transition.expected_status is not None
            and task.status != transition.expected_status.value
        ):
            raise _error(
                reason_code=RuntimeStoreReason.STATE_CONFLICT,
                operation=operation,
                message=(
                    f"task {transition.task_id} status conflict: "
                    f"expected={transition.expected_status.value} actual={task.status}"
                ),
            )
        if (
            transition.progress_percentage is not None
            and not 0 <= transition.progress_percentage <= 100
        ):
            raise _error(
                reason_code=RuntimeStoreReason.INTEGRITY_ERROR,
                operation=operation,
                message="task progress_percentage must be between 0 and 100",
            )
        setattr(task, "status", transition.target_status.value)
        if transition.progress_step is not None:
            setattr(task, "current_step", transition.progress_step)
        if transition.progress_percentage is not None:
            setattr(task, "progress_percentage", transition.progress_percentage)
        if transition.error_message is not None:
            setattr(task, "error_message", transition.error_message)
        elif transition.clear_error_message:
            setattr(task, "error_message", None)
        if transition.requires_human_review is not None:
            setattr(task, "requires_human_review", transition.requires_human_review)

    def load_session(self, session_id: int) -> RuntimeSessionRecord | None:
        operation = "load_session"
        session = self._db.get(WorkflowSession, session_id)
        if session is None:
            return None
        return self._session_record(session, operation=operation)

    def load_latest_session_for_task(self, task_id: str) -> RuntimeSessionRecord | None:
        operation = "load_latest_session_for_task"
        session = (
            self._db.execute(
                select(WorkflowSession)
                .join(Task, Task.id == WorkflowSession.task_db_id)
                .where(Task.task_id == task_id)
                .order_by(WorkflowSession.id.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )
        if session is None:
            return None
        return self._session_record(session, operation=operation)

    def load_reconcilable_sessions(
        self,
        *,
        mode: str,
        statuses: tuple[WorkflowSessionStatus, ...],
        limit: int,
    ) -> tuple[RuntimeSessionRecord, ...]:
        operation = "load_reconcilable_sessions"
        normalized_mode = str(mode or "").strip().lower()
        if not normalized_mode or not statuses or limit <= 0:
            raise _error(
                reason_code=RuntimeStoreReason.INTEGRITY_ERROR,
                operation=operation,
                message="runtime reconcile query requires mode, statuses, and a positive limit",
            )
        sessions = (
            self._db.execute(
                select(WorkflowSession)
                .where(
                    WorkflowSession.mode == normalized_mode,
                    WorkflowSession.status.in_(status.value for status in statuses),
                )
                .order_by(WorkflowSession.updated_at.asc(), WorkflowSession.id.asc())
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return tuple(self._session_record(session, operation=operation) for session in sessions)

    def load_nodes(self, session_id: int) -> tuple[RuntimeNodeRecord, ...]:
        operation = "load_nodes"
        nodes = (
            self._db.execute(
                select(WorkflowNodeState)
                .where(WorkflowNodeState.session_id == session_id)
                .order_by(WorkflowNodeState.order_index.asc(), WorkflowNodeState.id.asc())
            )
            .scalars()
            .all()
        )
        return tuple(self._node_record(node, operation=operation) for node in nodes)

    def load_node(self, session_id: int, node_key: str) -> RuntimeNodeRecord | None:
        operation = "load_node"
        node = self._db.execute(
            select(WorkflowNodeState).where(
                WorkflowNodeState.session_id == session_id,
                WorkflowNodeState.node_key == node_key,
            )
        ).scalar_one_or_none()
        if node is None:
            return None
        return self._node_record(node, operation=operation)

    def load_attempt(self, session_id: int, attempt_id: int) -> RuntimeAttemptRecord | None:
        operation = "load_attempt"
        attempt = self._db.execute(
            select(WorkflowNodeAttempt).where(
                WorkflowNodeAttempt.id == attempt_id,
                WorkflowNodeAttempt.session_id == session_id,
            )
        ).scalar_one_or_none()
        if attempt is None:
            return None
        return self._attempt_record(attempt, operation=operation)

    def load_latest_gate(
        self,
        session_id: int,
        node_key: str | None = None,
    ) -> RuntimeGateRecord | None:
        operation = "load_latest_gate"
        statement = select(WorkflowGate).where(WorkflowGate.session_id == session_id)
        if node_key is not None:
            statement = statement.join(
                WorkflowNodeState,
                WorkflowNodeState.id == WorkflowGate.node_id,
            ).where(WorkflowNodeState.node_key == node_key)
        gate = self._db.execute(statement.order_by(WorkflowGate.id.desc())).scalars().first()
        if gate is None:
            return None
        return self._gate_record(gate, operation=operation)

    def load_latest_gate_decision(self, gate_id: int) -> RuntimeGateDecisionRecord | None:
        operation = "load_latest_gate_decision"
        decision = (
            self._db.execute(
                select(WorkflowGateDecision)
                .where(WorkflowGateDecision.gate_id == gate_id)
                .order_by(WorkflowGateDecision.id.desc())
            )
            .scalars()
            .first()
        )
        if decision is None:
            return None
        return self._gate_decision_record(decision, operation=operation)

    def load_published_deliverable(
        self,
        session_id: int,
        node_key: str,
        attempt_id: int,
    ) -> RuntimePublishedDeliverableRecord | None:
        operation = "load_published_deliverable"
        node = self._db.execute(
            select(WorkflowNodeState).where(
                WorkflowNodeState.session_id == session_id,
                WorkflowNodeState.node_key == node_key,
            )
        ).scalar_one_or_none()
        if node is None:
            return None
        deliverable = (
            self._db.execute(
                select(WorkflowPublishedDeliverable)
                .where(
                    WorkflowPublishedDeliverable.session_id == session_id,
                    WorkflowPublishedDeliverable.node_id == node.id,
                    WorkflowPublishedDeliverable.attempt_id == attempt_id,
                )
                .order_by(WorkflowPublishedDeliverable.id.desc())
            )
            .scalars()
            .first()
        )
        if deliverable is None:
            return None
        return self._published_deliverable_record(deliverable, operation=operation)

    def publish_deliverable(
        self,
        command: RuntimePublishedDeliverableWrite,
    ) -> RuntimePublishedDeliverableRecord:
        operation = "publish_deliverable"
        session = self._locked_session(command.session_id, operation=operation)
        node = self._locked_node(command.session_id, command.node_key, operation=operation)
        attempt = self._locked_attempt(
            command.session_id,
            command.attempt_id,
            operation=operation,
        )
        if session.status != command.expected_session_status.value:
            raise _error(
                reason_code=RuntimeStoreReason.STATE_CONFLICT,
                operation=operation,
                message="runtime session status changed before deliverable publication",
            )
        if node.status != command.expected_node_status.value:
            raise _error(
                reason_code=RuntimeStoreReason.STATE_CONFLICT,
                operation=operation,
                message="runtime node status changed before deliverable publication",
            )
        if attempt.status != command.expected_attempt_status.value:
            raise _error(
                reason_code=RuntimeStoreReason.STATE_CONFLICT,
                operation=operation,
                message="runtime attempt status changed before deliverable publication",
            )
        if attempt.node_id != node.id:
            raise _error(
                reason_code=RuntimeStoreReason.STATE_CONFLICT,
                operation=operation,
                message="runtime attempt does not belong to the deliverable node",
            )
        deliverable = WorkflowPublishedDeliverable()
        setattr(deliverable, "session_id", session.id)
        setattr(deliverable, "node_id", node.id)
        setattr(deliverable, "attempt_id", attempt.id)
        setattr(deliverable, "deliverable_type", command.deliverable_type)
        setattr(deliverable, "scope_type", command.scope_type)
        setattr(deliverable, "scope_id", command.scope_id)
        setattr(deliverable, "revision_no", command.revision_no)
        setattr(deliverable, "payload_ref", command.payload_ref)
        setattr(deliverable, "summary", command.summary.to_dict())
        setattr(deliverable, "is_candidate", command.is_candidate)
        setattr(deliverable, "is_approved", command.is_approved)
        self._db.add(deliverable)
        self._db.flush()
        return self._published_deliverable_record(deliverable, operation=operation)

    def approve_deliverable(
        self,
        command: RuntimePublishedDeliverableApprovalCommand,
    ) -> RuntimePublishedDeliverableRecord:
        operation = "approve_deliverable"
        node = self._locked_node(command.session_id, command.node_key, operation=operation)
        attempt = self._locked_attempt(
            command.session_id,
            command.attempt_id,
            operation=operation,
        )
        deliverable = self._db.execute(
            select(WorkflowPublishedDeliverable)
            .where(
                WorkflowPublishedDeliverable.id == command.deliverable_id,
                WorkflowPublishedDeliverable.session_id == command.session_id,
                WorkflowPublishedDeliverable.node_id == node.id,
                WorkflowPublishedDeliverable.attempt_id == attempt.id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        ).scalar_one_or_none()
        if deliverable is None:
            raise _error(
                reason_code=RuntimeStoreReason.RECORD_NOT_FOUND,
                operation=operation,
                message="runtime published deliverable was not found for approval",
            )
        if (
            bool(deliverable.is_candidate) is not command.expected_is_candidate
            or bool(deliverable.is_approved) is not command.expected_is_approved
        ):
            raise _error(
                reason_code=RuntimeStoreReason.STATE_CONFLICT,
                operation=operation,
                message="runtime published deliverable approval state changed",
            )
        setattr(deliverable, "is_candidate", command.target_is_candidate)
        setattr(deliverable, "is_approved", command.target_is_approved)
        self._db.flush()
        return self._published_deliverable_record(deliverable, operation=operation)

    def start_attempt(self, command: RuntimeAttemptStartCommand) -> RuntimeAttemptRecord:
        operation = "start_attempt"
        session = self._locked_session(command.session_id, operation=operation)
        node = self._locked_node(command.session_id, command.node_key, operation=operation)
        if session.status != command.expected_session_status.value:
            raise _error(
                reason_code=RuntimeStoreReason.STATE_CONFLICT,
                operation=operation,
                message=(
                    f"runtime session status conflict: expected={command.expected_session_status.value} "
                    f"actual={session.status}"
                ),
            )
        if (
            command.expected_node_status is not None
            and node.status != command.expected_node_status.value
        ):
            raise _error(
                reason_code=RuntimeStoreReason.STATE_CONFLICT,
                operation=operation,
                message=(
                    f"runtime node status conflict: expected={command.expected_node_status.value} "
                    f"actual={node.status}"
                ),
            )
        latest_attempt_no = self._db.execute(
            select(func.max(WorkflowNodeAttempt.attempt_no)).where(
                WorkflowNodeAttempt.node_id == node.id
            )
        ).scalar_one()
        attempt = WorkflowNodeAttempt()
        setattr(attempt, "session_id", session.id)
        setattr(attempt, "node_id", node.id)
        setattr(attempt, "attempt_no", int(latest_attempt_no or 0) + 1)
        setattr(attempt, "trigger_reason", command.trigger_reason)
        setattr(attempt, "requested_by", command.requested_by)
        setattr(attempt, "input_contract", command.input_contract.to_dict())
        setattr(attempt, "status", command.target_attempt_status.value)
        self._db.add(attempt)
        self._db.flush()

        setattr(session, "status", command.target_session_status.value)
        setattr(session, "current_node_key", node.node_key)
        setattr(session, "current_attempt_id", attempt.id)
        setattr(session, "error_message", None)
        setattr(node, "status", command.target_node_status.value)
        self._apply_task_transition(session, command.task_transition, operation=operation)
        self._db.flush()
        return self._attempt_record(attempt, operation=operation)

    def grant_attempt_lease(self, command: RuntimeAttemptLeaseCommand) -> RuntimeAttemptRecord:
        operation = "grant_attempt_lease"
        attempt = self._locked_attempt(command.session_id, command.attempt_id, operation=operation)
        if attempt.status != command.expected_attempt_status.value:
            raise _error(
                reason_code=RuntimeStoreReason.STATE_CONFLICT,
                operation=operation,
                message="runtime attempt status does not permit lease grant",
            )
        if (
            cast(str | None, attempt.lease_token) is not None
            or cast(str | None, attempt.lease_owner) is not None
        ):
            raise _error(
                reason_code=RuntimeStoreReason.LEASE_CONFLICT,
                operation=operation,
                message="runtime attempt already has an execution lease",
            )
        heartbeat_at = _utc(
            command.heartbeat_at,
            operation=operation,
            field_path="command.heartbeat_at",
        )
        lease_expires_at = _utc(
            command.lease_expires_at,
            operation=operation,
            field_path="command.lease_expires_at",
        )
        if not command.lease_owner.strip() or not command.lease_token.strip():
            raise _error(
                reason_code=RuntimeStoreReason.INTEGRITY_ERROR,
                operation=operation,
                message="lease owner and token must be non-empty",
            )
        if lease_expires_at <= heartbeat_at:
            raise _error(
                reason_code=RuntimeStoreReason.INTEGRITY_ERROR,
                operation=operation,
                message="lease_expires_at must be after heartbeat_at",
            )
        setattr(attempt, "lease_token", command.lease_token)
        setattr(attempt, "lease_owner", command.lease_owner)
        setattr(attempt, "last_heartbeat_at", heartbeat_at)
        setattr(attempt, "lease_expires_at", lease_expires_at)
        self._db.flush()
        return self._attempt_record(attempt, operation=operation)

    def heartbeat_attempt_lease(
        self,
        command: RuntimeAttemptHeartbeatCommand,
    ) -> RuntimeAttemptRecord:
        operation = "heartbeat_attempt_lease"
        attempt = self._locked_attempt(command.session_id, command.attempt_id, operation=operation)
        if attempt.status != command.expected_attempt_status.value:
            raise _error(
                reason_code=RuntimeStoreReason.STATE_CONFLICT,
                operation=operation,
                message="runtime attempt status does not permit lease heartbeat",
            )
        if attempt.lease_token != command.lease_token or not attempt.lease_owner:
            raise _error(
                reason_code=RuntimeStoreReason.LEASE_CONFLICT,
                operation=operation,
                message="runtime attempt execution lease token mismatch",
            )
        heartbeat_at = _utc(
            command.heartbeat_at,
            operation=operation,
            field_path="command.heartbeat_at",
        )
        lease_expires_at = _utc(
            command.lease_expires_at,
            operation=operation,
            field_path="command.lease_expires_at",
        )
        current_expiry = cast(datetime | None, attempt.lease_expires_at)
        current_heartbeat = cast(datetime | None, attempt.last_heartbeat_at)
        if (
            current_expiry is None
            or _utc(
                current_expiry,
                operation=operation,
                field_path="workflow_node_attempts.lease_expires_at",
            )
            <= heartbeat_at
        ):
            raise _error(
                reason_code=RuntimeStoreReason.LEASE_CONFLICT,
                operation=operation,
                message="runtime attempt execution lease expired",
            )
        if (
            current_heartbeat is not None
            and _utc(
                current_heartbeat,
                operation=operation,
                field_path="workflow_node_attempts.last_heartbeat_at",
            )
            > heartbeat_at
        ):
            raise _error(
                reason_code=RuntimeStoreReason.LEASE_CONFLICT,
                operation=operation,
                message="runtime attempt heartbeat is stale",
            )
        if lease_expires_at <= heartbeat_at:
            raise _error(
                reason_code=RuntimeStoreReason.INTEGRITY_ERROR,
                operation=operation,
                message="lease_expires_at must be after heartbeat_at",
            )
        setattr(attempt, "last_heartbeat_at", heartbeat_at)
        setattr(attempt, "lease_expires_at", lease_expires_at)
        self._db.flush()
        return self._attempt_record(attempt, operation=operation)

    def release_attempt_lease(self, command: RuntimeAttemptReleaseCommand) -> RuntimeAttemptRecord:
        operation = "release_attempt_lease"
        attempt = self._locked_attempt(command.session_id, command.attempt_id, operation=operation)
        if (
            command.expected_attempt_status is not None
            and attempt.status != command.expected_attempt_status.value
        ):
            raise _error(
                reason_code=RuntimeStoreReason.STATE_CONFLICT,
                operation=operation,
                message="runtime attempt status does not permit lease release",
            )
        if command.lease_token is not None and attempt.lease_token != command.lease_token:
            raise _error(
                reason_code=RuntimeStoreReason.LEASE_CONFLICT,
                operation=operation,
                message="runtime attempt execution lease token mismatch",
            )
        setattr(attempt, "lease_token", None)
        setattr(attempt, "lease_owner", None)
        setattr(attempt, "last_heartbeat_at", None)
        setattr(attempt, "lease_expires_at", None)
        self._db.flush()
        return self._attempt_record(attempt, operation=operation)

    def bind_attempt_continuation(
        self,
        command: RuntimeContinuationBindCommand,
    ) -> RuntimeAttemptRecord:
        operation = "bind_attempt_continuation"
        attempt = self._locked_attempt(command.session_id, command.attempt_id, operation=operation)
        if attempt.status != command.expected_attempt_status.value:
            raise _error(
                reason_code=RuntimeStoreReason.STATE_CONFLICT,
                operation=operation,
                message="runtime attempt status does not permit continuation binding",
            )
        setattr(
            attempt,
            "continuation_checkpoint",
            command.continuation_checkpoint.to_dict(),
        )
        self._db.flush()
        return self._attempt_record(attempt, operation=operation)

    @staticmethod
    def _validate_attempt_lease(
        attempt: WorkflowNodeAttempt,
        *,
        expected_lease_token: str | None,
        observed_at: datetime,
        operation: str,
    ) -> None:
        actual_token = cast(str | None, attempt.lease_token)
        lease_owner = cast(str | None, attempt.lease_owner)
        lease_expires_at = cast(datetime | None, attempt.lease_expires_at)
        if expected_lease_token is None:
            if actual_token is not None or lease_owner is not None or lease_expires_at is not None:
                raise _error(
                    reason_code=RuntimeStoreReason.LEASE_CONFLICT,
                    operation=operation,
                    message="runtime attempt has an execution lease but no token was supplied",
                )
            return
        if actual_token != expected_lease_token or not lease_owner:
            raise _error(
                reason_code=RuntimeStoreReason.LEASE_CONFLICT,
                operation=operation,
                message="runtime attempt execution lease token mismatch",
            )
        if lease_expires_at is None or _utc(
            lease_expires_at,
            operation=operation,
            field_path="workflow_node_attempts.lease_expires_at",
        ) <= _utc(observed_at, operation=operation, field_path="command.observed_at"):
            raise _error(
                reason_code=RuntimeStoreReason.LEASE_CONFLICT,
                operation=operation,
                message="runtime attempt execution lease expired",
            )

    @staticmethod
    def _clear_attempt_lease(attempt: WorkflowNodeAttempt) -> None:
        setattr(attempt, "lease_token", None)
        setattr(attempt, "lease_owner", None)
        setattr(attempt, "last_heartbeat_at", None)
        setattr(attempt, "lease_expires_at", None)

    @staticmethod
    def _require_attempt_transition_state(
        *,
        session: WorkflowSession,
        node: WorkflowNodeState,
        attempt: WorkflowNodeAttempt,
        expected_session_status: WorkflowSessionStatus,
        expected_node_status: WorkflowNodeStatus,
        expected_attempt_status: WorkflowAttemptStatus,
        operation: str,
    ) -> None:
        if attempt.node_id != node.id:
            raise _error(
                reason_code=RuntimeStoreReason.STATE_CONFLICT,
                operation=operation,
                message="runtime attempt does not belong to the requested node",
            )
        if session.status != expected_session_status.value:
            raise _error(
                reason_code=RuntimeStoreReason.STATE_CONFLICT,
                operation=operation,
                message="runtime session status changed before attempt transition",
            )
        if node.status != expected_node_status.value:
            raise _error(
                reason_code=RuntimeStoreReason.STATE_CONFLICT,
                operation=operation,
                message="runtime node status changed before attempt transition",
            )
        if attempt.status != expected_attempt_status.value:
            raise _error(
                reason_code=RuntimeStoreReason.STATE_CONFLICT,
                operation=operation,
                message="runtime attempt status changed before transition",
            )

    def complete_attempt(
        self,
        command: RuntimeAttemptCompletionCommand,
    ) -> RuntimeAttemptRecord:
        operation = "complete_attempt"
        session = self._locked_session(command.session_id, operation=operation)
        node = self._locked_node(command.session_id, command.node_key, operation=operation)
        attempt = self._locked_attempt(command.session_id, command.attempt_id, operation=operation)
        self._require_attempt_transition_state(
            session=session,
            node=node,
            attempt=attempt,
            expected_session_status=command.expected_session_status,
            expected_node_status=command.expected_node_status,
            expected_attempt_status=command.expected_attempt_status,
            operation=operation,
        )
        self._validate_attempt_lease(
            attempt,
            expected_lease_token=command.expected_lease_token,
            observed_at=command.observed_at,
            operation=operation,
        )

        setattr(attempt, "status", command.target_attempt_status.value)
        self._clear_attempt_lease(attempt)
        setattr(
            attempt,
            "output_artifacts",
            [payload.to_dict() for payload in command.output_artifacts],
        )
        setattr(attempt, "metrics", command.metrics.to_dict())
        if command.continuation_checkpoint is not None:
            setattr(
                attempt,
                "continuation_checkpoint",
                command.continuation_checkpoint.to_dict(),
            )
        if command.node_artifact_refs is not None:
            setattr(
                node,
                "artifact_refs",
                [payload.to_dict() for payload in command.node_artifact_refs],
            )
        if command.node_diagnostics is not None:
            setattr(
                node,
                "diagnostics",
                [payload.to_dict() for payload in command.node_diagnostics],
            )
        setattr(node, "status", command.target_node_status.value)
        setattr(session, "status", command.target_session_status.value)
        setattr(session, "current_node_key", node.node_key)
        setattr(session, "current_attempt_id", attempt.id)
        setattr(session, "error_message", None)
        self._apply_task_transition(session, command.task_transition, operation=operation)
        self._db.flush()
        return self._attempt_record(attempt, operation=operation)

    def fail_attempt(self, command: RuntimeAttemptFailureCommand) -> RuntimeAttemptRecord:
        operation = "fail_attempt"
        session = self._locked_session(command.session_id, operation=operation)
        node = self._locked_node(command.session_id, command.node_key, operation=operation)
        attempt = self._locked_attempt(command.session_id, command.attempt_id, operation=operation)
        self._require_attempt_transition_state(
            session=session,
            node=node,
            attempt=attempt,
            expected_session_status=command.expected_session_status,
            expected_node_status=command.expected_node_status,
            expected_attempt_status=command.expected_attempt_status,
            operation=operation,
        )
        self._validate_attempt_lease(
            attempt,
            expected_lease_token=command.expected_lease_token,
            observed_at=command.observed_at,
            operation=operation,
        )

        setattr(attempt, "status", command.target_attempt_status.value)
        self._clear_attempt_lease(attempt)
        setattr(
            attempt,
            "output_artifacts",
            [payload.to_dict() for payload in command.output_artifacts],
        )
        setattr(attempt, "metrics", command.metrics.to_dict())
        setattr(attempt, "error_code", command.error_code)
        setattr(attempt, "error_message", command.error_message)
        if command.node_artifact_refs is not None:
            setattr(
                node,
                "artifact_refs",
                [payload.to_dict() for payload in command.node_artifact_refs],
            )
        setattr(
            node,
            "diagnostics",
            [payload.to_dict() for payload in command.diagnostics],
        )
        setattr(node, "status", command.target_node_status.value)
        setattr(session, "status", command.target_session_status.value)
        setattr(session, "current_node_key", node.node_key)
        setattr(session, "current_attempt_id", attempt.id)
        setattr(session, "error_message", command.error_message)
        self._apply_task_transition(session, command.task_transition, operation=operation)
        self._db.flush()
        return self._attempt_record(attempt, operation=operation)

    def upsert_node_diagnostic(
        self,
        *,
        session_id: int,
        attempt_id: int,
        diagnostic: JsonObjectPayload,
    ) -> RuntimeNodeRecord:
        operation = "upsert_node_diagnostic"
        attempt = self._locked_attempt(session_id, attempt_id, operation=operation)
        node = self._db.execute(
            select(WorkflowNodeState)
            .where(
                WorkflowNodeState.id == attempt.node_id,
                WorkflowNodeState.session_id == session_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        ).scalar_one_or_none()
        if node is None:
            raise _error(
                reason_code=RuntimeStoreReason.INTEGRITY_ERROR,
                operation=operation,
                message="runtime attempt references a missing node",
            )

        incoming = diagnostic.to_dict()
        existing = [
            payload.to_dict()
            for payload in _payloads(
                node.diagnostics,
                operation=operation,
                field_path="workflow_node_states.diagnostics",
            )
        ]
        code = str(incoming.get("code") or "").strip()
        diagnostic_attempt_id = incoming.get("attempt_id")
        matching_indices = [
            index
            for index, item in enumerate(existing)
            if code
            and str(item.get("code") or "").strip() == code
            and (diagnostic_attempt_id is None or item.get("attempt_id") == diagnostic_attempt_id)
        ]
        if matching_indices:
            existing[matching_indices[0]] = incoming
            for duplicate_index in reversed(matching_indices[1:]):
                del existing[duplicate_index]
        else:
            existing.append(incoming)
        setattr(node, "diagnostics", existing)
        self._db.flush()
        return self._node_record(node, operation=operation)

    def open_gate(self, command: RuntimeGateOpenCommand) -> RuntimeGateRecord:
        operation = "open_gate"
        session = self._locked_session(command.session_id, operation=operation)
        node = self._locked_node(command.session_id, command.node_key, operation=operation)
        attempt = None
        if command.attempt_id is not None:
            attempt = self._locked_attempt(
                command.session_id,
                command.attempt_id,
                operation=operation,
            )
            if attempt.node_id != node.id:
                raise _error(
                    reason_code=RuntimeStoreReason.STATE_CONFLICT,
                    operation=operation,
                    message="runtime gate attempt does not belong to the requested node",
                )
        elif command.expected_lease_token is not None:
            raise _error(
                reason_code=RuntimeStoreReason.INTEGRITY_ERROR,
                operation=operation,
                message="gate lease validation requires attempt_id",
            )

        if session.status != command.expected_session_status.value:
            raise _error(
                reason_code=RuntimeStoreReason.STATE_CONFLICT,
                operation=operation,
                message="runtime session status changed before gate open",
            )
        if node.status != command.expected_node_status.value:
            raise _error(
                reason_code=RuntimeStoreReason.STATE_CONFLICT,
                operation=operation,
                message="runtime node status changed before gate open",
            )
        if attempt is not None:
            if (
                command.expected_attempt_status is not None
                and attempt.status != command.expected_attempt_status.value
            ):
                raise _error(
                    reason_code=RuntimeStoreReason.STATE_CONFLICT,
                    operation=operation,
                    message="runtime attempt status changed before gate open",
                )
            self._validate_attempt_lease(
                attempt,
                expected_lease_token=command.expected_lease_token,
                observed_at=command.observed_at,
                operation=operation,
            )

        gate = WorkflowGate()
        setattr(gate, "session_id", session.id)
        setattr(gate, "node_id", node.id)
        setattr(gate, "attempt_id", command.attempt_id)
        setattr(gate, "gate_name", command.gate_name)
        setattr(gate, "gate_type", command.gate_type)
        setattr(gate, "status", command.target_gate_status.value)
        setattr(gate, "contract_version", command.contract_version)
        setattr(gate, "scope", command.scope.to_dict())
        setattr(
            gate,
            "artifact_refs",
            [payload.to_dict() for payload in command.artifact_refs],
        )
        setattr(gate, "facts", command.facts.to_dict())
        setattr(gate, "result_code", command.result_code)
        setattr(gate, "reason_code", command.reason_code)
        setattr(
            gate,
            "diagnostics",
            [payload.to_dict() for payload in command.diagnostics],
        )
        setattr(gate, "allowed_actions", list(command.allowed_actions))
        setattr(gate, "recommended_action", command.recommended_action)
        self._db.add(gate)
        self._db.flush()

        if attempt is not None and command.release_attempt_lease:
            self._clear_attempt_lease(attempt)
        setattr(node, "last_gate_id", gate.id)
        setattr(node, "status", command.target_node_status.value)
        if command.node_artifact_refs is not None:
            setattr(
                node,
                "artifact_refs",
                [payload.to_dict() for payload in command.node_artifact_refs],
            )
        if command.node_diagnostics is not None:
            setattr(
                node,
                "diagnostics",
                [payload.to_dict() for payload in command.node_diagnostics],
            )
        setattr(session, "status", command.target_session_status.value)
        setattr(session, "current_node_key", node.node_key)
        setattr(session, "current_attempt_id", command.attempt_id)
        if command.session_input_payload is not None:
            setattr(session, "input_payload", command.session_input_payload.to_dict())
        self._apply_task_transition(session, command.task_transition, operation=operation)
        self._db.flush()
        return self._gate_record(gate, operation=operation)

    def create_gate_decision(
        self,
        command: RuntimeGateDecisionCreateCommand,
    ) -> RuntimeGateDecisionRecord:
        operation = "create_gate_decision"
        session = self._locked_session(command.session_id, operation=operation)
        node = self._locked_node(command.session_id, command.node_key, operation=operation)
        gate = self._locked_gate(command.session_id, command.gate_id, operation=operation)
        if gate.node_id != node.id:
            raise _error(
                reason_code=RuntimeStoreReason.STATE_CONFLICT,
                operation=operation,
                message="runtime gate does not belong to the requested node",
            )
        if gate.status != command.expected_gate_status.value:
            raise _error(
                reason_code=RuntimeStoreReason.STATE_CONFLICT,
                operation=operation,
                message="runtime gate status changed before decision creation",
            )
        allowed_actions = _strings(
            gate.allowed_actions,
            operation=operation,
            field_path="workflow_gates.allowed_actions",
        )
        if allowed_actions and command.action not in allowed_actions:
            raise _error(
                reason_code=RuntimeStoreReason.STATE_CONFLICT,
                operation=operation,
                message=f"action {command.action!r} is not allowed for runtime gate",
            )

        decision = WorkflowGateDecision()
        setattr(decision, "gate_id", gate.id)
        setattr(decision, "session_id", session.id)
        setattr(decision, "node_id", node.id)
        setattr(decision, "action", command.action)
        setattr(decision, "actor_type", command.actor_type)
        setattr(decision, "actor_id", command.actor_id)
        setattr(decision, "feedback_text", command.feedback_text)
        setattr(
            decision,
            "structured_constraints",
            command.structured_constraints.to_dict(),
        )
        setattr(decision, "invalidation_scope", command.invalidation_scope)
        self._db.add(decision)
        self._db.flush()
        return self._gate_decision_record(decision, operation=operation)

    def apply_gate_decision(
        self,
        command: RuntimeGateDecisionApplyCommand,
    ) -> RuntimeGateDecisionRecord:
        operation = "apply_gate_decision"
        session = self._locked_session(command.session_id, operation=operation)
        node = self._locked_node(command.session_id, command.node_key, operation=operation)
        gate = self._locked_gate(command.session_id, command.gate_id, operation=operation)
        decision = self._db.execute(
            select(WorkflowGateDecision)
            .where(
                WorkflowGateDecision.id == command.decision_id,
                WorkflowGateDecision.gate_id == command.gate_id,
                WorkflowGateDecision.session_id == command.session_id,
                WorkflowGateDecision.node_id == node.id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        ).scalar_one_or_none()
        if decision is None:
            raise _error(
                reason_code=RuntimeStoreReason.RECORD_NOT_FOUND,
                operation=operation,
                message="runtime gate decision was not found for apply",
            )
        if gate.node_id != node.id or gate.attempt_id is None:
            raise _error(
                reason_code=RuntimeStoreReason.INTEGRITY_ERROR,
                operation=operation,
                message="runtime gate is missing its node or attempt binding",
            )
        attempt = self._locked_attempt(
            command.session_id,
            cast(int, gate.attempt_id),
            operation=operation,
        )
        if session.status != command.expected_session_status.value:
            raise _error(
                reason_code=RuntimeStoreReason.STATE_CONFLICT,
                operation=operation,
                message="runtime session status changed before gate decision apply",
            )
        if (
            node.status != command.expected_node_status.value
            or node.revision_index != command.expected_node_revision_index
        ):
            raise _error(
                reason_code=RuntimeStoreReason.STATE_CONFLICT,
                operation=operation,
                message="runtime node state changed before gate decision apply",
            )
        if attempt.status != command.expected_attempt_status.value:
            raise _error(
                reason_code=RuntimeStoreReason.STATE_CONFLICT,
                operation=operation,
                message="runtime attempt status changed before gate decision apply",
            )
        if gate.status != command.expected_gate_status.value:
            raise _error(
                reason_code=RuntimeStoreReason.STATE_CONFLICT,
                operation=operation,
                message="runtime gate status changed before decision apply",
            )

        if command.approved_deliverable_id is not None:
            deliverable = self._db.execute(
                select(WorkflowPublishedDeliverable)
                .where(
                    WorkflowPublishedDeliverable.id == command.approved_deliverable_id,
                    WorkflowPublishedDeliverable.session_id == command.session_id,
                    WorkflowPublishedDeliverable.node_id == node.id,
                    WorkflowPublishedDeliverable.attempt_id == attempt.id,
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            ).scalar_one_or_none()
            if deliverable is None:
                raise _error(
                    reason_code=RuntimeStoreReason.RECORD_NOT_FOUND,
                    operation=operation,
                    message="approved runtime deliverable was not found for gate decision",
                )
            setattr(deliverable, "is_candidate", False)
            setattr(deliverable, "is_approved", True)

        setattr(
            attempt,
            "continuation_checkpoint",
            command.continuation_checkpoint.to_dict(),
        )
        setattr(gate, "status", command.target_gate_status.value)
        setattr(gate, "result_code", command.gate_result_code)
        setattr(gate, "reason_code", command.gate_reason_code)
        setattr(node, "status", command.target_node_status.value)
        setattr(node, "revision_index", command.target_node_revision_index)
        setattr(session, "status", command.target_session_status.value)
        setattr(session, "current_node_key", node.node_key)
        setattr(session, "current_attempt_id", attempt.id)
        setattr(session, "error_message", None)
        setattr(session, "input_payload", command.session_input_payload.to_dict())
        self._apply_task_transition(session, command.task_transition, operation=operation)
        self._db.flush()
        return self._gate_decision_record(decision, operation=operation)

    def transition_session(
        self,
        command: RuntimeSessionTransitionCommand,
    ) -> RuntimeSessionRecord:
        operation = "transition_session"
        session = self._locked_session(command.session_id, operation=operation)
        if not command.expected_statuses or session.status not in {
            status.value for status in command.expected_statuses
        }:
            raise _error(
                reason_code=RuntimeStoreReason.STATE_CONFLICT,
                operation=operation,
                message=(
                    f"runtime session status conflict: expected="
                    f"{[status.value for status in command.expected_statuses]} actual={session.status}"
                ),
            )
        if (
            session.current_node_key != command.expected_current_node_key
            or session.current_attempt_id != command.expected_current_attempt_id
        ):
            raise _error(
                reason_code=RuntimeStoreReason.STATE_CONFLICT,
                operation=operation,
                message="runtime session anchor changed before session transition",
            )

        node_keys: set[str] = set()
        for transition in command.node_transitions:
            if transition.node_key in node_keys:
                raise _error(
                    reason_code=RuntimeStoreReason.INTEGRITY_ERROR,
                    operation=operation,
                    message=f"duplicate runtime node transition for {transition.node_key}",
                )
            node_keys.add(transition.node_key)
            node = self._locked_node(
                command.session_id,
                transition.node_key,
                operation=operation,
            )
            if node.status != transition.expected_status.value:
                raise _error(
                    reason_code=RuntimeStoreReason.STATE_CONFLICT,
                    operation=operation,
                    message=(
                        f"runtime node {transition.node_key} status conflict: "
                        f"expected={transition.expected_status.value} actual={node.status}"
                    ),
                )
            setattr(node, "status", transition.target_status.value)

        attempt_transition = command.attempt_transition
        if attempt_transition is not None:
            if attempt_transition.attempt_id != command.expected_current_attempt_id:
                raise _error(
                    reason_code=RuntimeStoreReason.INTEGRITY_ERROR,
                    operation=operation,
                    message="runtime attempt transition must target the current attempt anchor",
                )
            attempt = self._locked_attempt(
                command.session_id,
                attempt_transition.attempt_id,
                operation=operation,
            )
            if attempt.status != attempt_transition.expected_status.value:
                raise _error(
                    reason_code=RuntimeStoreReason.STATE_CONFLICT,
                    operation=operation,
                    message=(
                        f"runtime attempt {attempt_transition.attempt_id} status conflict: "
                        f"expected={attempt_transition.expected_status.value} actual={attempt.status}"
                    ),
                )
            setattr(attempt, "status", attempt_transition.target_status.value)
            if attempt_transition.error_code is not None:
                setattr(attempt, "error_code", attempt_transition.error_code)
            if attempt_transition.error_message is not None:
                setattr(attempt, "error_message", attempt_transition.error_message)
            if attempt_transition.clear_lease:
                self._clear_attempt_lease(attempt)

        setattr(session, "status", command.target_status.value)
        setattr(session, "current_node_key", command.target_current_node_key)
        setattr(session, "current_attempt_id", command.target_current_attempt_id)
        if command.summary_output is not None:
            setattr(session, "summary_output", command.summary_output.to_dict())
        if command.error_message is not None:
            setattr(session, "error_message", command.error_message)
        elif command.clear_error_message:
            setattr(session, "error_message", None)
        self._apply_task_transition(session, command.task_transition, operation=operation)
        self._db.flush()
        return self._session_record(session, operation=operation)


class SqlAlchemyRuntimeAttemptUnitOfWork:
    """Owns a SQLAlchemy transaction for runtime attempt capabilities."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory
        self._db: Session | None = None
        self._runtime: SqlAlchemyRuntimeAttemptStore | None = None
        self._finished = False

    @property
    def runtime(self) -> SqlAlchemyRuntimeAttemptStore:
        if self._runtime is None:
            raise RuntimeError("runtime attempt unit of work has not been entered")
        return self._runtime

    def __enter__(self) -> SqlAlchemyRuntimeAttemptUnitOfWork:
        if self._db is not None:
            raise RuntimeError("runtime attempt unit of work cannot be re-entered")
        self._db = self._session_factory()
        self._runtime = SqlAlchemyRuntimeAttemptStore(self._db)
        self._finished = False
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._db is None:
            return
        try:
            if exc_type is not None or not self._finished:
                self._db.rollback()
        finally:
            self._db.close()
            self._db = None
            self._runtime = None

    def commit(self) -> None:
        if self._db is None:
            raise RuntimeError("runtime attempt unit of work has not been entered")
        try:
            self._db.commit()
            self._finished = True
        except IntegrityError as exc:
            self._db.rollback()
            self._finished = True
            raise _error(
                reason_code=RuntimeStoreReason.INTEGRITY_ERROR,
                operation="commit_runtime_attempt_unit_of_work",
                message="runtime attempt transaction violated a persistence constraint",
            ) from exc
        except SQLAlchemyError as exc:
            self._db.rollback()
            self._finished = True
            raise _error(
                reason_code=RuntimeStoreReason.TRANSACTION_ERROR,
                operation="commit_runtime_attempt_unit_of_work",
                message="runtime attempt transaction failed",
            ) from exc

    def rollback(self) -> None:
        if self._db is None:
            raise RuntimeError("runtime attempt unit of work has not been entered")
        self._db.rollback()
        self._finished = True
