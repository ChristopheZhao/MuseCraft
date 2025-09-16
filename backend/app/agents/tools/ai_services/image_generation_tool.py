"""
Image Generation Tool - 封装图像生成业务逻辑
"""

import asyncio
import json
from typing import Dict, Any, List, Optional

from ..base_tool import AsyncTool, ToolMetadata, ToolType, ToolError
from .service_interfaces import get_vlm_service


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
        
        try:
            # 通过供应商无关的服务接口生成图像（当前默认Zhipu实现）
            if not self._vlm_service:
                self._vlm_service = get_vlm_service()

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
                "generation_metadata": res
            }
                
        except Exception as e:
            return {
                "success": False,
                "error": f"图像生成异常: {str(e)}"
            }
    
    async def _create_image_prompt_from_scene(self, scene_data: Dict[str, Any], style: str, style_guidance: Dict[str, Any] | None = None) -> str:
        """从场景数据创建图像生成提示词（轻量组合，避免强依赖LLM）。
        兼容场景字段：优先 visual_description；无则回退 description/title。
        同时融合 style_guidance: art_style, composition, color_palette, mood。
        """
        sd = scene_data or {}
        # 兼容字段：优先视觉描述
        visual_desc = (sd.get("visual_description") or sd.get("description") or sd.get("title") or "").strip()
        content_focus = (sd.get("content_focus") or "").strip()
        narrative_desc = (sd.get("narrative_description") or "").strip()
        # 角色注入：若场景标注了 characters_present/character_descriptions，将其作为语义约束追加
        # 兼容别名：scene_data.characters 视为 character_descriptions 的等价输入
        chars = sd.get("character_descriptions") or sd.get("characters") or []
        if not chars:
            # 回退：仅使用名字
            names = sd.get("characters_present") or []
            if names:
                chars = ["、".join(names)]

        parts = [p for p in [visual_desc, content_focus, narrative_desc] if p]
        if chars:
            parts.append("角色设定：" + "；".join(chars))
        base = "，".join(parts) if parts else "场景静态画面"

        # 风格融合：支持外部 style 文本与结构化 style_guidance
        sg = style_guidance or {}
        # 优先使用结构化的 art_style/风格提示；缺失时不强行回落到 "realistic"，保持风格中立
        art_style = sg.get("art_style") or sg.get("style") or sg.get("name") or style or ""
        composition = sg.get("composition") or ""
        color_palette = sg.get("color_palette") or ""
        mood = sg.get("mood") or ""

        style_bits = [
            f"风格：{art_style}" if art_style else "",
            f"构图：{composition}" if composition else "",
            f"配色：{color_palette}" if color_palette else "",
            f"氛围：{mood}" if mood else "",
        ]
        style_text = "，".join([b for b in style_bits if b])
        tail = "高质量，细节清晰，构图平衡"
        # 若无风格信息则不强加默认风格，避免与用户的动画/绘制意图冲突
        return f"{base}，{style_text}，{tail}" if style_text else f"{base}，{tail}"

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
        file_path = ""
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
            except Exception:
                try:
                    storage = get_tool_registry().get_tool("oss_storage")
                    res = await storage.execute(TI(action="mirror_from_url", parameters={
                        "url": image_url,
                        "remote_path": dest_key,
                        "public_read": True,
                        "content_type": "image/jpeg"
                    }))
                    payload = getattr(res, 'result', res)
                    if isinstance(payload, dict):
                        file_path = payload.get("url", "")
                except Exception:
                    # 忽略持久化失败，保留远程URL照常返回
                    file_path = ""

        return {
            "success": True,
            "image_url": image_url,
            "file_path": file_path,
            "prompt_text": prompt_text,
            "style": style,
            "size": size,
            "scene_number": scene_number
        }
    
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

            res = await llm.chat_completion(
                messages=[{"role":"system","content":system},{"role":"user","content":user_ctx}],
                temperature=0.3,
                model=(cfg_model or None)
            )
            prompt = (res.get("content") or "").strip()
            if not prompt:
                return {"success": False, "error": "未生成提示词"}
            return {
                "success": True,
                "prompt_text": prompt,
                "scene_number": params.get("scene_number")
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
