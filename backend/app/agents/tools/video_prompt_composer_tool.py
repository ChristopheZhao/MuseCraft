"""Video Prompt Composer Tool - combine prompt and consistency assets."""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .base_tool import AsyncTool, ToolMetadata, ToolType, ToolInput, ToolError, ToolValidationError


class VideoPromptComposerTool(AsyncTool):
    """Composite tool to attach consistency assets to a base prompt."""

    @classmethod
    def get_metadata(cls) -> ToolMetadata:
        return ToolMetadata(
            name="video_prompt_composer",
            version="1.0.0",
            description="Compose video prompts with consistency assets in a single call",
            tool_type=ToolType.UTILITY,
            author="system",
            tags=["prompt_builder", "video", "consistency"],
            capabilities=["prompt_synthesis", "consistency_injection"],
        )

    def _initialize(self):
        return None

    def get_available_actions(self) -> List[str]:
        return ["build_prompt"]

    def get_fc_visibility(self) -> Dict[str, Any]:
        return {"expose": True, "allowed_actions": ["build_prompt"]}

    def get_action_schema(self, action: str) -> Dict[str, Any]:
        if action != "build_prompt":
            return {}
        return {
            "type": "object",
            "properties": {
                "scene_number": {
                    "type": ["integer", "string"],
                    "description": "目标场景编号（用于追踪）",
                },
                "scene_info_ref": {
                    "type": "string",
                    "description": "场景信息引用（本地 JSON 路径或可访问引用）",
                },
            },
            "required": ["scene_number", "scene_info_ref"],
        }

    def _validate_action_parameters(self, action: str, parameters: Dict[str, Any]):
        if action != "build_prompt":
            return
        if parameters.get("scene_number") is None:
            raise ToolValidationError("scene_number is required", self.metadata.name)
        if not isinstance(parameters.get("scene_info_ref"), str) or not parameters.get("scene_info_ref"):
            raise ToolValidationError("scene_info_ref must be a non-empty string", self.metadata.name)

    async def _execute_impl(self, tool_input: ToolInput) -> Any:
        if tool_input.action != "build_prompt":
            raise ToolValidationError(
                f"Unsupported action '{tool_input.action}'",
                self.metadata.name,
            )

        params = tool_input.parameters or {}
        scene_number = params.get("scene_number")
        scene_info_ref = params.get("scene_info_ref") or ""

        if scene_number is None or not scene_info_ref:
            raise ToolValidationError("scene_number and scene_info_ref are required", self.metadata.name)

        from .tool_registry import get_tool_registry

        registry = get_tool_registry()
        builder = registry.get_tool("video_prompt_builder")
        consistency = registry.get_tool("consistency_tool")

        builder_input = ToolInput(
            action="build_prompt",
            parameters={"scene_number": scene_number, "scene_info_ref": scene_info_ref},
            context=tool_input.context or {},
            timeout=tool_input.timeout,
        )
        builder_res = await builder.execute(builder_input)
        builder_payload = builder_res.result if hasattr(builder_res, "result") else builder_res
        if not isinstance(builder_payload, dict):
            raise ToolError("video_prompt_builder returned empty payload", self.metadata.name)

        consistency_input = ToolInput(
            action="get_prompt_assets",
            parameters={"scene_number": scene_number, "scene_info_ref": scene_info_ref},
            context=tool_input.context or {},
            timeout=tool_input.timeout,
        )
        consistency_res = await consistency.execute(consistency_input)
        consistency_payload = consistency_res.result if hasattr(consistency_res, "result") else consistency_res
        if not isinstance(consistency_payload, dict):
            raise ToolError("consistency_tool returned empty payload", self.metadata.name)

        assets = consistency_payload.get("assets") if isinstance(consistency_payload, dict) else {}
        prompt_text = builder_payload.get("prompt_text") or ""
        consistency_block, categories = self._build_consistency_block(assets)

        if consistency_block:
            prompt_text = prompt_text.rstrip()
            prompt_text = prompt_text + ("\n" if prompt_text else "") + consistency_block

        metadata = dict(builder_payload.get("metadata") or {})
        metadata["consistency_injected"] = bool(consistency_block)
        metadata["consistency_categories"] = categories
        metadata["consistency_source"] = "scene_info_ref"

        try:
            self.logger.info(
                "CONSISTENCY_INJECT scene=%s injected=%s categories=%s",
                scene_number,
                bool(consistency_block),
                categories,
            )
        except Exception:
            pass

        return {
            "prompt_text": prompt_text,
            "positive_tokens": builder_payload.get("positive_tokens") or [],
            "negative_tokens": builder_payload.get("negative_tokens") or [],
            "metadata": metadata,
        }

    def _build_consistency_block(self, assets: Any) -> Tuple[str, List[str]]:
        if not isinstance(assets, dict):
            return "", []

        categories: List[str] = []
        lines: List[str] = []

        style_line = self._format_style(assets.get("style") or {})
        if style_line:
            categories.append("style")
            lines.append(f"- 画风：{style_line}")

        character_line = self._format_characters(assets.get("characters") or {})
        if character_line:
            categories.append("characters")
            lines.append(f"- 角色：{character_line}")

        environment_line = self._format_environment(assets.get("environment") or {})
        if environment_line:
            categories.append("environment")
            lines.append(f"- 场景氛围：{environment_line}")

        object_line = self._format_objects(assets.get("style") or {})
        if object_line:
            categories.append("objects")
            lines.append(f"- 道具：{object_line}")

        continuity_line = self._format_continuity(assets.get("continuity") or {})
        if continuity_line:
            categories.append("continuity")
            lines.append(f"- 连续性：{continuity_line}")

        if not lines:
            return "", []

        return "一致性要求：\n" + "\n".join(lines), categories

    def _format_style(self, style_assets: Dict[str, Any]) -> str:
        if not isinstance(style_assets, dict):
            return ""
        guidelines = style_assets.get("consistency_guidelines") or {}
        style_consistency = self._clip_text(guidelines.get("style_consistency"), 160)

        design = (
            style_assets.get("intelligent_style_design")
            or style_assets.get("intelligent_style")
            or {}
        )
        headline = self._clip_text(design.get("headline") or design.get("summary") or design.get("style_name"), 120)
        color_palette = self._join_items(design.get("color_palette") or [], max_items=6)
        style_tags = self._join_items(design.get("style_tags") or design.get("tags") or [], max_items=6)

        parts: List[str] = []
        if style_consistency:
            parts.append(style_consistency)
        if headline and headline not in parts:
            parts.append(headline)
        if style_tags:
            parts.append(f"风格标签：{style_tags}")
        if color_palette:
            parts.append(f"色彩：{color_palette}")
        return "；".join([p for p in parts if p])

    def _format_characters(self, character_assets: Dict[str, Any]) -> str:
        if not isinstance(character_assets, dict):
            return ""
        present = self._join_items(character_assets.get("present") or [], max_items=6)
        descriptions = self._join_items(character_assets.get("descriptions") or [], max_items=4, sep="；")

        guideline = ""
        if isinstance(character_assets.get("guidelines"), str):
            guideline = self._clip_text(character_assets.get("guidelines"), 140)

        parts = []
        if guideline:
            parts.append(guideline)
        if present:
            parts.append(f"出现角色：{present}")
        if descriptions:
            parts.append(f"特征：{descriptions}")
        return "；".join([p for p in parts if p])

    def _format_environment(self, environment_assets: Dict[str, Any]) -> str:
        if not isinstance(environment_assets, dict):
            return ""
        guideline = self._clip_text(environment_assets.get("guidelines"), 140)
        visual = self._clip_text(environment_assets.get("visual_description"), 160)
        narrative = self._clip_text(environment_assets.get("narrative_description"), 120)

        parts: List[str] = []
        if guideline:
            parts.append(guideline)
        if visual:
            parts.append(visual)
        if narrative:
            parts.append(narrative)
        return "；".join([p for p in parts if p])

    def _format_objects(self, style_assets: Dict[str, Any]) -> str:
        if not isinstance(style_assets, dict):
            return ""
        guidelines = style_assets.get("consistency_guidelines") or {}
        return self._clip_text(guidelines.get("object_consistency"), 140)

    def _format_continuity(self, continuity_assets: Dict[str, Any]) -> str:
        if not isinstance(continuity_assets, dict):
            return ""
        depends_on = continuity_assets.get("depends_on_scene")
        if isinstance(depends_on, int):
            return f"承接场景 {depends_on}"
        return ""

    @staticmethod
    def _join_items(items: Any, *, max_items: int = 6, sep: str = "、") -> str:
        if isinstance(items, str):
            items = [items]
        if not isinstance(items, list):
            return ""
        cleaned = [str(item).strip() for item in items if str(item).strip()]
        if not cleaned:
            return ""
        return sep.join(cleaned[:max_items])

    @staticmethod
    def _clip_text(text: Any, max_len: int) -> str:
        if not isinstance(text, str):
            return ""
        text = text.strip()
        if not text:
            return ""
        if len(text) > max_len:
            if max_len <= 3:
                return text[:max_len]
            return text[: max_len - 3] + "..."
        return text
