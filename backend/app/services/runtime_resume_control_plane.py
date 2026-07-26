"""Database-independent continuation and resume-consumption policy."""

from __future__ import annotations

from typing import NoReturn

from ..domain import (
    JsonObjectPayload,
    RuntimeNodeDiagnosticsClearCommand,
    RuntimeResumeStore,
    RuntimeSessionNodeTransition,
    RuntimeSessionRecord,
    RuntimeSessionTransitionCommand,
    RuntimeStoreError,
    RuntimeStoreReason,
    RuntimeTaskTransition,
    TaskStatus,
    WorkflowNodeStatus,
    WorkflowSessionStatus,
)
from .orchestration_state_adapter import (
    ContinuationCheckpointContractError,
    OrchestrationStateAdapter,
)


class RuntimeResumeControlPlane:
    """Validates continuation anchors and applies explicit resume transitions."""

    def __init__(self, store: RuntimeResumeStore) -> None:
        self._store = store

    def load_continuation(
        self,
        session_id: int,
        *,
        expected_anchor_type: str | None,
        require_decision_id: bool,
        require_resuming: bool,
        expected_node_key: str | None = None,
    ) -> JsonObjectPayload:
        operation = "load_runtime_continuation"
        session = self._require_session(session_id, operation=operation)
        if require_resuming and session.status is not WorkflowSessionStatus.RESUMING:
            self._conflict(operation, f"runtime session {session_id} is not resuming")
        node_key = str(session.current_node_key or "").strip().lower()
        if not node_key:
            self._integrity(operation, f"runtime session {session_id} has no node anchor")
        if expected_node_key is not None and node_key != expected_node_key.strip().lower():
            self._conflict(
                operation,
                f"runtime continuation is not anchored to node {expected_node_key}",
            )
        attempt_id = session.current_attempt_id
        if attempt_id is None:
            self._integrity(operation, f"runtime session {session_id} has no attempt anchor")
        attempt = self._store.load_attempt(session_id, attempt_id)
        if attempt is None or attempt.continuation_checkpoint is None:
            self._integrity(operation, "runtime continuation checkpoint is missing")
        assert attempt is not None and attempt.continuation_checkpoint is not None
        try:
            checkpoint = OrchestrationStateAdapter.validate_continuation_checkpoint(
                attempt.continuation_checkpoint.to_dict(),
                require_decision_id=require_decision_id,
            )
        except ContinuationCheckpointContractError as exc:
            raise RuntimeStoreError(
                reason_code=RuntimeStoreReason.INTEGRITY_ERROR,
                operation=operation,
                message=(
                    "runtime continuation checkpoint is invalid "
                    f"reason_code={exc.reason_code.value}: {exc.message}"
                ),
            ) from exc
        anchor_type = str(checkpoint.get("anchor_type") or "").strip().lower()
        if expected_anchor_type is not None and anchor_type != expected_anchor_type.strip().lower():
            self._conflict(
                operation,
                "runtime continuation anchor type does not match the requested resume path",
            )
        if str(checkpoint.get("node_key") or "").strip().lower() != node_key:
            self._integrity(operation, "runtime continuation node anchor is stale")
        if checkpoint["attempt_id"] != attempt_id:
            self._integrity(operation, "runtime continuation attempt anchor is stale")

        if anchor_type == OrchestrationStateAdapter.CONTINUATION_ANCHOR_GATE_DECISION:
            gate = self._store.load_latest_gate(session_id, node_key)
            if gate is None or gate.attempt_id != attempt_id:
                self._integrity(operation, "runtime continuation gate binding is missing or stale")
            decision = self._store.load_latest_gate_decision(gate.gate_id)
            if decision is None:
                self._integrity(operation, "runtime continuation decision is missing")
            if require_decision_id and checkpoint["decision_id"] != decision.decision_id:
                self._conflict(operation, "runtime continuation decision binding is stale")

        return JsonObjectPayload.from_mapping(
            checkpoint,
            field_path="runtime_continuation.checkpoint",
        )

    def consume_script_approval(self, session_id: int) -> RuntimeSessionRecord:
        operation = "consume_script_approval_continuation"
        self.load_continuation(
            session_id,
            expected_anchor_type=OrchestrationStateAdapter.CONTINUATION_ANCHOR_GATE_DECISION,
            require_decision_id=True,
            require_resuming=True,
            expected_node_key="script",
        )
        session = self._require_session(session_id, operation=operation)
        node = self._store.load_node(session_id, "script")
        gate = self._store.load_latest_gate(session_id, "script")
        if node is None or gate is None:
            self._integrity(operation, "script approval continuation context is incomplete")
        assert node is not None and gate is not None
        decision = self._store.load_latest_gate_decision(gate.gate_id)
        if decision is None or decision.action != "approve":
            self._conflict(operation, "script continuation has no approval decision")
        if session.status is not WorkflowSessionStatus.RESUMING:
            self._conflict(operation, "runtime session is not awaiting continuation consumption")
        if node.status is not WorkflowNodeStatus.APPROVED:
            self._conflict(operation, "script node is not approved")
        return self._store.transition_session(
            RuntimeSessionTransitionCommand(
                session_id=session_id,
                expected_statuses=(session.status,),
                target_status=WorkflowSessionStatus.RUNNING,
                expected_current_node_key=session.current_node_key,
                expected_current_attempt_id=session.current_attempt_id,
                target_current_node_key=None,
                target_current_attempt_id=None,
                node_transitions=(
                    RuntimeSessionNodeTransition(
                        node_key="script",
                        expected_status=node.status,
                        target_status=WorkflowNodeStatus.COMPLETED,
                    ),
                ),
                clear_error_message=True,
                task_transition=RuntimeTaskTransition(
                    task_id=session.task_id,
                    expected_status=session.task_status,
                    target_status=TaskStatus.IN_PROGRESS,
                    requires_human_review=False,
                ),
            )
        )

    def clear_node_diagnostic_codes(
        self,
        session_id: int,
        *,
        node_key: str,
        codes: tuple[str, ...],
    ) -> None:
        normalized_codes = tuple(
            sorted({code.strip() for code in codes if isinstance(code, str) and code.strip()})
        )
        if not normalized_codes:
            return
        node = self._store.load_node(session_id, node_key)
        if node is None:
            self._missing("clear_runtime_node_diagnostics", session_id)
        assert node is not None
        self._store.clear_node_diagnostics(
            RuntimeNodeDiagnosticsClearCommand(
                session_id=session_id,
                node_key=node_key,
                codes=normalized_codes,
                expected_status=node.status,
                expected_diagnostics=node.diagnostics,
            )
        )

    def _require_session(self, session_id: int, *, operation: str) -> RuntimeSessionRecord:
        session = self._store.load_session(session_id)
        if session is None:
            self._missing(operation, session_id)
        assert session is not None
        return session

    @staticmethod
    def _missing(operation: str, session_id: int) -> NoReturn:
        raise RuntimeStoreError(
            reason_code=RuntimeStoreReason.RECORD_NOT_FOUND,
            operation=operation,
            message=f"runtime session {session_id} was not found",
        )

    @staticmethod
    def _conflict(operation: str, message: str) -> NoReturn:
        raise RuntimeStoreError(
            reason_code=RuntimeStoreReason.STATE_CONFLICT,
            operation=operation,
            message=message,
        )

    @staticmethod
    def _integrity(operation: str, message: str) -> NoReturn:
        raise RuntimeStoreError(
            reason_code=RuntimeStoreReason.INTEGRITY_ERROR,
            operation=operation,
            message=message,
        )
