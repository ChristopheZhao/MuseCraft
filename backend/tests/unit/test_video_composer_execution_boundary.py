import pytest

from app.agents.base import AgentError
from app.agents.utils.plan_context import build_plan_context
from app.agents.video_composer import VideoComposerAgent
from app.models import AgentType
from app.services.execution_boundary_assembler import ExecutionBoundaryAssembler
from app.services.video_composer_execution_contract import (
    build_video_composer_execution_contract,
    get_video_composer_compose_mode,
)


def test_resolve_execution_contract_prefers_explicit_boundary_over_legacy_flags():
    agent = object.__new__(VideoComposerAgent)
    contract = build_video_composer_execution_contract(
        workflow_state_id="wf-compose",
        compose_mode="compose",
    )

    resolved = agent._resolve_execution_contract(
        {
            "workflow_state_id": "wf-compose",
            "execution_contract": contract,
            "add_bgm": True,
            "static_context": {"requests": {"bgm_requested": True}},
        },
        "wf-compose",
    )

    assert get_video_composer_compose_mode(resolved) == "compose"


def test_resolve_execution_contract_defaults_to_compose_when_boundary_missing():
    agent = object.__new__(VideoComposerAgent)

    resolved = agent._resolve_execution_contract(
        {
            "workflow_state_id": "wf-voice",
        },
        "wf-voice",
    )

    assert get_video_composer_compose_mode(resolved) == "compose"
    assert resolved["storage"]["workflow_state_id"] == "wf-voice"


def test_resolve_execution_contract_rejects_legacy_inputs_without_boundary():
    agent = object.__new__(VideoComposerAgent)

    with pytest.raises(AgentError):
        agent._resolve_execution_contract(
            {
                "workflow_state_id": "wf-conflict",
                "add_bgm": True,
                "static_context": {"requests": {"bgm_requested": True}},
            },
            "wf-conflict",
        )


def test_build_mix_receipt_uses_contract_mode_not_legacy_flags():
    agent = object.__new__(VideoComposerAgent)
    receipt = agent._build_mix_receipt(
        input_data={
            "workflow_state_id": "wf-compose",
            "add_bgm": True,
            "static_context": {
                "requests": {"bgm_requested": True},
                "final_video": {"path": "/tmp/source.mp4", "url": "file:///tmp/source.mp4"},
                "background_music": {"path": "/tmp/bgm.wav", "url": "file:///tmp/bgm.wav"},
            },
        },
        mix_type="compose",
        output_path="/tmp/output.mp4",
        output_url="file:///tmp/output.mp4",
    )

    assert receipt["mix_type"] == "compose"
    assert "background_music" not in receipt["inputs"]


def test_execution_boundary_assembler_builds_video_composer_execution_contract_from_runtime_overrides():
    assembler = ExecutionBoundaryAssembler(memory_services=type("MS", (), {"short_term": object()})())

    contract = assembler.build_execution_contract(
        agent_type=AgentType.VIDEO_COMPOSER,
        workflow_state_id="wf-bgm",
        runtime_overrides={"compose_mode": "bgm"},
    )

    assert contract["agent"] == AgentType.VIDEO_COMPOSER.value
    assert contract["storage"]["workflow_state_id"] == "wf-bgm"
    assert contract["constraints"]["compose_mode"] == "bgm"


def test_execution_boundary_assembler_rejects_legacy_video_composer_runtime_overrides():
    assembler = ExecutionBoundaryAssembler(memory_services=type("MS", (), {"short_term": object()})())

    with pytest.raises(AgentError):
        assembler.build_execution_contract(
            agent_type=AgentType.VIDEO_COMPOSER,
            workflow_state_id="wf-legacy",
            runtime_overrides={"add_bgm": True},
        )


def test_execution_boundary_assembler_applies_video_composer_input_and_strips_legacy_flags():
    assembler = ExecutionBoundaryAssembler(memory_services=type("MS", (), {"short_term": object()})())
    contract = build_video_composer_execution_contract(
        workflow_state_id="wf-voice",
        compose_mode="voiceover",
    )

    normalized = assembler.apply_execution_boundary(
        agent_type=AgentType.VIDEO_COMPOSER,
        agent_input={
            "workflow_state_id": "wf-voice",
            "add_bgm": True,
            "add_voiceover": False,
            "compose_requested": False,
            "static_context": {
                "requests": {
                    "bgm_requested": True,
                    "voiceover_requested": False,
                    "compose_requested": False,
                }
            },
        },
        execution_contract=contract,
    )

    assert "add_bgm" not in normalized
    assert "add_voiceover" not in normalized
    assert "compose_requested" not in normalized
    assert "requests" not in normalized["static_context"]


def test_build_plan_context_includes_execution_contract():
    ctx = build_plan_context(
        input_data={
            "task": {"mission": "compose the final video", "deliverable": "final composed video"},
            "static_context": {"requests": {"compose_requested": True}},
            "execution_contract": build_video_composer_execution_contract(
                workflow_state_id="wf-compose",
                compose_mode="compose",
            ),
        },
        iteration_context=None,
    )

    assert "execution_contract" in ctx
    assert ctx["execution_contract"]["constraints"]["compose_mode"] == "compose"


def test_build_plan_context_exposes_task_assignment_contract():
    ctx = build_plan_context(
        input_data={
            "task": {
                "agent": "video_composer",
                "run": True,
                "mission": "compose the final trailer cut",
                "deliverable": "final composed video",
                "constraints": ["preserve scene order", "do not add narration"],
                "runtime_hints": {"compose_mode": "bgm"},
                "fallback_used": False,
            }
        },
        iteration_context=None,
    )

    assert ctx["task_assignment"] == {
        "agent": "video_composer",
        "run": True,
        "mission": "compose the final trailer cut",
        "deliverable": "final composed video",
        "constraints": ["preserve scene order", "do not add narration"],
        "runtime_hints": {"compose_mode": "bgm"},
    }
