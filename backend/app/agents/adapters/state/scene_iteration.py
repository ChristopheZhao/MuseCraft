from __future__ import annotations

"""Helpers for summarising multi-scene iteration state from WorkingMemory."""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ...memory.short_term.working_memory import WorkingMemory
from ..video import VideoMemoryAdapter


@dataclass
class SceneIterationStateSchema:
    include_completed_count: bool = True
    include_failed_count: bool = True
    include_failed_details: bool = True
    include_recent_events: bool = True
    include_recent_artifacts: bool = False
    events_limit: int = 5
    failed_limit: int = 4
    artifacts_limit: int = 3


class SceneIterationStateBuilder:
    """Transforms WorkingMemory facts into lightweight iteration summaries."""

    def __init__(self, schema: Optional[SceneIterationStateSchema] = None) -> None:
        self.schema = schema or SceneIterationStateSchema()

    def build(
        self,
        wm: Optional[WorkingMemory],
        *,
        overview: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        if wm is None and overview is None:
            return payload

        completed_numbers, failed_numbers = self._extract_completion_sets(wm, overview)
        if self.schema.include_completed_count:
            payload["completed_count"] = len(completed_numbers)
        if self.schema.include_failed_count:
            payload["failed_count"] = len(failed_numbers)

        if self.schema.include_failed_details:
            payload["failed_details"] = self._failed_details(wm, overview)

        if self.schema.include_recent_events and wm is not None:
            try:
                payload["recent_events"] = wm.get_recent_step_summaries(self.schema.events_limit)
            except Exception:
                payload["recent_events"] = []

        if self.schema.include_recent_artifacts and wm is not None:
            try:
                payload["recent_artifacts"] = wm.latest_iteration_artifacts(limit=self.schema.artifacts_limit)
            except Exception:
                payload["recent_artifacts"] = []

        return payload

    def _extract_completion_sets(
        self,
        wm: Optional[WorkingMemory],
        overview: Optional[Dict[str, Any]],
    ) -> tuple[List[int], List[int]]:
        if isinstance(overview, dict):
            completed = _coerce_int_list(overview.get("completed_scene_numbers"))
            failed = _coerce_int_list(overview.get("failed_scene_numbers"))
            if completed or failed:
                return completed, failed
        if wm is None:
            return [], []
        try:
            adapter = VideoMemoryAdapter(wm)
            view = adapter.build_fact_observation()
        except Exception:
            return [], []
        completed = _coerce_int_list(view.get("completed_scene_numbers"))
        failed = _coerce_int_list(view.get("failed_scene_numbers"))
        return completed, failed

    def _failed_details(
        self,
        wm: Optional[WorkingMemory],
        overview: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        scenes = []
        if isinstance(overview, dict):
            scenes = overview.get("scenes", [])
        elif wm is not None:
            try:
                adapter = VideoMemoryAdapter(wm)
                view = adapter.build_fact_observation()
                scenes = view.get("scenes", [])
            except Exception:
                scenes = []
        details: List[Dict[str, Any]] = []
        if not isinstance(scenes, list):
            return details
        for scene in scenes:
            if not isinstance(scene, dict):
                continue
            if not scene.get("failed"):
                continue
            entry = {
                "scene_number": scene.get("scene_number"),
                "reason": scene.get("failure_reason"),
                "retry_count": scene.get("retry_count"),
            }
            details.append(entry)
            if len(details) >= self.schema.failed_limit:
                break
        return details


def _coerce_int_list(values: Any) -> List[int]:
    if values is None:
        return []
    if not isinstance(values, list):
        values = list(values) if isinstance(values, (set, tuple)) else [values]
    numbers: List[int] = []
    for value in values:
        try:
            num = int(value)
        except Exception:
            continue
        numbers.append(num)
    return numbers


__all__ = ["SceneIterationStateSchema", "SceneIterationStateBuilder"]
