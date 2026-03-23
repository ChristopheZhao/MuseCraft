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
