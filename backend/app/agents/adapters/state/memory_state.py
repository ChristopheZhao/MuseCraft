"""Lightweight WorkingMemory state view (fact-based, no decisions).

This module provides a small, domain-neutral snapshot for progress/diagnostic
purposes. It relies only on WM facts/scene_outputs and does not enforce
workflow policy.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from ...memory.short_term.working_memory import WorkingMemory


def build_memory_state(
    wm: Optional[WorkingMemory],
    overview: Optional[Dict[str, Any]] = None,
    *,
    failed_limit: int = 5,
) -> Dict[str, Any]:
    """Return a lightweight state summary derived from WM facts/scene_outputs.

    - It reads scene overview facts (scenes list with completed/failed flags)
      when available; otherwise falls back to counts inferred from outputs.
    - No decisions or planning logic are included; this is for UI/diagnostics.
    """
    state: Dict[str, Any] = {}
    scenes, completed, failed = _extract_scene_sets(wm, overview)
    total = len(scenes) if scenes is not None else max(len(completed), len(failed))
    pending = max(total - len(completed) - len(failed), 0) if total else 0

    outputs_by_kind = _collect_outputs(wm)

    state["total_scenes"] = total
    state["completed_scenes"] = len(completed)
    state["failed_scenes"] = len(failed)
    state["pending_scenes"] = pending
    state["outputs"] = outputs_by_kind
    if failed and scenes:
        state["failed_details"] = _failed_details(scenes, limit=failed_limit)
    return state


def _extract_scene_sets(
    wm: Optional[WorkingMemory],
    overview: Optional[Dict[str, Any]],
) -> Tuple[Optional[list], set, set]:
    scenes = None
    completed = set()
    failed = set()
    view = overview
    if view is None and wm is not None:
        try:
            candidate = wm.get("scene_overview")
            if isinstance(candidate, dict):
                view = candidate
        except Exception:
            view = None
    if isinstance(view, dict):
        scenes = view.get("scenes")
        completed = set(_coerce_int_list(view.get("completed_scene_numbers")))
        failed = set(_coerce_int_list(view.get("failed_scene_numbers")))
    return scenes, completed, failed


def _collect_outputs(wm: Optional[WorkingMemory]) -> Dict[str, int]:
    if wm is None or not hasattr(wm, "facts"):
        return {}
    outputs: Dict[str, int] = {}
    try:
        for key, value in (wm.facts or {}).items():
            if not isinstance(key, str) or not key.startswith("scene_outputs."):
                continue
            kind = key.split(".", 1)[1] if "." in key else ""
            if not kind:
                continue
            bucket = value if isinstance(value, dict) else {}
            outputs[kind] = len(bucket)
    except Exception:
        return outputs
    return outputs


def _failed_details(scenes: Any, limit: int = 5) -> list:
    if not isinstance(scenes, list):
        return []
    details = []
    for scene in scenes:
        if not isinstance(scene, dict) or not scene.get("failed"):
            continue
        entry = {
            "scene_number": scene.get("scene_number"),
            "reason": scene.get("failure_reason") or scene.get("reason"),
        }
        details.append(entry)
        if len(details) >= max(1, limit):
            break
    return details


def _coerce_int_list(values: Any) -> list:
    if values is None:
        return []
    if not isinstance(values, list):
        values = list(values) if isinstance(values, (set, tuple)) else [values]
    numbers = []
    for v in values:
        try:
            numbers.append(int(v))
        except Exception:
            continue
    return numbers


__all__ = ["build_memory_state"]
