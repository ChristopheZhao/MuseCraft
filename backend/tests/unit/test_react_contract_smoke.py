import os
import sys
import json
from typing import Any, Dict

# Ensure backend package is importable when running pytest from repo root
CURRENT_DIR = os.path.dirname(__file__)
BACKEND_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
if BACKEND_ROOT not in sys.path:
    sys.path.append(BACKEND_ROOT)

from app.agents.react_agent import ReActAgent  # type: ignore
from app.models import AgentType  # type: ignore


class DummyAgent(ReActAgent):
    def __init__(self):
        super().__init__(
            agent_type=AgentType.IMAGE_GENERATOR,
            agent_name="dummy_react",
            max_iterations=1,
            tools=[],
        )

    async def _observe_current_state(self, input_data: Dict[str, Any], context: Dict[str, Any], iteration: int) -> Dict[str, Any]:
        return {"scenes": [], "completed_scene_numbers": [], "failed_scene_numbers": []}

    async def _think_and_plan(self, current_state: Dict[str, Any], task, execution, iteration: int) -> Dict[str, Any]:
        return {"action": "noop", "parameters": {}}

    async def _execute_action(self, action_plan: Dict[str, Any], input_data: Dict[str, Any], execution, db, iteration: int) -> Dict[str, Any]:
        return {"action_performed": "noop"}

    async def _reflect_on_results(self, action_result: Dict[str, Any], current_state: Dict[str, Any], task, iteration: int) -> Dict[str, Any]:
        return {"success": True, "task_complete": False, "should_stop": False, "context_updates": {}}


def test_parse_and_apply_contract_plan_only_round():
    agent = DummyAgent()
    agent.iteration_context = {"agent_state": {}}

    contract_json = {
        "task_complete": False,
        "should_stop": False,
        "context_updates": {
            "goal": "生成一个御剑飞行的短视频，男主角御剑飞行到极寒之地解救同门",
            "scenes_to_generate": [
                {"scene_number": 1, "title": "御风启程", "duration": 5, "depends_on_scene": None},
                {"scene_number": 2, "title": "穿越风雪", "duration": 5, "depends_on_scene": 1}
            ],
            "ready_items": [1],
            "blocked_items": [2]
        },
        "plan_delta": {
            "version": 1,
            "digest": "2步计划：启程→风雪",
            "changes": [{"op": "insert", "after": None, "step": {"id": "exec_1", "name": "执行1", "intent": "建立基调"}}],
            "active_steps": ["exec_1"]
        },
        "notes": "计划建立，不执行动作"
    }

    # Simulate LLM content payload (as string)
    content = json.dumps(contract_json, ensure_ascii=False)
    parsed = agent._parse_react_contract(content)
    assert parsed is not None, "Contract should be parsed"
    assert parsed.get("task_complete") is False
    assert parsed.get("should_stop") is False

    # Apply into iteration_context
    agent._apply_react_contract(parsed)
    ws = agent.iteration_context.get("agent_state", {})
    aps = agent.iteration_context.get("agent_plan_state", {})
    assert ws.get("goal"), "goal should be merged into agent_state"
    assert isinstance(aps.get("last_plan_delta"), dict), "plan_delta should be recorded in agent_plan_state"

    # Overlay on reflection (LLM has authority)
    reflection = {"success": True, "task_complete": False, "should_stop": False, "context_updates": {}}
    merged = agent._overlay_contract_on_reflection(reflection, parsed)
    assert merged["task_complete"] is False
    assert merged["should_stop"] is False
    assert "ready_items" in merged["context_updates"], "context updates should be carried over"
