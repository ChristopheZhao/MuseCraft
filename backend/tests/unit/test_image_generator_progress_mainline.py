from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.agents.base import BaseAgent
from app.agents.image_generator import ImageGeneratorAgent
from app.agents.utils.memory_helpers import ensure_agent_working_memory, ensure_mas_working_memory
from app.services.memory_provider import build_memory_services


class _StubImagePromptComposerTool:
    def get_available_actions(self):
        return ["generate"]


def _build_agent(monkeypatch) -> ImageGeneratorAgent:
    monkeypatch.setattr(
        BaseAgent,
        "_load_tools",
        lambda self, names: setattr(self, "_available_tools", {}),
    )

    services = build_memory_services()
    agent = ImageGeneratorAgent(llms={}, memory_services=services)
    agent.workflow_state_id = "wf-image-progress-mainline"
    agent._available_tools = {"image_prompt_composer": _StubImagePromptComposerTool()}
    agent._fc_function_map = {
        "image_prompt_composer.generate": (
            "image_prompt_composer",
            "generate",
        )
    }
    return agent


@pytest.mark.asyncio
async def test_image_generator_does_not_block_cross_iteration_repeat_before_act(monkeypatch):
    agent = _build_agent(monkeypatch)

    mas = ensure_mas_working_memory(agent.workflow_state_id, service=agent.short_term_service)
    agent_wm = ensure_agent_working_memory(
        agent.workflow_state_id,
        agent.agent_name,
        service=agent.short_term_service,
        shared_view=mas,
    )
    agent_wm.put(
        "obs_records",
        [
            {
                "iteration": 0,
                "action_result": {
                    "act_log": [
                        {
                            "tool": "image_prompt_composer.generate",
                            "scene_number": 1,
                            "success": True,
                        }
                    ]
                },
            }
        ],
    )

    executed = []

    async def _fake_execute(function_name, function_args, **_kwargs):
        executed.append((function_name, dict(function_args or {})))
        return SimpleNamespace(
            success=True,
            result={"image_url": "https://example.com/image.png"},
        )

    async def _fake_persist(executed_calls):
        return list(executed_calls or [])

    monkeypatch.setattr(agent, "_execute_function_call", _fake_execute)
    monkeypatch.setattr(agent, "_persist_executed_results", _fake_persist)

    result = await agent._execute_action(
        {
            "action": "execute_tool_calls",
            "tool_calls": [
                {
                    "function": {
                        "name": "image_prompt_composer.generate",
                        "arguments": {
                            "scene_number": 1,
                            "scene_info_ref": "/tmp/scene-info.json",
                        },
                    }
                }
            ],
        },
        input_data={},
        db=None,
        iteration=1,
    )

    assert len(executed) == 1
    assert executed[0][0] == "image_prompt_composer.generate"
    assert executed[0][1]["scene_number"] == 1
    assert len(result["executed_calls"]) == 1
    assert result["executed_calls"][0]["success"] is True
    assert "review_receipts" not in result


@pytest.mark.asyncio
async def test_image_generator_planner_prefers_remaining_scene_numbers_from_progress_read_model(monkeypatch):
    agent = _build_agent(monkeypatch)

    monkeypatch.setattr(
        agent.prompt_manager,
        "render_template",
        lambda cfg_name, template_name, variables, use_cache, auto_reload: (
            "system prompt" if template_name == "system" else ""
        ),
    )

    observed_payload = {}

    async def _fake_llm_function_call(*, messages, context_description, temperature):
        assert context_description == "image_generation_plan_fc"
        payload = json.loads(messages[-1]["content"])
        observed_payload.update(payload)
        remaining = payload["progress_read_model"]["remaining_scene_numbers"]
        return {
            "tool_calls": [
                {
                    "function": {
                        "name": "image_prompt_composer.generate",
                        "arguments": {
                            "scene_number": remaining[0],
                            "scene_info_ref": "/tmp/scene-info.json",
                        },
                    }
                }
            ],
            "llm_response": {"content": f"Generate scene {remaining[0]} next."},
        }

    monkeypatch.setattr(agent, "llm_function_call", _fake_llm_function_call)

    action_plan = await agent._think_and_plan(
        {
            "progress_read_model": {
                "planned_scene_numbers": [1, 2, 3],
                "successful_scene_numbers": [1],
                "remaining_scene_numbers": [2, 3],
                "recent_execution_receipts": [
                    {"iteration": 0, "scene_number": 1, "status": "succeeded"}
                ],
            }
        },
        task=SimpleNamespace(),
        iteration=0,
    )

    assert observed_payload["progress_read_model"]["successful_scene_numbers"] == [1]
    assert observed_payload["progress_read_model"]["remaining_scene_numbers"] == [2, 3]
    planned_call = action_plan["tool_calls"][0]["function"]
    assert planned_call["name"] == "image_prompt_composer.generate"
    assert planned_call["arguments"]["scene_number"] == 2
