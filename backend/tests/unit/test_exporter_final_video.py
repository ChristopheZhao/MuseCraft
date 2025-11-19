import pytest

from app.agents.services.mas_shared_memory import get_shared_wm
from app.services.memory_provider import build_memory_services, set_memory_services
from app.agents.memory.short_term.working_memory import SceneSnapshot
from app.agents.memory.long_term.snapshots import export_shared_wm_snapshot

memory_services = build_memory_services()
set_memory_services(memory_services)


def test_exporter_includes_final_video():
    task_id = "wm-export-final-video"
    wm = get_shared_wm()
    store = memory_services.fact_store

    # Prepare scenes and final video facts
    wm.upsert_scene(task_id, SceneSnapshot(scene_number=1, duration=3.0))
    store.put(task_id, "project.final_video", {
        "path": "/tmp/final_video.mp4",
        "url": "https://example.com/final.mp4",
        "remote_path": "oss://bucket/final.mp4",
        "storage": {"provider": "oss"},
        "mix": "concat_only",
    })

    snap = export_shared_wm_snapshot(task_id, memory_services=memory_services)
    fv = snap.get("final_video") or {}
    assert fv.get("path") == "/tmp/final_video.mp4"
    assert fv.get("url") == "https://example.com/final.mp4"
    assert fv.get("mix") == "concat_only"
