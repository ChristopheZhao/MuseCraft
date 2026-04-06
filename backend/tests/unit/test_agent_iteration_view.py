from app.agents.utils.iteration_view import build_agent_iteration_view
from app.agents.memory.short_term.service import WorkingMemoryService
from app.agents.memory.storage.in_memory import InMemoryShortTermStore
from app.agents.utils.memory_helpers import ensure_mas_working_memory, ensure_agent_working_memory


def _build_service() -> WorkingMemoryService:
    return WorkingMemoryService(store_factory=lambda: InMemoryShortTermStore())


def test_build_iteration_view_with_video_state():
    wf_id = "iter-view-wf"
    agent_name = "video_generator"
    service = _build_service()
    mas = ensure_mas_working_memory(wf_id, service=service)
    agent_wm = ensure_agent_working_memory(wf_id, agent_name, service=service, shared_view=mas)

    # completed/failed：均由 agent-scope obs_records 派生（本次执行轨迹）
    agent_wm.put(
        "obs_records",
        [
            {
                "action_result": {
                    "executed_calls": [
                        {"tool": "video_generation.generate_with_continuity", "success": True, "scene_number": 1},
                        {"tool": "video_generation.generate_with_continuity", "success": False, "scene_number": 2},
                    ],
                }
            }
        ],
    )

    view = build_agent_iteration_view(wf_id, agent_name, service=service)
    assert view["agent"] == agent_name
    assert view["target_kind"] == "video"
    assert view["completed_scene_numbers"] == [1]
    assert view["failed_scene_numbers"] == [2]


def test_build_iteration_view_creates_empty_when_absent():
    wf_id = "iter-view-empty"
    agent_name = "script_writer"
    service = _build_service()

    view = build_agent_iteration_view(wf_id, agent_name, service=service, create_if_absent=True)
    assert view["agent"] == agent_name
    assert view["completed_scene_numbers"] == []
    assert view["failed_scene_numbers"] == []
