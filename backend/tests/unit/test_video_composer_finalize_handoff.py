import logging

import pytest

from app.agents.memory.short_term.working_memory import WorkingMemory
from app.agents.video_composer import VideoComposerAgent


@pytest.mark.asyncio
async def test_video_composer_finalize_rebuilds_receipt_from_iteration_artifacts(monkeypatch):
    agent = object.__new__(VideoComposerAgent)
    agent.agent_name = "video_composer"
    agent.workflow_state_id = "wf-123"
    agent.logger = logging.getLogger("test.video_composer.finalize_handoff")
    agent._wm_cache = WorkingMemory(
        workflow_state_id="wf-123",
        scope="agent:video_composer",
        goal_text="finalize composer handoff",
    )

    agent._wm_cache.add_iteration_artifact(
        kind="video",
        file_path="/tmp/final.mp4",
        url="",
        stage="act",
    )
    agent._wm_cache.put(
        "composer_finalize_boundary",
        {
            "compose_mode": "bgm",
            "receipt_input": {
                "static_context": {
                    "final_video": {
                        "path": "/tmp/pre_mix.mp4",
                        "url": "/files/outputs/videos/pre_mix.mp4",
                    },
                    "background_music": {
                        "path": "/tmp/bgm.mp3",
                        "url": "/files/audio/bgm.mp3",
                    },
                },
            },
        },
    )

    monkeypatch.setattr(
        "app.agents.video_composer.build_local_public_url",
        lambda path: "/files/outputs/videos/final.mp4",
    )

    result = await agent._finalize_success_results(
        {
            "success": True,
            "subtask_state": "complete",
            "loop_end_reason": "plan_contract_task_complete",
        },
        {
            "workflow_state_id": "wf-123",
            "total_iterations": 2,
        },
    )

    assert result["final_video_path"] == "/tmp/final.mp4"
    assert result["final_video_url"] == "/files/outputs/videos/final.mp4"
    assert result["mix_receipt"]["mix_type"] == "bgm"
    assert result["mix_receipt"]["output_path"] == "/tmp/final.mp4"
    assert result["mix_receipt"]["inputs"]["background_music"]["path"] == "/tmp/bgm.mp3"
    assert result["mix_receipt"]["execution_id"] == ""
    assert result["orchestration_report"]["boundary_event"] == "compose_completed"
    assert result["orchestration_report"]["gate_triggers"] == ["workflow_global_bgm_mix_delivery"]
    assert result["loop_end_reason"] == "plan_contract_task_complete"
