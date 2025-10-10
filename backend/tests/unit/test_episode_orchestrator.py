from app.agents.episode_orchestrator import EpisodeOrchestratorAgent
from app.core.story_plan import (
    EpisodePlan,
    StoryPlan,
    ProjectState,
    project_state_repository,
    EpisodeStatus,
    normalize_character_bible,
)


def test_build_episode_payload_uses_episode_context(monkeypatch):
    agent = object.__new__(EpisodeOrchestratorAgent)

    story_plan = StoryPlan(
        project_id="pid",
        user_prompt="Overall project brief",
        target_duration_seconds=180,
        aspect_ratio="16:9",
    )
    story_plan.global_theme = "Heroic loyalty"
    story_plan.merge_character_profiles(
        normalize_character_bible(
            {
                "zhao_zilong": {
                    "canonical_id": "zhao_zilong",
                    "display_name": "赵子龙",
                    "aliases": ["Zhao"],
                    "key_traits": ["brave"],
                    "signature_outfit_or_props": ["silver armor"],
                }
            }
        )
    )
    story_plan.visual_style = {"palette": "ink"}
    story_plan.tone_and_mood = "epic"
    story_plan.additional_notes = {"music": "dramatic"}

    episode = EpisodePlan.create(
        sequence_index=0,
        title="Episode 1",
        target_duration_seconds=60,
        summary="Zhao returns to the battlefield",
        narrative_purpose="Set up the rescue",
    )
    episode.continuity_notes = {"previous": "retreat"}
    story_plan.add_episode(episode)

    project_state = ProjectState(
        project_id="pid",
        mode="project",
        story_plan=story_plan,
        global_settings={},
    )
    runtime = project_state.ensure_runtime_state(episode.episode_id)
    runtime.status = EpisodeStatus.APPROVED
    runtime.approved_script = "00:00-00:10 战况紧急，赵子龙回马。"

    project_state_repository.save(project_state)

    payload = EpisodeOrchestratorAgent._build_episode_payload(agent, episode, project_state, runtime_overrides={})

    prompt_text = payload["user_prompt"]
    assert "00:00-00:10" not in prompt_text
    ctx = payload.get("episode_context")
    assert ctx
    assert ctx["episode_index"] == 1
    assert ctx["episode_count"] == 1
    assert ctx["summary"] == "Zhao returns to the battlefield"
    assert ctx["approved_script"] == "00:00-00:10 战况紧急，赵子龙回马。"
    proj_ctx = payload.get("project_context")
    assert proj_ctx
    assert proj_ctx["global_theme"] == "Heroic loyalty"
    assert proj_ctx["project_brief"].startswith("Overall project brief")
    assert "zhao_zilong" in proj_ctx["character_bible"]
    assert ctx.get("character_ids") == ["zhao_zilong"]

    project_state_repository.remove("pid")
