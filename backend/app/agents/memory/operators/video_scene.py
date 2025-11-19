"""Video-scene domain helpers for WorkingMemory and SharedWM."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

from app.core.config import settings


@dataclass
class SceneSnapshot:
    scene_number: int
    depends_on_scene: Optional[int] = None
    duration: float = 0.0
    visual_description: str = ""
    narrative_description: str = ""
    image_url: str = ""
    motion_beats: List[Dict[str, Any]] = field(default_factory=list)

    def as_fact(self) -> Dict[str, Any]:
        return {
            "scene_number": self.scene_number,
            "depends_on_scene": self.depends_on_scene,
            "duration": self.duration,
            "visual_description": self.visual_description,
            "narrative_description": self.narrative_description,
            "image_url": self.image_url,
            "has_reference_image": bool(self.image_url),
            "motion_beats": self.motion_beats,
        }


@dataclass
class SceneArtifact:
    video_url: str = ""
    video_path: str = ""
    prompt_text: str = ""
    duration: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def as_output(self, scene_number: int) -> Dict[str, Any]:
        payload = {
            "scene_number": scene_number,
            "video_url": self.video_url,
            "video_path": self.video_path,
            "prompt_text": self.prompt_text,
            "duration": self.duration,
        }
        if self.metadata:
            payload["metadata"] = self.metadata
        return payload


# --- WorkingMemory helpers -------------------------------------------------

def upsert_scene(wm, snapshot: SceneSnapshot) -> None:
    wm.scenes[snapshot.scene_number] = snapshot
    wm.depends_map[snapshot.scene_number] = snapshot.depends_on_scene
    wm.scene_events.setdefault(snapshot.scene_number, wm._new_event_queue())


def has_scene(wm, scene_number: int) -> bool:
    try:
        return int(scene_number) in wm.scenes
    except Exception:
        return False


def mark_scene_completed(wm, scene_number: int, artifact: SceneArtifact) -> None:
    sn = int(scene_number)
    wm.completed[sn] = artifact
    wm.failed.pop(sn, None)
    wm.retry_counts.pop(sn, None)
    wm.failed_retryable.pop(sn, None)
    wm.record_event(sn, action="scene_completed", success=True)


def mark_scene_failed(
    wm,
    scene_number: int,
    reason: str,
    metadata: Optional[Dict[str, Any]] = None,
    *,
    retryable: bool = True,
) -> None:
    sn = int(scene_number)
    wm.failed[sn] = {"reason": reason, "metadata": metadata or {}}
    wm.failed_retryable[sn] = bool(retryable)
    wm.retry_counts[sn] = int(wm.retry_counts.get(sn, 0) or 0) + 1
    wm.record_event(sn, action="scene_failed", success=False, error_type=(metadata or {}).get("error_type"))


def set_scene_failed_state(
    wm,
    scene_number: int,
    reason: str,
    metadata: Optional[Dict[str, Any]] = None,
    *,
    retryable: bool = True,
    retries: Optional[int] = None,
) -> None:
    sn = int(scene_number)
    wm.failed[sn] = {"reason": reason, "metadata": metadata or {}}
    wm.failed_retryable[sn] = bool(retryable)
    if retries is not None:
        try:
            wm.retry_counts[sn] = int(retries)
        except Exception:
            wm.retry_counts[sn] = 0
    else:
        wm.retry_counts.setdefault(sn, 0)


def ready_scene_numbers(wm) -> List[int]:
    ready = []
    for sn in sorted(wm.scenes.keys()):
        if sn in wm.completed:
            continue
        dep = wm.depends_map.get(sn)
        if dep and dep not in wm.completed:
            continue
        ready.append(sn)
    return ready


def set_prepared_assets(wm, scene_number: int, assets: Dict[str, Any]) -> None:
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
        wm.prepared_assets.pop(sn, None)
        return
    merged = dict(wm.prepared_assets.get(sn, {}))
    merged.update(normalized)
    wm.prepared_assets[sn] = merged


def get_prepared_assets(wm, scene_number: int) -> Optional[Dict[str, Any]]:
    try:
        return wm.prepared_assets.get(int(scene_number))
    except Exception:
        return None


def scene_view(wm, scene_number: int, *, max_events: int = 5) -> Dict[str, Any]:
    sn = int(scene_number)
    snapshot = wm.scenes.get(sn)
    view = {"scene_number": sn}
    if snapshot:
        view.update(snapshot.as_fact())
    view["completed"] = sn in wm.completed
    view["failed"] = sn in wm.failed
    view["retry_count"] = int(wm.retry_counts.get(sn, 0))
    dq = list(wm.scene_events.get(sn) or [])
    if dq and max_events > 0:
        view["events"] = dq[-max_events:]
    prepared = wm.prepared_assets.get(sn)
    if prepared:
        view["prepared_assets_keys"] = list(prepared.keys())
    return view


def classify_scenes(
    wm,
    *,
    ready_limit: int = 5,
    dependency_limit: int = 3,
    failure_limit: int = 3,
    ready_event_limit: int = 3,
) -> Dict[str, Any]:
    total = len(wm.scenes)
    completed = len(wm.completed)
    failed = len(wm.failed)
    ready = len(ready_scene_numbers(wm))
    summary = {
        "total": total,
        "completed": completed,
        "failed": failed,
        "ready": ready,
        "pending": max(total - completed - failed, 0),
    }
    ready_views = [scene_view(wm, sn, max_events=ready_event_limit) for sn in ready_scene_numbers(wm)[:ready_limit]]
    dep_views: List[Dict[str, Any]] = []
    for sn, dep in wm.depends_map.items():
        if dep and dep not in wm.completed:
            dep_views.append(scene_view(wm, dep))
        if len(dep_views) >= dependency_limit:
            break
    failure_views = [scene_view(wm, sn, max_events=ready_event_limit) for sn in list(wm.failed.keys())[:failure_limit]]
    retry_hotspots = [
        {
            "scene_number": sn,
            "retries": wm.retry_counts.get(sn, 0),
            "retryable": wm.failed_retryable.get(sn, True),
            "failure_reason": (wm.failed.get(sn) or {}).get("reason"),
        }
        for sn in list(wm.failed.keys())[:failure_limit]
    ]
    global_stats = {
        "total_scenes": total,
        "completed_scenes": completed,
        "failed_scenes": failed,
        "ready_scene_numbers": ready_scene_numbers(wm),
        "retry_hotspots": retry_hotspots,
        "notes_count": len(wm.notes),
    }
    return {
        "summary": summary,
        "ready": ready_views,
        "dependencies": dep_views,
        "failures": failure_views,
        "global_stats": global_stats,
    }


def build_fact_observation(wm) -> Dict[str, Any]:
    scenes: List[Dict[str, Any]] = []
    for sn in sorted(wm.scenes.keys()):
        snapshot = wm.scenes.get(sn)
        payload = snapshot.as_fact() if snapshot else {"scene_number": sn}
        if sn in wm.completed:
            payload["completed"] = True
        if sn in wm.failed:
            payload["failed"] = True
            payload["failure_reason"] = (wm.failed.get(sn) or {}).get("reason")
        payload["retry_count"] = int(wm.retry_counts.get(sn, 0))
        scenes.append(payload)
    completed_numbers = sorted(wm.completed.keys())
    failed_numbers = sorted(wm.failed.keys())
    prepared_refs = sorted(wm.prepared_assets.keys())
    return {
        "scenes": scenes,
        "completed_scene_numbers": completed_numbers,
        "failed_scene_numbers": failed_numbers,
        "prepared_assets_refs": prepared_refs,
        "notes": list(wm.notes or []),
    }


def export_observation(
    wm,
    *,
    strategy: Optional[Dict[str, Any]] = None,
    target_model: Optional[str] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    view = build_fact_observation(wm)
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


def completed_outputs(wm) -> List[Dict[str, Any]]:
    """Return normalized outputs for completed scenes."""
    if wm is None:
        return []
    results: List[Dict[str, Any]] = []
    for sn, artifact in sorted((getattr(wm, "completed", {}) or {}).items(), key=lambda item: item[0]):
        if isinstance(artifact, SceneArtifact):
            results.append(artifact.as_output(sn))
        elif isinstance(artifact, dict):
            payload = dict(artifact)
            payload.setdefault("scene_number", sn)
            results.append(payload)
        else:
            results.append({"scene_number": sn, "artifact": artifact})
    return results


def failed_outputs(wm) -> List[Dict[str, Any]]:
    """Return normalized payloads for failed scenes."""
    if wm is None:
        return []
    failures: List[Dict[str, Any]] = []
    failed = getattr(wm, "failed", {}) or {}
    for sn, info in sorted(failed.items(), key=lambda item: item[0]):
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
    wm,
    *,
    kind: Optional[str] = None,
    scene_number: Optional[int] = None,
    limit: int = 1,
) -> List[Dict[str, Any]]:
    """Return the most recent iteration artifacts filtered by criteria."""
    entries = list(getattr(wm, "iteration_artifacts", []) or [])
    if not entries:
        return []
    samples: List[Dict[str, Any]] = []
    max_items = max(1, int(limit))
    for record in reversed(entries):
        if not isinstance(record, dict):
            continue
        if kind and record.get("kind") != kind:
            continue
        if scene_number is not None and record.get("scene_number") != scene_number:
            continue
        samples.append(record)
        if len(samples) >= max_items:
            break
    return samples

