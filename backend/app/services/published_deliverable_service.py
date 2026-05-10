"""
Published stage-deliverable helpers for gate/resume/downstream stable references.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from ..core.config import settings
from ..models import (
    WorkflowNodeState,
    WorkflowPublishedDeliverable,
    WorkflowSession,
)


PUBLISHED_DELIVERABLES_PAYLOAD_KEY = "published_deliverables"
PUBLISHED_DELIVERABLE_REF_TYPE = "published_deliverable"


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _resolve_config_path(path_value: str) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    return (_project_root() / path).resolve()


def _published_deliverable_dir() -> Path:
    return _resolve_config_path(str(settings.TEMP_PATH)) / "published_deliverables"


def _resolve_payload_path(payload_ref: str) -> Path:
    ref_path = Path(str(payload_ref or ""))
    if ref_path.is_absolute():
        return ref_path
    return (_backend_root() / ref_path).resolve()


def _persist_payload(
    *,
    workflow_id: str,
    deliverable_type: str,
    attempt_id: int,
    revision_no: int,
    payload: Dict[str, Any],
) -> str:
    base_dir = _published_deliverable_dir()
    base_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{deliverable_type}_{workflow_id}_attempt{attempt_id}_rev{revision_no}.json"
    target_path = (base_dir / filename).resolve()
    with open(target_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False)
    return str(target_path)


def load_published_payload(payload_ref: Optional[str]) -> Optional[Dict[str, Any]]:
    if not payload_ref:
        return None
    try:
        payload_path = _resolve_payload_path(payload_ref)
        if not payload_path.exists():
            return None
        with open(payload_path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def build_deliverable_ref(deliverable: WorkflowPublishedDeliverable) -> Dict[str, Any]:
    return {
        "type": PUBLISHED_DELIVERABLE_REF_TYPE,
        "deliverable_id": deliverable.id,
        "deliverable_type": deliverable.deliverable_type,
        "scope_type": deliverable.scope_type,
        "scope_id": deliverable.scope_id,
        "attempt_id": deliverable.attempt_id,
        "revision_no": deliverable.revision_no,
        "payload_ref": deliverable.payload_ref,
        "summary": deliverable.summary or {},
        "is_candidate": bool(deliverable.is_candidate),
        "is_approved": bool(deliverable.is_approved),
    }


def get_published_deliverables(payload: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    if not isinstance(payload, dict):
        return {}
    deliverables = payload.get(PUBLISHED_DELIVERABLES_PAYLOAD_KEY)
    if not isinstance(deliverables, dict):
        return {}
    normalized: Dict[str, Dict[str, Any]] = {}
    for node_key, ref in deliverables.items():
        if isinstance(node_key, str) and isinstance(ref, dict):
            normalized[node_key] = dict(ref)
    return normalized


def get_published_deliverable_ref(
    payload: Optional[Dict[str, Any]],
    *,
    node_key: str,
) -> Optional[Dict[str, Any]]:
    refs = get_published_deliverables(payload)
    ref = refs.get(node_key)
    return dict(ref) if isinstance(ref, dict) else None


def set_published_deliverable_ref(
    payload: Optional[Dict[str, Any]],
    *,
    node_key: str,
    ref: Dict[str, Any],
) -> Dict[str, Any]:
    merged = dict(payload or {})
    deliverables = dict(merged.get(PUBLISHED_DELIVERABLES_PAYLOAD_KEY) or {})
    deliverables[str(node_key)] = dict(ref)
    merged[PUBLISHED_DELIVERABLES_PAYLOAD_KEY] = deliverables
    return merged


def clear_published_deliverable_ref(
    payload: Optional[Dict[str, Any]],
    *,
    node_key: str,
) -> Dict[str, Any]:
    merged = dict(payload or {})
    deliverables = dict(merged.get(PUBLISHED_DELIVERABLES_PAYLOAD_KEY) or {})
    deliverables.pop(str(node_key), None)
    if deliverables:
        merged[PUBLISHED_DELIVERABLES_PAYLOAD_KEY] = deliverables
    else:
        merged.pop(PUBLISHED_DELIVERABLES_PAYLOAD_KEY, None)
    return merged


class PublishedDeliverableService:
    """Publishes non-artifact stage outputs as stable, referenced deliverables."""

    @staticmethod
    def publish_script_deliverable_sync(
        db: Session,
        *,
        session: WorkflowSession,
        workflow_id: str,
        attempt_id: int,
        payload: Dict[str, Any],
        summary: Optional[Dict[str, Any]] = None,
    ) -> WorkflowPublishedDeliverable:
        node = (
            db.query(WorkflowNodeState)
            .filter(
                WorkflowNodeState.session_id == session.id,
                WorkflowNodeState.node_key == "script",
            )
            .first()
        )
        if node is None:
            raise ValueError(f"Workflow node script not found for session {session.id}")

        revision_no = int(node.revision_index or 0)
        persisted_payload = {
            "deliverable_type": "script",
            "workflow_state_id": str(workflow_id),
            "scope_type": node.scope_type,
            "scope_id": node.scope_ref,
            "revision_no": revision_no,
            "attempt_id": attempt_id,
            **dict(payload or {}),
        }
        payload_ref = _persist_payload(
            workflow_id=str(workflow_id),
            deliverable_type="script",
            attempt_id=attempt_id,
            revision_no=revision_no,
            payload=persisted_payload,
        )

        deliverable = WorkflowPublishedDeliverable(
            session_id=session.id,
            node_id=node.id,
            attempt_id=attempt_id,
            deliverable_type="script",
            scope_type=node.scope_type,
            scope_id=node.scope_ref,
            revision_no=revision_no,
            payload_ref=payload_ref,
            summary=summary or {},
            is_candidate=True,
            is_approved=False,
        )
        db.add(deliverable)
        db.flush()
        db.refresh(deliverable)
        return deliverable

    @staticmethod
    def get_node_deliverable_ref_sync(
        db: Session,
        *,
        session: WorkflowSession,
        node_key: str,
        attempt_id: Optional[int],
    ) -> Optional[Dict[str, Any]]:
        if attempt_id is None:
            return None
        node = (
            db.query(WorkflowNodeState)
            .filter(
                WorkflowNodeState.session_id == session.id,
                WorkflowNodeState.node_key == node_key,
            )
            .first()
        )
        if node is None:
            return None
        deliverable = (
            db.query(WorkflowPublishedDeliverable)
            .filter(
                WorkflowPublishedDeliverable.session_id == session.id,
                WorkflowPublishedDeliverable.node_id == node.id,
                WorkflowPublishedDeliverable.attempt_id == attempt_id,
            )
            .order_by(WorkflowPublishedDeliverable.id.desc())
            .first()
        )
        return build_deliverable_ref(deliverable) if deliverable is not None else None

    @staticmethod
    def mark_node_deliverable_approved_sync(
        db: Session,
        *,
        session: WorkflowSession,
        node_key: str,
        attempt_id: Optional[int],
    ) -> WorkflowPublishedDeliverable:
        node = (
            db.query(WorkflowNodeState)
            .filter(
                WorkflowNodeState.session_id == session.id,
                WorkflowNodeState.node_key == node_key,
            )
            .first()
        )
        if node is None:
            raise ValueError(f"Workflow node {node_key} not found for session {session.id}")
        if attempt_id is None:
            raise ValueError(f"Cannot approve deliverable for node {node_key} without attempt_id")

        deliverable = (
            db.query(WorkflowPublishedDeliverable)
            .filter(
                WorkflowPublishedDeliverable.session_id == session.id,
                WorkflowPublishedDeliverable.node_id == node.id,
                WorkflowPublishedDeliverable.attempt_id == attempt_id,
            )
            .order_by(WorkflowPublishedDeliverable.id.desc())
            .first()
        )
        if deliverable is None:
            raise ValueError(
                f"No published deliverable found for node {node_key} attempt {attempt_id} in session {session.id}"
            )

        deliverable.is_candidate = False
        deliverable.is_approved = True
        db.flush()
        db.refresh(deliverable)
        return deliverable
