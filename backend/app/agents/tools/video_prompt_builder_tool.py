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
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base_tool import (
    AsyncTool,
    ToolMetadata,
    ToolType,
    ToolValidationError,
)
from . import video_prompt_normalization as prompt_norm


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
        creative_intent = self._clip_text(scene_facts.get("creative_intent"), 140)
        negative_guidance: List[str] = []

        lines: List[str] = []

        def _append(text: Optional[str]):
            if isinstance(text, str) and text.strip():
                lines.append(text.strip())

        header = f"场景 {scene_number}" if scene_number is not None else "目标场景"
        _append(f"{header}：")

        visual = scene_facts.get("visual_description") or scene_facts.get("description")
        narrative = self._clip_text(scene_facts.get("narrative_description") or scene_facts.get("story"), 180)
        if narrative:
            narrative = narrative.strip()

        duration = scene_facts.get("duration")
        if duration:
            _append(f"- 目标时长：{duration}s")

        prompt_mode = self._resolve_prompt_mode(scene_facts, continuity_assets)
        if prompt_mode == "continuity":
            _append("- 创作重点：延续上一场尾帧状态与动作趋势，不重新建立角色造型。")
        elif prompt_mode == "image_to_video":
            _append("- 创作重点：基于当前首帧向后推进动作，不重复静态复述整张首帧。")
        else:
            _append("- 创作重点：先建立角色与环境，再推进关键动作变化。")

        opening_state = self._resolve_opening_state(scene_facts, visual)
        if opening_state:
            _append(f"- 开场状态：{opening_state}")

        event_trigger = self._clip_text(scene_facts.get("event_trigger"), 160)
        if event_trigger:
            _append(f"- 触发动作：{event_trigger}")

        action_phases = self._normalize_action_phases(scene_facts)
        action_arc = self._format_action_arc(action_phases)
        if action_arc:
            _append(f"- 动作推进：{action_arc}")

        camera_language = self._clip_text(
            scene_facts.get("camera_language") or scene_facts.get("camera_angle"),
            140,
        )
        if camera_language:
            _append(f"- 镜头语言：{camera_language}")
        else:
            phase_camera = self._format_phase_camera_hints(action_phases)
            if phase_camera:
                _append(f"- 镜头语言：{phase_camera}")

        end_state = self._clip_text(scene_facts.get("end_state"), 160)
        if not end_state:
            end_state = self._infer_end_state(action_phases)
        if end_state:
            _append(f"- 收束画面：{end_state}")

        script_text = prompt_norm.compact_story_detail(
            scene_facts.get("script_text"),
            action_text=action_arc,
            max_len=90,
        )
        if script_text:
            _append(f"- 剧情细节：{script_text}")
        else:
            narrative_detail = prompt_norm.compact_story_detail(
                narrative,
                action_text=action_arc,
                max_len=90,
            )
            if narrative_detail:
                _append(f"- 剧情细节：{narrative_detail}")

        mood = self._clip_text(scene_facts.get("mood_and_atmosphere"), 120)
        if mood:
            _append(f"- 氛围控制：{mood}")

        if creative_intent:
            _append(f"- 创作意图：{creative_intent}")

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
            "prompt_mode": prompt_mode,
            "action_phase_count": len(action_phases),
            "action_source": self._detect_action_source(scene_facts),
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
        candidate_paths = []
        try:
            candidate = Path(path)
        except Exception as exc:
            raise ToolValidationError(
                f"scene_info_ref 路径解析失败: {exc}",
                tool_name=self.metadata.name,
            ) from exc
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
            raise ToolValidationError(
                f"scene_info_ref 不存在: {path}",
                tool_name=self.metadata.name,
            )
        try:
            with open(resolved_path, "r", encoding="utf-8") as fh:
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

    def _resolve_prompt_mode(self, scene_facts: Dict[str, Any], continuity_assets: Dict[str, Any]) -> str:
        if isinstance(continuity_assets, dict) and continuity_assets:
            return "continuity"
        image_url = scene_facts.get("image_url") if isinstance(scene_facts, dict) else ""
        if isinstance(image_url, str) and image_url.strip():
            return "image_to_video"
        return "text_to_video"

    def _resolve_opening_state(self, scene_facts: Dict[str, Any], visual: str) -> str:
        if isinstance(scene_facts.get("opening_state"), str) and scene_facts.get("opening_state").strip():
            return self._clip_text(scene_facts.get("opening_state"), 160)
        return prompt_norm.compact_lock_text(visual, max_len=120, max_clauses=2)

    def _normalize_action_phases(self, scene_facts: Dict[str, Any]) -> List[Dict[str, Any]]:
        phases = scene_facts.get("action_phases") or []
        normalized: List[Dict[str, Any]] = []
        if isinstance(phases, list) and phases:
            for idx, raw in enumerate(phases):
                if not isinstance(raw, dict):
                    continue
                normalized.append(
                    {
                        "index": idx + 1,
                        "phase": str(raw.get("phase") or raw.get("label") or "").strip(),
                        "observable_actions": str(
                            raw.get("observable_actions")
                            or raw.get("action")
                            or raw.get("description")
                            or raw.get("beat_summary")
                            or ""
                        ).strip(),
                        "camera_hint": str(
                            raw.get("camera_hint")
                            or raw.get("camera")
                            or raw.get("shot")
                            or ""
                        ).strip(),
                    }
                )
            if normalized:
                return normalized

        motion_beats = scene_facts.get("motion_beats") or []
        if isinstance(motion_beats, list):
            for idx, raw in enumerate(motion_beats):
                if not isinstance(raw, dict):
                    continue
                visual_focus = str(raw.get("visual_focus") or raw.get("focus") or "").strip()
                beat_summary = str(
                    raw.get("beat_summary")
                    or raw.get("description")
                    or raw.get("action")
                    or ""
                ).strip()
                normalized.append(
                    {
                        "index": idx + 1,
                        "phase": visual_focus,
                        "observable_actions": beat_summary or visual_focus,
                        "camera_hint": str(raw.get("camera_hint") or "").strip(),
                    }
                )
        return normalized

    def _format_action_arc(self, action_phases: List[Dict[str, Any]]) -> str:
        if not isinstance(action_phases, list) or not action_phases:
            return ""
        lead_ins = ["先", "随后", "接着", "最后"]
        parts: List[str] = []
        for idx, phase in enumerate(action_phases[:4]):
            if not isinstance(phase, dict):
                continue
            phase_name, observable = prompt_norm.compact_action_pair(
                phase.get("phase"),
                phase.get("observable_actions"),
            )
            if not phase_name and not observable:
                continue
            lead_in = lead_ins[idx] if idx < len(lead_ins) else "随后"
            if observable and phase_name and phase_name not in observable:
                segment = f"{lead_in}{phase_name}，{observable}"
            else:
                segment = f"{lead_in}{observable or phase_name}"
            camera_hint = str(phase.get("camera_hint") or "").strip()
            if camera_hint:
                segment += f"，镜头{camera_hint}"
            parts.append(segment)
        return "；".join(parts)

    def _infer_end_state(self, action_phases: List[Dict[str, Any]]) -> str:
        if not isinstance(action_phases, list) or not action_phases:
            return ""
        for phase in reversed(action_phases):
            if not isinstance(phase, dict):
                continue
            phase_name, observable = prompt_norm.compact_action_pair(
                phase.get("phase"),
                phase.get("observable_actions"),
                phase_max_len=56,
                extra_max_len=56,
            )
            end_state = "，".join([part for part in (phase_name, observable) if part])
            if end_state:
                return self._clip_text(end_state, 100)
        return ""

    def _format_phase_camera_hints(self, action_phases: List[Dict[str, Any]]) -> str:
        hints: List[str] = []
        for phase in action_phases:
            if not isinstance(phase, dict):
                continue
            hint = str(phase.get("camera_hint") or "").strip()
            if hint and hint not in hints:
                hints.append(hint)
        return "；".join(hints[:3])

    def _detect_action_source(self, scene_facts: Dict[str, Any]) -> str:
        if isinstance(scene_facts.get("action_phases"), list) and scene_facts.get("action_phases"):
            return "action_phases"
        if isinstance(scene_facts.get("motion_beats"), list) and scene_facts.get("motion_beats"):
            return "motion_beats"
        return "summary_only"

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

    @staticmethod
    def _clip_text(text: Any, max_len: int) -> str:
        if not isinstance(text, str):
            return ""
        text = text.strip()
        if not text:
            return ""
        if len(text) <= max_len:
            return text
        if max_len <= 3:
            return text[:max_len]
        return text[: max_len - 3] + "..."
