"""Script-review decision semantics over generic runtime gate capabilities."""

from __future__ import annotations

from ..domain import (
    JsonObjectPayload,
    RuntimeGateDecisionRecord,
    RuntimeGateStore,
    RuntimeStoreError,
    RuntimeStoreReason,
    RuntimeTaskTransition,
    TaskStatus,
    WorkflowNodeStatus,
)
from .orchestration_state_adapter import OrchestrationStateAdapter
from .published_deliverable_service import (
    clear_published_deliverable_ref,
    set_published_deliverable_ref,
)
from .runtime_gate_control_plane import RuntimeGateControlPlane
from .script_review_contract import build_script_review_contract, set_script_review_contract


class ScriptGateDecisionControlPlane:
    """Builds script-specific decision facts and applies them in the caller UoW."""

    _ACTIONS = {"approve", "revise", "replan"}

    def __init__(self, store: RuntimeGateStore) -> None:
        self._store = store
        self._gate_control = RuntimeGateControlPlane(store)

    @staticmethod
    def _deliverable_ref(deliverable) -> dict[str, object]:
        return {
            "type": "published_deliverable",
            "deliverable_id": deliverable.deliverable_id,
            "deliverable_type": deliverable.deliverable_type,
            "scope_type": deliverable.scope_type,
            "scope_id": deliverable.scope_id,
            "attempt_id": deliverable.attempt_id,
            "revision_no": deliverable.revision_no,
            "payload_ref": deliverable.payload_ref,
            "summary": deliverable.summary.to_dict(),
            "is_candidate": False,
            "is_approved": True,
        }

    def submit(
        self,
        *,
        session_id: int,
        node_key: str,
        action: str,
        feedback_text: str | None,
        structured_constraints: JsonObjectPayload,
        actor_type: str,
        actor_id: str | None,
        task_id: str,
        expected_task_status: TaskStatus,
    ) -> RuntimeGateDecisionRecord:
        normalized_action = action.strip().lower()
        if normalized_action not in self._ACTIONS:
            raise RuntimeStoreError(
                reason_code=RuntimeStoreReason.STATE_CONFLICT,
                operation="submit_script_gate_decision",
                message=f"unsupported script gate action {action!r}",
            )
        invalidation_scope = "workflow" if normalized_action == "replan" else "node"
        decision = self._gate_control.create_human_decision(
            session_id=session_id,
            node_key=node_key,
            action=normalized_action,
            actor_type=actor_type,
            actor_id=actor_id,
            feedback_text=feedback_text,
            structured_constraints=structured_constraints,
            invalidation_scope=invalidation_scope,
        )

        session = self._store.load_session(session_id)
        node = self._store.load_node(session_id, node_key)
        gate = self._store.load_latest_gate(session_id, node_key)
        if session is None or node is None or gate is None or gate.attempt_id is None:
            raise RuntimeStoreError(
                reason_code=RuntimeStoreReason.RECORD_NOT_FOUND,
                operation="submit_script_gate_decision",
                message="script gate decision context is incomplete",
            )
        attempt = self._store.load_attempt(session_id, gate.attempt_id)
        if attempt is None or attempt.continuation_checkpoint is None:
            raise RuntimeStoreError(
                reason_code=RuntimeStoreReason.STATE_CONFLICT,
                operation="submit_script_gate_decision",
                message="script gate continuation checkpoint is missing",
            )
        checkpoint = OrchestrationStateAdapter.validate_continuation_checkpoint(
            attempt.continuation_checkpoint.to_dict(),
            require_decision_id=False,
        )
        checkpoint["decision_id"] = decision.decision_id

        session_payload = session.input_payload.to_dict()
        approved_deliverable_id = None
        if normalized_action == "approve":
            deliverable = self._gate_control.require_published_deliverable(
                session_id=session_id,
                node_key=node_key,
                attempt_id=gate.attempt_id,
            )
            approved_deliverable_id = deliverable.deliverable_id
            session_payload = set_published_deliverable_ref(
                session_payload,
                node_key=node_key,
                ref=self._deliverable_ref(deliverable),
            )
            session_payload = set_script_review_contract(session_payload, None)
            target_node_status = WorkflowNodeStatus.APPROVED
            target_revision_index = node.revision_index
            progress_step = "Script approved, resuming generation"
            progress_percentage = 40
        else:
            session_payload = clear_published_deliverable_ref(
                session_payload,
                node_key=node_key,
            )
            session_payload = set_script_review_contract(
                session_payload,
                build_script_review_contract(
                    action=normalized_action,
                    gate_id=gate.gate_id,
                    decision_id=decision.decision_id,
                    feedback_text=feedback_text,
                    structured_constraints=structured_constraints.to_dict(),
                ),
            )
            target_node_status = WorkflowNodeStatus.NEEDS_REVISION
            target_revision_index = node.revision_index + 1
            progress_step = (
                "Script replan requested"
                if normalized_action == "replan"
                else "Script revision requested"
            )
            progress_percentage = 15 if normalized_action == "replan" else 20

        return self._gate_control.apply_human_decision(
            session_id=session_id,
            node_key=node_key,
            decision=decision,
            target_node_status=target_node_status,
            target_node_revision_index=target_revision_index,
            session_input_payload=JsonObjectPayload.from_mapping(
                session_payload,
                field_path="script_gate_decision.session_input_payload",
            ),
            continuation_checkpoint=JsonObjectPayload.from_mapping(
                checkpoint,
                field_path="script_gate_decision.continuation_checkpoint",
            ),
            approved_deliverable_id=approved_deliverable_id,
            task_transition=RuntimeTaskTransition(
                task_id=task_id,
                expected_status=expected_task_status,
                target_status=TaskStatus.IN_PROGRESS,
                progress_step=progress_step,
                progress_percentage=progress_percentage,
                requires_human_review=False,
            ),
        )
