import logging

import pytest

from app.agents.memory.short_term.working_memory import WorkingMemory
from app.agents.video_composer import VideoComposerAgent, VideoComposerFinalizeBoundaryError


@pytest.mark.asyncio
async def test_video_composer_finalize_rebuilds_result_from_explicit_finalize_receipt(monkeypatch):
    agent = object.__new__(VideoComposerAgent)
    agent.agent_name = "video_composer"
    agent.workflow_state_id = "wf-123"
    agent.logger = logging.getLogger("test.video_composer.finalize_handoff")
    agent._get_execution_id = lambda: "exec-123"
    agent._wm_cache = WorkingMemory(
        workflow_state_id="wf-123",
        scope="agent:video_composer",
        goal_text="finalize composer handoff",
    )

    agent._wm_cache.put(
        "composer_finalize_boundary",
        {
            "contract_version": "v1",
            "execution_id": "exec-123",
            "execution_contract": {
                "contract_version": "v1",
                "agent": "video_composer",
                "operation": "bgm",
                "workflow_state_id": "wf-123",
            },
            "output_path": "/tmp/final.mp4",
            "output_url": "/files/outputs/videos/final.mp4",
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
    assert result["mix_receipt"]["execution_id"] == "exec-123"
    assert result["orchestration_report"]["boundary_event"] == "compose_completed"
    assert result["orchestration_report"]["gate_triggers"] == ["workflow_global_bgm_mix_delivery"]
    assert result["loop_end_reason"] == "plan_contract_task_complete"


@pytest.mark.asyncio
async def test_video_composer_finalize_rejects_missing_finalize_receipt():
    agent = object.__new__(VideoComposerAgent)
    agent.agent_name = "video_composer"
    agent.workflow_state_id = "wf-missing-receipt"
    agent.logger = logging.getLogger("test.video_composer.finalize_missing_receipt")
    agent._get_execution_id = lambda: "exec-missing-receipt"
    agent._wm_cache = WorkingMemory(
        workflow_state_id="wf-missing-receipt",
        scope="agent:video_composer",
        goal_text="reject missing finalize receipt",
    )
    agent._wm_cache.add_iteration_artifact(
        kind="video",
        file_path="/tmp/stale-final.mp4",
        url="/files/outputs/videos/stale-final.mp4",
        stage="previous_act",
    )

    with pytest.raises(VideoComposerFinalizeBoundaryError) as exc_info:
        await agent._finalize_success_results(
            {
                "success": True,
                "subtask_state": "complete",
                "loop_end_reason": "plan_contract_task_complete",
            },
            {
                "workflow_state_id": "wf-missing-receipt",
                "total_iterations": 2,
            },
        )

    assert exc_info.value.reason_code == "video_composer_finalize_boundary_missing"


@pytest.mark.asyncio
async def test_video_composer_finalize_rejects_receipt_from_previous_attempt():
    agent = object.__new__(VideoComposerAgent)
    agent.agent_name = "video_composer"
    agent.workflow_state_id = "wf-attempt"
    agent.logger = logging.getLogger("test.video_composer.finalize_attempt_mismatch")
    agent._get_execution_id = lambda: "exec-current"
    agent._wm_cache = WorkingMemory(
        workflow_state_id="wf-attempt",
        scope="agent:video_composer",
        goal_text="reject stale attempt receipt",
    )
    agent._wm_cache.put(
        "composer_finalize_boundary",
        {
            "contract_version": "v1",
            "execution_id": "exec-previous",
            "execution_contract": {
                "contract_version": "v1",
                "agent": "video_composer",
                "operation": "compose",
                "workflow_state_id": "wf-attempt",
            },
            "output_path": "/tmp/stale.mp4",
            "output_url": "/files/outputs/videos/stale.mp4",
            "receipt_input": {"static_context": {}},
        },
    )

    with pytest.raises(VideoComposerFinalizeBoundaryError) as exc_info:
        await agent._finalize_success_results(
            {
                "success": True,
                "subtask_state": "complete",
                "loop_end_reason": "plan_contract_task_complete",
            },
            {"workflow_state_id": "wf-attempt", "total_iterations": 2},
        )

    assert exc_info.value.reason_code == "video_composer_finalize_boundary_execution_mismatch"
