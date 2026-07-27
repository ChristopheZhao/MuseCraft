import pytest

from app.domain import AgentType, JsonObjectPayload
from app.services.orchestration_state_adapter import (
    ContinuationCheckpointContractError,
    ContinuationCheckpointContractReason,
    OrchestrationStateAdapter,
)


def test_checkpoint_task_specs_use_explicit_order_after_canonical_json_round_trip():
    checkpoint = OrchestrationStateAdapter.build_continuation_checkpoint(
        task_specs={
            AgentType.CONCEPT_PLANNER: {"run": True, "order": 0},
            AgentType.SCRIPT_WRITER: {"run": True, "order": 1},
            AgentType.IMAGE_GENERATOR: {"run": True, "order": 2},
        },
        conditional_task_specs={},
        candidate_agents=[
            AgentType.CONCEPT_PLANNER,
            AgentType.SCRIPT_WRITER,
            AgentType.IMAGE_GENERATOR,
        ],
        anchor_type=OrchestrationStateAdapter.CONTINUATION_ANCHOR_GATE_DECISION,
        node_key="script",
        attempt_id=9,
    )
    canonical_checkpoint = JsonObjectPayload.from_mapping(
        checkpoint,
        field_path="test.continuation_checkpoint",
    ).to_dict()

    task_specs, _, candidate_agents = OrchestrationStateAdapter.checkpoint_to_task_specs(
        canonical_checkpoint,
        require_decision_id=False,
    )

    assert list(task_specs) == [
        AgentType.CONCEPT_PLANNER,
        AgentType.SCRIPT_WRITER,
        AgentType.IMAGE_GENERATOR,
    ]
    assert candidate_agents == list(task_specs)


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("run", "false"),
        ("run", 0),
        ("fallback_used", "false"),
        ("fallback_used", 1),
    ],
)
def test_continuation_spec_boolean_fields_reject_truthiness_coercion(
    field_name,
    invalid_value,
):
    with pytest.raises(ContinuationCheckpointContractError) as exc_info:
        OrchestrationStateAdapter.build_continuation_checkpoint(
            task_specs={
                AgentType.IMAGE_GENERATOR: {
                    "run": True,
                    field_name: invalid_value,
                }
            },
            conditional_task_specs={},
            candidate_agents=[AgentType.IMAGE_GENERATOR],
            anchor_type=(OrchestrationStateAdapter.CONTINUATION_ANCHOR_RUNTIME_CHECKPOINT),
            node_key="image",
            attempt_id=1,
        )

    assert exc_info.value.reason_code is ContinuationCheckpointContractReason.SPEC_BOOLEAN_INVALID
    assert exc_info.value.field_path.endswith(field_name)


def test_continuation_spec_preserves_explicit_false_booleans():
    checkpoint = OrchestrationStateAdapter.build_continuation_checkpoint(
        task_specs={
            AgentType.IMAGE_GENERATOR: {
                "run": False,
                "fallback_used": False,
            }
        },
        conditional_task_specs={},
        candidate_agents=[AgentType.IMAGE_GENERATOR],
        anchor_type=OrchestrationStateAdapter.CONTINUATION_ANCHOR_RUNTIME_CHECKPOINT,
        node_key="image",
        attempt_id=1,
    )

    spec = checkpoint["task_specs"][AgentType.IMAGE_GENERATOR.value]
    assert spec["run"] is False
    assert spec["fallback_used"] is False


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("mission", {"text": "generate images"}),
        ("deliverable", ["scene images"]),
        ("constraints", ["canonical", 7]),
        ("order", "1"),
        ("runtime_hints", ["fast"]),
        ("conditional_task_id", 7),
        ("trigger", {"event": "approved"}),
        ("scope", ["scene-1"]),
    ],
)
def test_continuation_spec_rejects_noncanonical_json_field_types(
    field_name,
    invalid_value,
):
    with pytest.raises(ContinuationCheckpointContractError) as exc_info:
        OrchestrationStateAdapter.build_continuation_checkpoint(
            task_specs={
                AgentType.IMAGE_GENERATOR: {
                    "run": True,
                    field_name: invalid_value,
                }
            },
            conditional_task_specs={},
            candidate_agents=[AgentType.IMAGE_GENERATOR],
            anchor_type=OrchestrationStateAdapter.CONTINUATION_ANCHOR_RUNTIME_CHECKPOINT,
            node_key="image",
            attempt_id=1,
        )

    assert (
        exc_info.value.reason_code is ContinuationCheckpointContractReason.SPEC_FIELD_TYPE_INVALID
    )
    assert exc_info.value.field_path.endswith(field_name)


@pytest.mark.parametrize(
    ("field_name", "invalid_value", "reason"),
    [
        (
            "anchor_type",
            " runtime_checkpoint ",
            ContinuationCheckpointContractReason.CHECKPOINT_ANCHOR_INVALID,
        ),
        (
            "node_key",
            7,
            ContinuationCheckpointContractReason.CHECKPOINT_NODE_INVALID,
        ),
        (
            "attempt_id",
            "1",
            ContinuationCheckpointContractReason.CHECKPOINT_ATTEMPT_INVALID,
        ),
    ],
)
def test_build_continuation_checkpoint_rejects_noncanonical_boundary_types(
    field_name,
    invalid_value,
    reason,
):
    kwargs = {
        "task_specs": {AgentType.IMAGE_GENERATOR: {"run": True}},
        "conditional_task_specs": {},
        "candidate_agents": [AgentType.IMAGE_GENERATOR],
        "anchor_type": OrchestrationStateAdapter.CONTINUATION_ANCHOR_RUNTIME_CHECKPOINT,
        "node_key": "image",
        "attempt_id": 1,
    }
    kwargs[field_name] = invalid_value

    with pytest.raises(ContinuationCheckpointContractError) as exc_info:
        OrchestrationStateAdapter.build_continuation_checkpoint(**kwargs)

    assert exc_info.value.reason_code is reason


@pytest.mark.parametrize(
    ("field_name", "invalid_value", "reason"),
    [
        (
            "anchor_type",
            "RUNTIME_CHECKPOINT",
            ContinuationCheckpointContractReason.CHECKPOINT_ANCHOR_INVALID,
        ),
        (
            "node_key",
            7,
            ContinuationCheckpointContractReason.CHECKPOINT_NODE_INVALID,
        ),
        (
            "attempt_id",
            "1",
            ContinuationCheckpointContractReason.CHECKPOINT_ATTEMPT_INVALID,
        ),
        (
            "candidate_agents",
            [AgentType.IMAGE_GENERATOR],
            ContinuationCheckpointContractReason.CHECKPOINT_AGENT_INVALID,
        ),
    ],
)
def test_validate_continuation_checkpoint_rejects_noncanonical_boundary_types(
    field_name,
    invalid_value,
    reason,
):
    checkpoint = _valid_image_checkpoint()
    checkpoint[field_name] = invalid_value

    with pytest.raises(ContinuationCheckpointContractError) as exc_info:
        OrchestrationStateAdapter.validate_continuation_checkpoint(
            checkpoint,
            require_decision_id=False,
        )

    assert exc_info.value.reason_code is reason


def _valid_image_checkpoint():
    return OrchestrationStateAdapter.build_continuation_checkpoint(
        task_specs={
            AgentType.IMAGE_GENERATOR: {
                "agent": AgentType.IMAGE_GENERATOR.value,
                "run": True,
                "order": 0,
            }
        },
        conditional_task_specs={},
        candidate_agents=[AgentType.IMAGE_GENERATOR],
        anchor_type=OrchestrationStateAdapter.CONTINUATION_ANCHOR_RUNTIME_CHECKPOINT,
        node_key="image",
        attempt_id=1,
    )


def test_build_continuation_checkpoint_requires_primary_run_control():
    with pytest.raises(ContinuationCheckpointContractError) as exc_info:
        OrchestrationStateAdapter.build_continuation_checkpoint(
            task_specs={
                AgentType.IMAGE_GENERATOR: {
                    "agent": AgentType.IMAGE_GENERATOR.value,
                    "order": 0,
                }
            },
            conditional_task_specs={},
            candidate_agents=[AgentType.IMAGE_GENERATOR],
            anchor_type=OrchestrationStateAdapter.CONTINUATION_ANCHOR_RUNTIME_CHECKPOINT,
            node_key="image",
            attempt_id=1,
        )

    assert exc_info.value.reason_code.value == "continuation_spec_required_field_missing"
    assert exc_info.value.field_path.endswith(".run")


def test_validate_continuation_checkpoint_rejects_duplicate_candidates():
    checkpoint = _valid_image_checkpoint()
    checkpoint["candidate_agents"].append(AgentType.IMAGE_GENERATOR.value)

    with pytest.raises(ContinuationCheckpointContractError) as exc_info:
        OrchestrationStateAdapter.validate_continuation_checkpoint(
            checkpoint,
            require_decision_id=False,
        )

    assert (
        exc_info.value.reason_code
        is ContinuationCheckpointContractReason.CHECKPOINT_CANDIDATES_INVALID
    )


def test_validate_continuation_checkpoint_requires_candidate_spec_identity_set_match():
    checkpoint = _valid_image_checkpoint()
    checkpoint["candidate_agents"].append(AgentType.VIDEO_GENERATOR.value)

    with pytest.raises(ContinuationCheckpointContractError) as exc_info:
        OrchestrationStateAdapter.validate_continuation_checkpoint(
            checkpoint,
            require_decision_id=False,
        )

    assert (
        exc_info.value.reason_code
        is ContinuationCheckpointContractReason.CHECKPOINT_TASK_SPECS_INVALID
    )


def test_validate_continuation_checkpoint_rejects_float_version():
    checkpoint = _valid_image_checkpoint()
    checkpoint["version"] = float(OrchestrationStateAdapter.CONTINUATION_CHECKPOINT_VERSION)

    with pytest.raises(ContinuationCheckpointContractError) as exc_info:
        OrchestrationStateAdapter.validate_continuation_checkpoint(
            checkpoint,
            require_decision_id=False,
        )

    assert (
        exc_info.value.reason_code
        is ContinuationCheckpointContractReason.CHECKPOINT_VERSION_UNSUPPORTED
    )


def test_build_continuation_checkpoint_rejects_task_key_spec_agent_mismatch():
    with pytest.raises(ContinuationCheckpointContractError) as exc_info:
        OrchestrationStateAdapter.build_continuation_checkpoint(
            task_specs={
                AgentType.IMAGE_GENERATOR: {
                    "agent": AgentType.VIDEO_GENERATOR.value,
                    "run": True,
                }
            },
            conditional_task_specs={},
            candidate_agents=[AgentType.IMAGE_GENERATOR],
            anchor_type=OrchestrationStateAdapter.CONTINUATION_ANCHOR_RUNTIME_CHECKPOINT,
            node_key="image",
            attempt_id=1,
        )

    assert exc_info.value.reason_code is ContinuationCheckpointContractReason.SPEC_AGENT_MISMATCH


def test_build_continuation_checkpoint_rejects_explicit_null_spec_agent():
    with pytest.raises(ContinuationCheckpointContractError) as exc_info:
        OrchestrationStateAdapter.build_continuation_checkpoint(
            task_specs={
                AgentType.IMAGE_GENERATOR: {
                    "agent": None,
                    "run": True,
                }
            },
            conditional_task_specs={},
            candidate_agents=[AgentType.IMAGE_GENERATOR],
            anchor_type=OrchestrationStateAdapter.CONTINUATION_ANCHOR_RUNTIME_CHECKPOINT,
            node_key="image",
            attempt_id=1,
        )

    assert exc_info.value.reason_code is ContinuationCheckpointContractReason.SPEC_AGENT_INVALID


@pytest.mark.parametrize(
    ("agent_value", "reason"),
    [
        ("unknown_generator", ContinuationCheckpointContractReason.SPEC_AGENT_INVALID),
        (
            AgentType.VIDEO_GENERATOR.value,
            ContinuationCheckpointContractReason.SPEC_AGENT_MISMATCH,
        ),
        (None, ContinuationCheckpointContractReason.SPEC_AGENT_INVALID),
    ],
)
def test_validate_continuation_checkpoint_rejects_invalid_or_mismatched_spec_agent(
    agent_value,
    reason,
):
    checkpoint = _valid_image_checkpoint()
    if agent_value is None:
        checkpoint["task_specs"][AgentType.IMAGE_GENERATOR.value].pop("agent")
    else:
        checkpoint["task_specs"][AgentType.IMAGE_GENERATOR.value]["agent"] = agent_value

    with pytest.raises(ContinuationCheckpointContractError) as exc_info:
        OrchestrationStateAdapter.validate_continuation_checkpoint(
            checkpoint,
            require_decision_id=False,
        )

    assert exc_info.value.reason_code is reason
