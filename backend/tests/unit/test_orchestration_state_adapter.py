from app.domain import AgentType, JsonObjectPayload
from app.services.orchestration_state_adapter import OrchestrationStateAdapter


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
