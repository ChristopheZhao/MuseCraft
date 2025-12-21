"""SeriesPlannerAgent orchestrates story planning for multi-episode projects."""

from __future__ import annotations

import math
import json
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from .base import BaseAgent, AgentError
from ..models import Task, AgentType
from ..core.story_plan import (
    CharacterProfile,
    EpisodePlan,
    EpisodeStatus,
    ProjectState,
    StoryPlan,
    normalize_character_bible,
    project_state_repository,
)
from ..services.memory_provider import MemoryServices, build_memory_services


class SeriesPlannerAgent(BaseAgent):
    """Generate an episode-level plan while keeping MAS internals untouched."""

    def __init__(self, llms=None, memory_services: Optional[MemoryServices] = None) -> None:
        super().__init__(
            agent_type=AgentType.SERIES_PLANNER,
            agent_name="series_planner",
            timeout_seconds=180,
            max_retries=1,
            tools=[],
            llms=llms,
            memory_services=memory_services or build_memory_services(),
        )

    async def _execute_impl(
        self,
        task: Task,
        input_data: Dict[str, Any],
        db: Session,
    ) -> Dict[str, Any]:
        self._validate_input(input_data, ["project_id", "user_prompt", "target_duration_seconds"])

        project_id = input_data["project_id"]
        user_prompt = input_data["user_prompt"]
        target_duration = max(60, int(input_data["target_duration_seconds"]))
        aspect_ratio = input_data.get("aspect_ratio", "16:9")
        mode = input_data.get("mode", "project")
        per_episode_cap = int(input_data.get("episode_cap_seconds", 60)) or 60
        min_episode_duration = int(input_data.get("episode_min_seconds", 45)) or 45

        episodes_count = max(1, math.ceil(target_duration / per_episode_cap))
        planned_episode_duration = max(min_episode_duration, min(per_episode_cap, target_duration // episodes_count))

        story_plan = StoryPlan(
            project_id=project_id,
            user_prompt=user_prompt,
            target_duration_seconds=target_duration,
            aspect_ratio=aspect_ratio,
        )

        outline = await self._generate_episode_outline(
            user_prompt=user_prompt,
            episodes_count=episodes_count,
            per_episode_duration=planned_episode_duration,
            total_duration=target_duration,
        )

        remainder = target_duration
        for index in range(episodes_count):
            target_for_episode = planned_episode_duration
            if index == episodes_count - 1:
                target_for_episode = remainder
            remainder = max(0, remainder - target_for_episode)

            outline_entry = outline["episodes"][index] if outline.get("episodes", []) else {}
            episode = EpisodePlan.create(
                sequence_index=index,
                title=outline_entry.get("title") or f"Episode {index + 1}",
                target_duration_seconds=target_for_episode,
                summary=outline_entry.get("summary") or outline_entry.get("synopsis") or f"Episode {index + 1}",
                narrative_purpose=outline_entry.get("narrative_purpose") or outline_entry.get("goal") or "",
            )
            episode.continuity_notes = outline_entry.get("continuity_notes", {}) or {}
            episode.required_assets = outline_entry.get("required_assets", {}) or {}
            story_plan.add_episode(episode)

        story_plan.global_theme = input_data.get("global_theme", "")
        story_plan.merge_character_profiles(
            normalize_character_bible(input_data.get("character_bible"))
        )
        if input_data.get("visual_style"):
            story_plan.visual_style.update(input_data.get("visual_style") or {})
        story_plan.tone_and_mood = input_data.get("tone_and_mood", "")
        story_plan.additional_notes.update(input_data.get("additional_notes", {}) or {})

        story_plan.global_theme = outline.get("global_theme", story_plan.global_theme)
        story_plan.tone_and_mood = outline.get("tone_and_mood", story_plan.tone_and_mood)
        if isinstance(outline.get("additional_notes"), dict):
            story_plan.additional_notes.update(outline["additional_notes"])

        derived_characters, derived_style = await self._derive_character_bible(
            user_prompt=user_prompt,
            episodes=story_plan.episodes,
            outline=outline,
            existing=story_plan.character_bible,
        )
        story_plan.merge_character_profiles(derived_characters)
        if derived_style:
            merged_style = dict(derived_style)
            merged_style.update(story_plan.visual_style or {})
            story_plan.visual_style = merged_style

        existing_state = project_state_repository.get(project_id)
        existing_settings = {}
        if existing_state and isinstance(getattr(existing_state, "global_settings", None), dict):
            existing_settings = dict(existing_state.global_settings)

        project_state = ProjectState(
            project_id=project_id,
            mode=mode,
            story_plan=story_plan,
            style_profile=dict(story_plan.visual_style or {}),
            character_bible=dict(story_plan.character_bible or {}),
            global_settings={
                "resolution": input_data.get("resolution"),
                "style_preference": input_data.get("style_preference"),
            },
            cost_budget=input_data.get("cost_budget"),
        )
        if existing_settings:
            merged_settings = dict(existing_settings)
            merged_settings.update(project_state.global_settings or {})
            project_state.global_settings = merged_settings

        for episode in story_plan.episodes:
            runtime = project_state.ensure_runtime_state(episode.episode_id)
            if runtime.status == EpisodeStatus.DRAFT:
                runtime.status = EpisodeStatus.PENDING_APPROVAL
            episode.status = runtime.status

        if input_data.get("auto_generate_scripts", True):
            await self._populate_episode_scripts(
                project_state=project_state,
                user_prompt=user_prompt,
            )

        project_state_repository.save(project_state)

        return {
            "project_id": project_id,
            "story_plan": story_plan.to_dict(),
        }

    async def _populate_episode_scripts(self, project_state: ProjectState, user_prompt: str) -> None:
        story_plan = project_state.story_plan
        episodes = story_plan.episodes
        if not episodes:
            return

        previous_summary = ""

        for episode in episodes:
            try:
                payload = {
                    "project_id": project_state.project_id,
                    "episode_index": episode.sequence_index,
                    "episode_title": episode.title,
                    "episode_summary": episode.summary,
                    "narrative_purpose": episode.narrative_purpose,
                    "target_duration_seconds": episode.target_duration_seconds,
                    "user_prompt": user_prompt,
                    "global_theme": story_plan.global_theme,
                    "tone_and_mood": story_plan.tone_and_mood,
                    "previous_episode_summary": previous_summary,
                }
                script_payload = await self._draft_episode_script(payload)
                episode.script_draft = script_payload.get("script", episode.summary)
            except Exception as exc:  # noqa: BLE001
                self.logger.warning(
                    "Episode script draft failed for episode %s: %s",
                    episode.sequence_index + 1,
                    exc,
                )
                episode.script_draft = self._fallback_script(episode)

            previous_summary = episode.summary or previous_summary

    async def _draft_episode_script(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        messages = [
            {
                "role": "system",
                "content": (
                    "你是一位擅长 60 秒动画短片的编剧。"
                    "请根据给定的项目背景与分集目标，输出 JSON：{\"script\": string, \"beats\": [{\"title\": string, \"description\": string}] }"
                    "脚本需使用中文，包含时间或镜头提示，节奏紧凑，结尾可铺垫下一集。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"项目梗概：{payload['user_prompt']}\n"
                    f"主题：{payload.get('global_theme') or '未指定'}\n"
                    f"情绪基调：{payload.get('tone_and_mood') or '未指定'}\n"
                    f"当前集数：{payload['episode_index'] + 1}\n"
                    f"标题：{payload.get('episode_title')}\n"
                    f"摘要：{payload.get('episode_summary')}\n"
                    f"剧情使命：{payload.get('narrative_purpose') or '未指定'}\n"
                    f"上一集概览：{payload.get('previous_episode_summary') or '无'}\n"
                    f"目标时长：{payload['target_duration_seconds']} 秒。\n"
                    "请直接返回 JSON，不要额外解释。"
                ),
            },
        ]

        response = await self.llm_function_call(
            messages=messages,
            context_description="episode script drafting",
            temperature=0.6,
            response_format={"type": "json_object"},
            thinking={"type": "disabled"},
            request_timeout=90,
        )

        content = response.get("content") if isinstance(response, dict) else None
        if not content:
            raise AgentError("episode script draft returned empty content")

        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            data = {"script": content.strip(), "beats": []}

        script_text = str(data.get("script", "")).strip()
        if not script_text:
            data["script"] = self._fallback_script(None, payload)

        beats = data.get("beats")
        if not isinstance(beats, list):
            data["beats"] = []
        return data

    async def _derive_character_bible(
        self,
        *,
        user_prompt: str,
        episodes: List[EpisodePlan],
        outline: Dict[str, Any],
        existing: Dict[str, CharacterProfile],
    ) -> tuple[Dict[str, CharacterProfile], Dict[str, Any]]:
        """Ask LLM for canonical character bible and style alignment."""

        if not episodes:
            return {}, {}

        episode_summaries: List[str] = []
        for episode in episodes:
            lines = [
                f"第 {episode.sequence_index + 1} 集《{episode.title or '未命名'}》",
                f"摘要：{episode.summary or '无'}",
            ]
            if episode.narrative_purpose:
                lines.append(f"剧情使命：{episode.narrative_purpose}")
            if episode.continuity_notes:
                lines.append(f"衔接提示：{json.dumps(episode.continuity_notes, ensure_ascii=False)}")
            episode_summaries.append("\n".join(lines))

        known_characters = []
        for profile in existing.values():
            snippet = {
                "canonical_id": profile.canonical_id,
                "display_name": profile.display_name,
                "description": profile.description,
                "narrative_role": profile.narrative_role,
                "visual_traits": profile.visual_traits,
            }
            known_characters.append(snippet)

        outline_notes = outline.get("additional_notes") if isinstance(outline, dict) else {}

        system_prompt = (
            "你是一名长篇动画项目的角色设定统筹，需要根据项目梗概与分集提要梳理角色手册。"
            "请仅返回 JSON 对象，包含："
            "characters (数组，每项含 canonical_id 可选、display_name、description、narrative_role、aliases、personality_traits、visual_traits、style_preferences、voice_profile、reference_assets)、"
            "style_preferences (对象，可为空)。"
        )

        user_payload = {
            "project_brief": user_prompt,
            "episodes": episode_summaries,
            "known_characters": known_characters,
            "additional_notes": outline_notes,
        }

        try:
            response = await self.llm_function_call(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": json.dumps(user_payload, ensure_ascii=False),
                    },
                ],
                context_description="project character bible planning",
                temperature=0.4,
                response_format={"type": "json_object"},
                thinking={"type": "disabled"},
                request_timeout=90,
            )
            content = response.get("content") if isinstance(response, dict) else None
            data = json.loads(content) if content else {}
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("Character bible derivation failed: %s", exc)
            return {}, {}

        characters_raw = data.get("characters") if isinstance(data, dict) else []
        style_preferences = data.get("style_preferences") if isinstance(data, dict) else {}

        characters = normalize_character_bible(characters_raw)

        return characters, style_preferences if isinstance(style_preferences, dict) else {}

    async def _generate_episode_outline(
        self,
        user_prompt: str,
        episodes_count: int,
        per_episode_duration: int,
        total_duration: int,
    ) -> Dict[str, Any]:
        messages = [
            {
                "role": "system",
                "content": (
                    "你是一名剧本统筹，需要将整体梗概拆分为多集结构。"
                    "请返回 JSON：{\"global_theme\": string, \"tone_and_mood\": string, \"episodes\": [{\"title\", \"summary\", \"narrative_purpose\", \"continuity_notes\", \"required_assets\"}], \"additional_notes\": object }"
                    "每集给出具体剧情摘要和叙事使命，确保多集衔接自然。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"项目梗概：{user_prompt}\n"
                    f"需要拆分的集数：{episodes_count} 集，每集约 {per_episode_duration} 秒，总时长 {total_duration} 秒。\n"
                    "请聚焦人物关系、情节冲突与悬念设置。"
                ),
            },
        ]

        try:
            response = await self.llm_function_call(
                messages=messages,
                context_description="episode outline planning",
                temperature=0.6,
                response_format={"type": "json_object"},
                thinking={"type": "disabled"},
                request_timeout=90,
            )
            content = response.get("content") if isinstance(response, dict) else None
            data = json.loads(content) if content else {}
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("Episode outline generation failed: %s", exc)
            data = {}

        episodes_data = data.get("episodes")
        normalized: List[Dict[str, Any]] = []
        if isinstance(episodes_data, list):
            for entry in episodes_data[:episodes_count]:
                if not isinstance(entry, dict):
                    entry = {"summary": str(entry)}
                normalized.append(self._normalize_outline_entry(entry))
        while len(normalized) < episodes_count:
            normalized.append(self._normalize_outline_entry({}))
        data["episodes"] = normalized
        return data

    def _fallback_script(
        self,
        episode: EpisodePlan | None,
        payload: Dict[str, Any] | None = None,
    ) -> str:
        title = "Episode"
        summary = ""
        duration = 60
        if episode:
            title = episode.title or title
            summary = episode.summary or summary
            duration = int(episode.target_duration_seconds or duration)
        elif payload:
            title = payload.get("episode_title", title)
            summary = payload.get("episode_summary", summary)
            duration = int(payload.get("target_duration_seconds", duration))

        segment = max(10, duration // 6)
        return (
            f"【{title} 草稿】\n"
            f"00:00-00:{segment:02d}：设定场景，引出核心冲突（依据摘要：{summary or '待补充'}）。\n"
            f"00:{segment:02d}-00:{2*segment:02d}：角色推动剧情或遭遇阻碍。\n"
            f"00:{2*segment:02d}-00:{4*segment:02d}：冲突升级或情绪高潮。\n"
            f"00:{4*segment:02d}-01:00：暂时解决并埋下下一集悬念。"
        )

    def _normalize_outline_entry(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        notes = entry.get("continuity_notes")
        if isinstance(notes, list):
            entry["continuity_notes"] = {"items": notes}
        elif isinstance(notes, str):
            entry["continuity_notes"] = {"note": notes}
        elif not isinstance(notes, dict) or notes is None:
            entry["continuity_notes"] = {}

        assets = entry.get("required_assets")
        if isinstance(assets, list):
            entry["required_assets"] = {"items": assets}
        elif isinstance(assets, str):
            entry["required_assets"] = {"note": assets}
        elif not isinstance(assets, dict) or assets is None:
            entry["required_assets"] = {}

        return entry
