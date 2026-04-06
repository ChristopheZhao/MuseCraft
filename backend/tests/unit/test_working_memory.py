import pytest

from app.agents.memory.short_term import WorkingMemory, SceneSnapshot, SceneArtifact
from app.agents.utils.memory_helpers import agent_scope
from app.agents.adapters.video.memory_adapter import VideoMemoryAdapter


def test_working_memory_fact_observation():
    scope = agent_scope("wf-1", "test")
    wm = WorkingMemory(workflow_state_id="wf-1", scope=scope, goal_text="goal", journal_max_events=3)
    video_adapter = VideoMemoryAdapter(wm)
    video_adapter.upsert_scene(SceneSnapshot(scene_number=1, depends_on_scene=None, duration=5.0))
    video_adapter.upsert_scene(SceneSnapshot(scene_number=2, depends_on_scene=1, duration=5.0))

    video_adapter.mark_completed(1, SceneArtifact(video_url="https://example.com/v1.mp4", video_path="/tmp/v1.mp4", prompt_text="p1"))
    video_adapter.mark_failed(2, "error", {"error_type": "temporary"}, retryable=True)

    fact_view = video_adapter.build_fact_observation()

    assert fact_view["completed_scene_numbers"] == [1]
    assert fact_view["failed_scene_numbers"] == [2]
    scenes = {entry["scene_number"]: entry for entry in fact_view["scenes"]}
    assert scenes[1].get("completed") is True
    assert scenes[2].get("failed") is True
    assert "summary" not in fact_view


@pytest.mark.asyncio
async def test_video_memory_adapter_scene_classification():
    scope = agent_scope("wf-obs", "test")
    wm = WorkingMemory(workflow_state_id="wf-obs", scope=scope, goal_text="goal", journal_max_events=3)
    video_adapter = VideoMemoryAdapter(wm)
    video_adapter.upsert_scene(SceneSnapshot(scene_number=1, depends_on_scene=None, duration=5.0))
    video_adapter.upsert_scene(SceneSnapshot(scene_number=2, depends_on_scene=1, duration=5.0))
    video_adapter.upsert_scene(SceneSnapshot(scene_number=3, depends_on_scene=None, duration=5.0))

    video_adapter.mark_completed(1, SceneArtifact(video_url="https://example.com/v1.mp4", video_path="/tmp/v1.mp4", prompt_text="p1"))
    video_adapter.mark_failed(2, "error", {"error_type": "temporary"}, retryable=True)
    video_adapter.mark_failed(2, "error", {"error_type": "temporary"}, retryable=True)

    classified = video_adapter.classify_scenes()
    ready = classified.get("ready") or []
    failures = classified.get("failures") or []
    summary = classified.get("summary") or {}

    assert summary.get("completed") == 1
    assert any(entry.get("scene_number") == 2 for entry in failures)
    assert any(entry.get("scene_number") == 3 for entry in ready)
