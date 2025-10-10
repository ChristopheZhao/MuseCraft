"""Episode-level script drafting agent for project mode."""

from __future__ import annotations

import json
from typing import Any, Dict

from sqlalchemy.orm import Session

from .base import BaseAgent, AgentError
from ..models import Task, AgentExecution, AgentType


class EpisodeScriptPlannerAgent(BaseAgent):
    """Generate draft scripts for a single episode (~60s) using LLM."""

    def __init__(self, llms=None) -> None:
        super().__init__(
            agent_type=AgentType.EPISODE_SCRIPT_PLANNER,
            agent_name="episode_script_planner",
            timeout_seconds=120,
            max_retries=1,
            tools=[],
            llms=llms,
        )

    async def _execute_impl(
        self,
        task: Task,
        input_data: Dict[str, Any],
        execution: AgentExecution,
        db: Session,
    ) -> Dict[str, Any]:
        self._validate_input(
            input_data,
            [
                "project_id",
                "episode_index",
                "episode_title",
                "episode_summary",
                "target_duration_seconds",
                "user_prompt",
            ],
        )

        payload = await self._draft_episode_script(input_data)
        script_text = payload.get("script")
        if not script_text:
            raise AgentError("Episode script planner returned empty script")

        return {
            "script": script_text,
            "beats": payload.get("beats", []),
            "raw": payload,
        }

    async def _draft_episode_script(self, context: Dict[str, Any]) -> Dict[str, Any]:
        user_prompt = context["user_prompt"]
        episode_summary = context["episode_summary"] or context.get("episode_title", "")
        episode_title = context.get("episode_title", f"Episode {context['episode_index'] + 1}")
        narrative_purpose = context.get("narrative_purpose", "")
        target_duration = int(context.get("target_duration_seconds", 60))
        global_theme = context.get("global_theme", "")
        tone_and_mood = context.get("tone_and_mood", "")
        previous_summary = context.get("previous_episode_summary", "")

        messages = [
            {
                "role": "system",
                "content": (
                    "你是一名擅长短篇动画脚本创作的剧作家。"
                    "请基于给定的项目梗概与分集目标，生成一段约 60 秒的剧本草稿。"
                    "输出 JSON，对象结构固定为 {\"script\": string, \"beats\": [{\"title\": string, \"description\": string}] }。"
                    "剧本中建议包含 4~6 个镜头或节奏点，可标注大致时间范围，语言使用中文。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"项目总梗概：{user_prompt}\n"
                    f"全局主题：{global_theme or '未指定'}\n"
                    f"整体情绪基调：{tone_and_mood or '未指定'}\n"
                    f"本集编号：{context['episode_index'] + 1}\n"
                    f"本集标题：{episode_title}\n"
                    f"本集摘要：{episode_summary}\n"
                    f"剧情使命：{narrative_purpose or '未指定'}\n"
                    f"上一集简述：{previous_summary or '无'}\n"
                    f"目标时长：{target_duration} 秒。"
                    "\n请返回 JSON，字段含义如下：\n"
                    "- script: 多行文本，按时间顺序描述镜头与对白，标注核心事件或情绪。\n"
                    "- beats: 数组，列出每个节奏点的标题与简述。"
                ),
            },
        ]

        response = await self.llm_function_call(
            messages=messages,
            context_description="draft episode script",
            temperature=0.65,
            response_format={"type": "json_object"},
            max_tokens=2048,
            thinking={"type": "disabled"},
            request_timeout=90,
        )

        content = response.get("content") if isinstance(response, dict) else None
        if not content:
            raise AgentError("LLM返回空脚本内容")

        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            # 若解析失败，使用整体文本作为脚本
            data = {"script": content.strip(), "beats": []}

        script_text = str(data.get("script", "")).strip()
        if not script_text:
            # 回退：基于摘要生成简易草稿
            script_text = self._build_fallback_script(episode_title, episode_summary, target_duration)
            data["script"] = script_text

        beats = data.get("beats")
        if not isinstance(beats, list):
            data["beats"] = []

        return data

    def _build_fallback_script(self, title: str, summary: str, duration: int) -> str:
        minutes = max(1, duration // 60)
        return (
            f"【{title} 自动草稿】\n"
            f"00:00-00:{max(10, duration // 6):02d}：基于摘要展开：{summary}.\n"
            "00:10-00:30：角色推进冲突或挑战。\n"
            "00:30-00:50：情绪/动作高潮。\n"
            "00:50-01:00：收束，与下集埋伏笔。"
        )
