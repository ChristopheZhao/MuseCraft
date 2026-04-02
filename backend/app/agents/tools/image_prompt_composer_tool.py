"""Image Prompt Composer Tool - combine prompt, consistency assets, and generation."""
from __future__ import annotations

from collections import OrderedDict
from typing import Any, Dict, List, Tuple

from .base_tool import AsyncTool, ToolMetadata, ToolType, ToolInput, ToolError, ToolValidationError
from .ai_services.service_interfaces import get_vlm_capabilities
from . import image_prompt_normalization as prompt_norm
from ...services.scene_info_reference_service import (
    SceneInfoReferenceResolutionError,
    load_scene_info_payload,
)


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
                "image_purpose": {
                    "type": "string",
                    "description": "可选：图像用途提示（例如 scene_opening_anchor、action_keyframe、continuity_bridge、character_reference）",
                },
                "task_direction": {
                    "type": "string",
                    "description": "可选：图像方向提示（例如 avatar、full_body）",
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
        image_purpose = str(params.get("image_purpose") or "").strip()
        task_direction = str(params.get("task_direction") or "").strip()

        if scene_number is None or not scene_info_ref:
            raise ToolValidationError("scene_number and scene_info_ref are required", self.metadata.name)

        scene_info = self._load_scene_info(scene_info_ref)
        scene_entry = self._extract_scene_entry(scene_info, scene_number)
        if not scene_entry:
            raise ToolValidationError("scene_number not found in scene_info_ref", self.metadata.name)

        scene_data = self._build_scene_data(
            scene_entry,
            scene_number,
            image_purpose=image_purpose,
            task_direction=task_direction,
        )
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
        consistency_block, categories, locked_segments = self._build_consistency_block(
            assets,
            image_purpose=scene_data.get("image_purpose") or image_purpose,
            task_direction=scene_data.get("task_direction") or task_direction,
        )

        if consistency_block:
            prompt_text = self._merge_prompt_text_with_consistency(
                prompt_text,
                assets,
                image_purpose=scene_data.get("image_purpose") or image_purpose,
                task_direction=scene_data.get("task_direction") or task_direction,
            )

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
        if locked_segments:
            image_params["consistency_locks"] = locked_segments

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
        metadata["consistency_lock_count"] = len(locked_segments)
        metadata["consistency_source"] = "scene_info_ref"
        metadata["image_purpose"] = scene_data.get("image_purpose") or self._canonicalize_image_purpose(image_purpose)
        metadata["frame_thesis"] = scene_data.get("frame_thesis") or ""
        if scene_data.get("task_direction"):
            metadata["task_direction"] = scene_data.get("task_direction")

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
        try:
            return load_scene_info_payload(ref)
        except SceneInfoReferenceResolutionError as exc:
            raise ToolValidationError(str(exc), self.metadata.name) from exc

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

    def _build_scene_data(
        self,
        scene_entry: Dict[str, Any],
        scene_number: Any,
        *,
        image_purpose: str = "",
        task_direction: str = "",
    ) -> Dict[str, Any]:
        scene_data = dict(scene_entry or {})
        scene_data.setdefault("scene_number", scene_number)
        normalized_task_direction = str(
            task_direction
            or scene_data.get("task_direction")
            or scene_data.get("reference_view")
            or scene_data.get("reference_kind")
            or scene_data.get("reference_type")
            or ""
        ).strip()
        scene_data["image_purpose"] = prompt_norm.infer_image_purpose(
            scene_data,
            explicit_value=image_purpose or scene_data.get("image_purpose"),
            task_direction=normalized_task_direction.lower(),
        )
        scene_data["frame_thesis"] = str(
            scene_data.get("frame_thesis")
            or prompt_norm.select_frame_thesis(
                scene_data,
                image_purpose=scene_data["image_purpose"],
                fallback_title=(scene_data.get("title") or "单帧静态画面").strip(),
            )
        ).strip()
        if normalized_task_direction:
            scene_data["task_direction"] = normalized_task_direction

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

    @staticmethod
    def _canonicalize_image_purpose(value: Any, *, task_direction: str = "") -> str:
        return prompt_norm.canonicalize_image_purpose(value, task_direction=task_direction)

    def _compress_character_description(self, value: Any, *, max_len: int = 100) -> str:
        return prompt_norm.compress_character_description(
            value,
            segment_max_len=72,
            fallback_max_len=max_len,
            output_max_len=max_len,
        )

    def _build_consistency_block(
        self,
        assets: Any,
        *,
        image_purpose: Any = "",
        task_direction: Any = "",
    ) -> Tuple[str, List[str], List[str]]:
        sections, categories, locked_segments = self._build_consistency_sections(
            assets,
            image_purpose=image_purpose,
            task_direction=task_direction,
        )
        if not sections:
            return "", [], []

        ordered_lines: List[str] = []
        for entries in sections.values():
            ordered_lines.extend(f"- {entry}" for entry in entries if entry)
        if not ordered_lines:
            return "", [], []
        return "一致性要求：\n" + "\n".join(ordered_lines), categories, locked_segments

    def _build_consistency_sections(
        self,
        assets: Any,
        *,
        image_purpose: Any = "",
        task_direction: Any = "",
    ) -> Tuple[Dict[str, List[str]], List[str], List[str]]:
        if not isinstance(assets, dict):
            return {}, [], []

        purpose = self._canonicalize_image_purpose(image_purpose)
        categories: List[str] = []
        sections: "OrderedDict[str, List[str]]" = OrderedDict()
        locked_segments: List[str] = []
        focus_label = "参考方向" if purpose == "character_reference" else "画面焦点"
        character_label = "稳定特征" if purpose == "character_reference" else "主体锁定"

        style_line = self._format_style(assets.get("style") or {})
        if style_line:
            categories.append("global_style_lock")
            sections.setdefault("风格指导", []).append(f"全局画风锁定：{style_line}")
            locked_segments.append(style_line)

        character_line = self._format_characters(
            assets.get("characters") or {},
            image_purpose=purpose,
            task_direction=task_direction,
        )
        if character_line:
            categories.append("character_lock")
            sections.setdefault(character_label, []).append(f"角色锁定：{character_line}")
            locked_segments.append(character_line)

        environment_line = self._format_environment(
            assets.get("environment") or {},
            image_purpose=purpose,
        )
        if environment_line:
            categories.append("opening_anchor")
            sections.setdefault(focus_label, []).append(f"开场锚点：{environment_line}")
            locked_segments.append(environment_line)

        continuity_line = self._format_continuity(
            assets.get("continuity") or {},
            image_purpose=purpose,
        )
        if continuity_line:
            categories.append("local_continuity")
            sections.setdefault("连续性提示", []).append(f"局部连续性：{continuity_line}")
            locked_segments.append(continuity_line)

        if not sections:
            return {}, [], []

        normalized_sections: Dict[str, List[str]] = OrderedDict()
        for label, entries in sections.items():
            normalized_entries = self._dedupe_prompt_entries(entries)
            if normalized_entries:
                normalized_sections[label] = normalized_entries
        return normalized_sections, categories, locked_segments

    def _merge_prompt_text_with_consistency(
        self,
        prompt_text: str,
        assets: Any,
        *,
        image_purpose: Any = "",
        task_direction: Any = "",
    ) -> str:
        sections, _categories, _locked = self._build_consistency_sections(
            assets,
            image_purpose=image_purpose,
            task_direction=task_direction,
        )
        if not sections:
            return (prompt_text or "").strip()

        prompt_sections, render_requirements = self._parse_prompt_sections(prompt_text)
        if not prompt_sections:
            return (prompt_text or "").strip()

        merged_sections: "OrderedDict[str, List[str]]" = OrderedDict(
            (label, list(entries)) for label, entries in prompt_sections
        )
        root_label = next(iter(merged_sections.keys()), "单帧构图")
        preferred_order = [
            root_label,
            "画面焦点",
            "参考方向",
            "主体锁定",
            "稳定特征",
            "风格指导",
            "光线与氛围",
            "色彩提示",
            "关键细节",
            "连续性提示",
            "注意事项",
        ]

        for label, entries in sections.items():
            bucket = merged_sections.setdefault(label, [])
            for entry in entries:
                self._append_unique_entry(bucket, entry)
            if label not in preferred_order:
                preferred_order.append(label)

        ordered_labels = [label for label in preferred_order if label in merged_sections]
        for label in merged_sections.keys():
            if label not in ordered_labels:
                ordered_labels.append(label)

        return self._render_prompt_sections(
            [(label, merged_sections[label]) for label in ordered_labels],
            render_requirements=render_requirements,
        )

    def _format_style(self, style_assets: Dict[str, Any]) -> str:
        if not isinstance(style_assets, dict):
            return ""
        lock = style_assets.get("global_lock") or {}
        guidelines = style_assets.get("consistency_guidelines") or {}
        style_consistency = self._clip_text(
            lock.get("style_guidelines") or guidelines.get("style_consistency"),
            120,
        )

        design = (
            style_assets.get("intelligent_style_design")
            or style_assets.get("intelligent_style")
            or {}
        )
        headline = self._clip_text(
            lock.get("headline") or design.get("headline") or design.get("summary") or design.get("style_name"),
            100,
        )
        color_palette = self._join_items(lock.get("color_palette") or design.get("color_palette") or [], max_items=4)
        style_tags = self._join_items(lock.get("style_tags") or design.get("style_tags") or design.get("tags") or [], max_items=4)
        object_guidelines = self._clip_text(lock.get("object_guidelines"), 100)

        parts: List[str] = []
        if headline:
            parts.append(headline)
        if style_tags:
            parts.append(f"风格标签：{style_tags}")
        if color_palette:
            parts.append(f"主色：{color_palette}")
        if object_guidelines:
            parts.append(f"关键道具：{object_guidelines}")
        if style_consistency and not parts:
            parts.append(style_consistency)
        return "；".join([p for p in parts if p])

    def _format_characters(
        self,
        character_assets: Dict[str, Any],
        *,
        image_purpose: str,
        task_direction: Any = "",
    ) -> str:
        if not isinstance(character_assets, dict):
            return ""
        lock = character_assets.get("global_lock") or {}
        scene_cast = character_assets.get("scene_cast") or {}
        present = self._join_items(scene_cast.get("present") or character_assets.get("present") or [], max_items=4)
        descriptions_raw = scene_cast.get("descriptions") or character_assets.get("descriptions") or []
        descriptions_list: List[str] = []
        if isinstance(descriptions_raw, list):
            for item in descriptions_raw:
                normalized = self._compress_character_description(item, max_len=100)
                if not normalized:
                    continue
                if prompt_norm.contains_video_only_language(item) and normalized == str(item).strip():
                    continue
                descriptions_list.append(normalized)
        descriptions = self._join_items(descriptions_list, max_items=2, sep="；")
        stable_traits = self._join_items(lock.get("stable_traits") or [], max_items=6)

        guideline = ""
        if isinstance(lock.get("guidelines"), str) and lock.get("guidelines"):
            guideline = self._clip_text(lock.get("guidelines"), 120)
        elif isinstance(character_assets.get("guidelines"), str):
            guideline = self._clip_text(character_assets.get("guidelines"), 120)

        parts = []
        if image_purpose == "character_reference" and task_direction:
            parts.append(f"参考方向：{str(task_direction).strip()}")
        if present:
            parts.append(f"角色：{present}")
        if stable_traits:
            parts.append(f"稳定特征：{stable_traits}")
        if descriptions:
            parts.append(f"场景特征：{descriptions}")
        elif guideline:
            parts.append(guideline)
        return "；".join([p for p in parts if p])

    def _format_environment(self, environment_assets: Dict[str, Any], *, image_purpose: str) -> str:
        if not isinstance(environment_assets, dict):
            return ""
        if image_purpose == "character_reference":
            return ""
        opening_anchor = environment_assets.get("opening_anchor") or {}
        raw_opening_state = str(opening_anchor.get("opening_state") or "").strip()
        opening_state = prompt_norm.normalize_still_text(raw_opening_state, max_len=120)
        end_state = prompt_norm.normalize_still_text(
            opening_anchor.get("end_state") or environment_assets.get("end_state"),
            max_len=120,
        )
        visual = prompt_norm.normalize_still_text(
            opening_anchor.get("visual_description") or environment_assets.get("visual_description"),
            max_len=120,
        )
        guideline = prompt_norm.normalize_still_text(
            (environment_assets.get("global_lock") or {}).get("guidelines") or environment_assets.get("guidelines"),
            max_len=80,
        )

        parts: List[str] = []
        if opening_state and not prompt_norm.contains_high_risk_action_language(raw_opening_state):
            parts.append(f"开场状态：{opening_state}")
        elif end_state:
            parts.append(f"静态落点：{end_state}")
        elif visual:
            parts.append(f"场景主体：{visual}")
        if guideline and guideline not in parts:
            parts.append(f"环境基调：{guideline}")
        return "；".join([p for p in parts if p])

    def _format_objects(self, style_assets: Dict[str, Any]) -> str:
        if not isinstance(style_assets, dict):
            return ""
        guidelines = style_assets.get("consistency_guidelines") or {}
        return self._clip_text(guidelines.get("object_consistency"), 140)

    def _format_continuity(self, continuity_assets: Dict[str, Any], *, image_purpose: str) -> str:
        if not isinstance(continuity_assets, dict):
            return ""
        if image_purpose == "character_reference":
            return ""
        local = continuity_assets.get("local_continuity") or {}
        depends_on = local.get("depends_on_scene") if isinstance(local, dict) else continuity_assets.get("depends_on_scene")
        if isinstance(depends_on, int):
            notes = prompt_norm.normalize_still_text(local.get("transition_notes"), max_len=80) if isinstance(local, dict) else ""
            if notes:
                return f"承接场景{depends_on}：{notes}"
            return f"承接场景{depends_on}"
        return ""

    def _parse_prompt_sections(self, prompt_text: str) -> Tuple[List[Tuple[str, List[str]]], str]:
        sections: List[Tuple[str, List[str]]] = []
        current_label = ""
        current_entries: List[str] = []
        render_requirements = ""

        for raw_line in str(prompt_text or "").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("画面要求："):
                render_requirements = line[len("画面要求：") :].strip()
                continue
            if line.endswith("：") and not line.startswith("- "):
                if current_label:
                    sections.append((current_label, current_entries))
                current_label = line[:-1].strip()
                current_entries = []
                continue
            if not current_label:
                continue
            if line.startswith("- "):
                current_entries.append(line[2:].strip())
            else:
                current_entries.append(line)

        if current_label:
            sections.append((current_label, current_entries))
        return sections, render_requirements

    def _render_prompt_sections(
        self,
        sections: List[Tuple[str, List[str]]],
        *,
        render_requirements: str,
    ) -> str:
        lines: List[str] = []
        for index, (label, entries) in enumerate(sections):
            normalized_entries = self._dedupe_prompt_entries(entries)
            if not label or not normalized_entries:
                continue
            if lines:
                lines.append("")
            lines.append(f"{label}：")
            if index == 0:
                lines.extend(normalized_entries)
            else:
                lines.extend(f"- {entry}" for entry in normalized_entries)
        if render_requirements:
            if lines:
                lines.append("")
            lines.append(f"画面要求：{render_requirements}")
        return "\n".join(lines).strip()

    def _append_unique_entry(self, bucket: List[str], entry: str) -> None:
        normalized_entry = str(entry or "").strip()
        if not normalized_entry:
            return
        entry_core = self._entry_core(normalized_entry)
        for existing in bucket:
            existing_core = self._entry_core(existing)
            if (
                normalized_entry == existing
                or entry_core == existing_core
                or (entry_core and entry_core in existing_core)
                or (existing_core and existing_core in entry_core)
            ):
                return
        bucket.append(normalized_entry)

    def _dedupe_prompt_entries(self, entries: List[str]) -> List[str]:
        deduped: List[str] = []
        for entry in entries:
            self._append_unique_entry(deduped, entry)
        return deduped

    @staticmethod
    def _entry_core(entry: str) -> str:
        text = str(entry or "").strip()
        if "：" in text:
            text = text.split("：", 1)[1].strip()
        return text

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
