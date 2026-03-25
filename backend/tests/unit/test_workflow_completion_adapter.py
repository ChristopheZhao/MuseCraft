import asyncio
from types import SimpleNamespace

from app.services.workflow_completion_adapter import WorkflowCompletionAdapter


def test_build_persistence_payload_projects_scene_and_final_resources(monkeypatch):
    adapter = WorkflowCompletionAdapter(memory_services=SimpleNamespace(short_term=object()))

    wm = {
        "scene_overview": {
            "scenes": [
                {
                    "scene_number": 1,
                    "title": "Intro",
                    "visual_description": "Opening frame",
                    "duration": 3.5,
                }
            ]
        },
        "scene_outputs.video": {
            "1": {"scene_number": 1, "video_path": "/tmp/scene1.mp4", "video_url": "/files/scene1.mp4"}
        },
        "scene_outputs.image": {
            "1": {"scene_number": 1, "image_path": "/tmp/scene1.jpg", "image_url": "/files/scene1.jpg"}
        },
        "project.final_video": {"path": "/tmp/final.mp4", "url": "/files/final.mp4"},
        "project.background_music": {"audio_path": "/tmp/bgm.mp3", "audio_url": "/files/bgm.mp3"},
    }

    monkeypatch.setattr(
        "app.services.workflow_completion_adapter.get_mas_working_memory",
        lambda workflow_id, service=None: wm,
    )

    payload = adapter.build_persistence_payload("wf-1")

    assert payload["scenes"] == [
        {
            "scene_number": 1,
            "title": "Intro",
            "description": "Opening frame",
            "duration": 3.5,
        }
    ]
    assert any(item.get("kind") == "final_video" for item in payload["resources"])
    assert any(item.get("filename") == "scene_1_video.mp4" for item in payload["resources"])
    assert any(item.get("filename") == "scene_1_image.jpg" for item in payload["resources"])


def test_publish_completed_emits_bounded_terminal_summary(monkeypatch):
    adapter = WorkflowCompletionAdapter(memory_services=SimpleNamespace(short_term=object()))

    adapter.build_persistence_payload = lambda workflow_id: {
        "scenes": [{"scene_number": 1}],
        "resources": [{"kind": "final_video", "url": "/files/final.mp4"}],
    }
    adapter.resolve_final_video_url = lambda workflow_id: "/files/final.mp4"
    monkeypatch.setattr(
        "app.services.workflow_completion_adapter.build_mas_state_view",
        lambda workflow_id, service=None: {"projection_role": "facts_summary", "completed_scenes": 1},
    )

    captured = {}

    async def _capture_publish_event(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr("app.services.workflow_completion_adapter.publish_event", _capture_publish_event)

    task = SimpleNamespace(task_id="task-1", id=11)
    result = asyncio.run(
        adapter.publish_completed(
            task=task,
            workflow_id="wf-1",
            results={"ok": True},
            quality_score=0.92,
        )
    )

    payload = captured["payload"]
    assert payload["state"] == "workflow_completed"
    assert payload["projection_role"] == "bounded_terminal_summary"
    assert payload["runtime_authoritative"] is False
    assert payload["refresh_required"] is True
    assert payload["facts_summary"]["completed_scenes"] == 1
    assert payload["results"] == {"ok": True}
    assert payload["quality_score"] == 0.92
    assert result["final_video_url"] == "/files/final.mp4"


def test_publish_failed_emits_bounded_terminal_summary(monkeypatch):
    adapter = WorkflowCompletionAdapter(memory_services=SimpleNamespace(short_term=object()))

    captured = {}

    async def _capture_publish_event(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr("app.services.workflow_completion_adapter.publish_event", _capture_publish_event)

    task = SimpleNamespace(task_id="task-2", id=12)
    asyncio.run(
        adapter.publish_failed(
            task=task,
            workflow_id="wf-2",
            error_message="boom",
        )
    )

    payload = captured["payload"]
    assert payload["state"] == "workflow_failed"
    assert payload["projection_role"] == "bounded_terminal_summary"
    assert payload["runtime_authoritative"] is False
    assert payload["refresh_required"] is True
    assert payload["error"] == "boom"
