import logging
import json

import pytest

from app.agents.orchestrator import OrchestratorAgent
from app.agents.utils.plan_context import build_plan_context
from app.agents.tools.ai_services.video_generation_tool_v2 import VideoGenerationTool
from app.agents.video_generator import VideoGeneratorAgent
from app.models import AgentType
from app.services.video_execution_contract import build_video_generation_execution_contract


def test_validate_video_generation_calls_allows_missing_llm_facing_execution_bindings():
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


def test_validate_video_generation_calls_rejects_conflicting_execution_audio_constraint():
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
                        "generate_audio": True,
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


def test_bind_execution_context_strips_runtime_fields_from_fc_arguments():
    agent = object.__new__(VideoGeneratorAgent)
    contract = build_video_generation_execution_contract(
        workflow_state_id="wf-1",
        generate_audio=True,
    )
    planned_calls = [
        {
            "function": {
                "name": "video_generation.generate_with_continuity",
                "arguments": {
                    "scene_number": 1,
                    "duration": 5,
                    "workflow_state_id": "wf-1",
                    "generate_audio": True,
                },
            }
        }
    ]

    agent.logger = logging.getLogger("test.video_generator")
    bound_calls = agent._bind_execution_context_to_planned_calls(
        planned_calls,
        execution_contract=contract,
    )

    arguments = bound_calls[0]["function"]["arguments"]
    assert "workflow_state_id" not in arguments
    assert "generate_audio" not in arguments
    assert bound_calls[0]["execution_context"]["workflow_state_id"] == "wf-1"
    assert bound_calls[0]["execution_context"]["execution_contract"]["constraints"]["generate_audio"] is True


def test_video_generation_tool_reads_runtime_binding_from_execution_context():
    tool = object.__new__(VideoGenerationTool)
    tool.metadata = VideoGenerationTool.get_metadata()
    contract = build_video_generation_execution_contract(
        workflow_state_id="wf-tool",
        generate_audio=True,
    )

    merged = tool._merge_execution_context_into_params(
        {"scene_number": 1, "duration": 5},
        {
            "workflow_state_id": "wf-tool",
            "execution_contract": contract,
        },
    )

    assert merged["workflow_state_id"] == "wf-tool"
    assert merged["generate_audio"] is True


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


def test_orchestrator_builds_video_execution_contract_from_runtime_hints():
    contract = OrchestratorAgent._build_agent_execution_contract(
        agent_type=AgentType.VIDEO_GENERATOR,
        workflow_state_id="wf-9",
        runtime_hints={"generate_audio": True},
    )

    assert contract["agent"] == AgentType.VIDEO_GENERATOR.value
    assert contract["storage"]["workflow_state_id"] == "wf-9"
    assert contract["constraints"]["generate_audio"] is True


def test_build_plan_context_can_exclude_execution_contract_from_planner_surface():
    ctx = build_plan_context(
        input_data={
            "task": {"mission": "generate scene videos"},
            "execution_contract": build_video_generation_execution_contract(
                workflow_state_id="wf-ctx",
                generate_audio=True,
            ),
        },
        iteration_context=None,
        include_execution_contract=False,
    )

    assert "execution_contract" not in ctx
