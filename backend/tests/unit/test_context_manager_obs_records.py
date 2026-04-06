from app.agents.utils.context_manager import build_agent_context
from app.agents.memory.short_term.service import WorkingMemoryService
from app.agents.memory.storage.in_memory import InMemoryShortTermStore
from app.agents.utils.memory_helpers import ensure_mas_working_memory, ensure_agent_working_memory


def _build_service() -> WorkingMemoryService:
    return WorkingMemoryService(store_factory=lambda: InMemoryShortTermStore())


def test_build_agent_context_preserves_tool_results_in_obs_records():
    wf_id = "ctx-obs-preserve"
    agent_name = "audio_generator"
    service = _build_service()
    mas = ensure_mas_working_memory(wf_id, service=service)
    agent_wm = ensure_agent_working_memory(wf_id, agent_name, service=service, shared_view=mas)

    agent_wm.put(
        "obs_records",
        [
            {
                "iteration": 0,
                "action_result": {
                    "action_performed": "batch_audio_generation",
                    "executed_calls": [
                        {
                            "tool": "suno_client.generate_background_music",
                            "success": True,
                            "result": {"audio_url": "https://example.com/bgm.mp3"},
                        }
                    ],
                    "generation_results": [{"success": True, "audio_url": "https://example.com/bgm.mp3"}],
                },
            }
        ],
    )

    ctx = build_agent_context(
        workflow_id=wf_id,
        agent_name=agent_name,
        service=service,
        max_turn=None,
    )
    assert "obs_records" in ctx
    assert ctx["obs_records"][0]["action_result"]["executed_calls"][0]["result"]["audio_url"] == "https://example.com/bgm.mp3"
    assert ctx["obs_records"][0]["action_result"]["generation_results"][0]["audio_url"] == "https://example.com/bgm.mp3"

