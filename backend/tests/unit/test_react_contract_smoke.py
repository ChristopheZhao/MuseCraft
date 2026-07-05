from app.agents.utils.tool_contracts import (
    overlay_contract_on_reflection,
    plan_contract_conflicts_with_actions,
)


def test_plan_contract_conflict_requires_completion_and_actions():
    assert plan_contract_conflicts_with_actions(
        {"task_complete": True, "completed_reason": "all_scenes_complete"},
        [{"function": {"name": "image_prompt_composer.generate", "arguments": {}}}],
    )

    assert not plan_contract_conflicts_with_actions(
        {"task_complete": False, "completed_reason": "needs_generation"},
        [{"function": {"name": "image_prompt_composer.generate", "arguments": {}}}],
    )

    assert not plan_contract_conflicts_with_actions(
        {"task_complete": True, "completed_reason": "all_scenes_complete"},
        [],
    )


def test_overlay_contract_on_reflection_respects_action_guard():
    contract = {
        "task_complete": True,
        "completed_reason": "all_scenes_complete",
        "plan_summary": "planner reports completion",
    }

    reflected = overlay_contract_on_reflection({"success": True}, contract)
    assert reflected["task_complete"] is True
    assert reflected["completed_reason"] == "all_scenes_complete"

    guarded = overlay_contract_on_reflection({"success": True}, contract, ignore_complete=True)
    assert "task_complete" not in guarded
    assert guarded["completed_reason"] == "all_scenes_complete"
