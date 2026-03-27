from app.agents.episode_orchestrator import EpisodeOrchestratorAgent
from app.core.story_plan import EpisodePlan, ProjectState, StoryPlan, normalize_character_bible
from app.core.story_plan import project_state_repository


import pytest


pytestmark = pytest.mark.usefixtures("project_state_store")


def test_sync_project_foundation_reuses_story_plan_foundation():
    project_id = "proj-test"
    story_plan = StoryPlan(
        project_id=project_id,
        user_prompt="制作史诗动漫短片",
        target_duration_seconds=180,
        aspect_ratio="16:9",
    )
    story_plan.add_episode(EpisodePlan.create(0, "Episode 1", 60))
    story_plan.visual_style = {
        "style_name": "Anime Cel",
        "style_description": "Cel shaded anime aesthetic",
    }
    story_plan.merge_character_profiles(
        normalize_character_bible(
            {
                "zhao_zilong": {
                    "canonical_id": "zhao_zilong",
                    "display_name": "赵子龙",
                    "aliases": ["常山赵子龙"],
                    "description": "英勇的常胜将军",
                }
            }
        )
    )

    project_state = ProjectState(
        project_id=project_id,
        mode="project",
        story_plan=story_plan,
    )

    agent = object.__new__(EpisodeOrchestratorAgent)
    EpisodeOrchestratorAgent._sync_project_foundation(agent, project_state)

    assert project_state.style_profile["style_name"] == "Anime Cel"
    canonical_ids = list(project_state.character_bible.keys())
    assert canonical_ids, "character bible should not be empty"
    profile = project_state.character_bible[canonical_ids[0]]
    assert profile.display_name == "赵子龙"
    assert story_plan.visual_style["style_name"] == "Anime Cel"
    assert story_plan.character_bible is project_state.character_bible

    # cleanup
    project_state_repository.remove(project_id)
