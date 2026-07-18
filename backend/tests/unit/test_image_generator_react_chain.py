import pytest

from app.domain import AgentTaskReference
from app.services.memory_provider import build_memory_services


def _task_reference():
    return AgentTaskReference(
        task_id="task-image-react-chain",
        task_type="video_generation",
    )


@pytest.mark.asyncio
async def test_think_and_plan_returns_plan_and_act(monkeypatch):
    from app.agents.image_generator import ImageGeneratorAgent
    from app.agents.base import BaseAgent

    # 禁止加载真实工具
    monkeypatch.setattr(BaseAgent, "_load_tools", lambda self, names: setattr(self, "_available_tools", {}))

    agent = ImageGeneratorAgent(llms=None, memory_services=build_memory_services())

    async def fake_llm_function_call(*_args, **_kwargs):
        return {
            "tool_calls": [
                {
                    "id": "call-image-1",
                    "type": "function",
                    "function": {
                        "name": "generate_image",
                        "arguments": '{"scene_number": 1}',
                    },
                }
            ],
            "llm_response": {"finish_reason": "tool_calls"},
        }

    monkeypatch.setattr(agent, "llm_function_call", fake_llm_function_call)

    observation = {
        "scenes": [{"scene_number": 1}],
        "completed_scene_numbers": [],
        "failed_scene_numbers": [],
    }

    plan = await agent._think_and_plan(observation, task=_task_reference(), iteration=1)

    assert plan.get("action") == "execute_tool_calls"
    assert plan["tool_calls"][0]["function"]["name"] == "generate_image"


@pytest.mark.asyncio
async def test_execute_action_runs_planned_calls_and_reflects_receipt(monkeypatch):
    from app.agents.image_generator import ImageGeneratorAgent
    from app.agents.base import BaseAgent

    monkeypatch.setattr(BaseAgent, "_load_tools", lambda self, names: setattr(self, "_available_tools", {}))

    agent = ImageGeneratorAgent(llms=None, memory_services=build_memory_services())
    agent.workflow_state_id = "wf-test"

    async def fake_execute_tool_calls(*_args, **_kwargs):
        return {
            "executed_calls": [
                {
                    "tool": "generate_image",
                    "args": {"scene_number": 1},
                    "success": True,
                    "result": {"image_url": "memory://scene-1"},
                }
            ],
            "act_log": [],
            "react_metrics": {},
        }

    async def fake_persist_executed_results(_executed_calls):
        return [{"scene_number": 1, "image_url": "memory://scene-1"}]

    monkeypatch.setattr(agent, "execute_tool_calls", fake_execute_tool_calls)
    monkeypatch.setattr(agent, "_persist_executed_results", fake_persist_executed_results)

    action_plan = {
        "action": "execute_tool_calls",
        "tool_calls": [
            {
                "id": "call-image-1",
                "type": "function",
                "function": {
                    "name": "generate_image",
                    "arguments": '{"scene_number": 1}',
                },
            }
        ],
    }
    result = await agent._execute_action(action_plan, input_data={}, iteration=0)

    assert result["action_performed"] == "execute_tool_calls"
    assert result["batch_size"] == 1
    assert result["executed_calls"][0]["success"] is True

    observation = {
        "scenes": [{"scene_number": 1, "completed": True}],
        "completed_scene_numbers": [1],
        "failed_scene_numbers": [],
    }

    reflection = await agent._reflect_on_results(
        result,
        observation,
        task=_task_reference(),
        iteration=0,
    )

    assert reflection["success"] is True
    assert reflection["reflection_summary"]
    assert "task_complete" not in reflection
