"""Database-independent runtime control-plane persistence contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from types import TracebackType
from typing import Protocol, runtime_checkable

from .agent_execution import JsonObjectPayload
from .enums import (
    TaskStatus,
    WorkflowAttemptStatus,
    WorkflowGateStatus,
    WorkflowNodeStatus,
    WorkflowSessionStatus,
)


def _require_id(value: int, *, field_name: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def _require_text(value: str, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


class RuntimeStoreReason(str, Enum):
    RECORD_NOT_FOUND = "record_not_found"
    STATE_CONFLICT = "state_conflict"
    LEASE_CONFLICT = "lease_conflict"
    INTEGRITY_ERROR = "integrity_error"
    TRANSACTION_ERROR = "transaction_error"


class RuntimeStoreError(RuntimeError):
    """Typed persistence error; it never selects an orchestration action."""

    def __init__(
        self,
        *,
        reason_code: RuntimeStoreReason,
        operation: str,
        message: str,
    ) -> None:
        self.reason_code = reason_code
        self.operation = _require_text(operation, field_name="operation")
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class RuntimeSessionRecord:
    session_id: int
    task_id: str
    task_status: TaskStatus
    mode: str
    status: WorkflowSessionStatus
    project_id: str | None = None
    episode_id: str | None = None
    shared_memory_id: str | None = None
    current_node_key: str | None = None
    current_attempt_id: int | None = None
    input_payload: JsonObjectPayload = field(default_factory=JsonObjectPayload.empty)
    gate_policy: JsonObjectPayload = field(default_factory=JsonObjectPayload.empty)
    summary_output: JsonObjectPayload = field(default_factory=JsonObjectPayload.empty)
    error_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        _require_id(self.session_id, field_name="session_id")
        _require_text(self.task_id, field_name="task_id")
        if not isinstance(self.task_status, TaskStatus):
            raise ValueError("task_status must be TaskStatus")
        _require_text(self.mode, field_name="mode")
        if not isinstance(self.status, WorkflowSessionStatus):
            raise ValueError("status must be WorkflowSessionStatus")


@dataclass(frozen=True, slots=True)
class RuntimeNodeRecord:
    node_id: int
    session_id: int
    node_key: str
    node_type: str
    order_index: int
    scope_type: str
    status: WorkflowNodeStatus
    scope_ref: str | None = None
    revision_index: int = 0
    gate_required: bool = False
    last_gate_id: int | None = None
    artifact_refs: tuple[JsonObjectPayload, ...] = ()
    diagnostics: tuple[JsonObjectPayload, ...] = ()


@dataclass(frozen=True, slots=True)
class RuntimeAttemptRecord:
    attempt_id: int
    session_id: int
    node_id: int
    attempt_no: int
    trigger_reason: str
    requested_by: str
    status: WorkflowAttemptStatus
    input_contract: JsonObjectPayload = field(default_factory=JsonObjectPayload.empty)
    continuation_checkpoint: JsonObjectPayload | None = None
    output_artifacts: tuple[JsonObjectPayload, ...] = ()
    metrics: JsonObjectPayload = field(default_factory=JsonObjectPayload.empty)
    error_code: str | None = None
    error_message: str | None = None
    lease_token: str | None = None
    lease_owner: str | None = None
    last_heartbeat_at: datetime | None = None
    lease_expires_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class RuntimeGateRecord:
    gate_id: int
    session_id: int
    node_id: int
    gate_name: str
    gate_type: str
    status: WorkflowGateStatus
    attempt_id: int | None = None
    contract_version: str = "v1"
    scope: JsonObjectPayload = field(default_factory=JsonObjectPayload.empty)
    artifact_refs: tuple[JsonObjectPayload, ...] = ()
    facts: JsonObjectPayload = field(default_factory=JsonObjectPayload.empty)
    result_code: str | None = None
    reason_code: str | None = None
    diagnostics: tuple[JsonObjectPayload, ...] = ()
    allowed_actions: tuple[str, ...] = ()
    recommended_action: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class RuntimeGateDecisionRecord:
    decision_id: int
    gate_id: int
    session_id: int
    node_id: int
    action: str
    actor_type: str
    actor_id: str | None = None
    feedback_text: str | None = None
    structured_constraints: JsonObjectPayload = field(default_factory=JsonObjectPayload.empty)
    invalidation_scope: str = "node"
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class RuntimePublishedDeliverableRecord:
    deliverable_id: int
    session_id: int
    node_id: int
    attempt_id: int
    deliverable_type: str
    scope_type: str
    revision_no: int
    payload_ref: str
    scope_id: str | None = None
    summary: JsonObjectPayload = field(default_factory=JsonObjectPayload.empty)
    is_candidate: bool = True
    is_approved: bool = False


@dataclass(frozen=True, slots=True)
class RuntimeTaskTransition:
    task_id: str
    expected_status: TaskStatus | None
    target_status: TaskStatus
    progress_step: str | None = None
    progress_percentage: int | None = None
    error_message: str | None = None
    clear_error_message: bool = False
    requires_human_review: bool | None = None


@dataclass(frozen=True, slots=True)
class RuntimeNodeCreate:
    node_key: str
    node_type: str
    order_index: int
    scope_type: str
    target_status: WorkflowNodeStatus
    scope_ref: str | None = None
    revision_index: int = 0
    gate_required: bool = False


@dataclass(frozen=True, slots=True)
class RuntimeSessionCreateCommand:
    task_id: str
    mode: str
    input_payload: JsonObjectPayload
    target_status: WorkflowSessionStatus
    nodes: tuple[RuntimeNodeCreate, ...]
    project_id: str | None = None
    episode_id: str | None = None
    shared_memory_id: str | None = None
    gate_policy: JsonObjectPayload = field(default_factory=JsonObjectPayload.empty)


@dataclass(frozen=True, slots=True)
class RuntimeNodeTransitionCommand:
    session_id: int
    node_key: str
    expected_status: WorkflowNodeStatus | None
    target_status: WorkflowNodeStatus
    session_status: WorkflowSessionStatus | None = None
    artifact_refs: tuple[JsonObjectPayload, ...] | None = None
    diagnostics: tuple[JsonObjectPayload, ...] | None = None
    task_transition: RuntimeTaskTransition | None = None


@dataclass(frozen=True, slots=True)
class RuntimeAttemptStartCommand:
    session_id: int
    node_key: str
    trigger_reason: str
    requested_by: str
    input_contract: JsonObjectPayload
    expected_session_status: WorkflowSessionStatus
    expected_node_status: WorkflowNodeStatus | None = None
    target_session_status: WorkflowSessionStatus = WorkflowSessionStatus.RUNNING
    target_node_status: WorkflowNodeStatus = WorkflowNodeStatus.RUNNING
    target_attempt_status: WorkflowAttemptStatus = WorkflowAttemptStatus.RUNNING
    task_transition: RuntimeTaskTransition | None = None


@dataclass(frozen=True, slots=True)
class RuntimeAttemptLeaseCommand:
    session_id: int
    attempt_id: int
    lease_owner: str
    lease_token: str
    heartbeat_at: datetime
    lease_expires_at: datetime
    expected_attempt_status: WorkflowAttemptStatus = WorkflowAttemptStatus.RUNNING


@dataclass(frozen=True, slots=True)
class RuntimeAttemptHeartbeatCommand:
    session_id: int
    attempt_id: int
    lease_token: str
    heartbeat_at: datetime
    lease_expires_at: datetime
    expected_attempt_status: WorkflowAttemptStatus = WorkflowAttemptStatus.RUNNING


@dataclass(frozen=True, slots=True)
class RuntimeAttemptReleaseCommand:
    session_id: int
    attempt_id: int
    lease_token: str | None
    expected_attempt_status: WorkflowAttemptStatus | None = None


@dataclass(frozen=True, slots=True)
class RuntimeContinuationBindCommand:
    session_id: int
    attempt_id: int
    continuation_checkpoint: JsonObjectPayload
    expected_attempt_status: WorkflowAttemptStatus = WorkflowAttemptStatus.RUNNING


@dataclass(frozen=True, slots=True)
class RuntimeAttemptCompletionCommand:
    session_id: int
    node_key: str
    attempt_id: int
    expected_lease_token: str | None
    observed_at: datetime
    expected_session_status: WorkflowSessionStatus
    expected_node_status: WorkflowNodeStatus
    expected_attempt_status: WorkflowAttemptStatus
    target_attempt_status: WorkflowAttemptStatus
    target_node_status: WorkflowNodeStatus
    target_session_status: WorkflowSessionStatus
    output_artifacts: tuple[JsonObjectPayload, ...] = ()
    metrics: JsonObjectPayload = field(default_factory=JsonObjectPayload.empty)
    continuation_checkpoint: JsonObjectPayload | None = None
    node_artifact_refs: tuple[JsonObjectPayload, ...] | None = None
    node_diagnostics: tuple[JsonObjectPayload, ...] | None = None
    task_transition: RuntimeTaskTransition | None = None


@dataclass(frozen=True, slots=True)
class RuntimeAttemptFailureCommand:
    session_id: int
    node_key: str
    attempt_id: int
    expected_lease_token: str | None
    observed_at: datetime
    expected_session_status: WorkflowSessionStatus
    expected_node_status: WorkflowNodeStatus
    expected_attempt_status: WorkflowAttemptStatus
    target_attempt_status: WorkflowAttemptStatus
    target_node_status: WorkflowNodeStatus
    target_session_status: WorkflowSessionStatus
    error_code: str
    error_message: str
    output_artifacts: tuple[JsonObjectPayload, ...] = ()
    metrics: JsonObjectPayload = field(default_factory=JsonObjectPayload.empty)
    node_artifact_refs: tuple[JsonObjectPayload, ...] | None = None
    diagnostics: tuple[JsonObjectPayload, ...] = ()
    task_transition: RuntimeTaskTransition | None = None


@dataclass(frozen=True, slots=True)
class RuntimeGateOpenCommand:
    session_id: int
    node_key: str
    attempt_id: int | None
    gate_name: str
    gate_type: str
    contract_version: str
    scope: JsonObjectPayload
    artifact_refs: tuple[JsonObjectPayload, ...]
    facts: JsonObjectPayload
    allowed_actions: tuple[str, ...]
    recommended_action: str | None
    expected_lease_token: str | None
    observed_at: datetime
    expected_session_status: WorkflowSessionStatus
    expected_node_status: WorkflowNodeStatus
    expected_attempt_status: WorkflowAttemptStatus | None
    target_gate_status: WorkflowGateStatus
    target_node_status: WorkflowNodeStatus
    target_session_status: WorkflowSessionStatus
    result_code: str
    reason_code: str | None = None
    diagnostics: tuple[JsonObjectPayload, ...] = ()
    session_input_payload: JsonObjectPayload | None = None
    node_artifact_refs: tuple[JsonObjectPayload, ...] | None = None
    node_diagnostics: tuple[JsonObjectPayload, ...] | None = None
    release_attempt_lease: bool = True
    task_transition: RuntimeTaskTransition | None = None


@dataclass(frozen=True, slots=True)
class RuntimeGateDecisionCreateCommand:
    session_id: int
    gate_id: int
    node_key: str
    action: str
    actor_type: str
    actor_id: str | None
    feedback_text: str | None
    structured_constraints: JsonObjectPayload
    invalidation_scope: str
    expected_gate_status: WorkflowGateStatus


@dataclass(frozen=True, slots=True)
class RuntimeGateDecisionApplyCommand:
    session_id: int
    gate_id: int
    node_key: str
    decision_id: int
    expected_gate_status: WorkflowGateStatus
    expected_session_status: WorkflowSessionStatus
    expected_node_status: WorkflowNodeStatus
    expected_node_revision_index: int
    expected_attempt_status: WorkflowAttemptStatus
    target_gate_status: WorkflowGateStatus
    gate_result_code: str
    gate_reason_code: str
    target_node_status: WorkflowNodeStatus
    target_node_revision_index: int
    target_session_status: WorkflowSessionStatus
    session_input_payload: JsonObjectPayload
    continuation_checkpoint: JsonObjectPayload
    approved_deliverable_id: int | None = None
    task_transition: RuntimeTaskTransition | None = None


@dataclass(frozen=True, slots=True)
class RuntimeSessionTransitionCommand:
    session_id: int
    expected_statuses: tuple[WorkflowSessionStatus, ...]
    target_status: WorkflowSessionStatus
    expected_current_node_key: str | None
    expected_current_attempt_id: int | None
    target_current_node_key: str | None
    target_current_attempt_id: int | None
    node_transitions: tuple[RuntimeSessionNodeTransition, ...] = ()
    attempt_transition: RuntimeSessionAttemptTransition | None = None
    summary_output: JsonObjectPayload | None = None
    error_message: str | None = None
    clear_error_message: bool = False
    task_transition: RuntimeTaskTransition | None = None


@dataclass(frozen=True, slots=True)
class RuntimeSessionNodeTransition:
    node_key: str
    expected_status: WorkflowNodeStatus
    target_status: WorkflowNodeStatus


@dataclass(frozen=True, slots=True)
class RuntimeSessionAttemptTransition:
    attempt_id: int
    expected_status: WorkflowAttemptStatus
    target_status: WorkflowAttemptStatus
    clear_lease: bool
    error_code: str | None = None
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class RuntimePublishedDeliverableWrite:
    session_id: int
    node_key: str
    attempt_id: int
    deliverable_type: str
    payload_ref: str
    summary: JsonObjectPayload
    scope_type: str
    scope_id: str | None
    revision_no: int
    expected_session_status: WorkflowSessionStatus
    expected_node_status: WorkflowNodeStatus
    expected_attempt_status: WorkflowAttemptStatus
    is_candidate: bool = True
    is_approved: bool = False


@dataclass(frozen=True, slots=True)
class RuntimePublishedDeliverableApprovalCommand:
    session_id: int
    node_key: str
    attempt_id: int
    deliverable_id: int
    expected_is_candidate: bool
    expected_is_approved: bool
    target_is_candidate: bool
    target_is_approved: bool


@dataclass(frozen=True, slots=True)
class RuntimeReadModel:
    session: RuntimeSessionRecord
    nodes: tuple[RuntimeNodeRecord, ...]
    active_gate: RuntimeGateRecord | None
    latest_decision: RuntimeGateDecisionRecord | None
    resume_control: JsonObjectPayload | None


@runtime_checkable
class RuntimeReadStore(Protocol):
    """Read-only access to immutable committed runtime records."""

    def load_session(self, session_id: int) -> RuntimeSessionRecord | None:
        ...

    def load_latest_session_for_task(self, task_id: str) -> RuntimeSessionRecord | None:
        ...

    def load_nodes(self, session_id: int) -> tuple[RuntimeNodeRecord, ...]:
        ...

    def load_attempt(self, session_id: int, attempt_id: int) -> RuntimeAttemptRecord | None:
        ...

    def load_latest_gate(
        self, session_id: int, node_key: str | None = None
    ) -> RuntimeGateRecord | None:
        ...

    def load_latest_gate_decision(self, gate_id: int) -> RuntimeGateDecisionRecord | None:
        ...


@runtime_checkable
class RuntimeSessionStore(RuntimeReadStore, Protocol):
    """Atomic session-terminal transition capabilities."""

    def transition_session(self, command: RuntimeSessionTransitionCommand) -> RuntimeSessionRecord:
        ...


@runtime_checkable
class RuntimeMaintenanceStore(RuntimeSessionStore, Protocol):
    """Bounded candidate access for explicit control-plane maintenance."""

    def load_reconcilable_sessions(
        self,
        *,
        mode: str,
        statuses: tuple[WorkflowSessionStatus, ...],
        limit: int,
    ) -> tuple[RuntimeSessionRecord, ...]:
        ...


@runtime_checkable
class RuntimeAttemptStore(Protocol):
    """Attempt capability port implemented before the remaining runtime store."""

    def load_session(self, session_id: int) -> RuntimeSessionRecord | None:
        ...

    def load_node(self, session_id: int, node_key: str) -> RuntimeNodeRecord | None:
        ...

    def load_attempt(self, session_id: int, attempt_id: int) -> RuntimeAttemptRecord | None:
        ...

    def start_attempt(self, command: RuntimeAttemptStartCommand) -> RuntimeAttemptRecord:
        ...

    def grant_attempt_lease(self, command: RuntimeAttemptLeaseCommand) -> RuntimeAttemptRecord:
        ...

    def heartbeat_attempt_lease(
        self, command: RuntimeAttemptHeartbeatCommand
    ) -> RuntimeAttemptRecord:
        ...

    def release_attempt_lease(self, command: RuntimeAttemptReleaseCommand) -> RuntimeAttemptRecord:
        ...

    def bind_attempt_continuation(
        self, command: RuntimeContinuationBindCommand
    ) -> RuntimeAttemptRecord:
        ...

    def complete_attempt(self, command: RuntimeAttemptCompletionCommand) -> RuntimeAttemptRecord:
        ...

    def fail_attempt(self, command: RuntimeAttemptFailureCommand) -> RuntimeAttemptRecord:
        ...

    def upsert_node_diagnostic(
        self,
        *,
        session_id: int,
        attempt_id: int,
        diagnostic: JsonObjectPayload,
    ) -> RuntimeNodeRecord:
        ...


@runtime_checkable
class RuntimeGateStore(Protocol):
    """Human and automated gate persistence capabilities."""

    def load_session(self, session_id: int) -> RuntimeSessionRecord | None:
        ...

    def load_node(self, session_id: int, node_key: str) -> RuntimeNodeRecord | None:
        ...

    def load_attempt(self, session_id: int, attempt_id: int) -> RuntimeAttemptRecord | None:
        ...

    def load_latest_gate(self, session_id: int, node_key: str) -> RuntimeGateRecord | None:
        ...

    def load_published_deliverable(
        self, session_id: int, node_key: str, attempt_id: int
    ) -> RuntimePublishedDeliverableRecord | None:
        ...

    def open_gate(self, command: RuntimeGateOpenCommand) -> RuntimeGateRecord:
        ...

    def create_gate_decision(
        self, command: RuntimeGateDecisionCreateCommand
    ) -> RuntimeGateDecisionRecord:
        ...

    def apply_gate_decision(
        self, command: RuntimeGateDecisionApplyCommand
    ) -> RuntimeGateDecisionRecord:
        ...


@runtime_checkable
class RuntimePublishedDeliverableStore(Protocol):
    """Published deliverable persistence capabilities."""

    def load_session(self, session_id: int) -> RuntimeSessionRecord | None:
        ...

    def load_node(self, session_id: int, node_key: str) -> RuntimeNodeRecord | None:
        ...

    def load_attempt(self, session_id: int, attempt_id: int) -> RuntimeAttemptRecord | None:
        ...

    def load_published_deliverable(
        self, session_id: int, node_key: str, attempt_id: int
    ) -> RuntimePublishedDeliverableRecord | None:
        ...

    def publish_deliverable(
        self, command: RuntimePublishedDeliverableWrite
    ) -> RuntimePublishedDeliverableRecord:
        ...

    def approve_deliverable(
        self, command: RuntimePublishedDeliverableApprovalCommand
    ) -> RuntimePublishedDeliverableRecord:
        ...


@runtime_checkable
class RuntimeControlPlaneStore(Protocol):
    """Persistence capabilities. Commands contain facts chosen by the control plane."""

    def load_session(self, session_id: int) -> RuntimeSessionRecord | None:
        ...

    def load_latest_session_for_task(self, task_id: str) -> RuntimeSessionRecord | None:
        ...

    def load_node(self, session_id: int, node_key: str) -> RuntimeNodeRecord | None:
        ...

    def load_nodes(self, session_id: int) -> tuple[RuntimeNodeRecord, ...]:
        ...

    def load_attempt(self, session_id: int, attempt_id: int) -> RuntimeAttemptRecord | None:
        ...

    def load_latest_gate(
        self, session_id: int, node_key: str | None = None
    ) -> RuntimeGateRecord | None:
        ...

    def load_latest_gate_decision(self, gate_id: int) -> RuntimeGateDecisionRecord | None:
        ...

    def load_published_deliverable(
        self, session_id: int, node_key: str, attempt_id: int
    ) -> RuntimePublishedDeliverableRecord | None:
        ...

    def create_session(self, command: RuntimeSessionCreateCommand) -> RuntimeSessionRecord:
        ...

    def transition_node(self, command: RuntimeNodeTransitionCommand) -> RuntimeNodeRecord:
        ...

    def start_attempt(self, command: RuntimeAttemptStartCommand) -> RuntimeAttemptRecord:
        ...

    def grant_attempt_lease(self, command: RuntimeAttemptLeaseCommand) -> RuntimeAttemptRecord:
        ...

    def heartbeat_attempt_lease(
        self, command: RuntimeAttemptHeartbeatCommand
    ) -> RuntimeAttemptRecord:
        ...

    def release_attempt_lease(self, command: RuntimeAttemptReleaseCommand) -> RuntimeAttemptRecord:
        ...

    def bind_attempt_continuation(
        self, command: RuntimeContinuationBindCommand
    ) -> RuntimeAttemptRecord:
        ...

    def complete_attempt(self, command: RuntimeAttemptCompletionCommand) -> RuntimeAttemptRecord:
        ...

    def fail_attempt(self, command: RuntimeAttemptFailureCommand) -> RuntimeAttemptRecord:
        ...

    def open_gate(self, command: RuntimeGateOpenCommand) -> RuntimeGateRecord:
        ...

    def create_gate_decision(
        self, command: RuntimeGateDecisionCreateCommand
    ) -> RuntimeGateDecisionRecord:
        ...

    def apply_gate_decision(
        self, command: RuntimeGateDecisionApplyCommand
    ) -> RuntimeGateDecisionRecord:
        ...

    def transition_session(self, command: RuntimeSessionTransitionCommand) -> RuntimeSessionRecord:
        ...

    def publish_deliverable(
        self, command: RuntimePublishedDeliverableWrite
    ) -> RuntimePublishedDeliverableRecord:
        ...

    def approve_deliverable(
        self, command: RuntimePublishedDeliverableApprovalCommand
    ) -> RuntimePublishedDeliverableRecord:
        ...

    def upsert_node_diagnostic(
        self,
        *,
        session_id: int,
        attempt_id: int,
        diagnostic: JsonObjectPayload,
    ) -> RuntimeNodeRecord:
        ...


@runtime_checkable
class RuntimeReadModelQuery(Protocol):
    """Read-only projection port over authoritative committed runtime records."""

    def load_for_task(self, task_id: str) -> RuntimeReadModel | None:
        ...


@runtime_checkable
class RuntimeAttemptUnitOfWork(Protocol):
    """One transaction over attempt capabilities; no Session escapes this port."""

    @property
    def runtime(self) -> RuntimeAttemptStore:
        ...

    def __enter__(self) -> RuntimeAttemptUnitOfWork:
        ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        ...

    def commit(self) -> None:
        ...

    def rollback(self) -> None:
        ...


@runtime_checkable
class RuntimeControlPlaneUnitOfWork(Protocol):
    """One transaction over runtime capabilities; no Session escapes this port."""

    @property
    def runtime(self) -> RuntimeControlPlaneStore:
        ...

    def __enter__(self) -> RuntimeControlPlaneUnitOfWork:
        ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        ...

    def commit(self) -> None:
        ...

    def rollback(self) -> None:
        ...
