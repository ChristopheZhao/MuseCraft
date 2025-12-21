"""
Video Prompt Builder Tool
根据场景信息引用与场景编号，组合提示词要素生成视频提示词。

该工具保持供应商无关，返回标准字段：
- prompt_text
- positive_tokens / negative_tokens
- metadata（含 scene_number、是否引用一致性资产等）
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from .base_tool import (
    AsyncTool,
    ToolMetadata,
    ToolType,
    ToolValidationError,
)


class VideoPromptBuilderTool(AsyncTool):
    """根据场景信息引用与场景编号生成视频提示词。"""

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
                "scene_info_ref": {
                    "type": "string",
                    "description": "场景信息引用（本地 JSON 路径或可访问的引用）",
                },
            },
            "required": ["scene_number", "scene_info_ref"],
        }

    def _validate_action_parameters(self, action: str, parameters: Dict[str, Any]):
        if action != "build_prompt":
            return
        if parameters.get("scene_number") is None:
            raise ToolValidationError(
                "scene_number 不能为空",
                tool_name=self.metadata.name,
            )
        if not isinstance(parameters.get("scene_info_ref"), str) or not parameters.get("scene_info_ref"):
            raise ToolValidationError(
                "scene_info_ref 必须为非空字符串",
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
        scene_info_ref = params.get("scene_info_ref") or ""
        scene_info = self._load_scene_info(scene_info_ref)
        scene_facts = self._extract_scene_facts(scene_info, scene_number)
        style_assets = self._extract_style_assets(scene_info)
        character_assets = self._extract_character_assets(scene_info)
        continuity_assets = self._extract_continuity_assets(scene_info, scene_number)
        creative_intent = ""
        negative_guidance: List[str] = []

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

    def _load_scene_info(self, ref: str) -> Dict[str, Any]:
        if not isinstance(ref, str) or not ref.strip():
            raise ToolValidationError(
                "scene_info_ref 为空或无效",
                tool_name=self.metadata.name,
            )
        path = ref.strip()
        if path.startswith("file://"):
            path = path[len("file://"):]
        if not os.path.exists(path):
            raise ToolValidationError(
                f"scene_info_ref 不存在: {path}",
                tool_name=self.metadata.name,
            )
        try:
            with open(path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
        except Exception as exc:
            raise ToolValidationError(
                f"scene_info_ref 解析失败: {exc}",
                tool_name=self.metadata.name,
            ) from exc
        if not isinstance(payload, dict):
            raise ToolValidationError(
                "scene_info_ref 必须指向 JSON 对象",
                tool_name=self.metadata.name,
            )
        return payload

    def _extract_scene_facts(self, static_context: Dict[str, Any], scene_number: Any) -> Dict[str, Any]:
        sn = self._coerce_int(scene_number)
        if sn is None:
            return {}
        scenes = static_context.get("scenes_to_generate") or []
        if isinstance(scenes, list):
            for scene in scenes:
                if not isinstance(scene, dict):
                    continue
                if self._coerce_int(scene.get("scene_number")) == sn:
                    return scene
        overview = static_context.get("scene_overview") or {}
        if isinstance(overview, dict):
            for scene in overview.get("scenes") or []:
                if not isinstance(scene, dict):
                    continue
                if self._coerce_int(scene.get("scene_number")) == sn:
                    return scene
        return {}

    def _extract_style_assets(self, static_context: Dict[str, Any]) -> Dict[str, Any]:
        style_assets: Dict[str, Any] = {}
        intelligent_style = static_context.get("intelligent_style") or {}
        if intelligent_style:
            style_assets["intelligent_style_design"] = intelligent_style
        concept_plan = static_context.get("concept_plan") or {}
        if isinstance(concept_plan, dict):
            consistency_hints = concept_plan.get("consistency_hints")
            if isinstance(consistency_hints, dict):
                style_assets["consistency_hints"] = consistency_hints
        return style_assets

    def _extract_character_assets(self, static_context: Dict[str, Any]) -> Dict[str, Any]:
        roles_ctx = static_context.get("roles_context") or {}
        if isinstance(roles_ctx, dict) and roles_ctx.get("roles"):
            return {"characters": roles_ctx.get("roles")}
        concept_plan = static_context.get("concept_plan") or {}
        if isinstance(concept_plan, dict) and concept_plan.get("roles"):
            return {"characters": concept_plan.get("roles")}
        return {}

    def _extract_continuity_assets(self, static_context: Dict[str, Any], scene_number: Any) -> Dict[str, Any]:
        sn = self._coerce_int(scene_number)
        if sn is None:
            return {}
        continuity_sources = static_context.get("continuity_sources") or {}
        if isinstance(continuity_sources, dict):
            candidate = continuity_sources.get(sn) or continuity_sources.get(str(sn)) or {}
            if isinstance(candidate, dict):
                return candidate
        return {}

    @staticmethod
    def _coerce_int(value: Any) -> Optional[int]:
        try:
            if value is None:
                return None
            return int(value)
        except Exception:
            return None

    def _format_continuity(self, continuity_assets: Dict[str, Any]) -> List[str]:
        lines: List[str] = []
        if not isinstance(continuity_assets, dict):
            return lines
        previous_frame = continuity_assets.get("previous_frame_url") or continuity_assets.get("continuity_frame_url")
        if previous_frame:
            lines.append(f"- Use previous frame {previous_frame} as continuity reference")
        previous_video = continuity_assets.get("previous_scene_video_url") or continuity_assets.get("previous_video_url")
        if previous_video:
            lines.append(f"- Previous scene video: {previous_video}")
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
