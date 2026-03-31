"""Video Prompt Composer Tool - combine prompt and consistency assets."""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .base_tool import AsyncTool, ToolMetadata, ToolType, ToolInput, ToolError, ToolValidationError
from . import video_prompt_normalization as prompt_norm


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

    @staticmethod
    def _extract_tool_payload(
        output: Any,
        *,
        tool_name: str,
        action: str,
        caller_tool: str,
    ) -> Dict[str, Any]:
        """Unwrap tool output and preserve failure diagnostics across wrapper layers."""
        if hasattr(output, "success"):
            success = bool(getattr(output, "success", False))
            if not success:
                err = str(getattr(output, "error", "") or "unknown error")
                meta = getattr(output, "metadata", {}) or {}
                error_type = meta.get("error_type") if isinstance(meta, dict) else None
                details_raw = meta.get("error_details_struct") if isinstance(meta, dict) else None
                details = details_raw if isinstance(details_raw, dict) else {}
                raise ToolError(
                    f"{tool_name}.{action} failed: {err}",
                    caller_tool,
                    error_code=error_type,
                    details=details,
                )
            payload = getattr(output, "result", None)
            if not isinstance(payload, dict):
                raise ToolError(f"{tool_name}.{action} returned empty payload", caller_tool)
            return payload

        if isinstance(output, dict):
            if output.get("success") is False:
                err = str(output.get("error") or "unknown error")
                meta = output.get("metadata") if isinstance(output.get("metadata"), dict) else {}
                error_type = meta.get("error_type") if isinstance(meta, dict) else None
                details_raw = meta.get("error_details_struct") if isinstance(meta, dict) else None
                details = details_raw if isinstance(details_raw, dict) else {}
                raise ToolError(
                    f"{tool_name}.{action} failed: {err}",
                    caller_tool,
                    error_code=error_type,
                    details=details,
                )
            if isinstance(output.get("result"), dict):
                return output["result"]
            return output

        raise ToolError(
            f"{tool_name}.{action} returned invalid output type: {type(output).__name__}",
            caller_tool,
        )

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
        builder_payload = self._extract_tool_payload(
            builder_res,
            tool_name="video_prompt_builder",
            action="build_prompt",
            caller_tool=self.metadata.name,
        )

        consistency_input = ToolInput(
            action="get_prompt_assets",
            parameters={"scene_number": scene_number, "scene_info_ref": scene_info_ref},
            context=tool_input.context or {},
            timeout=tool_input.timeout,
        )
        consistency_res = await consistency.execute(consistency_input)
        consistency_payload = self._extract_tool_payload(
            consistency_res,
            tool_name="consistency_tool",
            action="get_prompt_assets",
            caller_tool=self.metadata.name,
        )

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
            categories.append("global_style_lock")
            lines.append(f"- 全局画风锁定：{style_line}")

        character_line = self._format_characters(assets.get("characters") or {})
        if character_line:
            categories.append("character_lock")
            lines.append(f"- 角色锁定：{character_line}")

        environment_line = self._format_environment(assets.get("environment") or {})
        if environment_line:
            categories.append("opening_anchor")
            lines.append(f"- 开场锚点：{environment_line}")

        continuity_line = self._format_continuity(assets.get("continuity") or {})
        if continuity_line:
            categories.append("local_continuity")
            lines.append(f"- 局部连续性：{continuity_line}")

        if not lines:
            return "", []

        return "一致性要求：\n" + "\n".join(lines), categories

    def _format_style(self, style_assets: Dict[str, Any]) -> str:
        if not isinstance(style_assets, dict):
            return ""
        lock = style_assets.get("global_lock") or {}
        guidelines = style_assets.get("consistency_guidelines") or {}
        style_consistency = prompt_norm.compact_lock_text(
            lock.get("style_guidelines") or guidelines.get("style_consistency"),
            max_len=56,
            max_clauses=1,
        )

        design = (
            style_assets.get("intelligent_style_design")
            or style_assets.get("intelligent_style")
            or {}
        )
        headline = prompt_norm.compact_lock_text(
            lock.get("headline") or design.get("headline") or design.get("summary") or design.get("style_name"),
            max_len=40,
            max_clauses=1,
        )
        color_palette = self._join_items(lock.get("color_palette") or design.get("color_palette") or [], max_items=3)
        style_tags = self._join_items(lock.get("style_tags") or design.get("style_tags") or design.get("tags") or [], max_items=3)

        parts: List[str] = []
        if headline:
            parts.append(headline)
        if style_consistency and not any(prompt_norm.is_similar(style_consistency, part) for part in parts):
            parts.append(style_consistency)
        if style_tags and len(parts) < 3:
            parts.append(f"风格标签：{style_tags}")
        elif color_palette and len(parts) < 3:
            parts.append(f"色彩：{color_palette}")
        return "；".join([p for p in parts if p])

    def _format_characters(self, character_assets: Dict[str, Any]) -> str:
        if not isinstance(character_assets, dict):
            return ""
        lock = character_assets.get("global_lock") or {}
        scene_cast = character_assets.get("scene_cast") or {}
        present = self._join_items(scene_cast.get("present") or character_assets.get("present") or [], max_items=3)
        descriptions = self._compact_scene_descriptions(
            scene_cast.get("descriptions") or character_assets.get("descriptions") or []
        )
        stable_traits = self._join_items(lock.get("stable_traits") or [], max_items=3)

        guideline = ""
        if isinstance(lock.get("guidelines"), str) and lock.get("guidelines"):
            guideline = prompt_norm.compact_lock_text(lock.get("guidelines"), max_len=48, max_clauses=1)
        elif isinstance(character_assets.get("guidelines"), str):
            guideline = prompt_norm.compact_lock_text(character_assets.get("guidelines"), max_len=48, max_clauses=1)

        parts = []
        if present:
            parts.append(f"出现角色：{present}")
        if stable_traits and not any(prompt_norm.is_similar(stable_traits, part) for part in parts):
            parts.append(f"稳定特征：{stable_traits}")
        if descriptions:
            parts.append(f"场景特征：{descriptions}")
        if guideline and not parts:
            parts.append(guideline)
        return "；".join([p for p in parts if p])

    def _format_environment(self, environment_assets: Dict[str, Any]) -> str:
        if not isinstance(environment_assets, dict):
            return ""
        opening_anchor = environment_assets.get("opening_anchor") or {}
        global_lock = environment_assets.get("global_lock") or {}
        guideline = prompt_norm.compact_lock_text(
            global_lock.get("guidelines") or environment_assets.get("guidelines"),
            max_len=40,
            max_clauses=1,
        )
        opening_state = prompt_norm.compact_lock_text(
            opening_anchor.get("opening_state"),
            max_len=56,
            max_clauses=1,
        )
        visual = prompt_norm.compact_lock_text(
            opening_anchor.get("visual_description") or environment_assets.get("visual_description"),
            max_len=56,
            max_clauses=1,
        )

        parts: List[str] = []
        if opening_state:
            parts.append(f"开场状态：{opening_state}")
        elif visual:
            parts.append(visual)
        if guideline and not any(prompt_norm.is_similar(guideline, part) for part in parts):
            parts.append(f"环境基调：{guideline}")
        return "；".join([p for p in parts if p])

    def _format_objects(self, style_assets: Dict[str, Any]) -> str:
        if not isinstance(style_assets, dict):
            return ""
        guidelines = style_assets.get("consistency_guidelines") or {}
        return self._clip_text(guidelines.get("object_consistency"), 140)

    def _format_continuity(self, continuity_assets: Dict[str, Any]) -> str:
        if not isinstance(continuity_assets, dict):
            return ""
        local = continuity_assets.get("local_continuity") or {}
        depends_on = local.get("depends_on_scene") if isinstance(local, dict) else continuity_assets.get("depends_on_scene")
        if isinstance(depends_on, int):
            notes = prompt_norm.compact_lock_text(local.get("transition_notes"), max_len=48, max_clauses=1) if isinstance(local, dict) else ""
            if notes:
                return f"承接场景 {depends_on}；{notes}"
            return f"承接场景 {depends_on}"
        return ""

    def _compact_scene_descriptions(self, descriptions: Any) -> str:
        if isinstance(descriptions, str):
            descriptions = [descriptions]
        if not isinstance(descriptions, list):
            return ""

        metadata_markers = ("原型：", "物种：", "role:", "archetype", "species")
        ranked: List[tuple[int, int, str]] = []
        for raw in descriptions:
            text = str(raw or "").strip()
            if not text:
                continue
            segments = [
                segment.strip()
                for segment in text.replace("；", ";").split(";")
                if segment.strip() and not any(marker in segment for marker in metadata_markers)
            ]
            source_text = "；".join(segments) if segments else text
            compact = prompt_norm.compact_lock_text(text, max_len=40, max_clauses=2, drop_meta=True)
            if not compact or any(marker in compact for marker in metadata_markers):
                compact = prompt_norm.compact_lock_text(source_text, max_len=40, max_clauses=2, drop_meta=True)
            if not compact:
                continue
            separator_weight = text.count("；") + text.count(";") + text.count("：")
            ranked.append((separator_weight, len(text), compact))

        ranked.sort(key=lambda item: (item[0], item[1]))
        selected = prompt_norm.dedupe_clauses([item[2] for item in ranked])[:2]
        return "；".join(selected)

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
