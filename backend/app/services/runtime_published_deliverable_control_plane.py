"""Control-plane publication of stable runtime deliverable references."""

from __future__ import annotations

from collections.abc import Callable

from ..domain import (
    JsonObjectPayload,
    RuntimePublishedDeliverableApprovalCommand,
    RuntimePublishedDeliverableRecord,
    RuntimePublishedDeliverableStore,
    RuntimePublishedDeliverableWrite,
    RuntimeStoreError,
    RuntimeStoreReason,
)
from .published_deliverable_service import discard_published_payload, persist_published_payload

PayloadWriter = Callable[..., str]
PayloadDiscarder = Callable[[str], None]


class RuntimePublishedDeliverableControlPlane:
    """Selects publication facts; persistence adapters only validate and write."""

    def __init__(
        self,
        store: RuntimePublishedDeliverableStore,
        *,
        payload_writer: PayloadWriter = persist_published_payload,
        payload_discarder: PayloadDiscarder = discard_published_payload,
    ) -> None:
        self._store = store
        self._payload_writer = payload_writer
        self._payload_discarder = payload_discarder

    def publish_script(
        self,
        *,
        session_id: int,
        workflow_id: str,
        attempt_id: int,
        payload: JsonObjectPayload,
        summary: JsonObjectPayload,
    ) -> RuntimePublishedDeliverableRecord:
        operation = "publish_script_deliverable"
        session = self._store.load_session(session_id)
        node = self._store.load_node(session_id, "script")
        attempt = self._store.load_attempt(session_id, attempt_id)
        if session is None or node is None or attempt is None:
            raise RuntimeStoreError(
                reason_code=RuntimeStoreReason.RECORD_NOT_FOUND,
                operation=operation,
                message="script publication requires an existing session, node, and attempt",
            )
        if attempt.node_id != node.node_id:
            raise RuntimeStoreError(
                reason_code=RuntimeStoreReason.STATE_CONFLICT,
                operation=operation,
                message="script publication attempt does not belong to the script node",
            )
        persisted_payload = JsonObjectPayload.from_mapping(
            {
                "deliverable_type": "script",
                "workflow_state_id": str(workflow_id),
                "scope_type": node.scope_type,
                "scope_id": node.scope_ref,
                "revision_no": node.revision_index,
                "attempt_id": attempt_id,
                **payload.to_dict(),
            },
            field_path="script_published_deliverable.payload",
        )
        payload_ref = self._payload_writer(
            workflow_id=str(workflow_id),
            deliverable_type="script",
            attempt_id=attempt_id,
            revision_no=node.revision_index,
            payload=persisted_payload.to_dict(),
        )
        if not isinstance(payload_ref, str) or not payload_ref.strip():
            raise RuntimeStoreError(
                reason_code=RuntimeStoreReason.INTEGRITY_ERROR,
                operation=operation,
                message="published payload writer returned an empty reference",
            )
        normalized_payload_ref = payload_ref.strip()
        try:
            return self._store.publish_deliverable(
                RuntimePublishedDeliverableWrite(
                    session_id=session_id,
                    node_key=node.node_key,
                    attempt_id=attempt_id,
                    deliverable_type="script",
                    payload_ref=normalized_payload_ref,
                    summary=summary,
                    scope_type=node.scope_type,
                    scope_id=node.scope_ref,
                    revision_no=node.revision_index,
                    expected_session_status=session.status,
                    expected_node_status=node.status,
                    expected_attempt_status=attempt.status,
                    is_candidate=True,
                    is_approved=False,
                )
            )
        except Exception as publication_error:
            try:
                self._payload_discarder(normalized_payload_ref)
            except Exception as cleanup_error:
                raise RuntimeStoreError(
                    reason_code=RuntimeStoreReason.INTEGRITY_ERROR,
                    operation=operation,
                    message=(
                        "deliverable publication failed and payload cleanup also failed: "
                        f"publication={type(publication_error).__name__}; "
                        f"cleanup={type(cleanup_error).__name__}"
                    ),
                ) from cleanup_error
            raise

    def approve(
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
            raise RuntimeStoreError(
                reason_code=RuntimeStoreReason.RECORD_NOT_FOUND,
                operation="approve_published_deliverable",
                message="published deliverable was not found for approval",
            )
        return self._store.approve_deliverable(
            RuntimePublishedDeliverableApprovalCommand(
                session_id=session_id,
                node_key=node_key,
                attempt_id=attempt_id,
                deliverable_id=deliverable.deliverable_id,
                expected_is_candidate=deliverable.is_candidate,
                expected_is_approved=deliverable.is_approved,
                target_is_candidate=False,
                target_is_approved=True,
            )
        )
