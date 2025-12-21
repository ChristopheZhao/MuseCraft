import logging
import types

import pytest

from app.agents.episode_orchestrator import EpisodeOrchestratorAgent
from app.core.story_plan import (
    CharacterProfile,
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


@pytest.mark.asyncio
async def test_project_character_reference_images_generated_and_idempotent():
    agent = object.__new__(EpisodeOrchestratorAgent)
    agent.logger = logging.getLogger("test.episode_orchestrator")

    calls = {"image": 0, "upload": 0}

    class _StubTool:
        def __init__(self, kind: str):
            self._kind = kind

        async def execute(self, tool_input):
            action = tool_input.get("action")
            params = tool_input.get("parameters") or {}
            if self._kind == "image":
                calls["image"] += 1
                scene_number = str(params.get("scene_number") or "")
                ref_kind = scene_number.split(":")[-1] if ":" in scene_number else "unknown"
                return types.SimpleNamespace(
                    success=True,
                    result={
                        "image_url": f"https://example.com/{ref_kind}.png",
                        "generated_prompt": params.get("prompt") or "",
                    },
                    error=None,
                )
            if self._kind == "upload":
                calls["upload"] += 1
                destination_key = params.get("destination_key") or ""
                return types.SimpleNamespace(
                    success=True,
                    result={
                        "url": f"file:///{destination_key}",
                        "file_key": destination_key,
                        "local_path": f"/tmp/{destination_key}",
                        "storage_type": "local",
                    },
                    error=None,
                )
            return types.SimpleNamespace(success=False, result=None, error=f"unexpected {action}")

    class _StubRegistry:
        def get_tool(self, name: str):
            if name == "image_generation":
                return _StubTool("image")
            if name == "file_storage_tool":
                return _StubTool("upload")
            raise KeyError(name)

    agent.tool_registry = _StubRegistry()

    story_plan = StoryPlan(
        project_id="pid-charref",
        user_prompt="Project",
        target_duration_seconds=120,
        aspect_ratio="16:9",
    )
    profile = CharacterProfile(
        canonical_id="little_bunny",
        display_name="小兔子",
        description="一只活泼可爱的小兔子",
        personality_traits=["好奇", "热情"],
        visual_traits={"identity_tags": ["白色绒毛", "粉色耳朵"], "signature_props": ["红色小领结", "生日帽"]},
        reference_assets={"items": []},
    )
    project_state = ProjectState(
        project_id="pid-charref",
        mode="project",
        story_plan=story_plan,
        style_profile={"style_name": "森林童话幻想风"},
        character_bible={"little_bunny": profile},
    )
    project_state_repository.save(project_state)

    await EpisodeOrchestratorAgent._ensure_project_character_reference_images(
        agent,
        project_state,
        {"runtime_overrides": {"project_character_reference_images_enabled": True}},
    )

    assets = project_state.character_bible["little_bunny"].reference_assets
    assert assets["avatar"]["url"].endswith("/avatar.png")
    assert assets["full_body"]["url"].endswith("/full_body.png")
    assert project_state.story_plan.character_bible is project_state.character_bible

    call_count = dict(calls)
    await EpisodeOrchestratorAgent._ensure_project_character_reference_images(
        agent,
        project_state,
        {"project_character_reference_images_enabled": True},
    )
    assert calls == call_count

    project_state_repository.remove("pid-charref")
