from types import SimpleNamespace

import pytest

from app.agents.base import BaseAgent
from app.agents.react_agent import ReActAgent
from app.models import AgentType
from app.services.memory_provider import build_memory_services


class _ConflictReactAgent(ReActAgent):
    def __init__(self, *, memory_services):
        super().__init__(
            agent_type=AgentType.IMAGE_GENERATOR,
            agent_name="image_generator",
            max_iterations=1,
            llms={},
            memory_services=memory_services,
        )
        self.executed = False

    async def _think_and_plan(self, current_state, task, iteration):
        return {
            "action": "execute_planned_calls",
            "tool_calls": [
                {
                    "function": {
                        "name": "image_generation.generate_with_autoprompt",
                        "arguments": {"scene_number": 1},
                    }
                }
            ],
            "plan_llm": {"content": "任务已经完成，不需要继续生成。"},
        }

    async def _execute_action(self, action_plan, input_data, db, iteration):
        self.executed = True
        return {"executed_calls": []}


@pytest.mark.asyncio
async def test_react_contract_conflict_stops_before_act(monkeypatch):
    monkeypatch.setattr(
        BaseAgent,
        "_load_tools",
        lambda self, names: setattr(self, "_available_tools", {}),
    )
    agent = _ConflictReactAgent(memory_services=build_memory_services())

    async def _fake_normalize(_raw_text):
        return {
            "task_complete": True,
            "completed_reason": "all_scenes_complete",
            "plan_summary": "任务已经完成。",
        }

    monkeypatch.setattr(agent, "_normalize_plan_contract_from_text", _fake_normalize)

    result = await agent._execute_impl(
        task=SimpleNamespace(),
        input_data={"workflow_state_id": "wf-react-conflict"},
        db=None,
    )

    assert agent.executed is False
    assert result["subtask_state"] == "error"
    assert result["loop_end_reason"] == "plan_contract_conflict"
    assert result["completed_reason"] == "all_scenes_complete"
