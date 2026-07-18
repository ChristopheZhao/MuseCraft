"""Control-plane semantics for runtime attempt and execution-lease transitions."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from ..domain import (
    JsonObjectPayload,
    RuntimeAttemptCompletionCommand,
    RuntimeAttemptFailureCommand,
    RuntimeAttemptHeartbeatCommand,
    RuntimeAttemptLeaseCommand,
    RuntimeAttemptRecord,
    RuntimeAttemptReleaseCommand,
    RuntimeAttemptStartCommand,
    RuntimeAttemptStore,
    RuntimeContinuationBindCommand,
    RuntimeNodeRecord,
    RuntimeSessionRecord,
    RuntimeStoreError,
    RuntimeStoreReason,
    RuntimeTaskTransition,
    WorkflowAttemptStatus,
    WorkflowNodeStatus,
    WorkflowSessionStatus,
)

Clock = Callable[[], datetime]
TokenFactory = Callable[[], str]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _new_lease_token() -> str:
    return uuid4().hex


class RuntimeAttemptControlPlane:
    """Selects transition facts while delegating persistence mechanics to a store."""

    def __init__(
        self,
        store: RuntimeAttemptStore,
        *,
        clock: Clock = _utc_now,
        token_factory: TokenFactory = _new_lease_token,
    ) -> None:
        self._store = store
        self._clock = clock
        self._token_factory = token_factory

    @staticmethod
    def _missing(*, operation: str, message: str) -> RuntimeStoreError:
        return RuntimeStoreError(
            reason_code=RuntimeStoreReason.RECORD_NOT_FOUND,
            operation=operation,
            message=message,
        )

    def start_attempt(
        self,
        *,
        session_id: int,
        node_key: str,
        trigger_reason: str,
        requested_by: str,
        input_contract: JsonObjectPayload,
        task_transition: RuntimeTaskTransition | None = None,
    ) -> RuntimeAttemptRecord:
        operation = "start_attempt"
        session = self._store.load_session(session_id)
        if session is None:
            raise self._missing(
                operation=operation,
                message=f"runtime session {session_id} was not found",
            )
        node = self._store.load_node(session_id, node_key)
        if node is None:
            raise self._missing(
                operation=operation,
                message=f"runtime node {node_key!r} was not found in session {session_id}",
            )
        return self._store.start_attempt(
            RuntimeAttemptStartCommand(
                session_id=session_id,
                node_key=node_key,
                trigger_reason=trigger_reason,
                requested_by=requested_by,
                input_contract=input_contract,
                expected_session_status=session.status,
                expected_node_status=node.status,
                target_session_status=WorkflowSessionStatus.RUNNING,
                target_node_status=WorkflowNodeStatus.RUNNING,
                target_attempt_status=WorkflowAttemptStatus.RUNNING,
                task_transition=task_transition,
            )
        )

    def grant_lease(
        self,
        *,
        session_id: int,
        attempt_id: int,
        lease_owner: str,
        lease_timeout_seconds: int,
        lease_token: str | None = None,
    ) -> RuntimeAttemptRecord:
        if lease_timeout_seconds <= 0:
            raise RuntimeStoreError(
                reason_code=RuntimeStoreReason.INTEGRITY_ERROR,
                operation="grant_attempt_lease",
                message="lease_timeout_seconds must be positive",
            )
        heartbeat_at = self._clock()
        token = (lease_token if lease_token is not None else self._token_factory()).strip()
        return self._store.grant_attempt_lease(
            RuntimeAttemptLeaseCommand(
                session_id=session_id,
                attempt_id=attempt_id,
                lease_owner=lease_owner,
                lease_token=token,
                heartbeat_at=heartbeat_at,
                lease_expires_at=heartbeat_at + timedelta(seconds=lease_timeout_seconds),
                expected_attempt_status=WorkflowAttemptStatus.RUNNING,
            )
        )

    def heartbeat_lease(
        self,
        *,
        session_id: int,
        attempt_id: int,
        lease_token: str,
        lease_timeout_seconds: int,
    ) -> RuntimeAttemptRecord:
        if lease_timeout_seconds <= 0:
            raise RuntimeStoreError(
                reason_code=RuntimeStoreReason.INTEGRITY_ERROR,
                operation="heartbeat_attempt_lease",
                message="lease_timeout_seconds must be positive",
            )
        heartbeat_at = self._clock()
        return self._store.heartbeat_attempt_lease(
            RuntimeAttemptHeartbeatCommand(
                session_id=session_id,
                attempt_id=attempt_id,
                lease_token=lease_token,
                heartbeat_at=heartbeat_at,
                lease_expires_at=heartbeat_at + timedelta(seconds=lease_timeout_seconds),
                expected_attempt_status=WorkflowAttemptStatus.RUNNING,
            )
        )

    def release_lease(
        self,
        *,
        session_id: int,
        attempt_id: int,
        lease_token: str | None,
        expected_attempt_status: WorkflowAttemptStatus | None = None,
    ) -> RuntimeAttemptRecord:
        return self._store.release_attempt_lease(
            RuntimeAttemptReleaseCommand(
                session_id=session_id,
                attempt_id=attempt_id,
                lease_token=lease_token,
                expected_attempt_status=expected_attempt_status,
            )
        )

    def bind_continuation(
        self,
        *,
        session_id: int,
        attempt_id: int,
        continuation_checkpoint: JsonObjectPayload,
    ) -> RuntimeAttemptRecord:
        return self._store.bind_attempt_continuation(
            RuntimeContinuationBindCommand(
                session_id=session_id,
                attempt_id=attempt_id,
                continuation_checkpoint=continuation_checkpoint,
                expected_attempt_status=WorkflowAttemptStatus.RUNNING,
            )
        )

    def _load_transition_records(
        self,
        *,
        session_id: int,
        node_key: str,
        attempt_id: int,
    ) -> tuple[RuntimeSessionRecord, RuntimeNodeRecord, RuntimeAttemptRecord]:
        operation = "load_attempt_transition_records"
        session = self._store.load_session(session_id)
        if session is None:
            raise self._missing(
                operation=operation,
                message=f"runtime session {session_id} was not found",
            )
        node = self._store.load_node(session_id, node_key)
        if node is None:
            raise self._missing(
                operation=operation,
                message=f"runtime node {node_key!r} was not found in session {session_id}",
            )
        attempt = self._store.load_attempt(session_id, attempt_id)
        if attempt is None:
            raise self._missing(
                operation=operation,
                message=f"runtime attempt {attempt_id} was not found in session {session_id}",
            )
        if attempt.node_id != node.node_id:
            raise RuntimeStoreError(
                reason_code=RuntimeStoreReason.STATE_CONFLICT,
                operation=operation,
                message="runtime attempt does not belong to the requested node",
            )
        return session, node, attempt

    def complete_attempt(
        self,
        *,
        session_id: int,
        node_key: str,
        attempt_id: int,
        expected_lease_token: str | None,
        target_node_status: WorkflowNodeStatus,
        output_artifacts: tuple[JsonObjectPayload, ...] = (),
        metrics: JsonObjectPayload | None = None,
        node_artifact_refs: tuple[JsonObjectPayload, ...] | None = None,
        node_diagnostics: tuple[JsonObjectPayload, ...] | None = None,
        continuation_checkpoint: JsonObjectPayload | None = None,
        task_transition: RuntimeTaskTransition | None = None,
    ) -> RuntimeAttemptRecord:
        session, node, attempt = self._load_transition_records(
            session_id=session_id,
            node_key=node_key,
            attempt_id=attempt_id,
        )
        return self._store.complete_attempt(
            RuntimeAttemptCompletionCommand(
                session_id=session_id,
                node_key=node_key,
                attempt_id=attempt_id,
                expected_lease_token=expected_lease_token,
                observed_at=self._clock(),
                expected_session_status=session.status,
                expected_node_status=node.status,
                expected_attempt_status=attempt.status,
                target_attempt_status=WorkflowAttemptStatus.SUCCEEDED,
                target_node_status=target_node_status,
                target_session_status=session.status,
                output_artifacts=output_artifacts,
                metrics=metrics or JsonObjectPayload.empty(),
                continuation_checkpoint=continuation_checkpoint,
                node_artifact_refs=node_artifact_refs,
                node_diagnostics=node_diagnostics,
                task_transition=task_transition,
            )
        )

    def fail_attempt(
        self,
        *,
        session_id: int,
        node_key: str,
        attempt_id: int,
        expected_lease_token: str | None,
        error_message: str,
        diagnostics: tuple[JsonObjectPayload, ...] = (),
        output_artifacts: tuple[JsonObjectPayload, ...] = (),
        metrics: JsonObjectPayload | None = None,
        node_artifact_refs: tuple[JsonObjectPayload, ...] | None = None,
        task_transition: RuntimeTaskTransition | None = None,
    ) -> RuntimeAttemptRecord:
        session, node, attempt = self._load_transition_records(
            session_id=session_id,
            node_key=node_key,
            attempt_id=attempt_id,
        )
        observed_at = self._clock()
        lease_snapshot = JsonObjectPayload.from_mapping(
            {
                "code": "execution_lease_snapshot",
                "node_key": node_key,
                "attempt_id": attempt_id,
                "reason_code": "node_attempt_failed",
                "lease_owner": attempt.lease_owner,
                "lease_token_present": bool(attempt.lease_token),
                "lease_live": bool(
                    attempt.lease_token
                    and attempt.lease_owner
                    and attempt.lease_expires_at is not None
                    and attempt.lease_expires_at > observed_at
                ),
                "last_heartbeat_at": (
                    attempt.last_heartbeat_at.isoformat()
                    if attempt.last_heartbeat_at is not None
                    else None
                ),
                "lease_expires_at": (
                    attempt.lease_expires_at.isoformat()
                    if attempt.lease_expires_at is not None
                    else None
                ),
                "captured_at": observed_at.isoformat(),
                "validation_error": None,
            },
            field_path="runtime_attempt.failure_lease_snapshot",
        )
        return self._store.fail_attempt(
            RuntimeAttemptFailureCommand(
                session_id=session_id,
                node_key=node_key,
                attempt_id=attempt_id,
                expected_lease_token=expected_lease_token,
                observed_at=observed_at,
                expected_session_status=session.status,
                expected_node_status=node.status,
                expected_attempt_status=attempt.status,
                target_attempt_status=WorkflowAttemptStatus.FAILED,
                target_node_status=WorkflowNodeStatus.FAILED,
                target_session_status=session.status,
                error_code="node_attempt_failed",
                error_message=error_message,
                output_artifacts=output_artifacts,
                metrics=metrics or JsonObjectPayload.empty(),
                node_artifact_refs=node_artifact_refs,
                diagnostics=(*node.diagnostics, *diagnostics, lease_snapshot),
                task_transition=task_transition,
            )
        )

    def transition_validation_diagnostic(
        self,
        *,
        session_id: int,
        node_key: str,
        attempt_id: int,
        validation_error: RuntimeStoreError,
        diagnostic_code: str,
    ) -> JsonObjectPayload:
        _, _, attempt = self._load_transition_records(
            session_id=session_id,
            node_key=node_key,
            attempt_id=attempt_id,
        )
        return JsonObjectPayload.from_mapping(
            {
                "code": diagnostic_code,
                "node_key": node_key,
                "attempt_id": attempt_id,
                "reason_code": validation_error.reason_code.value,
                "last_heartbeat_at": (
                    attempt.last_heartbeat_at.isoformat()
                    if attempt.last_heartbeat_at is not None
                    else None
                ),
                "lease_expires_at": (
                    attempt.lease_expires_at.isoformat()
                    if attempt.lease_expires_at is not None
                    else None
                ),
                "validation_error": str(validation_error),
                "captured_at": self._clock().isoformat(),
            },
            field_path="runtime_attempt.transition_validation_diagnostic",
        )

    def upsert_diagnostic(
        self,
        *,
        session_id: int,
        attempt_id: int,
        diagnostic: JsonObjectPayload,
    ) -> RuntimeNodeRecord:
        return self._store.upsert_node_diagnostic(
            session_id=session_id,
            attempt_id=attempt_id,
            diagnostic=diagnostic,
        )
