import pytest
from types import SimpleNamespace

from app.agents.series_planner import SeriesPlannerAgent
from app.core.story_plan import (
    CharacterProfile,
    EpisodePlan,
    ProjectOperationState,
    ProjectState,
    StoryPlan,
    project_state_repository,
)


pytestmark = pytest.mark.usefixtures("project_state_store")


@pytest.mark.asyncio
async def test_series_planner_persists_planned_state_into_shared_store():
    project_id = "project-series-planner-store"

    placeholder_story_plan = StoryPlan(
        project_id=project_id,
        user_prompt="placeholder",
        target_duration_seconds=120,
        aspect_ratio="16:9",
    )
    placeholder_story_plan.add_episode(EpisodePlan.create(0, "Placeholder", 60))
    placeholder_state = ProjectState(
        project_id=project_id,
        mode="project",
        story_plan=placeholder_story_plan,
        global_settings={"resolution": "1080p", "style_preference": "storybook"},
    )
    placeholder_state.progress.planning.status = ProjectOperationState.QUEUED
    project_state_repository.save(placeholder_state)

    agent = object.__new__(SeriesPlannerAgent)
    agent.logger = SimpleNamespace(warning=lambda *args, **kwargs: None)
    agent._validate_input = lambda _input, _required: None

    async def _generate_episode_outline(**kwargs):
        return {
            "episodes": [
                {
                    "title": "Episode 1",
                    "summary": "The rabbit receives the mission",
                    "narrative_purpose": "Introduce the quest",
                    "continuity_notes": {"opening": True},
                },
                {
                    "title": "Episode 2",
                    "summary": "The rabbit crosses the forest",
                    "narrative_purpose": "Escalate the journey",
                    "required_assets": {"location": "forest"},
                },
            ],
            "global_theme": "Courage",
            "tone_and_mood": "Warm adventure",
            "additional_notes": {"audience": "family"},
        }

    async def _derive_character_bible(**kwargs):
        return (
            {
                "little_bunny": CharacterProfile(
                    canonical_id="little_bunny",
                    display_name="小兔子",
                    description="主角兔子",
                )
            },
            {"style_name": "storybook", "style_description": "storybook watercolor"},
        )

    async def _populate_episode_scripts(*, project_state, user_prompt):
        for episode in project_state.story_plan.episodes:
            episode.script_draft = f"{user_prompt}-{episode.sequence_index + 1}"

    agent._generate_episode_outline = _generate_episode_outline
    agent._derive_character_bible = _derive_character_bible
    agent._populate_episode_scripts = _populate_episode_scripts

    result = await SeriesPlannerAgent._execute_impl(
        agent,
        task=SimpleNamespace(),
        input_data={
            "project_id": project_id,
            "user_prompt": "Rabbit hero project",
            "target_duration_seconds": 120,
            "mode": "project",
            "aspect_ratio": "16:9",
            "resolution": "1080p",
            "style_preference": "storybook",
            "episode_cap_seconds": 60,
            "episode_min_seconds": 45,
            "auto_generate_scripts": True,
        },
        db=None,
    )

    saved = project_state_repository.get(project_id)

    assert saved is not None
    assert saved.project_id == project_id
    assert saved.global_settings["resolution"] == "1080p"
    assert saved.global_settings["style_preference"] == "storybook"
    assert len(saved.story_plan.episodes) == 2
    assert saved.story_plan.episodes[0].title == "Episode 1"
    assert saved.story_plan.episodes[0].script_draft == "Rabbit hero project-1"
    assert saved.story_plan.episodes[1].required_assets == {"location": "forest"}
    assert "little_bunny" in saved.character_bible
    assert saved.style_profile["style_name"] == "storybook"
    assert result["story_plan"]["episodes"][0]["title"] == "Episode 1"

    project_state_repository.remove(project_id)
