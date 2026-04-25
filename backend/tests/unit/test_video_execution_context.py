import pytest

from app.services.video_execution_context import merge_video_execution_context_into_params


def test_merge_video_execution_context_binds_workflow_and_audio_constraint():
    merged = merge_video_execution_context_into_params(
        {"scene_number": 1, "duration": 5},
        {
            "workflow_state_id": "wf-tool",
            "execution_contract": {
                "storage": {"workflow_state_id": "wf-tool"},
                "constraints": {"generate_audio": True},
            },
        },
    )

    assert merged["workflow_state_id"] == "wf-tool"
    assert merged["generate_audio"] is True


def test_merge_video_execution_context_rejects_conflicting_workflow_binding():
    with pytest.raises(ValueError, match="workflow_state_id conflicts"):
        merge_video_execution_context_into_params(
            {"scene_number": 1, "duration": 5, "workflow_state_id": "wf-other"},
            {
                "workflow_state_id": "wf-tool",
                "execution_contract": {
                    "storage": {"workflow_state_id": "wf-tool"},
                    "constraints": {"generate_audio": True},
                },
            },
        )


def test_merge_video_execution_context_uses_tool_error_factory():
    class StubToolError(Exception):
        pass

    with pytest.raises(StubToolError, match="generate_audio conflicts"):
        merge_video_execution_context_into_params(
            {"scene_number": 1, "duration": 5, "generate_audio": False},
            {
                "workflow_state_id": "wf-tool",
                "execution_contract": {
                    "storage": {"workflow_state_id": "wf-tool"},
                    "constraints": {"generate_audio": True},
                },
            },
            validation_error_factory=StubToolError,
        )
