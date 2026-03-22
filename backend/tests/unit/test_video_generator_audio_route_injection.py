import json
from types import SimpleNamespace

import pytest

from app.agents.video_generator import VideoGeneratorAgent
from app.models import AgentType
from app.services.execution_boundary_assembler import ExecutionBoundaryAssembler
from app.services.video_execution_contract import build_video_generation_execution_contract


def test_validate_video_generation_calls_accepts_matching_execution_contract():
    agent = object.__new__(VideoGeneratorAgent)
    contract = build_video_generation_execution_contract(
        workflow_state_id="wf-1",
        generate_audio=True,
    )
    planned_calls = [
        {
            "function": {
                "name": "video_generation.generate_with_continuity",
                "arguments": json.dumps(
                    {
                        "scene_number": 1,
                        "duration": 5,
                        "workflow_state_id": "wf-1",
                        "generate_audio": True,
                    },
                    ensure_ascii=False,
                ),
            }
        }
    ]

    agent._validate_video_generation_calls_against_contract(
        planned_calls,
        execution_contract=contract,
    )


def test_validate_video_generation_calls_rejects_missing_execution_constraint():
    agent = object.__new__(VideoGeneratorAgent)
    contract = build_video_generation_execution_contract(
        workflow_state_id="wf-1",
        generate_audio=False,
    )
    planned_calls = [
        {
            "function": {
                "name": "video_generation.generate_with_continuity",
                "arguments": json.dumps(
                    {
                        "scene_number": 1,
                        "duration": 5,
                        "workflow_state_id": "wf-1",
                    },
                    ensure_ascii=False,
                ),
            }
        }
    ]

    with pytest.raises(Exception, match="generate_audio"):
        agent._validate_video_generation_calls_against_contract(
            planned_calls,
            execution_contract=contract,
        )


def test_validate_video_generation_calls_rejects_mismatched_workflow_state_id():
    agent = object.__new__(VideoGeneratorAgent)
    contract = build_video_generation_execution_contract(
        workflow_state_id="wf-required",
        generate_audio=True,
    )
    planned_calls = [
        {
            "function": {
                "name": "video_generation.generate_with_continuity",
                "arguments": json.dumps(
                    {
                        "scene_number": 1,
                        "duration": 5,
                        "workflow_state_id": "wf-other",
                        "generate_audio": True,
                    },
                    ensure_ascii=False,
                ),
            }
        }
    ]

    with pytest.raises(Exception, match="workflow_state_id"):
        agent._validate_video_generation_calls_against_contract(
            planned_calls,
            execution_contract=contract,
        )


def test_resolve_execution_contract_uses_explicit_contract_without_plan_or_route_reads(monkeypatch):
    agent = object.__new__(VideoGeneratorAgent)
    contract = build_video_generation_execution_contract(
        workflow_state_id="wf-1",
        generate_audio=False,
    )

    def _fail(*args, **kwargs):
        raise AssertionError("workflow.plan/audio_route should not be read")

    monkeypatch.setattr("app.agents.video_generator.get_mas_working_memory", _fail)

    resolved = agent._resolve_execution_contract(
        {"execution_contract": contract},
        workflow_id="wf-ignored",
    )
    assert resolved["storage"]["workflow_state_id"] == "wf-1"
    assert resolved["constraints"]["generate_audio"] is False


def test_execution_boundary_assembler_builds_video_execution_contract_from_runtime_overrides():
    assembler = ExecutionBoundaryAssembler(SimpleNamespace(short_term=object()))

    contract = assembler.build_execution_contract(
        agent_type=AgentType.VIDEO_GENERATOR,
        workflow_state_id="wf-9",
        runtime_overrides={"generate_audio": True},
    )

    assert contract["agent"] == AgentType.VIDEO_GENERATOR.value
    assert contract["storage"]["workflow_state_id"] == "wf-9"
    assert contract["constraints"]["generate_audio"] is True
