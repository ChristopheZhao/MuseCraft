import pytest


@pytest.mark.asyncio
async def test_think_and_plan_returns_plan_and_act(monkeypatch):
    from app.agents.image_generator import ImageGeneratorAgent
    from app.agents.base import BaseAgent

    # 禁止加载真实工具
    monkeypatch.setattr(BaseAgent, "_load_tools", lambda self, names: setattr(self, "_available_tools", {}))

    agent = ImageGeneratorAgent(llms=None)

    observation = {
        "scenes": [{"scene_number": 1}],
        "completed_scene_numbers": [],
        "failed_scene_numbers": [],
    }

    plan = await agent._think_and_plan(observation, task=None, execution=None, iteration=1)

    assert plan.get("action") == "plan_and_act"
    assert isinstance(plan.get("parameters", {}).get("messages"), list)


@pytest.mark.asyncio
async def test_execute_action_contract_completion(monkeypatch):
    from app.agents.image_generator import ImageGeneratorAgent
    from app.agents.base import BaseAgent

    monkeypatch.setattr(BaseAgent, "_load_tools", lambda self, names: setattr(self, "_available_tools", {}))

    agent = ImageGeneratorAgent(llms=None)
    agent.iteration_context["workflow_state_id"] = "wf-test"
    agent._set_agent_state({"context": {"scenes_to_generate": []}})

    async def fake_run_fc_round(*args, **kwargs):
        return {
            "fc_plan": {},
            "executed_calls": [],
            "results": [],
            "contract": {"task_complete": True, "context_updates": {"notes": "done"}},
        }

    async def fake_postprocess(_):
        return []

    monkeypatch.setattr(agent, "run_fc_round", fake_run_fc_round)
    monkeypatch.setattr(agent, "_postprocess_executed_results", fake_postprocess)
    monkeypatch.setattr(agent, "_write_image_results_to_memory", lambda results: None)

    action_plan = {"action": "plan_and_act", "parameters": {"messages": []}}
    result = await agent._execute_action(action_plan, input_data={}, execution=None, db=None, iteration=0)

    assert result.get("contract", {}).get("task_complete") is True

    observation = {
        "scenes": [{"scene_number": 1, "completed": True}],
        "completed_scene_numbers": [1],
        "failed_scene_numbers": [],
    }

    reflection = await agent._reflect_on_results(result, observation, task=None, iteration=0)

    assert reflection.get("task_complete") is True
    assert reflection.get("should_stop") is True
