import asyncio
from types import SimpleNamespace

import pytest

from app.agents.concept_planner import ConceptPlannerAgent


class _StubSession:
    def add(self, *_):
        return None

    def commit(self):
        return None

    def refresh(self, *_):
        return None


@pytest.mark.asyncio
async def test_project_mode_skips_scene_generation(monkeypatch):
    agent = ConceptPlannerAgent()

    async def noop_update_progress(*args, **kwargs):
        return None

    async def noop_store_guidance(*args, **kwargs):
        return False

    agent._update_progress = noop_update_progress  # type: ignore
    agent.store_creative_guidance = noop_store_guidance  # type: ignore
    agent.websocket_manager = SimpleNamespace(
        broadcast_to_task=lambda *args, **kwargs: asyncio.Future(),
    )
    agent.websocket_manager.broadcast_to_task().set_result(None)

    skeleton_payload = {
        "overview": "Project outline",
        "genre_and_theme": {},
        "target_audience": "fans",
        "key_messages": ["message"],
        "scene_blueprint": [
            {"scene_number": 1, "duration_hint": 10, "title": "Intro"}
        ],
    }

    async def stub_generate_skeleton(*args, **kwargs):
        return skeleton_payload, 0

    async def stub_generate_style(*args, **kwargs):
        return {
            "payload": {
                "intelligent_style_design": {
                    "style_name": "Anime",
                    "style_description": "Anime style",
                },
                "content_elements": {
                    "characters": [
                        {
                            "canonical_name": "hero",
                            "display_name": "Hero",
                        }
                    ]
                },
                "consistency_hints": {},
            },
            "usage": 0,
        }

    async def stub_generate_voice(*args, **kwargs):
        return {"payload": {"voice_plan": {}}, "usage": 0}

    async def fail_scene_details(*args, **kwargs):
        raise AssertionError("scene generation should be skipped in project mode")

    def fail_create_scenes(*args, **kwargs):
        raise AssertionError("no workflow scenes should be created in project mode")

    monkeypatch.setattr(agent, "_generate_skeleton", stub_generate_skeleton)
    monkeypatch.setattr(agent, "_generate_style_bundle", stub_generate_style)
    monkeypatch.setattr(agent, "_generate_voice_plan", stub_generate_voice)
    monkeypatch.setattr(agent, "_generate_scene_details", fail_scene_details)
    monkeypatch.setattr(agent, "_create_scenes_in_workflow_state", fail_create_scenes)

    task = SimpleNamespace(
        task_id="task-id",
        status="pending",
        update_progress=lambda *args, **kwargs: None,
    )
    execution = SimpleNamespace(output_data={}, tokens_used=0, api_calls_made=0, estimate_cost=lambda: None)

    result = await agent._execute_impl(
        task,
        {
            "user_prompt": "制作史诗动漫项目",
            "duration": 180,
            "aspect_ratio": "16:9",
            "workflow_state_id": "wf-project-mode",
            "concept_mode": "project",
            "style_taxonomy_summary": "动漫风格",
        },
        execution,
        _StubSession(),
    )

    concept_plan = result["concept_plan"]
    assert concept_plan["intelligent_style_design"]["style_name"] == "Anime"
    assert concept_plan["scenes"] == []
