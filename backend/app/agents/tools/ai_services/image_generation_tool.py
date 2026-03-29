"""
Image Generation Tool - 封装图像生成业务逻辑
"""

import asyncio
import json
import os
import tempfile
from typing import Dict, Any, List, Optional

import httpx

from ....core.config import settings
from ....core.consistency_policy import get_consistency_policy

from ..base_tool import AsyncTool, ToolMetadata, ToolType, ToolError
from .service_interfaces import get_vlm_service, get_vlm_capabilities
from ...prompts.template_manager import get_template_manager
from ....services.prompt_safety import (
    sanitize_prompt,
    apply_prompt_safety,
    get_prompt_safety_advisor,
    SafetyContext,
    sanitize_with_locks,
)
from ....services.prompt_safety.rewrite import (
    is_sensitive_error as ps_is_sensitive_error,
    rewrite_prompt_preserving_locks as ps_rewrite_preserving_locks,
)


class ImageGenerationTool(AsyncTool):
    """
    图像生成工具 - 封装图像生成业务逻辑
    
    基于ZhipuClientTool，提供图像生成相关的业务功能
    """
    
    @classmethod
    def get_metadata(cls) -> ToolMetadata:
        return ToolMetadata(
            name="image_generation",
            version="1.0.0",
            description="使用AI服务生成图像，包括场景图像、视觉风格分析等",
            tool_type=ToolType.AI_SERVICE,
            author="system",
            tags=["图像生成", "视觉分析", "AI图像"],
            capabilities=["图像生成", "图像风格分析", "提示词优化", "视觉特征提取"],
            dependencies=["zhipu_client"]
        )
    
    def __init__(self, **kwargs):
        # 从kwargs中移除metadata，使用classmethod获取
        kwargs.pop('metadata', None)
        metadata = self.get_metadata()
        super().__init__(metadata=metadata, **kwargs)
        self._vlm_service = None
        self._prompt_manager = get_template_manager("image_generator")
    
    def get_available_actions(self) -> List[str]:
        # 精简对FC暴露的动作：优先复合函数
        return [
            "generate_with_autoprompt",
            "generate_image",
            "gen_image_prompt"
        ]
    
    def _initialize(self):
        """初始化工具"""
        pass

    def get_fc_visibility(self) -> Dict[str, Any]:
        """为业务级图像工具提供默认的 FC 暴露策略"""
        return {
            "expose": True,
            # 优先推荐复合函数
            "allowed_actions": ["generate_with_autoprompt"]
        }
    
    def get_action_schema(self, action: str) -> Dict[str, Any]:
        """获取指定操作的参数架构"""
        base_schema = {
            "type": "object",
            "properties": {},
        }
        
        if action == "generate_image":
            base_schema["properties"] = {
                "scene_number": {
                    "type": ["integer", "string"],
                    "description": "可选：用于对齐多场景批处理的标识"
                },
                "prompt": {
                    "type": "string",
                    "description": "图像生成提示词"
                },
                "style": {
                    "type": "string",
                    "description": "图像风格（例如 写实、艺术、电影感 等）"
                },
                "size": self._build_size_schema_property("图像尺寸；若不提供则由当前 provider 能力自动选择默认值"),
                "persist": {
                    "type": "boolean",
                    "description": "可选：将生成结果持久化到文件存储/OSS（若可用）并返回可访问 URL"
                },
                "destination_key": {
                    "type": "string",
                    "description": "可选：持久化时使用的目标路径/键名（例如 projects/<id>/characters/<cid>/avatar.jpg）"
                }
            }
            base_schema["required"] = ["prompt"]
            base_schema["description"] = "根据用户提供的提示词直接生成图像，可选指定尺寸以及风格。"

        elif action == "gen_image_prompt":
            base_schema["properties"] = {
                "scene_number": {
                    "type": ["integer", "string"],
                    "description": "可选：用于标识所属场景"
                },
                "scene_data": {
                    "type": "object",
                    "description": "场景信息（例如视觉描述、叙事要点、时长等）"
                },
                "style_guidance": {
                    "type": "object",
                    "description": "风格指导（如画风、构图偏好、色彩基调等）"
                }
            }
            base_schema["description"] = "根据场景信息和风格指导生成图像提示词，而不直接产出图像。"
        elif action == "generate_with_autoprompt":
            base_schema["properties"] = {
                "scene_number": {"type": ["integer", "string"], "description": "可选：用于追踪与持久化命名"},
                "scene_data": {"type": "object", "description": "场景信息（视觉描述/标题/脚本摘要等）"},
                "style_guidance": {"type": "object", "description": "风格指导（如画风、构图偏好、色彩基调等）"},
                "fallback_prompt": {"type": "string", "description": "当自动提示生成失败时使用的备用提示词"},
                "size": self._build_size_schema_property("图像尺寸；若不提供则由当前 provider 能力自动选择默认值"),
                "persist": {"type": "boolean", "description": "是否持久化到存储（默认 true）"}
            }
            base_schema["description"] = "自动生成符合场景的图像提示词并调用底层服务生成图像，可配置尺寸与持久化。"
        elif action == "analyze_image_style":
            base_schema["properties"] = {
                "image_url": {
                    "type": "string",
                    "description": "图像 URL"
                },
                "image_path": {
                    "type": "string", 
                    "description": "图像本地路径"
                }
            }
            base_schema["description"] = "分析指定图像的风格特征信息。"
            
        elif action == "extract_visual_features":
            base_schema["properties"] = {
                "image_url": {
                    "type": "string",
                    "description": "图像 URL"
                },
                "image_path": {
                    "type": "string",
                    "description": "图像本地路径"
                }
            }
            base_schema["description"] = "提取图像的视觉特征向量等信息。"
        
        return base_schema

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

    def _get_active_vlm_service(self):
        if not self._vlm_service:
            self._vlm_service = get_vlm_service()
        return self._vlm_service

    def _normalize_image_size(self, requested_size: Any) -> str:
        service = self._get_active_vlm_service()
        provider_name = "unknown"
        try:
            provider_name = service.get_provider_name() or provider_name
        except Exception:
            pass

        caps = None
        if hasattr(service, "get_capabilities"):
            try:
                caps = service.get_capabilities()
            except Exception:
                caps = None
        if caps is None:
            try:
                caps = get_vlm_capabilities()
            except Exception:
                caps = None

        size_cap = caps.size if caps and getattr(caps, "size", None) else None
        requested = str(requested_size).strip() if requested_size is not None else ""

        if size_cap:
            if requested:
                normalized = size_cap.resolve(requested)
                if normalized:
                    return normalized
            else:
                default_size = size_cap.default_option()
                if default_size:
                    return default_size

            raise ToolError(
                (
                    f"Unsupported image size for provider '{provider_name}': "
                    f"requested={requested or '<missing>'}, allowed={list(size_cap.options or [])}"
                ),
                tool_name=self.metadata.name,
                error_code="invalid_image_size",
                details={
                    "provider": provider_name,
                    "requested_size": requested or None,
                    "allowed_sizes": list(size_cap.options or []),
                    "accepted_inputs": size_cap.expand_enum(),
                },
            )

        raise ToolError(
            f"Image size capability is unavailable for provider '{provider_name}'",
            tool_name=self.metadata.name,
            error_code="image_size_capability_missing",
            details={
                "provider": provider_name,
                "requested_size": requested or None,
            },
        )

    # 取消阶段语义：工具仅具有执行属性
    
    async def _execute_impl(self, tool_input) -> Dict[str, Any]:
        """执行图像生成相关操作"""
        
        action = tool_input.action
        parameters = tool_input.parameters
        
        if action == "generate_image":
            return await self._generate_image(parameters)
        elif action == "gen_image_prompt":
            return await self._gen_image_prompt(parameters)
        elif action == "generate_with_autoprompt":
            return await self._generate_with_autoprompt(parameters)
        elif action == "analyze_image_style":
            return await self._analyze_image_style(parameters)
        elif action == "extract_visual_features":
            return await self._extract_visual_features(parameters)
        else:
            raise ValueError(f"Unknown action: {action}")
    
    async def _generate_image(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """生成图像"""
        
        prompt = (params.get("prompt", "") or "").strip()
        # 风格改为“按需透传”：无则不默认，避免硬编码偏置
        style = (params.get("style") or "").strip()
        size = self._normalize_image_size(params.get("size"))
        persist = bool(params.get("persist", False))
        destination_key = (params.get("destination_key") or "").strip()
        scene_number = params.get("scene_number")

        async def _maybe_persist(image_url: str) -> str:
            if not persist:
                return image_url
            if not image_url:
                return image_url

            dest_key = destination_key
            if not dest_key:
                safe_scene = str(scene_number) if scene_number is not None else "image"
                safe_scene = safe_scene.replace("/", "_").replace("\\", "_").replace(" ", "_")
                dest_key = f"images/scene_{safe_scene}_image.jpg"

            hosted_url = ""
            try:
                from ..tool_registry import get_tool_registry
                from ..base_tool import ToolInput as TI

                storage = get_tool_registry().get_tool("file_storage_tool")
                res = await storage.execute(
                    TI(
                        action="upload_from_url",
                        parameters={
                            "url": image_url,
                            "destination_key": dest_key,
                            "metadata": {"scene_number": scene_number, "source": "generate_image"},
                            "public": True,
                        },
                    )
                )
                payload = getattr(res, "result", res)
                if isinstance(payload, dict):
                    candidate = payload.get("url")
                    if isinstance(candidate, str) and candidate.startswith(("http://", "https://")):
                        hosted_url = candidate
            except Exception:
                hosted_url = ""

            if not hosted_url:
                try:
                    oss_url = await self._mirror_image_url_to_oss(
                        image_url,
                        dest_key,
                        metadata={"scene_number": scene_number, "source": "generate_image", "original_url": image_url},
                    )
                    if isinstance(oss_url, str) and oss_url.startswith(("http://", "https://")):
                        hosted_url = oss_url
                except Exception:
                    hosted_url = ""

            if hosted_url:
                try:
                    self.logger.info("IMAGE_REHOST_RESULT(scene=%s) url=%s", scene_number, hosted_url)
                except Exception:
                    pass
                return hosted_url
            return image_url

        # 轻量提示词质量校验
        if self._is_prompt_weak(prompt):
            raise ToolError(
                "PROMPT_TOO_WEAK: 缺少或过短的图像生成提示词",
                error_code="prompt_too_weak",
            )
        
        advisor_meta: Dict[str, Any] = {}
        try:
            # 通过供应商无关的服务接口生成图像（当前默认Zhipu实现）
            self._get_active_vlm_service()

            provider_name = None
            if self._vlm_service and hasattr(self._vlm_service, "get_provider_name"):
                try:
                    provider_name = self._vlm_service.get_provider_name()
                except Exception:
                    provider_name = None

            safe_prompt, advice = apply_prompt_safety(
                prompt,
                SafetyContext(
                    modality="image",
                    provider=provider_name,
                    language="zh",
                    metadata={
                        "action": "generate_image",
                        "scene_number": params.get("scene_number"),
                    },
                ),
            )
            advisor_meta = advice.metadata
            # 锁定片段（可选）：若上层传入 consistency_locks/locked_segments，则在 sanitize 时保持不变
            try:
                locks = params.get("locked_segments") or params.get("consistency_locks")
                if not isinstance(locks, list):
                    locks = []
            except Exception:
                locks = []
            sanitized = sanitize_with_locks(
                safe_prompt,
                locks,
                {
                    "modality": "image",
                    "scene_number": params.get("scene_number"),
                    "tool": self.metadata.name,
                    "advisor_layers": advisor_meta.get("applied_layers"),
                },
            )
            prompt = sanitized.text or safe_prompt
            advisor_meta["sanitized_changed"] = sanitized.changed
            advisor_meta["sanitized_matches"] = sanitized.matches

            # 构造最小必需参数；仅当上层明确提供 style/quality 时才透传
            gen_args = {"prompt": prompt, "size": size}
            if style:
                gen_args["style"] = style
            if params.get("quality"):
                gen_args["quality"] = params["quality"]
            # 调试期保留组合提示词日志
            try:
                prompt_bytes_len = len(prompt.encode("utf-8")) if isinstance(prompt, str) else 0
                self.logger.info(
                    "PROMPT_COMBINED(generate_image): len=%d bytes text=%s",
                    prompt_bytes_len,
                    prompt,
                )
            except Exception:
                pass

            try:
                res = await self._vlm_service.image_generation(**gen_args)
                image_url = res.get("image_url") or res.get("url") or ""
                if not image_url:
                    # 统一抛错，让下方敏感处理或上层 ReAct 接手
                    raise ToolError("image_generation returned no image_url", self.metadata.name)
                image_url = await _maybe_persist(image_url)
                return {
                    "image_url": image_url,
                    "generated_prompt": prompt,
                    "style": style,
                    "size": size,
                    "generation_metadata": res,
                    "prompt_safety": advisor_meta,
                }
            except ToolError as terr:
                # 仅当供应商明确返回“敏感/违规”错误时，触发一次轻量重写
                try:
                    policy = get_consistency_policy()
                    ps_cfg = getattr(policy, "prompt_safety", None)
                    enable_rewrite = bool(getattr(ps_cfg, "enable_rewrite_on_sensitive_error", False))
                except Exception:
                    ps_cfg = None
                    enable_rewrite = False

                if enable_rewrite and ps_is_sensitive_error(terr):
                    locked_segments = []
                    # 支持可选锁定片段透传：params["locked_segments"] 或 params["consistency_locks"]
                    try:
                        cand = params.get("locked_segments") or params.get("consistency_locks") or []
                        if isinstance(cand, list):
                            locked_segments = [str(x).strip() for x in cand if str(x).strip()]
                    except Exception:
                        locked_segments = []

                    rewrite_model = getattr(ps_cfg, "rewrite_model", None)
                    rewritten, telemetry = await ps_rewrite_preserving_locks(
                        prompt,
                        locked_segments,
                        model=rewrite_model,
                        language="zh",
                        metadata={"action": "generate_image", "scene_number": params.get("scene_number"), "tool": self.metadata.name},
                    )
                    # 记录事件
                    try:
                        self.logger.info(
                            "prompt_rewrite(image): applied=%s reason=sensitive_error model=%s tokens=%s",
                            bool(rewritten),
                            telemetry.get("model"),
                            telemetry.get("tokens"),
                        )
                    except Exception:
                        pass

                    if rewritten and rewritten.strip() and rewritten.strip() != prompt:
                        prompt = rewritten.strip()
                        # 调试日志：重写后的组合提示词
                        try:
                            self.logger.info(
                                "PROMPT_COMBINED(generate_image:rewrite): len=%d bytes text=%s",
                                len(prompt.encode("utf-8")),
                                prompt,
                            )
                        except Exception:
                            pass
                        # 重试一次
                        gen_args_retry = dict(gen_args)
                        gen_args_retry["prompt"] = prompt
                        res2 = await self._vlm_service.image_generation(**gen_args_retry)
                        image_url2 = res2.get("image_url") or res2.get("url") or ""
                        if not image_url2:
                            # 二次仍失败，走原有失败路径
                            raise terr
                        image_url2 = await _maybe_persist(image_url2)
                        return {
                            "image_url": image_url2,
                            "generated_prompt": prompt,
                            "style": style,
                            "size": size,
                            "generation_metadata": res2,
                            "prompt_safety": advisor_meta,
                            "prompt_safety_rewrite": {
                                "applied": True,
                                "reason": "sensitive_error",
                                "model": rewrite_model,
                            },
                        }
                # 非敏感或关闭重写：交由下方 except 统一返回失败
                raise
        except ToolError:
            raise
        except Exception as e:
            raise ToolError(
                f"图像生成异常: {str(e)}",
                error_code="image_generation_failed",
            )
    
    async def _create_image_prompt_from_scene(
        self,
        scene_data: Dict[str, Any],
        style: str,
        style_guidance: Dict[str, Any] | None = None,
    ) -> str:
        """根据场景与风格信息构建结构化图像提示词。

        - 统一通过 prompt 模板输出，确保角色/画风描述与其它 Agent 保持一致性。
        - 若模板渲染失败，则回退到轻量串接逻辑（与旧版本兼容）。
        """

        sd = scene_data or {}
        sg = style_guidance or {}

        def _as_list(value: Any) -> List[str]:
            if isinstance(value, list):
                return [str(v).strip() for v in value if isinstance(v, (str, int, float)) and str(v).strip()]
            if isinstance(value, (str, int, float)) and str(value).strip():
                return [str(value).strip()]
            return []

        def _dedup(values: List[str]) -> List[str]:
            seen = set()
            result = []
            for item in values:
                if not item:
                    continue
                if item not in seen:
                    seen.add(item)
                    result.append(item)
            return result

        visual_desc = (sd.get("visual_description") or sd.get("description") or sd.get("title") or "").strip()
        content_focus = (sd.get("content_focus") or "").strip()
        narrative_desc = (sd.get("narrative_description") or "").strip()

        # 角色结构化描述：优先使用结构化约束，其次角色描述文本
        character_sections: List[str] = []
        char_structs = sd.get("character_constraints_struct")
        if isinstance(char_structs, list):
            for item in char_structs:
                if not isinstance(item, dict):
                    continue
                name = (item.get("display_name") or item.get("name") or "").strip()
                segments: List[str] = []
                for key in ["archetype_or_identity", "species_or_breed"]:
                    val = item.get(key)
                    if isinstance(val, str) and val.strip():
                        segments.append(val.strip())
                sig = _as_list(item.get("signature_outfit_or_props"))
                if sig:
                    segments.append("标志道具：" + "、".join(sig[:4]))
                traits = _as_list(item.get("key_traits"))
                if traits:
                    segments.append("特征：" + "、".join(traits[:6]))
                role = item.get("role")
                if isinstance(role, str) and role.strip():
                    segments.append(f"叙事角色：{role.strip()}")
                if segments:
                    block = f"{name}：" + "；".join(segments) if name else "；".join(segments)
                    character_sections.append(block)

        if not character_sections:
            char_descs = _as_list(sd.get("character_descriptions")) or _as_list(sd.get("characters"))
            if not char_descs:
                names = _as_list(sd.get("characters_present"))
                if names:
                    char_descs.append("登场角色：" + "、".join(names))
            character_sections = char_descs

        # 风格 / 媒介 / 情绪等信息
        style_sections: List[str] = []
        style_map = {
            "style_name": "风格",
            "style_description": "风格说明",
            "visual_approach": "媒介表现",
            "narrative_style": "叙事方式",
            "production_taste": "制作风格",
        }
        for key, label in style_map.items():
            val = sg.get(key)
            if isinstance(val, str) and val.strip():
                style_sections.append(f"{label}：{val.strip()}")

        mood_sections = []
        for key in ["emotional_tone", "mood", "mood_and_atmosphere"]:
            val = sg.get(key) if key in sg else sd.get(key)
            if isinstance(val, str) and val.strip():
                mood_sections.append(val.strip())
        mood_sections = _dedup(mood_sections)

        color_sections = _dedup(
            _as_list(sg.get("color_palette")) + _as_list(sd.get("color_palette"))
        )

        props_sections = _dedup(_as_list(sd.get("props_and_objects")))

        # 辅助 bullet：内容焦点/叙事实要
        scene_focus = _dedup([item for item in [content_focus, narrative_desc] if item])

        cautionary_notes: List[str] = []
        anime_hint_sources = style_sections + mood_sections
        if any("动画" in seg or "动漫" in seg for seg in anime_hint_sources):
            cautionary_notes.append("保持动画笔触，避免写实摄影质感")

        template_payload = {
            "scene_description": visual_desc or "场景静态画面",
            "scene_focus": scene_focus,
            "character_sections": _dedup(character_sections),
            "style_sections": _dedup(style_sections),
            "mood_sections": mood_sections,
            "color_sections": color_sections,
            "props_sections": props_sections,
            "cautionary_notes": cautionary_notes,
        }

        try:
            return self._prompt_manager.render_template(
                "image_autoprompt",
                template_payload,
                validate=False,
            ).strip()
        except Exception:
            # 回退：延用旧的串接逻辑，确保功能不中断
            parts = [visual_desc, content_focus, narrative_desc]
            chars = _dedup(character_sections)
            if chars:
                parts.append("角色设定：" + "；".join(chars))

            base = "，".join([p for p in parts if p]) or "场景静态画面"

            art_style = (
                sg.get("style_name")
                or sg.get("visual_approach")
                or sg.get("style")
                or style
                or ""
            )
            extra_bits = []
            if art_style:
                extra_bits.append(f"风格：{art_style}")
            if color_sections:
                extra_bits.append("配色：" + "、".join(color_sections))
            if mood_sections:
                extra_bits.append("氛围：" + "、".join(mood_sections))

            tail = "高质量，细节清晰，构图平衡"
            return f"{base}，{'，'.join(extra_bits)}，{tail}" if extra_bits else f"{base}，{tail}"

    async def _generate_with_autoprompt(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """复合：自动提示词 → 生成 → 可选持久化。"""
        scene_data = params.get("scene_data") or {}
        style_guidance = params.get("style_guidance") or {}
        size = params.get("size")
        persist = params.get("persist", True)
        scene_number = params.get("scene_number")

        # 仅在有显式风格时传递；避免默认强制 realistic
        style = style_guidance.get("art_style") or style_guidance.get("style") or style_guidance.get("name") or ""
        prompt_text = await self._create_image_prompt_from_scene(scene_data, style, style_guidance)
        # 观测：记录提示词预览，便于核对与优化（不使用固定模板，仅日志）
        try:
            from ....core.config import settings as _cfg  # lazy import to avoid hard dependency at import time
            max_chars = int(getattr(_cfg, 'CONTENT_PREVIEW_CHARS', 300))
        except Exception:
            max_chars = 300
        preview = (prompt_text or "").replace("\n", " ")[:max_chars]
        try:
            self.logger.info(
                f"🖼️ IMAGE_PROMPT scene={scene_number} len={len(prompt_text or '')} preview={preview}"
            )
        except Exception:
            pass
        if self._is_prompt_weak(prompt_text) and params.get("fallback_prompt"):
            prompt_text = params.get("fallback_prompt")

        gen = await self._generate_image({
            "prompt": prompt_text,
            # 风格可选：缺省时不传递，避免下游误导
            **({"style": style} if style else {}),
            **({"size": size} if size else {}),
            "scene_number": scene_number
        })

        image_url = gen.get("image_url")
        if not image_url:
            raise ToolError(gen.get("error") or "image_generation returned no image_url", self.metadata.name)
        prompt_text = gen.get("generated_prompt", prompt_text)
        file_path = ""
        hosted_url = ""
        if persist and image_url:
            from ..tool_registry import get_tool_registry
            from ..base_tool import ToolInput as TI
            dest_key = f"images/scene_{scene_number}_image.jpg" if scene_number is not None else "images/autoprompt_image.jpg"
            # 优先使用本地文件存储工具；失败再尝试 OSS
            try:
                storage = get_tool_registry().get_tool("file_storage_tool")
                res = await storage.execute(TI(action="upload_from_url", parameters={
                    "url": image_url,
                    "destination_key": dest_key,
                    "metadata": {"scene_number": scene_number, "source": "generate_with_autoprompt"}
                }))
                payload = getattr(res, 'result', res)
                if isinstance(payload, dict):
                    file_path = payload.get("local_path") or payload.get("file_path", "")
                    hosted_candidate = payload.get("url")
                    if isinstance(hosted_candidate, str) and hosted_candidate.startswith(("http://", "https://")):
                        hosted_url = hosted_candidate
            except Exception:
                # 忽略本地落盘失败，继续尝试直接上传到OSS（若可用）
                file_path = ""

            # 如果配置了 OSS，并且当前还没有公开 URL，则将本地文件上传到 OSS
            if not hosted_url:
                local_source = file_path or ""
                if local_source:
                    oss_url = await self._upload_local_image_to_oss(
                        local_source,
                        dest_key,
                        metadata={"scene_number": scene_number, "source": "generate_with_autoprompt"}
                    )
                    if oss_url:
                        hosted_url = oss_url
                else:
                    # 若没有本地文件，但仍有原始URL，尝试直接镜像上传
                    oss_url = await self._mirror_image_url_to_oss(
                        image_url,
                        dest_key,
                        metadata={"scene_number": scene_number, "source": "generate_with_autoprompt", "original_url": image_url}
                    )
                    if oss_url:
                        hosted_url = oss_url

        # 若获得了公开可访问的URL，则优先使用之
        if hosted_url:
            self.logger.info(f"IMAGE_REHOST_RESULT scene={scene_number} url={hosted_url}")
            image_url = hosted_url

        return {
            "image_url": image_url,
            "file_path": file_path,
            "prompt_text": prompt_text,
            "style": style,
            "size": gen.get("size") or "",
            "scene_number": scene_number,
            "prompt_safety": gen.get("prompt_safety", {}),
        }

    async def _upload_local_image_to_oss(self, local_path: str, remote_path: str, metadata: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """将本地图片上传到 OSS，返回可公开访问的 URL。"""
        if not local_path or not os.path.exists(local_path):
            return None

        try:
            self.logger.info(
                "OSS_UPLOAD_DEBUG(local) local_path=%s remote_path=%s key_id=%s endpoint=%s bucket=%s",
                local_path,
                remote_path,
                getattr(settings, "OSS_ACCESS_KEY_ID", None),
                getattr(settings, "OSS_ENDPOINT", None),
                getattr(settings, "OSS_BUCKET_NAME", None),
            )
            from ..tool_registry import get_tool_registry
            from ..base_tool import ToolInput as TI

            registry = get_tool_registry()
            oss_tool = registry.get_tool("oss_storage")
            if not oss_tool:
                return None

            params = {
                "local_path": local_path,
                "remote_path": remote_path,
                "public_read": True,
                "overwrite": True,
                "metadata": metadata or {},
            }

            res = await oss_tool.execute(TI(action="upload", parameters=params))
            payload = getattr(res, 'result', res)
            if isinstance(payload, dict):
                url = payload.get("url")
                if url:
                    return url
                if payload.get("skipped") and payload.get("url"):
                    return payload.get("url")
        except Exception as exc:
            try:
                self.logger.warning(f"OSS upload failed for {local_path}: {exc}")
            except Exception:
                pass
        return None

    async def _mirror_image_url_to_oss(self, source_url: str, remote_path: str, metadata: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """当没有本地文件时，尝试将远端图片镜像到 OSS。"""
        if not source_url:
            return None

        temp_file = None
        try:
            self.logger.info(
                "OSS_UPLOAD_DEBUG(remote) source_url=%s remote_path=%s key_id=%s endpoint=%s bucket=%s",
                source_url,
                remote_path,
                getattr(settings, "OSS_ACCESS_KEY_ID", None),
                getattr(settings, "OSS_ENDPOINT", None),
                getattr(settings, "OSS_BUCKET_NAME", None),
            )
            timeout_seconds = 30
            try:
                from ....core.config import settings as _cfg
                timeout_seconds = int(getattr(_cfg, 'FILE_STORAGE_HTTP_TIMEOUT', timeout_seconds))
            except Exception:
                pass

            async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
                response = await client.get(source_url)
                response.raise_for_status()
                suffix = os.path.splitext(remote_path)[1] or ".jpg"
                fd, temp_file = tempfile.mkstemp(suffix=suffix)
                with os.fdopen(fd, "wb") as tmp:
                    tmp.write(response.content)

            url = await self._upload_local_image_to_oss(temp_file, remote_path, metadata=metadata)
            return url
        except Exception as exc:
            try:
                self.logger.warning(f"OSS mirror failed for {source_url}: {exc}")
            except Exception:
                pass
            return None
        finally:
            if temp_file and os.path.exists(temp_file):
                try:
                    os.unlink(temp_file)
                except Exception:
                    pass
    
    async def _analyze_image_style(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """分析图像风格"""
        
        image_url = params.get("image_url", "")
        image_path = params.get("image_path", "")
        
        if not image_url and not image_path:
            raise ToolError("需要提供图像URL或路径", error_code="missing_image_input")
        
        # 构建分析提示
        analysis_prompt = """分析这张图像的视觉风格特征：

请提供：
1. 主要风格类型（写实、艺术、卡通等）
2. 色彩特征
3. 构图特点
4. 光影效果
5. 情绪氛围

返回JSON格式的分析结果。"""
        
        try:
            if not self._vlm_service:
                self._vlm_service = get_vlm_service()

            target_image = image_url or image_path
            res = await self._vlm_service.image_understanding(
                image_input=target_image,
                prompt=analysis_prompt,
                model=None,
                temperature=0.3
            )

            analysis_content = res.get("analysis", "")
            try:
                style_analysis = json.loads(analysis_content)
                return {"style_analysis": style_analysis}
            except json.JSONDecodeError:
                return {
                    "style_analysis": {
                        "description": analysis_content,
                        "style_type": "mixed",
                        "confidence": 0.7,
                    }
                }
                
        except Exception as e:
            raise ToolError(f"图像风格分析异常: {str(e)}", error_code="style_analysis_failed")

    # 注意：建议在Agent中通过FC调用 gen_image_prompt 生成提示词，再调用 generate_image。

    async def _gen_image_prompt(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """为单个场景生成高质量图像提示词（由LLM生成，作为外部能力封装为工具动作）。"""
        try:
            from .service_interfaces import get_llm_service
            llm = get_llm_service()
            # 从 ai_config 读取工具模型映射
            try:
                from ....core.ai_config import get_ai_config
                ai_cfg = get_ai_config()
                cfg_model = ai_cfg.get_model_for_tool("image_generation")
                mcfg = ai_cfg.get_model_config(cfg_model) if cfg_model else None
            except Exception:
                cfg_model = None
                mcfg = None

            scene = params.get("scene_data", {}) or {}
            style = params.get("style_guidance", {}) or {}

            system = "你是资深动漫画面提示词工程师。请为给定场景生成高质量的图像提示词，突出主体、构图、光影与风格，避免含糊表述。只返回提示词文本。"
            user_ctx = (
                f"场景信息：\n"
                f"- 视觉描述：{scene.get('visual_description','')}\n"
                f"- 叙事要点：{scene.get('narrative_description','')}\n"
                f"- 时长：{scene.get('duration','')}\n"
                f"风格指导：{style}\n"
                f"请直接输出最终提示词。"
            )

            # 安全提示不注入LLM提示词，仅用于遥测；生成后的结果再做 sanitize
            system_prompt = system
            user_payload = user_ctx

            res = await llm.chat_completion(
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_payload}],
                temperature=0.3,
                model=(cfg_model or None)
            )
            prompt = (res.get("content") or "").strip()
            if not prompt:
                raise ToolError("未生成提示词", error_code="prompt_generation_failed")
            advisor_meta = {}
            sanitized = sanitize_prompt(
                prompt,
                {
                    "modality": "image",
                    "scene_number": params.get("scene_number"),
                    "tool": self.metadata.name,
                    "advisor_layers": advisor_meta.get("applied_layers") if advisor_meta else None,
                },
            )
            prompt = sanitized.text or prompt
            advisor_meta["sanitized_changed"] = sanitized.changed
            advisor_meta["sanitized_matches"] = sanitized.matches
            return {
                "prompt_text": prompt,
                "scene_number": params.get("scene_number"),
                "prompt_safety": advisor_meta,
            }
        except Exception as e:
            raise ToolError(f"提示词建议失败: {str(e)}", error_code="prompt_generation_failed")

    def _is_prompt_weak(self, prompt: str) -> bool:
        """极轻量提示词质量判断（读取配置）"""
        cfg = getattr(settings, "IMAGE_TOOL_PROMPT_RULES", {}) or {}
        min_length = int(cfg.get("min_length", 30))
        allow_weak = bool(cfg.get("allow_weak_prompt", False))
        p = (prompt or "").strip()
        if allow_weak:
            return False
        if len(p) < min_length:
            return True
        weak_markers = cfg.get("weak_markers")
        if not isinstance(weak_markers, list):
            weak_markers = ["高质量", "高清", "精美", "好看", "震撼", "唯美", "超清", "逼真"]
        near_limit = int(cfg.get("weak_marker_length_threshold", 50))
        if len(p) < near_limit:
            hits = sum(1 for w in weak_markers if isinstance(w, str) and w and w in p)
            threshold = int(cfg.get("weak_marker_threshold", 2))
            if hits >= threshold:
                return True
        return False
    
    async def _extract_visual_features(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """提取图像视觉特征"""
        
        image_url = params.get("image_url", "")
        image_path = params.get("image_path", "")
        
        if not image_url and not image_path:
            raise ToolError("需要提供图像URL或路径", error_code="missing_image_input")
        
        feature_prompt = """提取这张图像的关键视觉特征：

请识别：
1. 主要物体和元素
2. 颜色分布
3. 构图类型
4. 光照条件
5. 纹理特征
6. 空间关系

返回JSON格式的特征描述。"""
        
        try:
            # 供应商无关：统一 VLM 图像理解
            from .service_interfaces import get_vlm_service
            vlm = get_vlm_service()
            img_input = image_url or image_path
            res = await vlm.image_understanding(image_input=img_input, prompt=feature_prompt, model=None, temperature=0.2)
            content = (res.get("analysis") or res.get("content") or "").strip()
            if not content:
                raise ToolError("视觉特征提取为空", error_code="visual_feature_empty")
            try:
                visual_features = json.loads(content)
                return {"visual_features": visual_features}
            except json.JSONDecodeError:
                return {
                    "visual_features": {
                        "description": content,
                        "extraction_method": "vlm_analysis",
                        "confidence": 0.8
                    }
                }
        except Exception as e:
            raise ToolError(f"视觉特征提取异常: {str(e)}", error_code="visual_feature_failed")
