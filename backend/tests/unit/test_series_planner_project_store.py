from types import SimpleNamespace

import pytest

from app.agents.series_planner import SeriesPlannerAgent
from app.core.story_plan import CharacterProfile
from app.domain import AgentExecutionRequest, AgentTaskReference, AgentType, JsonObjectPayload


@pytest.mark.asyncio
async def test_series_planner_returns_definition_without_persistence_dependency():
    agent = object.__new__(SeriesPlannerAgent)
    agent.logger = SimpleNamespace(warning=lambda *args, **kwargs: None)
    agent._validate_input = lambda _input, _required: None

    async def _outline(**kwargs):
        return {
            "episodes": [{"title": "Episode 1", "summary": "Mission begins"}],
            "global_theme": "Courage",
        }

    async def _characters(**kwargs):
        return (
            {
                "hero": CharacterProfile(
                    canonical_id="hero",
                    display_name="Hero",
                )
            },
            {"style_name": "storybook"},
        )

    async def _scripts(*, project_definition, user_prompt):
        project_definition.story_plan.episodes[0].script_draft = user_prompt

    agent._generate_episode_outline = _outline
    agent._derive_character_bible = _characters
    agent._populate_episode_scripts = _scripts

    result = await SeriesPlannerAgent._execute_impl(
        agent,
        AgentExecutionRequest(
            task=AgentTaskReference(task_id="task-plan", task_type="project_workflow"),
            agent_type=AgentType.SERIES_PLANNER.value,
            input_data=JsonObjectPayload.from_mapping(
                {
                    "project_id": "project-plan",
                    "user_prompt": "Rabbit hero project",
                    "target_duration_seconds": 60,
                    "mode": "project",
                    "aspect_ratio": "16:9",
                    "episode_cap_seconds": 60,
                    "episode_min_seconds": 45,
                    "auto_generate_scripts": True,
                },
                field_path="test.input_data",
            ),
        ),
    )

    assert result["project_definition"]["project_id"] == "project-plan"
    assert result["project_definition"]["story_plan"]["episodes"][0]["script_draft"]
    assert "episodes_runtime" not in result["project_definition"]
