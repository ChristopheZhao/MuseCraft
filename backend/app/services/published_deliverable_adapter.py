"""Canonical payload builders for published deliverables."""
from __future__ import annotations

from typing import Any, Dict, TYPE_CHECKING

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
