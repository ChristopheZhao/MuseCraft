"""Video-domain adapter that proxies to the operator layer.

WorkingMemory interacts with this module instead of referencing the operator
directly so that future domains can plug in their own adapters without
touching the container.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..operators import video_scene as _ops

SceneSnapshot = _ops.SceneSnapshot
SceneArtifact = _ops.SceneArtifact

upsert_scene = _ops.upsert_scene
has_scene = _ops.has_scene
mark_scene_completed = _ops.mark_scene_completed
mark_scene_failed = _ops.mark_scene_failed
set_scene_failed_state = _ops.set_scene_failed_state
ready_scene_numbers = _ops.ready_scene_numbers
scene_view = _ops.scene_view
classify_scenes = _ops.classify_scenes
build_fact_observation = _ops.build_fact_observation
export_observation = _ops.export_observation
completed_outputs = _ops.completed_outputs
failed_outputs = _ops.failed_outputs
latest_iteration_artifacts = _ops.latest_iteration_artifacts
set_prepared_assets = _ops.set_prepared_assets
get_prepared_assets = _ops.get_prepared_assets

__all__ = [
    "SceneSnapshot",
    "SceneArtifact",
    "upsert_scene",
    "has_scene",
    "mark_scene_completed",
    "mark_scene_failed",
    "set_scene_failed_state",
    "ready_scene_numbers",
    "scene_view",
    "classify_scenes",
    "build_fact_observation",
    "export_observation",
    "completed_outputs",
    "failed_outputs",
    "latest_iteration_artifacts",
    "set_prepared_assets",
    "get_prepared_assets",
]
