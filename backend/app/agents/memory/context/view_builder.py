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

    return base_view


__all__ = ["build_react_context_view"]
