"""Control-plane semantics for runtime gate transitions."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from ..domain import (
    JsonObjectPayload,
    RuntimeGateDecisionApplyCommand,
    RuntimeGateDecisionCreateCommand,
    RuntimeGateDecisionRecord,
    RuntimeGateOpenCommand,
    RuntimeGateRecord,
    RuntimeGateStore,
    RuntimePublishedDeliverableRecord,
    RuntimeStoreError,
    RuntimeStoreReason,
    RuntimeTaskTransition,
    WorkflowAttemptStatus,
    WorkflowGateStatus,
    WorkflowNodeStatus,
    WorkflowSessionStatus,
)

Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RuntimeGateControlPlane:
    """Selects gate transition facts without owning persistence mechanics."""

    def __init__(self, store: RuntimeGateStore, *, clock: Clock = _utc_now) -> None:
        self._store = store
        self._clock = clock

    @staticmethod
    def _missing(*, operation: str, message: str) -> RuntimeStoreError:
        return RuntimeStoreError(
            reason_code=RuntimeStoreReason.RECORD_NOT_FOUND,
            operation=operation,
            message=message,
        )

    def open_human_gate(
        self,
        *,
        session_id: int,
        node_key: str,
        attempt_id: int | None,
        gate_name: str,
        gate_type: str,
        contract_version: str,
        scope: JsonObjectPayload,
        artifact_refs: tuple[JsonObjectPayload, ...],
        facts: JsonObjectPayload,
        allowed_actions: tuple[str, ...],
        recommended_action: str | None,
        expected_lease_token: str | None,
        result_code: str,
        reason_code: str | None,
        diagnostics: tuple[JsonObjectPayload, ...] = (),
        session_input_payload: JsonObjectPayload | None = None,
        node_artifact_refs: tuple[JsonObjectPayload, ...] | None = None,
        node_diagnostics: tuple[JsonObjectPayload, ...] | None = None,
        task_transition: RuntimeTaskTransition | None = None,
    ) -> RuntimeGateRecord:
        operation = "open_gate"
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
        attempt = None
        if attempt_id is not None:
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
                    message="runtime gate attempt does not belong to the requested node",
                )

        return self._store.open_gate(
            RuntimeGateOpenCommand(
                session_id=session_id,
                node_key=node_key,
                attempt_id=attempt_id,
                gate_name=gate_name,
                gate_type=gate_type,
                contract_version=contract_version,
                scope=scope,
                artifact_refs=artifact_refs,
                facts=facts,
                allowed_actions=allowed_actions,
                recommended_action=recommended_action,
                expected_lease_token=expected_lease_token,
                observed_at=self._clock(),
                expected_session_status=session.status,
                expected_node_status=node.status,
                expected_attempt_status=attempt.status if attempt is not None else None,
                target_gate_status=WorkflowGateStatus.AWAITING_HUMAN,
                target_node_status=WorkflowNodeStatus.PENDING_GATE,
                target_session_status=WorkflowSessionStatus.WAITING_GATE,
                result_code=result_code,
                reason_code=reason_code,
                diagnostics=diagnostics,
                session_input_payload=session_input_payload,
                node_artifact_refs=node_artifact_refs,
                node_diagnostics=node_diagnostics,
                release_attempt_lease=True,
                task_transition=task_transition,
            )
        )

    def create_human_decision(
        self,
        *,
        session_id: int,
        node_key: str,
        action: str,
        actor_type: str,
        actor_id: str | None,
        feedback_text: str | None,
        structured_constraints: JsonObjectPayload,
        invalidation_scope: str,
    ) -> RuntimeGateDecisionRecord:
        gate = self._store.load_latest_gate(session_id, node_key)
        if gate is None:
            raise self._missing(
                operation="create_gate_decision",
                message=f"runtime gate for node {node_key!r} was not found",
            )
        return self._store.create_gate_decision(
            RuntimeGateDecisionCreateCommand(
                session_id=session_id,
                gate_id=gate.gate_id,
                node_key=node_key,
                action=action,
                actor_type=actor_type,
                actor_id=actor_id,
                feedback_text=feedback_text,
                structured_constraints=structured_constraints,
                invalidation_scope=invalidation_scope,
                expected_gate_status=WorkflowGateStatus.AWAITING_HUMAN,
            )
        )

    def require_published_deliverable(
        self,
        *,
        session_id: int,
        node_key: str,
        attempt_id: int,
    ) -> RuntimePublishedDeliverableRecord:
        deliverable = self._store.load_published_deliverable(
            session_id,
            node_key,
            attempt_id,
        )
        if deliverable is None:
            raise self._missing(
                operation="load_published_deliverable",
                message=(
                    f"runtime deliverable for node {node_key!r} attempt {attempt_id} "
                    "was not found"
                ),
            )
        return deliverable

    def apply_human_decision(
        self,
        *,
        session_id: int,
        node_key: str,
        decision: RuntimeGateDecisionRecord,
        target_node_status: WorkflowNodeStatus,
        target_node_revision_index: int,
        session_input_payload: JsonObjectPayload,
        continuation_checkpoint: JsonObjectPayload,
        approved_deliverable_id: int | None,
        task_transition: RuntimeTaskTransition,
    ) -> RuntimeGateDecisionRecord:
        session = self._store.load_session(session_id)
        node = self._store.load_node(session_id, node_key)
        gate = self._store.load_latest_gate(session_id, node_key)
        if session is None or node is None or gate is None or gate.attempt_id is None:
            raise self._missing(
                operation="apply_gate_decision",
                message="runtime gate decision context is incomplete",
            )
        attempt = self._store.load_attempt(session_id, gate.attempt_id)
        if attempt is None:
            raise self._missing(
                operation="apply_gate_decision",
                message="runtime gate attempt was not found",
            )
        if attempt.status is not WorkflowAttemptStatus.SUCCEEDED:
            raise RuntimeStoreError(
                reason_code=RuntimeStoreReason.STATE_CONFLICT,
                operation="apply_gate_decision",
                message="runtime gate attempt must be succeeded before decision apply",
            )
        return self._store.apply_gate_decision(
            RuntimeGateDecisionApplyCommand(
                session_id=session_id,
                gate_id=gate.gate_id,
                node_key=node_key,
                decision_id=decision.decision_id,
                expected_gate_status=gate.status,
                expected_session_status=session.status,
                expected_node_status=node.status,
                expected_node_revision_index=node.revision_index,
                expected_attempt_status=attempt.status,
                target_gate_status=WorkflowGateStatus.DECIDED,
                gate_result_code=decision.action,
                gate_reason_code="human_gate_decision",
                target_node_status=target_node_status,
                target_node_revision_index=target_node_revision_index,
                target_session_status=WorkflowSessionStatus.RESUMING,
                session_input_payload=session_input_payload,
                continuation_checkpoint=continuation_checkpoint,
                approved_deliverable_id=approved_deliverable_id,
                task_transition=task_transition,
            )
        )
