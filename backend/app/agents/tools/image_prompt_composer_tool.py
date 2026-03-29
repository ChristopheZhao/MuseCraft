"""Image Prompt Composer Tool - combine prompt, consistency assets, and generation."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .base_tool import AsyncTool, ToolMetadata, ToolType, ToolInput, ToolError, ToolValidationError
from .ai_services.service_interfaces import get_vlm_capabilities


class ImagePromptComposerTool(AsyncTool):
    """Composite tool to compose an image prompt with consistency assets and generate."""

    @classmethod
    def get_metadata(cls) -> ToolMetadata:
        return ToolMetadata(
            name="image_prompt_composer",
            version="1.0.0",
            description="Compose image prompts with consistency assets and generate images",
            tool_type=ToolType.UTILITY,
            author="system",
            tags=["prompt_builder", "image", "consistency"],
            capabilities=["prompt_synthesis", "consistency_injection", "image_generation"],
        )

    def _initialize(self):
        return None

    def get_available_actions(self) -> List[str]:
        return ["generate"]

    def get_fc_visibility(self) -> Dict[str, Any]:
        return {"expose": True, "allowed_actions": ["generate"]}

    def get_action_schema(self, action: str) -> Dict[str, Any]:
        if action != "generate":
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
                "size": {
                    **self._build_size_schema_property(
                        "图像尺寸；若不提供则由底层图像生成工具按当前 provider 能力自动选择"
                    ),
                },
                "persist": {
                    "type": "boolean",
                    "description": "是否持久化到存储（若可用）",
                },
                "destination_key": {
                    "type": "string",
                    "description": "可选：持久化目标路径/键名",
                },
                "fallback_prompt": {
                    "type": "string",
                    "description": "可选：生成提示词为空时的备用提示词",
                },
            },
            "required": ["scene_number", "scene_info_ref"],
        }

    def _build_size_schema_property(self, description: str) -> Dict[str, Any]:
        prop: Dict[str, Any] = {
            "type": "string",
            "description": description,
        }
        try:
            caps = get_vlm_capabilities()
            size_cap = caps.size if caps else None
            if size_cap and size_cap.options:
                prop["enum"] = list(size_cap.options)
                notes: List[str] = []
                if size_cap.description_suffix:
                    notes.append(size_cap.description_suffix)
                if size_cap.note:
                    notes.append(size_cap.note)
                if notes:
                    prop["description"] = f"{description} {' '.join(notes)}"
        except Exception:
            pass
        return prop

    def _validate_action_parameters(self, action: str, parameters: Dict[str, Any]):
        if action != "generate":
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
        if tool_input.action != "generate":
            raise ToolValidationError(
                f"Unsupported action '{tool_input.action}'",
                self.metadata.name,
            )

        params = tool_input.parameters or {}
        scene_number = params.get("scene_number")
        scene_info_ref = params.get("scene_info_ref") or ""
        size = params.get("size")
        persist = True if "persist" not in params else bool(params.get("persist"))
        destination_key = (params.get("destination_key") or "").strip()
        fallback_prompt = params.get("fallback_prompt") or ""

        if scene_number is None or not scene_info_ref:
            raise ToolValidationError("scene_number and scene_info_ref are required", self.metadata.name)

        scene_info = self._load_scene_info(scene_info_ref)
        scene_entry = self._extract_scene_entry(scene_info, scene_number)
        if not scene_entry:
            raise ToolValidationError("scene_number not found in scene_info_ref", self.metadata.name)

        scene_data = self._build_scene_data(scene_entry, scene_number)
        style_guidance = self._build_style_guidance(scene_info)
        style_name = self._resolve_style_name(style_guidance)

        from .tool_registry import get_tool_registry

        registry = get_tool_registry()
        image_tool = registry.get_tool("image_generation")
        consistency = registry.get_tool("consistency_tool")

        try:
            prompt_text = await image_tool._create_image_prompt_from_scene(
                scene_data,
                style_name,
                style_guidance,
            )
        except Exception as exc:
            raise ToolError(f"compose prompt failed: {exc}", self.metadata.name) from exc
        prompt_text = (prompt_text or "").strip()
        if hasattr(image_tool, "_is_prompt_weak") and callable(getattr(image_tool, "_is_prompt_weak")):
            try:
                if image_tool._is_prompt_weak(prompt_text) and isinstance(fallback_prompt, str) and fallback_prompt.strip():
                    prompt_text = fallback_prompt.strip()
            except Exception:
                pass
        if not prompt_text and isinstance(fallback_prompt, str) and fallback_prompt.strip():
            prompt_text = fallback_prompt.strip()
        if not prompt_text:
            raise ToolError("composed prompt is empty", self.metadata.name)

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
        consistency_block, categories = self._build_consistency_block(assets)

        if consistency_block:
            prompt_text = prompt_text.rstrip()
            prompt_text = prompt_text + ("\n" if prompt_text else "") + consistency_block

        image_params: Dict[str, Any] = {
            "scene_number": scene_number,
            "prompt": prompt_text,
            "persist": persist,
        }
        if size:
            image_params["size"] = size
        if destination_key:
            image_params["destination_key"] = destination_key
        if style_name:
            image_params["style"] = style_name

        gen_input = ToolInput(
            action="generate_image",
            parameters=image_params,
            context=tool_input.context or {},
            timeout=tool_input.timeout,
        )
        gen_res = await image_tool.execute(gen_input)
        gen_payload = self._extract_tool_payload(
            gen_res,
            tool_name="image_generation",
            action="generate_image",
            caller_tool=self.metadata.name,
        )

        image_url = gen_payload.get("image_url") or ""
        if not image_url:
            raise ToolError("image_generation.generate_image returned no image_url", self.metadata.name)

        metadata = dict(gen_payload.get("metadata") or {})
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
            "image_url": image_url,
            "file_path": gen_payload.get("file_path") or gen_payload.get("local_path") or "",
            "prompt_text": gen_payload.get("generated_prompt") or prompt_text,
            "style": gen_payload.get("style") or style_name or "",
            "size": gen_payload.get("size") or "",
            "scene_number": scene_number,
            "prompt_safety": gen_payload.get("prompt_safety") or {},
            "metadata": metadata,
        }

    def _load_scene_info(self, ref: str) -> Dict[str, Any]:
        if not isinstance(ref, str) or not ref.strip():
            raise ToolValidationError("scene_info_ref is empty", self.metadata.name)
        path = ref.strip()
        if path.startswith("file://"):
            path = path[len("file://"):]
        candidate_paths: List[Path] = []
        try:
            candidate = Path(path)
        except Exception as exc:
            raise ToolValidationError(f"scene_info_ref parse failed: {exc}", self.metadata.name) from exc
        if candidate is not None:
            if candidate.is_absolute():
                candidate_paths.append(candidate)
            else:
                candidate_paths.append(candidate)
                try:
                    backend_root = Path(__file__).resolve().parents[3]
                    candidate_paths.append(backend_root / candidate)
                except Exception:
                    pass
        resolved_path = None
        for cand in candidate_paths:
            try:
                if cand and cand.exists():
                    resolved_path = cand
                    break
            except Exception:
                continue
        if resolved_path is None:
            raise ToolValidationError(f"scene_info_ref not found: {path}", self.metadata.name)
        try:
            payload = json.loads(resolved_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ToolValidationError(f"scene_info_ref load failed: {exc}", self.metadata.name) from exc
        if not isinstance(payload, dict):
            raise ToolValidationError("scene_info_ref must be a JSON object", self.metadata.name)
        return payload

    def _extract_scene_entry(self, scene_info: Dict[str, Any], scene_number: Any) -> Dict[str, Any]:
        sn = self._coerce_int(scene_number)
        if sn is None:
            return {}
        for source in (
            scene_info.get("scenes_to_generate") or [],
            (scene_info.get("scene_overview") or {}).get("scenes") or [],
            (scene_info.get("concept_plan") or {}).get("scenes") or [],
        ):
            if not isinstance(source, list):
                continue
            for scene in source:
                if not isinstance(scene, dict):
                    continue
                if self._coerce_int(scene.get("scene_number")) == sn:
                    return scene
        return {}

    def _build_scene_data(self, scene_entry: Dict[str, Any], scene_number: Any) -> Dict[str, Any]:
        scene_data = dict(scene_entry or {})
        scene_data.setdefault("scene_number", scene_number)

        visual_description = scene_data.get("visual_description") or scene_data.get("description") or ""
        narrative_description = scene_data.get("narrative_description") or scene_data.get("story") or ""
        scene_data["visual_description"] = str(visual_description) if visual_description is not None else ""
        scene_data["narrative_description"] = str(narrative_description) if narrative_description is not None else ""

        content_elements = scene_data.get("content_elements") or {}
        if isinstance(content_elements, dict):
            if not scene_data.get("characters_present") and content_elements.get("characters_present"):
                scene_data["characters_present"] = content_elements.get("characters_present")
            if not scene_data.get("props_and_objects") and content_elements.get("key_objects"):
                scene_data["props_and_objects"] = content_elements.get("key_objects")

        scene_data["characters_present"] = self._coerce_list(scene_data.get("characters_present"))
        scene_data["character_descriptions"] = self._coerce_list(scene_data.get("character_descriptions"))

        return scene_data

    def _build_style_guidance(self, scene_info: Dict[str, Any]) -> Dict[str, Any]:
        concept_plan = scene_info.get("concept_plan") or {}
        style_design = (
            scene_info.get("intelligent_style")
            or scene_info.get("intelligent_style_design")
            or (concept_plan.get("intelligent_style_design") if isinstance(concept_plan, dict) else {})
            or {}
        )
        style_guidance = dict(style_design) if isinstance(style_design, dict) else {}
        if "style_name" not in style_guidance:
            headline = style_guidance.get("headline") or style_guidance.get("summary")
            if isinstance(headline, str) and headline.strip():
                style_guidance["style_name"] = headline.strip()
        if "style_description" not in style_guidance:
            summary = style_guidance.get("summary") or style_guidance.get("headline")
            if isinstance(summary, str) and summary.strip():
                style_guidance["style_description"] = summary.strip()
        if style_guidance.get("style_name") and "art_style" not in style_guidance:
            style_guidance["art_style"] = style_guidance.get("style_name")
        if style_guidance.get("style_name") and "style" not in style_guidance:
            style_guidance["style"] = style_guidance.get("style_name")
        return style_guidance

    def _resolve_style_name(self, style_guidance: Dict[str, Any]) -> str:
        if not isinstance(style_guidance, dict):
            return ""
        for key in ("art_style", "style_name", "style", "name"):
            value = style_guidance.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

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

    @staticmethod
    def _coerce_int(value: Any) -> int | None:
        try:
            if value is None:
                return None
            return int(value)
        except Exception:
            return None

    @staticmethod
    def _coerce_list(value: Any) -> List[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []
