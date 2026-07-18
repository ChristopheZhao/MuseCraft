"""Canonical payload builders for published deliverables."""
from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Dict

from ..domain import JsonObjectPayload

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


def _normalize_scene_scripts(value: object) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("Script deliverable scene_scripts must be an object")
    normalized: Dict[str, Any] = {}
    for raw_key, script in value.items():
        if not isinstance(raw_key, (str, int)) or isinstance(raw_key, bool):
            raise ValueError("Script deliverable scene key must be a string or integer")
        scene_key = str(raw_key).strip()
        if not scene_key:
            raise ValueError("Script deliverable scene key cannot be empty")
        if scene_key in normalized:
            raise ValueError(f"Duplicate script deliverable scene key: {scene_key}")
        normalized[scene_key] = script
    return normalized


def build_script_deliverable_payload(
    workflow_id: str,
    *,
    service: "WorkingMemoryService",
) -> Dict[str, Any]:
    concept_plan = (
        _read_shared_fact(
            workflow_id,
            "project.concept_plan",
            {},
            service=service,
        )
        or {}
    )
    scene_overview = (
        _read_shared_fact(
            workflow_id,
            "scene_overview",
            {},
            service=service,
        )
        or {}
    )
    scene_scripts = (
        _read_shared_fact(
            workflow_id,
            "project.scene_scripts",
            {},
            service=service,
        )
        or {}
    )

    if not any([concept_plan, scene_overview, scene_scripts]):
        raise ValueError(
            f"Script deliverable cannot be published for workflow {workflow_id}: no shared facts found"
        )

    return JsonObjectPayload.from_mapping(
        {
            "concept_plan": concept_plan,
            "scene_overview": scene_overview,
            "scene_scripts": _normalize_scene_scripts(scene_scripts),
        },
        field_path="script_deliverable.payload",
    ).to_dict()
