"""
Compatibility bridge helpers for explicitly projecting published deliverables into shared WM.

These projections are not authoritative boundary truth. Active runtime paths should read
published-deliverable refs from the runtime carrier (`session.input_payload`) instead.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, TYPE_CHECKING

from .published_deliverable_service import (
    PUBLISHED_DELIVERABLES_PAYLOAD_KEY,
    get_published_deliverables,
    load_published_payload,
)

if TYPE_CHECKING:
    from ..agents.memory.short_term.service import WorkingMemoryService


def _read_shared_fact(
    workflow_id: str,
    key: str,
    default: Any,
    *,
    service: "WorkingMemoryService",
) -> Any:
    from ..agents.utils.memory_helpers import read_shared_fact

    return read_shared_fact(
        workflow_id,
        key,
        default,
        service=service,
    )


def _write_shared_fact(
    workflow_id: str,
    key: str,
    value: Any,
    *,
    service: "WorkingMemoryService",
) -> None:
    from ..agents.utils.memory_helpers import write_shared_fact

    write_shared_fact(
        workflow_id,
        key,
        value,
        service=service,
    )


def _wm_latest_key(node_key: str) -> str:
    return f"{PUBLISHED_DELIVERABLES_PAYLOAD_KEY}.{node_key}.latest"


def _wm_approved_key(node_key: str) -> str:
    return f"{PUBLISHED_DELIVERABLES_PAYLOAD_KEY}.{node_key}.approved"


def build_script_deliverable_payload(
    workflow_id: str,
    *,
    service: "WorkingMemoryService",
) -> Dict[str, Any]:
    concept_plan = _read_shared_fact(
        workflow_id,
        "project.concept_plan",
        {},
        service=service,
    ) or {}
    scene_overview = _read_shared_fact(
        workflow_id,
        "scene_overview",
        {},
        service=service,
    ) or {}
    scene_scripts = _read_shared_fact(
        workflow_id,
        "project.scene_scripts",
        {},
        service=service,
    ) or {}

    if not any([concept_plan, scene_overview, scene_scripts]):
        raise ValueError(
            f"Script deliverable cannot be published for workflow {workflow_id}: no shared facts found"
        )

    return {
        "concept_plan": concept_plan,
        "scene_overview": scene_overview,
        "scene_scripts": scene_scripts,
    }


def project_deliverable_ref_to_shared_wm(
    workflow_id: str,
    *,
    node_key: str,
    ref: Dict[str, Any],
    service: "WorkingMemoryService",
) -> None:
    _write_shared_fact(
        workflow_id,
        _wm_latest_key(node_key),
        dict(ref),
        service=service,
    )
    _write_shared_fact(
        workflow_id,
        _wm_approved_key(node_key),
        dict(ref) if bool(ref.get("is_approved")) else None,
        service=service,
    )


def project_payload_deliverables_to_shared_wm(
    workflow_id: str,
    payload: Optional[Dict[str, Any]],
    *,
    service: "WorkingMemoryService",
) -> None:
    for node_key, ref in get_published_deliverables(payload).items():
        project_deliverable_ref_to_shared_wm(
            workflow_id,
            node_key=node_key,
            ref=ref,
            service=service,
        )


def get_projected_deliverable_ref_from_shared_wm(
    workflow_id: str,
    *,
    node_key: str,
    service: "WorkingMemoryService",
    prefer_approved: bool = True,
) -> Optional[Dict[str, Any]]:
    if prefer_approved:
        approved_ref = _read_shared_fact(
            workflow_id,
            _wm_approved_key(node_key),
            None,
            service=service,
        )
        if isinstance(approved_ref, dict):
            return dict(approved_ref)
    latest_ref = _read_shared_fact(
        workflow_id,
        _wm_latest_key(node_key),
        None,
        service=service,
    )
    return dict(latest_ref) if isinstance(latest_ref, dict) else None


def load_published_deliverable_payload_from_shared_wm(
    workflow_id: str,
    *,
    node_key: str,
    service: "WorkingMemoryService",
    prefer_approved: bool = True,
) -> Optional[Dict[str, Any]]:
    ref = get_projected_deliverable_ref_from_shared_wm(
        workflow_id,
        node_key=node_key,
        service=service,
        prefer_approved=prefer_approved,
    )
    if not isinstance(ref, dict):
        return None
    payload_ref = str(ref.get("payload_ref") or "").strip()
    if not payload_ref:
        return None
    return load_published_payload(payload_ref)
