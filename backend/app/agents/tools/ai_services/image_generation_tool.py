"""
Image Generation Tool - 封装图像生成业务逻辑
"""

import asyncio
import json
from typing import Dict, Any, List, Optional

from ..base_tool import AsyncTool, ToolMetadata, ToolType
from .zhipu_client import ZhipuClientTool


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
        self.zhipu_client = ZhipuClientTool()
    
    def get_available_actions(self) -> List[str]:
        return [
            "generate_image",
            "analyze_image_style",
            "enhance_prompt",
            "extract_visual_features"
        ]
    
    def _initialize(self):
        """初始化工具"""
        pass
    
    def get_action_schema(self, action: str) -> Dict[str, Any]:
        """获取指定操作的参数架构"""
        base_schema = {
            "type": "object", 
            "properties": {}
        }
        
        if action == "generate_image":
            base_schema["properties"] = {
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
                    "enum": ["1024x1024", "1024x1792", "1792x1024"],
                    "description": "图像尺寸"
                },
                "scene_data": {
                    "type": "object",
                    "description": "场景数据，用于生成对应的图像"
                }
            }
            base_schema["required"] = ["prompt"]
            
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
            
        elif action == "enhance_prompt":
            base_schema["properties"] = {
                "prompt": {
                    "type": "string",
                    "description": "原始提示词"
                },
                "target_style": {
                    "type": "string",
                    "description": "目标风格"
                },
                "focus": {
                    "type": "string",
                    "description": "优化重点"
                }
            }
            base_schema["required"] = ["prompt"]
            
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
    
    async def _execute_impl(self, tool_input) -> Dict[str, Any]:
        """执行图像生成相关操作"""
        
        action = tool_input.action
        parameters = tool_input.parameters
        
        if action == "generate_image":
            return await self._generate_image(parameters)
        elif action == "analyze_image_style":
            return await self._analyze_image_style(parameters)
        elif action == "enhance_prompt":
            return await self._enhance_prompt(parameters)
        elif action == "extract_visual_features":
            return await self._extract_visual_features(parameters)
        else:
            raise ValueError(f"Unknown action: {action}")
    
    async def _generate_image(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """生成图像"""
        
        prompt = params.get("prompt", "")
        style = params.get("style", "realistic")
        size = params.get("size", "1024x1024")
        scene_data = params.get("scene_data", {})
        
        if not prompt and scene_data:
            # 如果没有直接提示词，从场景数据生成
            prompt = await self._create_image_prompt_from_scene(scene_data, style)
        
        if not prompt:
            return {
                "success": False,
                "error": "缺少图像生成提示词"
            }
        
        try:
            # 使用ZhipuClient的CogView进行图像生成
            from ..base_tool import ToolInput
            zhipu_input = ToolInput(
                action="generate_image",
                parameters={
                    "prompt": prompt,
                    "size": size,
                    "model": "cogview-3"
                }
            )
            zhipu_result = await self.zhipu_client.execute(zhipu_input)
            
            if zhipu_result.success:
                return {
                    "success": True,
                    "image_url": zhipu_result.result.get("image_url", ""),
                    "image_path": zhipu_result.result.get("image_path", ""),
                    "generated_prompt": prompt,
                    "style": style,
                    "size": size,
                    "generation_metadata": zhipu_result.result
                }
            else:
                return {
                    "success": False,
                    "error": f"图像生成失败: {zhipu_result.error}"
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": f"图像生成异常: {str(e)}"
            }
    
    async def _create_image_prompt_from_scene(self, scene_data: Dict[str, Any], style: str) -> str:
        """从场景数据创建图像生成提示词"""
        
        visual_desc = scene_data.get("visual_description", "")
        content_focus = scene_data.get("content_focus", "")
        narrative_desc = scene_data.get("narrative_description", "")
        
        # 使用LLM优化图像提示词
        enhance_prompt = f"""基于以下场景信息，生成一个适合AI图像生成的详细提示词：

场景信息：
- 视觉描述：{visual_desc}
- 内容重点：{content_focus}
- 叙事描述：{narrative_desc}

目标风格：{style}

请生成：
1. 详细的视觉描述
2. 适合的构图和镜头角度
3. 色彩和光影效果
4. 符合{style}风格的特征

返回优化后的图像生成提示词（英文，适合AI图像生成）："""
        
        try:
            from ..base_tool import ToolInput
            zhipu_input = ToolInput(
                action="chat_completion",
                parameters={
                    "messages": [{"role": "user", "content": enhance_prompt}],
                    "temperature": 0.7,
                    "max_tokens": 500
                }
            )
            zhipu_result = await self.zhipu_client.execute(zhipu_input)
            
            if zhipu_result.success:
                enhanced_prompt = zhipu_result.result.get("content", "")
                return enhanced_prompt.strip()
            else:
                # Fallback: 使用原始描述
                return f"{visual_desc}, {content_focus}, {style} style"
                
        except Exception:
            # Fallback: 使用基本组合
            return f"{visual_desc}, {content_focus}, {style} style"
    
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
            # 使用ZhipuClient的视觉理解功能
            from ..base_tool import ToolInput
            zhipu_input = ToolInput(
                action="vision_chat",
                parameters={
                    "messages": [
                        {
                            "role": "user", 
                            "content": [
                                {"type": "text", "text": analysis_prompt},
                                {"type": "image_url", "image_url": {"url": image_url or image_path}}
                            ]
                        }
                    ],
                    "temperature": 0.3,
                    "max_tokens": 600
                }
            )
            zhipu_result = await self.zhipu_client.execute(zhipu_input)
            
            if zhipu_result.success:
                analysis_content = zhipu_result.result.get("content", "")
                try:
                    style_analysis = json.loads(analysis_content)
                    return {
                        "success": True,
                        "style_analysis": style_analysis
                    }
                except json.JSONDecodeError:
                    return {
                        "success": True,
                        "style_analysis": {
                            "description": analysis_content,
                            "style_type": "mixed",
                            "confidence": 0.7
                        }
                    }
            else:
                return {
                    "success": False,
                    "error": f"图像分析失败: {zhipu_result.error}"
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": f"图像风格分析异常: {str(e)}"
            }
    
    async def _enhance_prompt(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """增强图像生成提示词"""
        
        original_prompt = params.get("prompt", "")
        target_style = params.get("target_style", "realistic")
        enhancement_focus = params.get("focus", "quality")
        
        if not original_prompt:
            return {
                "success": False,
                "error": "需要提供原始提示词"
            }
        
        enhance_request = f"""请优化以下图像生成提示词：

原始提示词：{original_prompt}
目标风格：{target_style}
优化重点：{enhancement_focus}

优化要求：
1. 增加视觉细节描述
2. 添加适当的风格关键词
3. 改进构图和镜头描述
4. 确保语法正确且适合AI理解

返回优化后的提示词（英文）："""
        
        try:
            from ..base_tool import ToolInput
            zhipu_input = ToolInput(
                action="chat_completion",
                parameters={
                    "messages": [{"role": "user", "content": enhance_request}],
                    "temperature": 0.6,
                    "max_tokens": 400
                }
            )
            zhipu_result = await self.zhipu_client.execute(zhipu_input)
            
            if zhipu_result.success:
                enhanced_prompt = zhipu_result.result.get("content", "").strip()
                # 🔧 修复：如果LLM返回空内容，使用原始提示词
                if not enhanced_prompt:
                    enhanced_prompt = original_prompt
                    self.logger.warning(f"LLM返回空的增强提示词，使用原始提示词: {original_prompt[:50]}...")
                
                return {
                    "success": True,
                    "original_prompt": original_prompt,
                    "enhanced_prompt": enhanced_prompt,
                    "enhancement_notes": f"针对{target_style}风格和{enhancement_focus}进行优化"
                }
            else:
                return {
                    "success": False,
                    "error": f"提示词优化失败: {zhipu_result.error}",
                    "original_prompt": original_prompt
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": f"提示词增强异常: {str(e)}",
                "original_prompt": original_prompt
            }
    
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
            from ..base_tool import ToolInput
            zhipu_input = ToolInput(
                action="vision_chat",
                parameters={
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": feature_prompt},
                                {"type": "image_url", "image_url": {"url": image_url or image_path}}
                            ]
                        }
                    ],
                    "temperature": 0.2,
                    "max_tokens": 500
                }
            )
            zhipu_result = await self.zhipu_client.execute(zhipu_input)
            
            if zhipu_result.success:
                features_content = zhipu_result.result.get("content", "")
                try:
                    visual_features = json.loads(features_content)
                    return {
                        "success": True,
                        "visual_features": visual_features
                    }
                except json.JSONDecodeError:
                    return {
                        "success": True,
                        "visual_features": {
                            "description": features_content,
                            "extraction_method": "llm_analysis",
                            "confidence": 0.8
                        }
                    }
            else:
                return {
                    "success": False,
                    "error": f"特征提取失败: {zhipu_result.error}"
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": f"视觉特征提取异常: {str(e)}"
            }