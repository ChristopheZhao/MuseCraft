"""Facts-only MAS summary view.

聚合 MAS WorkingMemory 中的领域事实，只回答 scene/deliverable 事实层状态。
它不是 runtime read-model，也不回答 live execution status/progress/current_step。
"""
from __future__ import annotations

from typing import Any, Dict, Optional, TYPE_CHECKING

from ...utils.memory_helpers import get_mas_working_memory

if TYPE_CHECKING:
    from ...memory.short_term.service import WorkingMemoryService


def build_mas_state_view(workflow_id: str, *, service: WorkingMemoryService) -> Dict[str, Any]:
    """Return a lightweight facts summary derived from WM facts only."""
    wm = get_mas_working_memory(str(workflow_id), service=service)
    overview = wm.get("scene_overview", {}) if wm else {}

    scenes = overview.get("scenes") if isinstance(overview, dict) else []
    completed_ids = set()
    failed_ids = set()
    if isinstance(overview, dict):
        completed_ids = set(_coerce_int_list(overview.get("completed_scene_numbers")))
        failed_ids = set(_coerce_int_list(overview.get("failed_scene_numbers")))
    outputs_by_kind = _collect_scene_output_buckets(wm)
    for bucket in (outputs_by_kind or {}).values():
        if not isinstance(bucket, dict):
            continue
        for sn in bucket.keys():
            try:
                completed_ids.add(int(sn))
            except Exception:
                continue

    total = len(scenes) if isinstance(scenes, list) else 0
    pending = max(total - len(completed_ids) - len(failed_ids), 0) if total else 0

    state: Dict[str, Any] = {
        "workflow_id": str(workflow_id),
        "projection_role": "facts_summary",
        "total_scenes": total,
        "completed_scenes": len(completed_ids),
        "failed_scenes": len(failed_ids),
        "pending_scenes": pending,
        "outputs_count": _collect_outputs_count(outputs_by_kind),
    }
    return state


def _collect_scene_output_buckets(wm: Any) -> Dict[str, Any]:
    """Collect scene_outputs buckets keyed by kind from WorkingMemory.

    Canonical shape:
    - separate facts under keys like `scene_outputs.image`
    """
    buckets: Dict[str, Any] = {}
    if wm is None:
        return buckets
    # Preferred: scan fact keys
    try:
        keys = wm.list_keys() if hasattr(wm, "list_keys") else []
    except Exception:
        keys = []
    for key in keys or []:
        if not isinstance(key, str) or not key.startswith("scene_outputs."):
            continue
        kind = key.split(".", 1)[1] if "." in key else ""
        if not kind:
            continue
        try:
            value = wm.get(key, {})
        except Exception:
            value = {}
        if isinstance(value, dict):
            buckets[kind] = value
    return buckets


def _collect_outputs_count(outputs_by_kind: Any) -> Dict[str, int]:
    if not isinstance(outputs_by_kind, dict):
        return {}
    counts: Dict[str, int] = {}
    for kind, bucket in outputs_by_kind.items():
        if not isinstance(kind, str) or not kind:
            continue
        counts[kind] = len(bucket) if isinstance(bucket, dict) else 0
    return counts


def _coerce_int_list(values: Any) -> list:
    if values is None:
        return []
    if not isinstance(values, list):
        try:
            values = list(values) if isinstance(values, (set, tuple)) else [values]
        except Exception:
            values = [values]
    nums = []
    for v in values:
        try:
            nums.append(int(v))
        except Exception:
            continue
    return nums


__all__ = ["build_mas_state_view"]
