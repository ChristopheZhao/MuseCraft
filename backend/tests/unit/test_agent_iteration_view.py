from app.agents.utils.iteration_view import build_agent_iteration_view
from app.agents.memory.short_term.service import WorkingMemoryService
from app.agents.memory.storage.in_memory import InMemoryShortTermStore
from app.agents.utils.memory_helpers import ensure_mas_working_memory, ensure_agent_working_memory
from app.agents.adapters.video.memory_adapter import VideoMemoryAdapter
from app.agents.adapters.video.models import SceneSnapshot, SceneArtifact


def _build_service() -> WorkingMemoryService:
    return WorkingMemoryService(store_factory=lambda: InMemoryShortTermStore())


def test_build_iteration_view_with_video_state():
    wf_id = "iter-view-wf"
    agent_name = "video_generator"
    service = _build_service()
    mas = ensure_mas_working_memory(wf_id, service=service)
    agent_wm = ensure_agent_working_memory(wf_id, agent_name, service=service, shared_view=mas)

    adapter = VideoMemoryAdapter(agent_wm)
    adapter.upsert_scene(SceneSnapshot(scene_number=1, duration=3.0))
    adapter.mark_completed(1, SceneArtifact(video_url="https://example.com/v1.mp4"))
    adapter.upsert_scene(SceneSnapshot(scene_number=2, duration=2.0))
    adapter.mark_failed(2, "generation_failed", metadata={"error_type": "gen_fail"}, retryable=True)

    view = build_agent_iteration_view(wf_id, agent_name, service=service)
    assert view["agent"] == agent_name
    assert view["scene_stats"]["summary"]["completed"] == 1
    assert view["scene_stats"]["summary"]["failed"] == 1
    assert view["scene_stats"]["summary"]["total"] == 2


def test_build_iteration_view_creates_empty_when_absent():
    wf_id = "iter-view-empty"
    agent_name = "script_writer"
    service = _build_service()

    view = build_agent_iteration_view(wf_id, agent_name, service=service, create_if_absent=True)
    assert view["agent"] == agent_name
    assert view["iteration_count"] == 0
