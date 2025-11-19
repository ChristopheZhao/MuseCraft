"""
Video Prompt Builder Tool
负责将场景事实、一致性资产、连续性信息和创意意图组合为统一的视频生成提示词。

该工具保持供应商无关，返回标准字段：
- prompt_text
- positive_tokens / negative_tokens
- metadata（含 scene_number、是否引用一致性资产等）
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .base_tool import (
    AsyncTool,
    ToolMetadata,
    ToolType,
    ToolValidationError,
)


class VideoPromptBuilderTool(AsyncTool):
    """根据输入的场景事实与一致性资料生成视频提示词。"""

    @classmethod
    def get_metadata(cls) -> ToolMetadata:
        return ToolMetadata(
            name="video_prompt_builder",
            version="1.0.0",
            description="Compose video generation prompts from scene facts and consistency assets",
            tool_type=ToolType.UTILITY,
            author="system",
            tags=["prompt_builder", "video"],
            dependencies=[],
            capabilities=["prompt_synthesis"],
        )

    def __init__(self, **kwargs):
        kwargs.pop("metadata", None)
        super().__init__(metadata=self.get_metadata(), **kwargs)

    def _initialize(self):
        """Prompt 构建工具暂无额外初始化逻辑。"""
        return None

    def get_available_actions(self) -> List[str]:
        return ["build_prompt"]

    def get_fc_visibility(self) -> Dict[str, Any]:
        return {"expose": True, "allowed_actions": ["build_prompt"]}

    # 取消阶段语义：工具仅具有执行属性

    def get_action_schema(self, action: str) -> Dict[str, Any]:
        if action != "build_prompt":
            return {}
        return {
            "type": "object",
            "properties": {
                "scene_number": {
                    "type": ["integer", "string"],
                    "description": "目标场景编号（便于日志追踪）",
                },
                "scene_facts": {
                    "type": "object",
                    "description": "场景事实（visual_description、narrative_description、motion_beats 等）",
                },
                "style_assets": {
                    "type": ["object", "null"],
                    "description": "全局或场景级风格约束",
                },
                "character_assets": {
                    "type": ["object", "null"],
                    "description": "角色形象与特征约束",
                },
                "continuity_assets": {
                    "type": ["object", "null"],
                    "description": "连续性参考（上一场景尾帧、衔接说明等）",
                },
                "creative_intent": {
                    "type": ["string", "null"],
                    "description": "本场景的核心创意目标",
                },
                "negative_guidance": {
                    "type": ["array", "null"],
                    "items": {"type": "string"},
                    "description": "需要排除的画面或风格要素",
                },
            },
            "required": ["scene_facts"],
        }

    def _validate_action_parameters(self, action: str, parameters: Dict[str, Any]):
        if action != "build_prompt":
            return
        if not isinstance(parameters.get("scene_facts"), dict):
            raise ToolValidationError(
                "scene_facts 必须为对象，包含视觉与叙事描述",
                tool_name=self.metadata.name,
            )

    async def _execute_impl(self, tool_input):
        if tool_input.action != "build_prompt":
            raise ToolValidationError(
                f"Unsupported action '{tool_input.action}'",
                tool_name=self.metadata.name,
            )
        return self._build_prompt(tool_input.parameters or {})

    def _build_prompt(self, params: Dict[str, Any]) -> Dict[str, Any]:
        scene_number = params.get("scene_number")
        scene_facts = params.get("scene_facts") or {}
        style_assets = params.get("style_assets") or {}
        character_assets = params.get("character_assets") or {}
        continuity_assets = params.get("continuity_assets") or {}
        creative_intent = params.get("creative_intent") or ""
        negative_guidance = params.get("negative_guidance") or []

        lines: List[str] = []

        def _append(text: Optional[str]):
            if isinstance(text, str) and text.strip():
                lines.append(text.strip())

        header = f"场景 {scene_number}" if scene_number is not None else "目标场景"
        _append(f"{header}：")

        visual = scene_facts.get("visual_description") or scene_facts.get("description")
        if visual:
            _append(f"- 视觉重点：{visual}")

        narrative = scene_facts.get("narrative_description") or scene_facts.get("story")
        if narrative:
            _append(f"- 叙事要点：{narrative}")

        duration = scene_facts.get("duration")
        if duration:
            _append(f"- 目标时长：{duration}s")

        if creative_intent:
            _append(f"- 创作意图：{creative_intent}")

        motion_beats = scene_facts.get("motion_beats") or []
        if isinstance(motion_beats, list) and motion_beats:
            beats_preview = "; ".join(
                f"{beat.get('label','beat')}: {beat.get('description','')}"
                for beat in motion_beats
                if isinstance(beat, dict)
            )
            if beats_preview:
                _append(f"- 运动节奏：{beats_preview}")

        continuity_lines = self._format_continuity(continuity_assets)
        if continuity_lines:
            _append("连续性提示：\n" + "\n".join(continuity_lines))

        style_lines = self._format_style(style_assets)
        if style_lines:
            _append("风格指导：\n" + "\n".join(style_lines))

        character_lines = self._format_characters(character_assets)
        if character_lines:
            _append("角色一致性：\n" + "\n".join(character_lines))

        prompt_text = "\n".join(lines).strip()
        positive_tokens = self._collect_tokens(style_assets, "positive_tokens")
        if isinstance(negative_guidance, list) and negative_guidance:
            negative_tokens = [str(t).strip() for t in negative_guidance if str(t).strip()]
        else:
            negative_tokens = self._collect_tokens(style_assets, "negative_tokens")

        metadata = {
            "scene_number": scene_number,
            "has_continuity": bool(continuity_assets),
            "references": {
                "style_assets": bool(style_assets),
                "character_assets": bool(character_assets),
            },
        }

        return {
            "prompt_text": prompt_text,
            "positive_tokens": positive_tokens,
            "negative_tokens": negative_tokens,
            "metadata": metadata,
        }

    def _format_continuity(self, continuity_assets: Dict[str, Any]) -> List[str]:
        lines: List[str] = []
        if not isinstance(continuity_assets, dict):
            return lines
        previous_frame = continuity_assets.get("previous_frame_url") or continuity_assets.get("continuity_frame_url")
        if previous_frame:
            lines.append(f"- Use previous frame {previous_frame} as continuity reference")
        notes = continuity_assets.get("transition_notes")
        if isinstance(notes, str) and notes.strip():
            lines.append(f"- Transition notes: {notes.strip()}")
        motion_guidance = continuity_assets.get("motion_guidance") or {}
        if isinstance(motion_guidance, dict) and motion_guidance.get("scene_guidance"):
            summary = motion_guidance.get("scene_guidance")
            if isinstance(summary, dict):
                desc = summary.get("description") or summary.get("key_points")
                if isinstance(desc, str) and desc.strip():
                    lines.append(f"- Motion guidance: {desc.strip()}")
        return lines

    def _format_style(self, style_assets: Dict[str, Any]) -> List[str]:
        lines: List[str] = []
        if not isinstance(style_assets, dict):
            return lines
        design = style_assets.get("intelligent_style_design") or {}
        if isinstance(design, dict):
            headline = design.get("headline") or design.get("summary")
            if headline:
                lines.append(f"- Overall style: {headline}")
            palette = design.get("color_palette") or style_assets.get("color_palette")
            if palette:
                palette_text = ", ".join(str(color) for color in palette if str(color).strip())
                if palette_text:
                    lines.append(f"- Palette: {palette_text}")
            texture = design.get("texture") or design.get("rendering")
            if texture:
                lines.append(f"- Texture & rendering: {texture}")
        consistency_hints = style_assets.get("consistency_hints")
        if isinstance(consistency_hints, dict):
            for key in ("mood", "lighting"):
                value = consistency_hints.get(key)
                if isinstance(value, str) and value.strip():
                    lines.append(f"- {key.title()}: {value.strip()}")
        modifiers = style_assets.get("scene_modifiers")
        if isinstance(modifiers, dict):
            for key, value in modifiers.items():
                if isinstance(value, str) and value.strip():
                    lines.append(f"- {key.replace('_', ' ').title()}: {value.strip()}")
        return lines

    def _format_characters(self, character_assets: Dict[str, Any]) -> List[str]:
        lines: List[str] = []
        if not isinstance(character_assets, dict):
            return lines
        profiles = character_assets.get("characters") or character_assets.get("profiles") or []
        for profile in profiles:
            if not isinstance(profile, dict):
                continue
            name = profile.get("display_name") or profile.get("name")
            traits = self._string_list(profile.get("key_traits") or profile.get("personality_traits"))
            appearance = self._string_list(profile.get("appearance") or profile.get("visual_traits"))
            parts: List[str] = []
            if traits:
                parts.append("traits: " + ", ".join(traits))
            if appearance:
                parts.append("appearance: " + ", ".join(appearance))
            snippet = "; ".join(parts)
            if name and snippet:
                lines.append(f"- {name}: {snippet}")
            elif name:
                lines.append(f"- {name}")
            elif snippet:
                lines.append(f"- {snippet}")
        return lines

    def _collect_tokens(self, assets: Dict[str, Any], key: str) -> List[str]:
        tokens: List[str] = []
        if not isinstance(assets, dict):
            return tokens
        for section in assets.values():
            if isinstance(section, dict) and isinstance(section.get(key), list):
                tokens.extend([str(t).strip() for t in section[key] if str(t).strip()])
        # 去重保序
        return list(dict.fromkeys(tokens))

    @staticmethod
    def _string_list(value: Any) -> List[str]:
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return []
