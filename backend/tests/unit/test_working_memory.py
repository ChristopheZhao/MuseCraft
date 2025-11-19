import pytest

from app.agents.memory.short_term.working_memory import WorkingMemory, SceneSnapshot, SceneArtifact
from app.agents.video_generator import VideoGeneratorAgent


def test_working_memory_fact_observation():
    wm = WorkingMemory(workflow_state_id="wf-1", goal_text="goal", journal_max_events=3)
    wm.upsert_scene(SceneSnapshot(scene_number=1, depends_on_scene=None, duration=5.0))
    wm.upsert_scene(SceneSnapshot(scene_number=2, depends_on_scene=1, duration=5.0))

    wm.mark_completed(1, SceneArtifact(video_url="https://example.com/v1.mp4", video_path="/tmp/v1.mp4", prompt_text="p1"))
    wm.mark_failed(2, "error", {"error_type": "temporary"}, retryable=True)

    fact_view = wm.build_fact_observation()

    assert fact_view["completed_scene_numbers"] == [1]
    assert fact_view["failed_scene_numbers"] == [2]
    scenes = {entry["scene_number"]: entry for entry in fact_view["scenes"]}
    assert scenes[1].get("completed") is True
    assert scenes[2].get("failed") is True
    assert "summary" not in fact_view


@pytest.mark.asyncio
async def test_video_generator_observation_fact_only():
    agent = object.__new__(VideoGeneratorAgent)
    agent.agent_name = "video_generator"  # 补齐 __init__ 里本应设置的属性
    agent.iteration_context = {}

    wm = WorkingMemory(workflow_state_id="wf-obs", goal_text="goal", journal_max_events=3)
    wm.upsert_scene(SceneSnapshot(scene_number=1, depends_on_scene=None, duration=5.0))
    wm.upsert_scene(SceneSnapshot(scene_number=2, depends_on_scene=1, duration=5.0))
    wm.upsert_scene(SceneSnapshot(scene_number=3, depends_on_scene=None, duration=5.0))

    wm.mark_completed(1, SceneArtifact(video_url="https://example.com/v1.mp4", video_path="/tmp/v1.mp4", prompt_text="p1"))
    wm.mark_failed(2, "error", {"error_type": "temporary"}, retryable=True)
    wm.mark_failed(2, "error", {"error_type": "temporary"}, retryable=True)

    view, ready_ids, completed_ids = await agent._build_observation_view(wm)

    assert "summary" not in view
    scenes = {entry["scene_number"]: entry for entry in view["scenes"]}
    assert scenes[1].get("completed") is True
    assert scenes[2].get("failed") is True
    assert ready_ids == [2, 3]
    assert completed_ids == [1]


def test_set_slot_value_updates_prepared_assets_and_slots():
    wm = WorkingMemory(workflow_state_id="wf-slots", goal_text="goal", journal_max_events=3)
    payload = {"style": {"mood": "calm"}, "environment": {"location": "forest"}}
    wm.set_slot_value("prepared_assets", 7, payload)

    slot_bucket = wm.facts_slots.get("prepared_assets") or {}
    assert 7 in slot_bucket
    assert slot_bucket[7]["style"]["mood"] == "calm"

    prepared = wm.get_prepared_assets(7)
    assert prepared is not None
    assert prepared.get("style", {}).get("mood") == "calm"
