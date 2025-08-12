"""
即梦AI图片生成工具 - 基于豆包Seedream模型
"""

import asyncio
import httpx
from typing import Dict, Any, Optional, List, Union
import base64
import io
from ..base_tool import AsyncTool, ToolInput, ToolError, ToolValidationError, ToolMetadata, ToolType
from ....core.config import settings


class JimengImageTool(AsyncTool):
    """即梦AI图片生成工具"""
    
    @classmethod
    def get_metadata(cls) -> ToolMetadata:
        return ToolMetadata(
            name="jimeng_image",
            version="1.0.0",
            description="即梦AI图片生成工具，基于豆包Seedream 3.0模型",
            tool_type=ToolType.AI_SERVICE,
            author="system",
            tags=["image-generation", "ai", "jimeng", "douyin"],
            capabilities=["text_to_image", "image_to_image", "get_styles", "upscale"],
            limitations=["requires_api_key", "rate_limited"]
        )
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(self.get_metadata(), config)
    
    def _initialize(self):
        """Initialize tool-specific resources"""
        # 尝试从配置获取API key，如果没有则从环境变量获取
        self.api_key = getattr(settings, 'JIMENG_API_KEY', None)
        if not self.api_key:
            import os
            self.api_key = os.getenv("JIMENG_API_KEY")
        
        self.base_url = getattr(settings, 'JIMENG_BASE_URL', 'https://api.jimeng.ai/v1')
        self.timeout = getattr(settings, 'AI_SERVICE_TIMEOUT', 30)
        
        # 工具可以在没有API key时创建，但在使用时会检查
        self._functional = bool(self.api_key)
        if not self._functional:
            self.logger.warning("JIMENG_API_KEY not configured, tool will not be functional")
        
        # 支持的模型
        self.models = [
            "general_v3.0",      # 豆包3.0通用模型
            "realistic_v2.0",    # 写实模型
            "anime_v2.0",        # 动漫模型
            "art_v1.0"           # 艺术模型
        ]
        
        # 支持的尺寸
        self.sizes = [
            "1024x1024",   # 正方形
            "1024x1792",   # 竖屏
            "1792x1024",   # 横屏
            "768x1344",    # 手机竖屏
            "1344x768",    # 手机横屏
            "512x512",     # 小尺寸
            "640x960",     # 标准竖屏
            "960x640"      # 标准横屏
        ]
    
    def get_available_actions(self) -> List[str]:
        """Get list of available actions this tool can perform"""
        return ["text_to_image", "image_to_image", "get_styles", "upscale"]
    
    def get_action_schema(self, action: str) -> Dict[str, Any]:
        """Get input schema for a specific action"""
        schemas = {
            "text_to_image": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "图像生成提示"},
                    "negative_prompt": {"type": "string", "description": "负面提示"},
                    "model": {"type": "string", "enum": self.models},
                    "size": {"type": "string", "enum": self.sizes},
                    "style": {"type": "string"},
                    "quality": {"type": "string", "enum": ["standard", "hd"]},
                    "num_images": {"type": "integer", "minimum": 1, "maximum": 4}
                },
                "required": ["prompt"]
            },
            "image_to_image": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "图像生成提示"},
                    "image": {"type": "string", "description": "输入图像（base64或URL）"},
                    "strength": {"type": "number", "minimum": 0, "maximum": 1}
                },
                "required": ["prompt", "image"]
            },
            "get_styles": {
                "type": "object",
                "properties": {
                    "model": {"type": "string", "enum": self.models}
                }
            },
            "upscale": {
                "type": "object",
                "properties": {
                    "image": {"type": "string", "description": "要放大的图像"},
                    "scale": {"type": "integer", "enum": [2, 4]}
                },
                "required": ["image"]
            }
        }
        return schemas.get(action, {})
    
    async def _execute_impl(self, tool_input: ToolInput) -> Any:
        """执行即梦图片生成操作"""
        # 检查工具是否功能可用
        if not self._functional:
            raise ToolError("JimengImageTool not functional - API key required", self.metadata.name)
            
        action = tool_input.action
        params = tool_input.parameters
        
        if action == "text_to_image":
            return await self._text_to_image(params)
        elif action == "image_to_image":
            return await self._image_to_image(params)
        elif action == "get_styles":
            return await self._get_styles(params)
        elif action == "upscale":
            return await self._upscale(params)
        else:
            raise ToolValidationError(f"Unsupported action: {action}", self.metadata.name)
    
    async def _text_to_image(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """文本生成图片"""
        prompt = params.get("prompt")
        negative_prompt = params.get("negative_prompt", "")
        model = params.get("model", "general_v3.0")
        size = params.get("size", "1024x1024")
        style = params.get("style", "default")
        quality = params.get("quality", "standard")  # standard, hd
        num_images = params.get("num_images", 1)
        seed = params.get("seed")  # 随机种子，用于复现
        guidance_scale = params.get("guidance_scale", 7.5)  # 引导强度
        
        if not prompt:
            raise ValueError("prompt is required for text_to_image")
        
        if model not in self.models:
            model = "general_v3.0"
        
        if size not in self.sizes:
            size = "1024x1024"
        
        # 构建请求数据
        request_data = {
            "model": model,
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "size": size,
            "style": style,
            "quality": quality,
            "n": min(num_images, 4),  # 最多4张
            "guidance_scale": guidance_scale
        }
        
        if seed:
            request_data["seed"] = seed
        
        # 发送请求
        async with httpx.AsyncClient(timeout=300) as client:
            response = await client.post(
                f"{self.base_url}/text_to_image",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json=request_data
            )
            response.raise_for_status()
            result = response.json()
        
        return {
            "images": result.get("data", []),
            "model": model,
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "size": size,
            "style": style,
            "quality": quality,
            "num_images": len(result.get("data", [])),
            "seed": result.get("seed"),
            "usage": result.get("usage", {})
        }
    
    async def _image_to_image(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """图片到图片生成"""
        prompt = params.get("prompt")
        image = params.get("image")  # base64或URL
        negative_prompt = params.get("negative_prompt", "")
        model = params.get("model", "general_v3.0")
        strength = params.get("strength", 0.7)  # 变化强度 0-1
        style = params.get("style", "default")
        quality = params.get("quality", "standard")
        num_images = params.get("num_images", 1)
        seed = params.get("seed")
        guidance_scale = params.get("guidance_scale", 7.5)
        
        if not prompt:
            raise ValueError("prompt is required for image_to_image")
        
        if not image:
            raise ValueError("image is required for image_to_image")
        
        # 构建请求数据
        request_data = {
            "model": model,
            "prompt": prompt,
            "image": image,
            "negative_prompt": negative_prompt,
            "strength": strength,
            "style": style,
            "quality": quality,
            "n": min(num_images, 4),
            "guidance_scale": guidance_scale
        }
        
        if seed:
            request_data["seed"] = seed
        
        # 发送请求
        async with httpx.AsyncClient(timeout=300) as client:
            response = await client.post(
                f"{self.base_url}/image_to_image",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json=request_data
            )
            response.raise_for_status()
            result = response.json()
        
        return {
            "images": result.get("data", []),
            "model": model,
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "strength": strength,
            "style": style,
            "quality": quality,
            "num_images": len(result.get("data", [])),
            "seed": result.get("seed"),
            "usage": result.get("usage", {})
        }
    
    async def _get_styles(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """获取可用的图片风格"""
        model = params.get("model", "general_v3.0")
        
        # 即梦支持的风格列表
        styles = {
            "general_v3.0": [
                {"name": "default", "display_name": "默认", "description": "平衡的通用风格"},
                {"name": "realistic", "display_name": "写实", "description": "逼真的照片风格"},
                {"name": "anime", "display_name": "动漫", "description": "日式动漫风格"},
                {"name": "artistic", "display_name": "艺术", "description": "艺术绘画风格"},
                {"name": "portrait", "display_name": "人像", "description": "人物肖像专用"},
                {"name": "landscape", "display_name": "风景", "description": "自然风景专用"},
                {"name": "sci_fi", "display_name": "科幻", "description": "科幻未来风格"},
                {"name": "fantasy", "display_name": "奇幻", "description": "魔幻奇幻风格"},
                {"name": "vintage", "display_name": "复古", "description": "怀旧复古风格"},
                {"name": "minimalist", "display_name": "极简", "description": "简约极简风格"}
            ],
            "realistic_v2.0": [
                {"name": "photorealistic", "display_name": "照片级", "description": "极度逼真"},
                {"name": "cinematic", "display_name": "电影感", "description": "电影画面风格"},
                {"name": "professional", "display_name": "专业", "description": "商业摄影风格"}
            ],
            "anime_v2.0": [
                {"name": "anime_classic", "display_name": "经典动漫", "description": "传统日式动漫"},
                {"name": "anime_modern", "display_name": "现代动漫", "description": "现代日式动漫"},
                {"name": "chibi", "display_name": "Q版", "description": "可爱Q版风格"}
            ],
            "art_v1.0": [
                {"name": "oil_painting", "display_name": "油画", "description": "传统油画风格"},
                {"name": "watercolor", "display_name": "水彩", "description": "水彩画风格"},
                {"name": "sketch", "display_name": "素描", "description": "铅笔素描风格"}
            ]
        }
        
        return {
            "model": model,
            "styles": styles.get(model, styles["general_v3.0"]),
            "total_styles": len(styles.get(model, styles["general_v3.0"]))
        }
    
    async def _upscale(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """图片放大"""
        image = params.get("image")  # base64或URL
        scale = params.get("scale", 2)  # 放大倍数 2x 或 4x
        
        if not image:
            raise ValueError("image is required for upscale")
        
        if scale not in [2, 4]:
            scale = 2
        
        # 构建请求数据
        request_data = {
            "image": image,
            "scale": scale
        }
        
        # 发送请求
        async with httpx.AsyncClient(timeout=300) as client:
            response = await client.post(
                f"{self.base_url}/upscale",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json=request_data
            )
            response.raise_for_status()
            result = response.json()
        
        return {
            "upscaled_image": result.get("upscaled_image"),
            "original_size": result.get("original_size"),
            "upscaled_size": result.get("upscaled_size"),
            "scale": scale,
            "usage": result.get("usage", {})
        }
    
    def get_supported_models(self) -> List[str]:
        """获取支持的模型列表"""
        return self.models.copy()
    
    def get_supported_sizes(self) -> List[str]:
        """获取支持的尺寸列表"""
        return self.sizes.copy()
    
    def estimate_cost(self, num_images: int, size: str = "1024x1024", quality: str = "standard") -> float:
        """估算图片生成成本（人民币）"""
        # 即梦AI定价（2025年1月）
        base_costs = {
            "512x512": {"standard": 0.02, "hd": 0.03},
            "640x960": {"standard": 0.03, "hd": 0.04},
            "768x1344": {"standard": 0.04, "hd": 0.06},
            "1024x1024": {"standard": 0.05, "hd": 0.08},
            "1024x1792": {"standard": 0.08, "hd": 0.12},
            "1792x1024": {"standard": 0.08, "hd": 0.12}
        }
        
        # 获取单张成本
        size_costs = base_costs.get(size, base_costs["1024x1024"])
        cost_per_image = size_costs.get(quality, size_costs["standard"])
        
        total_cost = num_images * cost_per_image
        return total_cost
    
    async def health_check(self) -> bool:
        """健康检查"""
        try:
            # 尝试获取风格列表
            result = await self._get_styles({"model": "general_v3.0"})
            return len(result.get("styles", [])) > 0
        except:
            return False
    
    def optimize_prompt_for_chinese(self, prompt: str) -> str:
        """优化中文提示词"""
        # 为中文用户优化提示词
        optimizations = {
            "人物": "人物, 高质量, 细节丰富",
            "风景": "风景, 自然光线, 高清晰度",
            "建筑": "建筑, 专业摄影, 对称构图",
            "动物": "动物, 自然环境, 生动表情",
            "美食": "美食, 诱人色彩, 专业布光"
        }
        
        # 添加通用的质量关键词
        if "高质量" not in prompt:
            prompt += ", 高质量"
        if "细节" not in prompt:
            prompt += ", 丰富细节"
        
        return prompt


# 导出工具实例
try:
    jimeng_image = JimengImageTool()
except Exception as e:
    jimeng_image = None
    print(f"Jimeng Image Tool initialization failed: {e}")