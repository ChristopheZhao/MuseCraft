from app.services.memory_provider import build_memory_services
from app.agents.memory.short_term import SceneSnapshot
from app.agents.memory.long_term.snapshots import export_shared_wm_snapshot


def test_smoke_no_registry():
    """纯注入模式下的最小冒烟：不依赖任何默认单例/registry。"""
    services = build_memory_services()
    wm_service = services.short_term
    task_id = "smoke-wm"
    mas = wm_service.create_or_get(task_id, f"mas:{task_id}")
    mas.put("scene_overview", {"scenes": [SceneSnapshot(scene_number=1, duration=1.0).as_fact()]})
    mas.put("final_video", {"path": "/tmp/smoke.mp4", "url": "https://example.com/smoke.mp4"})

    snap = export_shared_wm_snapshot(task_id, short_term_service=wm_service)
    assert snap["scenes"][0]["scene_number"] == 1
    assert snap["final_video"]["path"] == "/tmp/smoke.mp4"
