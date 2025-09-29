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

from ..base_tool import AsyncTool, ToolMetadata, ToolType, ToolError
from .service_interfaces import get_vlm_service
from ...prompts.template_manager import get_template_manager
from ....services.prompt_safety import (
    sanitize_prompt,
    apply_prompt_safety,
    get_prompt_safety_advisor,
    SafetyContext,
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
            # x-examples: 供提示展示，不参与校验
            "x-examples": []
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
                    "description": "图像风格，如realistic, artistic, cinematic等"
                },
                "size": {
                    "type": "string",
                    "description": "图像尺寸（自由字符串，如 1024x1024 / 2K / 1K）"
                }
            }
            base_schema["required"] = ["prompt"]
            base_schema["x-examples"] = [
                {
                    "prompt": "超广角镜头，金色夕阳照耀的城市天际线，细节清晰，电影级",
                    "size": "1024x1024"
                }
            ]

        elif action == "gen_image_prompt":
            base_schema["properties"] = {
                "scene_number": {
                    "type": ["integer", "string"],
                    "description": "可选：用于标识所属场景"
                },
                "scene_data": {
                    "type": "object",
                    "description": "场景信息（视觉描述/叙事要点/时长等）"
                },
                "style_guidance": {
                    "type": "object",
                    "description": "风格指导（如画风、构图偏好、色彩基调）"
                }
            }
            base_schema["x-examples"] = [
                {
                    "scene_data": {"visual_description": "森林中小木屋，黄昏光影"},
                    "style_guidance": {"color_tone": "warm", "composition": "wide-angle"}
                }
            ]
        elif action == "generate_with_autoprompt":
            base_schema["properties"] = {
                "scene_number": {"type": ["integer", "string"], "description": "可选：用于追踪与持久化命名"},
                "scene_data": {"type": "object", "description": "场景信息（视觉描述/标题/脚本摘要等）"},
                "style_guidance": {"type": "object", "description": "风格指导（如画风、构图偏好、色彩基调）"},
                "fallback_prompt": {"type": "string", "description": "当自动提示失败时使用的回退提示词"},
                "size": {"type": "string", "enum": ["1024x1024", "1024x1792", "1792x1024"], "description": "图像尺寸"},
                "persist": {"type": "boolean", "description": "是否持久化到存储（默认 true）"}
            }
            base_schema["x-examples"] = [
                {
                    "scene_data": {"visual_description": "古堡外夜景，薄雾，灯光从窗内透出"},
                    "style_guidance": {"style": "cinematic", "color_tone": "cool"},
                    "size": "1024x1024"
                }
            ]
        elif action == "analyze_image_style":
            base_schema["properties"] = {
                "image_url": {
                    "type": "string",
                    "description": "图像URL"
                },
                "image_path": {
                    "type": "string", 
                    "description": "图像路径"
                }
            }
            
        elif action == "extract_visual_features":
            base_schema["properties"] = {
                "image_url": {
                    "type": "string",
                    "description": "图像URL"
                },
                "image_path": {
                    "type": "string",
                    "description": "图像路径"
                }
            }
        
        return base_schema

    def get_action_stage(self, action: str) -> str:
        if action == "gen_image_prompt":
            return "plan"
        return "act"
    
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
        size = params.get("size", "1024x1024")
        
        # 轻量提示词质量校验
        if self._is_prompt_weak(prompt):
            return {
                "success": False,
                "error": "PROMPT_TOO_WEAK: 缺少或过短的图像生成提示词"
            }
        
        advisor_meta: Dict[str, Any] = {}
        try:
            # 通过供应商无关的服务接口生成图像（当前默认Zhipu实现）
            if not self._vlm_service:
                self._vlm_service = get_vlm_service()

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
            sanitized = sanitize_prompt(
                safe_prompt,
                {
                    "modality": "image",
                    "scene_number": params.get("scene_number"),
                    "tool": self.metadata.name,
                    "advisor_layers": advisor_meta.get("applied_layers"),
                },
            )
            prompt = sanitized.text
            advisor_meta["sanitized_changed"] = sanitized.changed
            advisor_meta["sanitized_matches"] = sanitized.matches

            # 构造最小必需参数；仅当上层明确提供 style/quality 时才透传
            gen_args = {"prompt": prompt, "size": size}
            if style:
                gen_args["style"] = style
            if params.get("quality"):
                gen_args["quality"] = params["quality"]
            res = await self._vlm_service.image_generation(**gen_args)

            image_url = res.get("image_url") or res.get("url") or ""
            if not image_url:
                # 将失败抛出为工具错误，以便上层Agent识别为失败而不是“成功但无产物”导致的重复尝试
                raise ToolError("image_generation returned no image_url", self.metadata.name)
            return {
                "success": True,
                "image_url": image_url,
                "generated_prompt": prompt,
                "style": style,
                "size": size,
                "generation_metadata": res,
                "prompt_safety": advisor_meta,
            }
                
        except Exception as e:
            return {
                "success": False,
                "error": f"图像生成异常: {str(e)}"
            }
    
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
        size = params.get("size", "1024x1024")
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
            "size": size,
            "scene_number": scene_number
        })

        if not gen.get("success"):
            # 再次保障：若下游未抛异常但返回success=False，也将其视为工具失败
            raise ToolError(gen.get("error") or "image_generation failed", self.metadata.name)

        image_url = gen.get("image_url")
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
            "success": True,
            "image_url": image_url,
            "file_path": file_path,
            "prompt_text": prompt_text,
            "style": style,
            "size": size,
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
            return {
                "success": False,
                "error": "需要提供图像URL或路径"
            }
        
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
                return {"success": True, "style_analysis": style_analysis}
            except json.JSONDecodeError:
                return {
                    "success": True,
                    "style_analysis": {
                        "description": analysis_content,
                        "style_type": "mixed",
                        "confidence": 0.7
                    }
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": f"图像风格分析异常: {str(e)}"
            }

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

            advisor = get_prompt_safety_advisor()
            provider_name = None
            if hasattr(llm, "get_provider_name"):
                try:
                    provider_name = llm.get_provider_name()
                except Exception:
                    provider_name = None
            safety_context = SafetyContext(
                modality="image",
                provider=provider_name,
                language="zh",
                metadata={
                    "action": "gen_image_prompt",
                    "scene_number": params.get("scene_number"),
                },
                tags=["prompt_engineering"],
            )
            advice = advisor.get_advice(safety_context, user_ctx)
            system_prompt = advice.compose_system_prompt(system) or system
            user_payload = advice.apply_to_prompt(user_ctx)

            res = await llm.chat_completion(
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_payload}],
                temperature=0.3,
                model=(cfg_model or None)
            )
            prompt = (res.get("content") or "").strip()
            if not prompt:
                return {"success": False, "error": "未生成提示词"}
            prompt = advice.apply_to_prompt(prompt)
            advisor_meta = advice.metadata.copy()
            sanitized = sanitize_prompt(
                prompt,
                {
                    "modality": "image",
                    "scene_number": params.get("scene_number"),
                    "tool": self.metadata.name,
                    "advisor_layers": advisor_meta.get("applied_layers"),
                },
            )
            prompt = sanitized.text
            advisor_meta["sanitized_changed"] = sanitized.changed
            advisor_meta["sanitized_matches"] = sanitized.matches
            return {
                "success": True,
                "prompt_text": prompt,
                "scene_number": params.get("scene_number"),
                "prompt_safety": advisor_meta,
            }
        except Exception as e:
            return {"success": False, "error": f"提示词建议失败: {str(e)}"}

    def _is_prompt_weak(self, prompt: str) -> bool:
        """极轻量提示词质量判断：
        - 长度不足（<30字符）视为弱；
        - 在较短（<50字符）时若包含多项口号式词汇也视为弱。
        仅作为底线兜底，避免在Agent中硬编码流程。
        """
        p = (prompt or "").strip()
        if len(p) < 30:
            return True
        weak_markers = ["高质量", "高清", "精美", "好看", "震撼", "唯美", "超清", "逼真"]
        if len(p) < 50:
            hits = sum(1 for w in weak_markers if w in p)
            if hits >= 2:
                return True
        return False
    
    async def _extract_visual_features(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """提取图像视觉特征"""
        
        image_url = params.get("image_url", "")
        image_path = params.get("image_path", "")
        
        if not image_url and not image_path:
            return {
                "success": False,
                "error": "需要提供图像URL或路径"
            }
        
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
                return {"success": False, "error": "视觉特征提取为空"}
            try:
                visual_features = json.loads(content)
                return {"success": True, "visual_features": visual_features}
            except json.JSONDecodeError:
                return {
                    "success": True,
                    "visual_features": {
                        "description": content,
                        "extraction_method": "vlm_analysis",
                        "confidence": 0.8
                    }
                }
        except Exception as e:
            return {"success": False, "error": f"视觉特征提取异常: {str(e)}"}
