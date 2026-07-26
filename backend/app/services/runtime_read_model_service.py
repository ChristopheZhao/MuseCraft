"""Database-independent runtime read-model assembly and presentation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from ..domain import (
    JsonObjectPayload,
    RuntimeAttemptRecord,
    RuntimeGateDecisionRecord,
    RuntimeGateRecord,
    RuntimeNodeRecord,
    RuntimeReadModel,
    RuntimeReadModelQuery,
    RuntimeReadStore,
    RuntimeSessionRecord,
    RuntimeStoreError,
    RuntimeStoreReason,
    WorkflowGateStatus,
    WorkflowSessionStatus,
)
from .orchestration_state_adapter import (
    ContinuationCheckpointContractError,
    OrchestrationStateAdapter,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _payload(
    state: str,
    can_resume: bool,
    reason_code: str,
    *,
    diagnostic_reason_code: str | None = None,
) -> JsonObjectPayload:
    payload = {
        "state": state,
        "can_resume": can_resume,
        "reason_code": reason_code,
    }
    if diagnostic_reason_code:
        payload["diagnostic_reason_code"] = diagnostic_reason_code
    return JsonObjectPayload.from_mapping(
        payload,
        field_path="runtime_read_model.resume_control",
    )


@dataclass(frozen=True)
class _ContinuationValidation:
    valid: bool
    reason_code: str
    diagnostic_reason_code: str | None = None


class RuntimeReadModelService(RuntimeReadModelQuery):
    """Builds a committed runtime projection without exposing persistence rows."""

    def __init__(
        self,
        store: RuntimeReadStore,
        *,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._store = store
        self._clock = clock

    def load_for_task(self, task_id: str) -> RuntimeReadModel | None:
        session = self._store.load_latest_session_for_task(task_id)
        if session is None:
            return None
        return self._build(session)

    def load_for_session(self, session_id: int) -> RuntimeReadModel | None:
        session = self._store.load_session(session_id)
        if session is None:
            return None
        return self._build(session)

    def _build(self, session: RuntimeSessionRecord) -> RuntimeReadModel:
        nodes = self._store.load_nodes(session.session_id)
        if not nodes:
            raise RuntimeStoreError(
                reason_code=RuntimeStoreReason.INTEGRITY_ERROR,
                operation="load_runtime_read_model",
                message=(
                    f"Runtime session {session.session_id} is missing workflow nodes; "
                    "the read path cannot repair runtime invariants"
                ),
            )
        active_gate = self._store.load_latest_gate(session.session_id)
        latest_decision = (
            self._store.load_latest_gate_decision(active_gate.gate_id)
            if active_gate is not None
            else None
        )
        resume_control = self._build_resume_control(
            session,
            active_gate=active_gate,
            latest_decision=latest_decision,
        )
        return RuntimeReadModel(
            session=session,
            nodes=nodes,
            active_gate=active_gate,
            latest_decision=latest_decision,
            resume_control=resume_control,
        )

    def _build_resume_control(
        self,
        session: RuntimeSessionRecord,
        *,
        active_gate: RuntimeGateRecord | None,
        latest_decision: RuntimeGateDecisionRecord | None,
    ) -> JsonObjectPayload | None:
        if session.status in {
            WorkflowSessionStatus.COMPLETED,
            WorkflowSessionStatus.FAILED,
            WorkflowSessionStatus.CANCELLED,
        }:
            return None
        if active_gate is not None and active_gate.status is WorkflowGateStatus.AWAITING_HUMAN:
            return _payload("waiting_gate", False, "awaiting_gate_decision")
        if session.current_attempt_id is None:
            return _payload("resume_blocked", False, "missing_current_attempt")
        attempt = self._store.load_attempt(session.session_id, session.current_attempt_id)
        if attempt is None:
            return _payload("resume_blocked", False, "missing_current_attempt")
        if self._lease_is_live(attempt):
            return _payload("view_only_running", False, "active_execution_lease")

        if session.status is WorkflowSessionStatus.RESUMING:
            validation = self._validate_continuation(
                session,
                attempt,
                active_gate=active_gate,
                latest_decision=latest_decision,
                allow_gate_decision=True,
            )
            if not validation.valid:
                return _payload(
                    "resume_blocked",
                    False,
                    validation.reason_code,
                    diagnostic_reason_code=validation.diagnostic_reason_code,
                )
            return _payload("view_only_running", False, "resume_scheduled")

        validation = self._validate_continuation(
            session,
            attempt,
            active_gate=active_gate,
            latest_decision=latest_decision,
            allow_gate_decision=False,
        )
        if not validation.valid:
            return _payload(
                "resume_blocked",
                False,
                validation.reason_code,
                diagnostic_reason_code=validation.diagnostic_reason_code,
            )
        return _payload("resume_available", True, "checkpoint_available")

    def _lease_is_live(self, attempt: RuntimeAttemptRecord) -> bool:
        expires_at = attempt.lease_expires_at
        if expires_at is None or attempt.lease_token is None or attempt.lease_owner is None:
            return False
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return expires_at.astimezone(timezone.utc) > self._clock().astimezone(timezone.utc)

    def _validate_continuation(
        self,
        session: RuntimeSessionRecord,
        attempt: RuntimeAttemptRecord,
        *,
        active_gate: RuntimeGateRecord | None,
        latest_decision: RuntimeGateDecisionRecord | None,
        allow_gate_decision: bool,
    ) -> _ContinuationValidation:
        if session.current_node_key is None or session.current_attempt_id is None:
            return _ContinuationValidation(
                valid=False,
                reason_code="invalid_continuation_checkpoint",
                diagnostic_reason_code="continuation_checkpoint_runtime_anchor_missing",
            )
        checkpoint_payload = attempt.continuation_checkpoint
        if checkpoint_payload is None:
            return _ContinuationValidation(
                valid=False,
                reason_code="missing_continuation_checkpoint",
            )
        try:
            checkpoint = OrchestrationStateAdapter.validate_continuation_checkpoint(
                checkpoint_payload.to_dict(),
                require_decision_id=False,
            )
        except ContinuationCheckpointContractError as exc:
            return _ContinuationValidation(
                valid=False,
                reason_code="invalid_continuation_checkpoint",
                diagnostic_reason_code=exc.reason_code.value,
            )
        if str(checkpoint.get("node_key") or "").strip().lower() != session.current_node_key:
            return _ContinuationValidation(
                valid=False,
                reason_code="invalid_continuation_checkpoint",
                diagnostic_reason_code="continuation_checkpoint_node_mismatch",
            )
        checkpoint_attempt_id = checkpoint.get("attempt_id")
        if type(checkpoint_attempt_id) is not int:
            return _ContinuationValidation(
                valid=False,
                reason_code="invalid_continuation_checkpoint",
                diagnostic_reason_code="continuation_checkpoint_attempt_type_invalid",
            )
        if checkpoint_attempt_id != session.current_attempt_id:
            return _ContinuationValidation(
                valid=False,
                reason_code="invalid_continuation_checkpoint",
                diagnostic_reason_code="continuation_checkpoint_attempt_mismatch",
            )

        anchor_type = str(checkpoint.get("anchor_type") or "").strip().lower()
        if anchor_type == OrchestrationStateAdapter.CONTINUATION_ANCHOR_RUNTIME_CHECKPOINT:
            return _ContinuationValidation(
                valid=True,
                reason_code="checkpoint_available",
            )
        if not allow_gate_decision:
            return _ContinuationValidation(
                valid=False,
                reason_code="invalid_continuation_checkpoint",
                diagnostic_reason_code="continuation_checkpoint_anchor_not_resumable",
            )
        if anchor_type != OrchestrationStateAdapter.CONTINUATION_ANCHOR_GATE_DECISION:
            return _ContinuationValidation(
                valid=False,
                reason_code="invalid_continuation_checkpoint",
                diagnostic_reason_code="continuation_checkpoint_anchor_invalid",
            )
        try:
            checkpoint = OrchestrationStateAdapter.validate_continuation_checkpoint(
                checkpoint_payload.to_dict(),
                require_decision_id=True,
            )
        except ContinuationCheckpointContractError as exc:
            return _ContinuationValidation(
                valid=False,
                reason_code="invalid_continuation_checkpoint",
                diagnostic_reason_code=exc.reason_code.value,
            )
        checkpoint_decision_id = checkpoint.get("decision_id")
        if type(checkpoint_decision_id) is not int:
            return _ContinuationValidation(
                valid=False,
                reason_code="invalid_continuation_checkpoint",
                diagnostic_reason_code="continuation_checkpoint_decision_type_invalid",
            )
        if active_gate is None or latest_decision is None:
            return _ContinuationValidation(
                valid=False,
                reason_code="invalid_continuation_checkpoint",
                diagnostic_reason_code="continuation_checkpoint_gate_binding_missing",
            )
        if active_gate.attempt_id != session.current_attempt_id:
            return _ContinuationValidation(
                valid=False,
                reason_code="invalid_continuation_checkpoint",
                diagnostic_reason_code="continuation_checkpoint_gate_attempt_mismatch",
            )
        if checkpoint_decision_id != latest_decision.decision_id:
            return _ContinuationValidation(
                valid=False,
                reason_code="invalid_continuation_checkpoint",
                diagnostic_reason_code="continuation_checkpoint_decision_mismatch",
            )
        return _ContinuationValidation(
            valid=True,
            reason_code="checkpoint_available",
        )


class RuntimeReadModelPresenter:
    """Converts the immutable read model to the public JSON projection."""

    @staticmethod
    def to_payload(model: RuntimeReadModel) -> JsonObjectPayload:
        session = model.session
        return JsonObjectPayload.from_mapping(
            {
                "session_id": session.session_id,
                "task_id": session.task_id,
                "mode": session.mode,
                "project_id": session.project_id,
                "episode_id": session.episode_id,
                "shared_memory_id": session.shared_memory_id,
                "status": session.status.value,
                "current_node_key": session.current_node_key,
                "current_attempt_id": session.current_attempt_id,
                "active_gate": RuntimeReadModelPresenter._gate_payload(
                    model.active_gate,
                    model.latest_decision,
                ),
                "error_message": session.error_message,
                "summary_output": session.summary_output.to_dict(),
                "resume_control": (
                    model.resume_control.to_dict() if model.resume_control is not None else None
                ),
                "nodes": [RuntimeReadModelPresenter._node_payload(node) for node in model.nodes],
                "created_at": RuntimeReadModelPresenter._timestamp(session.created_at),
                "updated_at": RuntimeReadModelPresenter._timestamp(session.updated_at),
            },
            field_path="runtime_read_model.public_projection",
        )

    @staticmethod
    def _node_payload(node: RuntimeNodeRecord) -> dict[str, object]:
        return {
            "id": node.node_id,
            "node_key": node.node_key,
            "node_type": node.node_type,
            "order_index": node.order_index,
            "scope_type": node.scope_type,
            "scope_ref": node.scope_ref,
            "status": node.status.value,
            "revision_index": node.revision_index,
            "gate_required": node.gate_required,
            "last_gate_id": node.last_gate_id,
            "artifact_refs": [item.to_dict() for item in node.artifact_refs],
            "diagnostics": [item.to_dict() for item in node.diagnostics],
        }

    @staticmethod
    def _gate_payload(
        gate: RuntimeGateRecord | None,
        decision: RuntimeGateDecisionRecord | None,
    ) -> dict[str, object] | None:
        if gate is None:
            return None
        decision_payload: dict[str, object] | None = None
        if decision is not None:
            decision_payload = {
                "id": decision.decision_id,
                "gate_id": decision.gate_id,
                "action": decision.action,
                "actor_type": decision.actor_type,
                "actor_id": decision.actor_id,
                "feedback_text": decision.feedback_text,
                "structured_constraints": decision.structured_constraints.to_dict(),
                "invalidation_scope": decision.invalidation_scope,
                "created_at": RuntimeReadModelPresenter._timestamp(decision.created_at),
                "updated_at": RuntimeReadModelPresenter._timestamp(decision.updated_at),
            }
        return {
            "id": gate.gate_id,
            "node_id": gate.node_id,
            "attempt_id": gate.attempt_id,
            "gate_name": gate.gate_name,
            "gate_type": gate.gate_type,
            "status": gate.status.value,
            "contract_version": gate.contract_version,
            "scope": gate.scope.to_dict(),
            "artifact_refs": [item.to_dict() for item in gate.artifact_refs],
            "facts": gate.facts.to_dict(),
            "result": gate.result_code or gate.status.value,
            "result_code": gate.result_code,
            "reason_code": gate.reason_code,
            "diagnostics": [item.to_dict() for item in gate.diagnostics],
            "allowed_actions": list(gate.allowed_actions),
            "recommended_action": gate.recommended_action,
            "latest_decision": decision_payload,
            "created_at": RuntimeReadModelPresenter._timestamp(gate.created_at),
            "updated_at": RuntimeReadModelPresenter._timestamp(gate.updated_at),
        }

    @staticmethod
    def _timestamp(value: datetime | None) -> str | None:
        return value.isoformat() if value is not None else None
