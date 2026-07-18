import math

import pytest

from app.domain.agent_execution import (
    AgentBoundaryEvent,
    AgentExecutionContractError,
    AgentExecutionContractReason,
    AgentExecutionRequest,
    AgentExecutionResult,
    AgentTaskReference,
    JsonObjectPayload,
)


def test_agent_execution_request_is_a_stable_json_snapshot():
    raw_input = {"scenes": [{"scene_number": 1}], "enabled": True}
    request = AgentExecutionRequest(
        task=AgentTaskReference(
            task_id="task-1",
            task_type="video_generation",
            user_id="user-1",
        ),
        agent_type="video_generator",
        workflow_state_id="workflow-1",
        execution_order=2,
        input_data=JsonObjectPayload.from_mapping(raw_input, field_path="input_data"),
    )

    raw_input["scenes"][0]["scene_number"] = 99
    first_projection = request.to_payload()
    first_projection["input_data"]["enabled"] = False

    assert request.to_payload() == {
        "task": {
            "task_id": "task-1",
            "task_type": "video_generation",
            "user_id": "user-1",
            "session_id": None,
        },
        "agent_type": "video_generator",
        "workflow_state_id": "workflow-1",
        "execution_order": 2,
        "input_data": {"enabled": True, "scenes": [{"scene_number": 1}]},
    }


@pytest.mark.parametrize("runtime_value", [object(), ("tuple-is-not-json-array",)])
def test_json_contract_rejects_runtime_objects_instead_of_stringifying(runtime_value):
    with pytest.raises(AgentExecutionContractError) as exc_info:
        JsonObjectPayload.from_mapping(
            {"runtime_dependency": runtime_value},
            field_path="input_data",
        )

    assert exc_info.value.reason_code == AgentExecutionContractReason.INVALID_JSON_VALUE
    assert exc_info.value.field_path == "input_data.runtime_dependency"


def test_json_contract_rejects_non_finite_numbers():
    with pytest.raises(AgentExecutionContractError) as exc_info:
        JsonObjectPayload.from_mapping(
            {"score": math.nan},
            field_path="output_data",
        )

    assert exc_info.value.reason_code == AgentExecutionContractReason.NON_FINITE_JSON_NUMBER


@pytest.mark.parametrize("encoded", ["not-json", "[]", '{"score": NaN}'])
def test_json_contract_direct_constructor_cannot_bypass_validation(encoded):
    with pytest.raises(AgentExecutionContractError):
        JsonObjectPayload(encoded)


def test_agent_result_requires_an_explicit_orchestration_report_when_consumed():
    result = AgentExecutionResult(
        output_data=JsonObjectPayload.from_mapping(
            {"success": True},
            field_path="output_data",
        )
    )

    with pytest.raises(AgentExecutionContractError) as exc_info:
        result.require_orchestration_report()

    assert exc_info.value.reason_code == AgentExecutionContractReason.ORCHESTRATION_REPORT_MISSING


def test_agent_result_separates_report_and_typed_boundary_events():
    report = JsonObjectPayload.from_mapping(
        {
            "status": "completed",
            "boundary_event": "scene_video_completed",
            "gate_triggers": [],
            "artifacts": [],
            "reflection": {
                "completion_state": "completed",
                "reported_gaps": [],
                "reported_hints": [],
            },
        },
        field_path="orchestration_report",
    )
    result = AgentExecutionResult(
        output_data=JsonObjectPayload.from_mapping(
            {"success": True},
            field_path="output_data",
        ),
        orchestration_report=report,
        boundary_events=(
            AgentBoundaryEvent(
                event_kind="scene_video_completed",
                reason_code="scene_output_accepted",
                payload=JsonObjectPayload.from_mapping(
                    {"scene_number": 1},
                    field_path="boundary_event.payload",
                ),
            ),
        ),
    )

    assert result.require_orchestration_report() == report
    assert result.to_payload()["boundary_events"] == [
        {
            "event_kind": "scene_video_completed",
            "reason_code": "scene_output_accepted",
            "payload": {"scene_number": 1},
        }
    ]


def test_agent_result_rejects_report_hidden_in_output_data():
    with pytest.raises(AgentExecutionContractError) as exc_info:
        AgentExecutionResult(
            output_data=JsonObjectPayload.from_mapping(
                {"orchestration_report": {}},
                field_path="output_data",
            )
        )

    assert exc_info.value.reason_code == AgentExecutionContractReason.RESERVED_OUTPUT_FIELD
