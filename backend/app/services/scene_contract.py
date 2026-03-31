"""
Helpers for the media-agent scene contract freeze.

This module does not create a new runtime carrier. It only annotates the
existing `scene_info_payload` boundary with explicit contract metadata so the
authoritative path is visible and future evolution stays in-place.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


SCENE_CONTRACT_VERSION = "v2"
SCENE_CONTRACT_DOC_REF = "docs/architecture/scene_contract_v2_freeze_20260329.md"
_VALID_MODES = {"image_generation", "video_generation"}


def build_scene_owner_matrix() -> Dict[str, Any]:
    """Return the frozen owner/SoT matrix for scene semantics."""
    return {
        "runtime_owner": "control_plane",
        "authoritative_carrier_path": "scene_info_payload.scenes_to_generate[]",
        "persisted_reference": "scene_info_ref",
        "carrier_evolution": "in_place_only",
        "parallel_carrier_forbidden": True,
        "read_models": {
            "scene_overview": "planning/read-model only",
            "task_overview": "planning/read-model only",
            "scene_dependency_graph": "planning/read-model only",
        },
        "validation_surfaces": [
            "docs/plans/active",
            "validation_ledger",
            "review_notes",
        ],
        "forbidden_surfaces": [
            "runtime_input_payload",
            "published_deliverables",
            "working_memory_primary_slots",
        ],
    }


def build_scene_contract_meta(*, mode: str) -> Dict[str, Any]:
    normalized_mode = str(mode or "").strip().lower()
    if normalized_mode not in _VALID_MODES:
        raise ValueError(f"unsupported scene contract mode: {mode}")
    return {
        "contract_version": SCENE_CONTRACT_VERSION,
        "status": "freeze_only",
        "mode": normalized_mode,
        "semantic_unit": "local_event",
        "timing_model": {
            "projection": "relative_phases",
            "supports_extension": True,
            "hardcoded_seconds_template_forbidden": True,
        },
        "scene_v2_fields": [
            "opening_state",
            "event_trigger",
            "action_phases",
            "end_state",
            "global_locks_ref",
            "continuity_ref",
        ],
        "owner_matrix": build_scene_owner_matrix(),
        "doc_ref": SCENE_CONTRACT_DOC_REF,
    }


def annotate_scene_info_payload(
    payload: Optional[Dict[str, Any]],
    *,
    mode: str,
) -> Dict[str, Any]:
    """
    Annotate the existing scene_info_payload with explicit scene-contract metadata.

    This keeps the current carrier as the only media-agent scene semantic path.
    """
    merged = dict(payload or {})
    merged["scene_contract_meta"] = build_scene_contract_meta(mode=mode)
    return merged


__all__ = [
    "SCENE_CONTRACT_DOC_REF",
    "SCENE_CONTRACT_VERSION",
    "annotate_scene_info_payload",
    "build_scene_contract_meta",
    "build_scene_owner_matrix",
]
