from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional

from ...memory.short_term.working_memory import WorkingMemory
from .models import SceneSnapshot, SceneArtifact


@dataclass
class VideoMemoryState:
    scenes: Dict[int, SceneSnapshot] = field(default_factory=dict)
    depends_map: Dict[int, Optional[int]] = field(default_factory=dict)
    completed: Dict[int, SceneArtifact] = field(default_factory=dict)
    failed: Dict[int, Dict[str, Any]] = field(default_factory=dict)
    retry_counts: Dict[int, int] = field(default_factory=dict)
    failed_retryable: Dict[int, bool] = field(default_factory=dict)
    scene_events: Dict[int, Deque[Dict[str, Any]]] = field(default_factory=dict)


class VideoMemoryAdapter:
    """桥接 WorkingMemory 与 Video 领域逻辑。"""

    STATE_KEY = "video_domain_state"

    def __init__(self, wm: WorkingMemory):
        self._wm = wm

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------
    def _state(self) -> VideoMemoryState:
        state = self._wm.get_fact(self.STATE_KEY)
        if not isinstance(state, VideoMemoryState):
            state = VideoMemoryState()
            self._wm.set_fact(self.STATE_KEY, state)
        return state

    def _event_queue(self) -> Deque[Dict[str, Any]]:
        return deque(maxlen=self._wm.journal_max_events)

    def _record_scene_event(
        self,
        scene_number: int,
        *,
        action: str,
        success: bool,
        error_type: Optional[str] = None,
        dur_sec: Optional[float] = None,
    ) -> None:
        state = self._state()
        sn = int(scene_number)
        dq = state.scene_events.setdefault(sn, self._event_queue())
        event: Dict[str, Any] = {
            "scene_number": sn,
            "action": action,
            "success": bool(success),
        }
        if error_type:
            event["error_type"] = error_type
        if dur_sec is not None:
            try:
                event["dur_sec"] = float(dur_sec)
            except Exception:
                pass
        dq.append(event)


    # ------------------------------------------------------------------
    # Basic scene operations
    # ------------------------------------------------------------------
    def upsert_scene(self, snapshot: SceneSnapshot) -> None:
        state = self._state()
        sn = int(snapshot.scene_number)
        state.scenes[sn] = snapshot
        state.depends_map[sn] = snapshot.depends_on_scene
        state.scene_events.setdefault(sn, self._event_queue())

    def get_scene(self, scene_number: int) -> Optional[SceneSnapshot]:
        try:
            sn = int(scene_number)
        except Exception:
            return None
        return self._state().scenes.get(sn)

    def ensure_scene(self, scene_number: int) -> SceneSnapshot:
        state = self._state()
        sn = int(scene_number)
        snapshot = state.scenes.get(sn)
        if snapshot is None:
            snapshot = SceneSnapshot(scene_number=sn)
            state.scenes[sn] = snapshot
        state.scene_events.setdefault(sn, self._event_queue())
        return snapshot

    def has_scene(self, scene_number: int) -> bool:
        try:
            sn = int(scene_number)
        except Exception:
            return False
        return sn in self._state().scenes

    def mark_completed(self, scene_number: int, artifact: SceneArtifact) -> None:
        sn = int(scene_number)
        state = self._state()
        state.completed[sn] = artifact
        state.failed.pop(sn, None)
        state.retry_counts.pop(sn, None)
        state.failed_retryable.pop(sn, None)
        self._record_scene_event(sn, action="scene_completed", success=True)

    def mark_failed(
        self,
        scene_number: int,
        reason: str,
        metadata: Optional[Dict[str, Any]] = None,
        *,
        retryable: bool = True,
    ) -> None:
        sn = int(scene_number)
        state = self._state()
        state.failed[sn] = {"reason": reason, "metadata": metadata or {}}
        state.failed_retryable[sn] = bool(retryable)
        state.retry_counts[sn] = int(state.retry_counts.get(sn, 0) or 0) + 1
        self._record_scene_event(
            sn,
            action="scene_failed",
            success=False,
            error_type=(metadata or {}).get("error_type"),
        )

    def set_failed_state(
        self,
        scene_number: int,
        reason: str,
        metadata: Optional[Dict[str, Any]] = None,
        *,
        retryable: bool = True,
        retries: Optional[int] = None,
    ) -> None:
        sn = int(scene_number)
        state = self._state()
        state.failed[sn] = {"reason": reason, "metadata": metadata or {}}
        state.failed_retryable[sn] = bool(retryable)
        if retries is not None:
            try:
                state.retry_counts[sn] = int(retries)
            except Exception:
                state.retry_counts[sn] = 0
        else:
            state.retry_counts.setdefault(sn, 0)

    # ------------------------------------------------------------------
    # Scene inspection helpers
    # ------------------------------------------------------------------
    def ready_scene_numbers(self) -> List[int]:
        state = self._state()
        ready: List[int] = []
        for sn in sorted(state.scenes.keys()):
            if sn in state.completed:
                continue
            dep = state.depends_map.get(sn)
            if dep and dep not in state.completed:
                continue
            ready.append(sn)
        return ready

    def scene_view(self, scene_number: int, *, max_events: int = 5) -> Dict[str, Any]:
        state = self._state()
        sn = int(scene_number)
        snapshot = state.scenes.get(sn)
        view = {"scene_number": sn}
        if snapshot:
            view.update(snapshot.as_fact())
        view["completed"] = sn in state.completed
        view["failed"] = sn in state.failed
        view["retry_count"] = int(state.retry_counts.get(sn, 0))
        dq = list(state.scene_events.get(sn) or [])
        if dq and max_events > 0:
            view["events"] = dq[-max_events:]
        prepared = self.get_prepared_assets(sn)
        if prepared:
            view["prepared_assets_keys"] = list(prepared.keys())
        return view

    def classify_scenes(
        self,
        *,
        ready_limit: int = 5,
        dependency_limit: int = 3,
        failure_limit: int = 3,
        ready_event_limit: int = 3,
    ) -> Dict[str, Any]:
        ready_numbers = self.ready_scene_numbers()
        state = self._state()
        total = len(state.scenes)
        completed = len(state.completed)
        failed = len(state.failed)
        summary = {
            "total": total,
            "completed": completed,
            "failed": failed,
            "ready": len(ready_numbers),
            "pending": max(total - completed - failed, 0),
        }
        ready_views = [self.scene_view(sn, max_events=ready_event_limit) for sn in ready_numbers[:ready_limit]]
        dep_views: List[Dict[str, Any]] = []
        for sn, dep in state.depends_map.items():
            if dep and dep not in state.completed:
                dep_views.append(self.scene_view(dep))
            if len(dep_views) >= dependency_limit:
                break
        failure_views = [
            self.scene_view(sn, max_events=ready_event_limit) for sn in list(state.failed.keys())[:failure_limit]
        ]
        retry_hotspots = [
            {
                "scene_number": sn,
                "retries": state.retry_counts.get(sn, 0),
                "retryable": state.failed_retryable.get(sn, True),
                "failure_reason": (state.failed.get(sn) or {}).get("reason"),
            }
            for sn in list(state.failed.keys())[:failure_limit]
        ]
        global_stats = {
            "total_scenes": total,
            "completed_scenes": completed,
            "failed_scenes": failed,
            "ready_scene_numbers": ready_numbers,
            "retry_hotspots": retry_hotspots,
            "notes_count": len(self._wm.notes),
        }
        return {
            "summary": summary,
            "ready": ready_views,
            "dependencies": dep_views,
            "failures": failure_views,
            "global_stats": global_stats,
        }

    def build_fact_observation(self) -> Dict[str, Any]:
        state = self._state()
        scenes: List[Dict[str, Any]] = []
        for sn in sorted(state.scenes.keys()):
            snapshot = state.scenes.get(sn)
            payload = snapshot.as_fact() if snapshot else {"scene_number": sn}
            if sn in state.completed:
                payload["completed"] = True
            if sn in state.failed:
                payload["failed"] = True
                payload["failure_reason"] = (state.failed.get(sn) or {}).get("reason")
            payload["retry_count"] = int(state.retry_counts.get(sn, 0))
            scenes.append(payload)
        completed_numbers = sorted(state.completed.keys())
        failed_numbers = sorted(state.failed.keys())
        prepared_refs = sorted((self._wm.facts_slots.get("prepared_assets") or {}).keys())
        return {
            "scenes": scenes,
            "completed_scene_numbers": completed_numbers,
            "failed_scene_numbers": failed_numbers,
            "prepared_assets_refs": prepared_refs,
            "notes": list(self._wm.notes or []),
        }

    def export_observation(
        self,
        *,
        strategy: Optional[Dict[str, Any]] = None,
        target_model: Optional[str] = None,
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        view = self.build_fact_observation()
        try:
            token_estimate = len(json.dumps(view, ensure_ascii=False)) // 4
        except Exception:
            token_estimate = 0
        receipt = {
            "strategy": (strategy or {}).get("name") if isinstance(strategy, dict) else None,
            "model_name": target_model,
            "compacted": False,
            "original_tokens": token_estimate,
            "input_budget_tokens": None,
        }
        return view, receipt

    # ------------------------------------------------------------------
    # Prepared assets slot helpers
    # ------------------------------------------------------------------
    def set_prepared_assets(self, scene_number: int, assets: Dict[str, Any]) -> None:
        try:
            sn = int(scene_number)
        except Exception:
            return
        whitelist = {"style", "characters", "environment", "continuity", "scene_references"}
        normalized: Dict[str, Any] = {}
        if isinstance(assets, dict):
            for key in whitelist:
                value = assets.get(key)
                if value:
                    normalized[key] = value
        if not normalized:
            (self._wm.facts_slots.setdefault("prepared_assets", {})).pop(sn, None)
            return
        bucket = self._wm.facts_slots.setdefault("prepared_assets", {})
        merged = dict(bucket.get(sn, {}))
        merged.update(normalized)
        bucket[sn] = merged

    def get_prepared_assets(self, scene_number: int) -> Optional[Dict[str, Any]]:
        try:
            sn = int(scene_number)
        except Exception:
            return None
        bucket = self._wm.facts_slots.get("prepared_assets") or {}
        record = bucket.get(sn)
        return dict(record) if isinstance(record, dict) else None

    # ------------------------------------------------------------------
    # Artifact helpers
    # ------------------------------------------------------------------
    def completed_outputs(self) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        state = self._state()
        for sn, artifact in sorted(state.completed.items(), key=lambda item: item[0]):
            if isinstance(artifact, SceneArtifact):
                results.append(artifact.as_output(sn))
            elif isinstance(artifact, dict):
                payload = dict(artifact)
                payload.setdefault("scene_number", sn)
                results.append(payload)
            else:
                results.append({"scene_number": sn, "artifact": artifact})
        return results

    def failed_outputs(self) -> List[Dict[str, Any]]:
        failures: List[Dict[str, Any]] = []
        state = self._state()
        for sn, info in sorted(state.failed.items(), key=lambda item: item[0]):
            payload: Dict[str, Any] = {"scene_number": sn}
            if isinstance(info, dict):
                if "reason" in info:
                    payload["reason"] = info["reason"]
                if "metadata" in info and info["metadata"]:
                    payload["metadata"] = info["metadata"]
                if "retryable" in info:
                    payload["retryable"] = bool(info["retryable"])
            failures.append(payload)
        return failures

    def latest_iteration_artifacts(
        self,
        *,
        kind: Optional[str] = None,
        scene_number: Optional[int] = None,
        limit: int = 1,
    ) -> List[Dict[str, Any]]:
        return self._wm.latest_iteration_artifacts(kind=kind, scene_number=scene_number, limit=limit)


__all__ = ["VideoMemoryAdapter", "VideoMemoryState"]
