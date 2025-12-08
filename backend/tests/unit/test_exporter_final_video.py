import pytest

from app.agents.memory.short_term import SceneSnapshot
from app.agents.memory.short_term.service import WorkingMemoryService
from app.agents.memory.storage.in_memory import InMemoryShortTermStore
from app.agents.memory.long_term.snapshots import export_shared_wm_snapshot


def _build_wm_service() -> WorkingMemoryService:
    return WorkingMemoryService(store_factory=lambda: InMemoryShortTermStore())


def test_exporter_includes_final_video():
    task_id = "wm-export-final-video"
    wm_service = _build_wm_service()
    mas = wm_service.create_or_get(task_id, f"mas:{task_id}")
    # Prepare scenes and final video facts
    mas.put("scene_overview", {"scenes": [SceneSnapshot(scene_number=1, duration=3.0).as_fact()]})
    mas.put("final_video", {
        "path": "/tmp/final_video.mp4",
        "url": "https://example.com/final.mp4",
        "remote_path": "oss://bucket/final.mp4",
        "storage": {"provider": "oss"},
        "mix": "concat_only",
    })

    snap = export_shared_wm_snapshot(task_id, short_term_service=wm_service)
    fv = snap.get("final_video") or {}
    assert fv.get("path") == "/tmp/final_video.mp4"
    assert fv.get("url") == "https://example.com/final.mp4"
    assert fv.get("mix") == "concat_only"
