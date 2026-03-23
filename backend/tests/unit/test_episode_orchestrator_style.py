import asyncio
from types import SimpleNamespace

import pytest

from app.agents.episode_orchestrator import EpisodeOrchestratorAgent
from app.core.story_plan import EpisodePlan, ProjectState, StoryPlan
from app.core.story_plan import project_state_repository


class _StubConceptPlanner:
    async def execute(self, *_, **__):
        return {
            "concept_plan": {
                "intelligent_style_design": {
                    "style_name": "Anime Cel",
                    "style_description": "Cel shaded anime aesthetic",
                    "visual_approach": "动画",
                    "narrative_style": "电影叙事式",
                    "production_taste": "精致奢华",
                    "emotional_tone": "史诗悲壮",
                },
                "content_elements": {
                    "characters": [
                        {
                            "canonical_name": "zhao_zilong",
                            "display_name": "赵子龙",
                            "aliases": ["常山赵子龙"],
                            "type": "人类",
                            "abstract_traits": ["英勇", "忠诚"],
                        }
                    ]
                },
            }
        }


class _StubSession:
    def add(self, *_):
        return None

    def commit(self):
        return None

    def refresh(self, *_):
        return None


@pytest.mark.asyncio
async def test_project_foundation_populates_style_and_character_bible():
    project_id = "proj-test"
    story_plan = StoryPlan(
        project_id=project_id,
        user_prompt="制作史诗动漫短片",
        target_duration_seconds=180,
        aspect_ratio="16:9",
    )
    story_plan.add_episode(EpisodePlan.create(0, "Episode 1", 60))

    project_state = ProjectState(
        project_id=project_id,
        mode="project",
        story_plan=story_plan,
    )

    agent = EpisodeOrchestratorAgent(
        memory_services=SimpleNamespace(
            short_term=object(),
            global_service=object(),
            long_term=object(),
        ),
        orchestrator=SimpleNamespace(),
        concept_planner=_StubConceptPlanner(),
    )

    base_task = SimpleNamespace(session_id="sess", user_id="user")

    await agent._ensure_project_foundation(base_task, project_state, _StubSession())

    assert project_state.style_profile["style_name"] == "Anime Cel"
    canonical_ids = list(project_state.character_bible.keys())
    assert canonical_ids, "character bible should not be empty"
    profile = project_state.character_bible[canonical_ids[0]]
    assert profile.display_name == "赵子龙"
    assert story_plan.visual_style["style_name"] == "Anime Cel"

    # cleanup
    project_state_repository.remove(project_id)
