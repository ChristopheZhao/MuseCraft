from __future__ import annotations

"""Builds base observation views for ReAct agents."""

from typing import Any, Dict, List, Optional

from ..short_term.working_memory import WorkingMemory


def build_react_context_view(
    wm: Optional[WorkingMemory],
    *,
    iteration: int,
    act_log: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Construct a WM-backed observation snapshot without domain coupling."""
    base_view: Dict[str, Any] = {
        "iteration": iteration,
        "scenes": [],
        "completed_scene_numbers": [],
        "failed_scene_numbers": [],
        "prepared_assets_refs": [],
        "notes": [],
        "act_log": act_log or [],
        "recent_events": [],
    }
    if wm is None:
        return base_view

    # Surface lightweight WM facts for downstream adapters
    if hasattr(wm, "facts") and isinstance(wm.facts, dict):
        base_view["facts"] = dict(wm.facts)
    if hasattr(wm, "workflow_facts") and isinstance(wm.workflow_facts, dict):
        base_view["workflow_facts"] = dict(wm.workflow_facts)

    notes = getattr(wm, "notes", []) or []
    base_view["notes"] = [str(note) for note in notes[-10:]]

    try:
        base_view["recent_events"] = wm.get_recent_step_summaries(10)
    except Exception:
        base_view["recent_events"] = []

    slots = getattr(wm, "facts_slots", {}) or {}
    prepared_bucket = slots.get("prepared_assets") or {}
    prepared_refs = []
    if isinstance(prepared_bucket, dict):
        for key in prepared_bucket.keys():
            try:
                prepared_refs.append(int(key))
            except Exception:
                continue
    base_view["prepared_assets_refs"] = sorted(set(prepared_refs))

    return base_view


__all__ = ["build_react_context_view"]
