"""MAS-level workflow state view (facts-based, no decisions).

聚合 MAS WorkingMemory 中的事实，提供轻量的工作流摘要：
- status/progress/current_step（从概览 fact 推导）
- 已完成/失败/待处理场景数（基于 scene_overview + scene_outputs）
- 最近错误/备注（可选）

不存储原子事实，不做决策，仅用于 UI/编排层展示。
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from ...utils.memory_helpers import get_mas_working_memory


def build_mas_state_view(workflow_id: str) -> Dict[str, Any]:
    """Return a lightweight MAS workflow state view derived from WM facts."""
    wm = get_mas_working_memory(str(workflow_id))
    overview = wm.get("scene_overview", {}) if wm else {}
    outputs = wm.get("scene_outputs", {}) if wm else {}
    wf_meta = wm.get("workflow_overview", {}) if wm else {}

    scenes = overview.get("scenes") if isinstance(overview, dict) else []
    completed_ids = set()
    failed_ids = set()
    if isinstance(overview, dict):
        completed_ids = set(_coerce_int_list(overview.get("completed_scene_numbers")))
        failed_ids = set(_coerce_int_list(overview.get("failed_scene_numbers")))
    if isinstance(outputs, dict):
        for bucket in outputs.values():
            if isinstance(bucket, dict):
                for sn in bucket.keys():
                    try:
                        completed_ids.add(int(sn))
                    except Exception:
                        continue

    total = len(scenes) if isinstance(scenes, list) else 0
    pending = max(total - len(completed_ids) - len(failed_ids), 0) if total else 0

    state: Dict[str, Any] = {
        "workflow_id": str(workflow_id),
        "total_scenes": total,
        "completed_scenes": len(completed_ids),
        "failed_scenes": len(failed_ids),
        "pending_scenes": pending,
        "status": wf_meta.get("status") if isinstance(wf_meta, dict) else None,
        "progress": wf_meta.get("progress") if isinstance(wf_meta, dict) else None,
        "current_step": wf_meta.get("current_step") if isinstance(wf_meta, dict) else None,
        "outputs_count": _collect_outputs_count(outputs),
    }
    last_error = wf_meta.get("last_error") if isinstance(wf_meta, dict) else None
    if last_error:
        state["last_error"] = last_error
    return state


def _collect_outputs_count(outputs: Any) -> Dict[str, int]:
    if not isinstance(outputs, dict):
        return {}
    counts: Dict[str, int] = {}
    for key, val in outputs.items():
        if not isinstance(key, str) or not key.startswith("scene_outputs."):
            continue
        kind = key.split(".", 1)[1] if "." in key else ""
        bucket = val if isinstance(val, dict) else {}
        counts[kind] = len(bucket)
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
