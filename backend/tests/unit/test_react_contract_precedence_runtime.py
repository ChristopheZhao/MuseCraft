from types import SimpleNamespace

import pytest

from app.agents.base import BaseAgent
from app.agents.react_agent import ReActAgent
from app.models import AgentType
from app.services.memory_provider import build_memory_services


@pytest.fixture(autouse=True)
def _use_in_memory_long_term_store(monkeypatch):
    monkeypatch.setenv("MEMORY_BACKEND", "dict")


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
                        "name": "image_prompt_composer.generate",
                        "arguments": {"scene_number": 1, "scene_info_ref": "/tmp/scene-info.json"},
                    }
                }
            ],
            "plan_llm": {"content": "任务已经完成，不需要继续生成。"},
        }

    async def _execute_action(self, action_plan, input_data, db, iteration):
        self.executed = True
        return {"executed_calls": []}


class _CompletionGateReactAgent(ReActAgent):
    def __init__(self, *, memory_services):
        super().__init__(
            agent_type=AgentType.IMAGE_GENERATOR,
            agent_name="image_generator",
            max_iterations=2,
            llms={},
            memory_services=memory_services,
        )
        self.gate_calls = 0

    async def _think_and_plan(self, current_state, task, iteration):
        return {
            "action": "observe",
            "plan_contract": {
                "task_complete": True,
                "completed_reason": "planner_prose_only",
                "plan_summary": "planner claims completion without deliveries",
            },
            "plan_llm": {"content": "任务已完成。"},
        }

    async def _execute_action(self, action_plan, input_data, db, iteration):
        raise AssertionError("ACT must not run when no tool calls are planned")

    def _accept_completion_request(
        self,
        *,
        stage,
        input_data,
        plan_context,
        iteration_context,
        iteration,
        plan_contract=None,
        reflection=None,
        action_result=None,
    ):
        self.gate_calls += 1
        return {"accepted": False, "reason": "missing_delivery_acceptance"}


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


@pytest.mark.asyncio
async def test_react_completion_gate_rejects_plan_only_completion(monkeypatch):
    monkeypatch.setattr(
        BaseAgent,
        "_load_tools",
        lambda self, names: setattr(self, "_available_tools", {}),
    )
    agent = _CompletionGateReactAgent(memory_services=build_memory_services())

    result = await agent._execute_impl(
        task=SimpleNamespace(),
        input_data={"workflow_state_id": "wf-react-gate"},
        db=None,
    )

    assert agent.gate_calls == 2
    assert result["subtask_state"] == "blocked"
    assert result["loop_end_reason"] == "no_tool_calls_streak"
