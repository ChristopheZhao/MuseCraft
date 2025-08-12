"""
Universal Image Generation Client - 通用图像生成工具
支持多个图像生成服务提供商
"""

import json
import httpx
import base64
from typing import Dict, Any, List, Optional, Union
from PIL import Image
import io

from ..base_tool import AsyncTool, ToolMetadata, ToolType, ToolInput, ToolError, ToolValidationError


class ImageGenerationClientTool(AsyncTool):
    """
    通用图像生成客户端工具
    
    支持的服务商：
    - Stability AI (SDXL, SD3)
    - 智谱AI (CogView)
    - DALL-E (OpenAI)
    - Midjourney (通过第三方API)
    - 通义万相 (Alibaba)
    """
    
    @classmethod
    def get_metadata(cls) -> ToolMetadata:
        return ToolMetadata(
            name="image_generation_client",
            version="1.0.0",
            description="通用图像生成客户端，支持多个AI图像生成服务",
            tool_type=ToolType.AI_SERVICE,
            author="system",
            tags=["image-generation", "ai", "stability", "dalle", "cogview", "midjourney"],
            capabilities=[
                "text_to_image",
                "image_to_image", 
                "style_transfer",
                "image_upscale",
                "multiple_providers",
                "batch_generation"
            ],
            limitations=[
                "requires_api_key",
                "rate_limited",
                "cost_per_image",
                "resolution_limits"
            ]
        )
    
    def _initialize(self):
        """初始化图像生成客户端 - 按优先级自动选择服务"""
        self.providers = {}
        self.timeout = self.config.get("timeout", 300)  # 图像生成需要较长时间
        
        # 按照优先级顺序初始化服务：GLM > OpenAI > Stability > Tongyi
        self._init_glm()       # 智谱AI CogView (一键多能)
        self._init_openai()    # OpenAI DALL-E
        self._init_stability_ai()  # Stability AI
        self._init_tongyi()    # 通义万相
        
        # 工具可以在没有providers时创建，但在使用时会检查
        self._functional = bool(self.providers)
        
        if not self.providers:
            self.logger.warning("ImageGenerationClientTool initialized without any providers - tool will not be functional")
            self.default_provider = None
            return
        
        # 自动选择第一个可用的服务作为默认服务
        self.default_provider = list(self.providers.keys())[0]
        
        self.logger.info(f"🎨 图像生成服务初始化完成")
        self.logger.info(f"📋 可用服务: {list(self.providers.keys())}")
        self.logger.info(f"⭐ 默认服务: {self.default_provider}")
        
        # 打印服务配置信息
        for provider_name, config in self.providers.items():
            models = ", ".join(config.get("models", []))
            self.logger.info(f"✅ {provider_name}: {models}")
    
    def _init_glm(self):
        """初始化智谱AI CogView (最高优先级)"""
        from ....core.config import settings
        api_key = settings.GLM_API_KEY
        if api_key:
            self.providers["glm"] = {
                "api_key": api_key,
                "base_url": settings.GLM_BASE_URL,
                "models": ["cogview-3", "cogview-3-plus"],
                "display_name": "智谱AI CogView"
            }
    
    def _init_openai(self):
        """初始化OpenAI DALL-E (第二优先级)"""
        from ....core.config import settings
        api_key = settings.OPENAI_API_KEY
        if api_key:
            self.providers["openai"] = {
                "api_key": api_key,
                "base_url": "https://api.openai.com/v1",
                "models": ["dall-e-3", "dall-e-2"],
                "display_name": "OpenAI DALL-E"
            }
    
    def _init_stability_ai(self):
        """初始化Stability AI (第三优先级)"""
        from ....core.config import settings
        api_key = settings.STABILITY_API_KEY
        if api_key:
            self.providers["stability"] = {
                "api_key": api_key,
                "base_url": "https://api.stability.ai",
                "models": ["sd3-medium", "sd3-large", "sdxl-1.0", "sd-1.6"],
                "display_name": "Stability AI"
            }
    
    def _init_tongyi(self):
        """初始化通义万相 (第四优先级)"""
        from ....core.config import settings
        # 通义万相可能没有在settings中定义，使用getattr避免错误
        api_key = getattr(settings, 'TONGYI_API_KEY', None)
        if api_key:
            self.providers["tongyi"] = {
                "api_key": api_key,
                "base_url": "https://dashscope.aliyuncs.com/api/v1",
                "models": ["wanx-v1"],
                "display_name": "阿里通义万相"
            }
    
    def get_available_actions(self) -> List[str]:
        return [
            "generate_image",
            "batch_generate_images",
            "image_to_image",
            "upscale_image",
            "get_generation_status",
            "list_providers",
            "get_provider_models"
        ]
    
    def get_action_schema(self, action: str) -> Dict[str, Any]:
        providers = list(self.providers.keys())
        
        schemas = {
            "generate_image": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "图像生成提示词"},
                    "negative_prompt": {"type": "string", "description": "负面提示词（可选）"},
                    "provider": {"type": "string", "enum": providers, "description": "服务提供商"},
                    "model": {"type": "string", "description": "使用的模型"},
                    "size": {"type": "string", "enum": ["512x512", "768x768", "1024x1024", "1024x768", "768x1024", "1344x768", "768x1344"]},
                    "quality": {"type": "string", "enum": ["standard", "hd"]},
                    "style": {"type": "string", "enum": ["natural", "vivid", "artistic", "photographic", "anime", "digital-art"]},
                    "steps": {"type": "integer", "minimum": 10, "maximum": 50},
                    "cfg_scale": {"type": "number", "minimum": 1, "maximum": 20},
                    "seed": {"type": "integer", "description": "随机种子"}
                },
                "required": ["prompt"]
            },
            "batch_generate_images": {
                "type": "object",
                "properties": {
                    "prompts": {"type": "array", "items": {"type": "string"}},
                    "provider": {"type": "string", "enum": providers},
                    "model": {"type": "string"},
                    "batch_size": {"type": "integer", "minimum": 1, "maximum": 10},
                    "common_params": {"type": "object", "description": "通用参数"}
                },
                "required": ["prompts"]
            },
            "image_to_image": {
                "type": "object",
                "properties": {
                    "image_url": {"type": "string", "description": "输入图像URL或base64"},
                    "prompt": {"type": "string", "description": "转换提示"},
                    "provider": {"type": "string", "enum": providers},
                    "strength": {"type": "number", "minimum": 0, "maximum": 1, "description": "变换强度"}
                },
                "required": ["image_url", "prompt"]
            },
            "upscale_image": {
                "type": "object",
                "properties": {
                    "image_url": {"type": "string", "description": "要放大的图像"},
                    "scale_factor": {"type": "integer", "enum": [2, 4], "description": "放大倍数"},
                    "provider": {"type": "string", "enum": providers}
                },
                "required": ["image_url"]
            }
        }
        
        return schemas.get(action, {})
    
    async def _execute_impl(self, tool_input: ToolInput) -> Any:
        """执行图像生成操作"""
        # 检查工具是否功能可用
        if not self._functional:
            raise ToolError("ImageGenerationClientTool not functional - no API keys configured", self.metadata.name)
        
        action = tool_input.action
        params = tool_input.parameters
        
        if action == "generate_image":
            return await self._generate_image(params)
        elif action == "batch_generate_images":
            return await self._batch_generate_images(params)
        elif action == "image_to_image":
            return await self._image_to_image(params)
        elif action == "upscale_image":
            return await self._upscale_image(params)
        elif action == "get_generation_status":
            return await self._get_generation_status(params)
        elif action == "list_providers":
            return self._list_providers()
        elif action == "get_provider_models":
            return self._get_provider_models(params)
        else:
            raise ToolValidationError(f"Unknown action: {action}", self.metadata.name)
    
    async def _generate_image(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """生成单张图像 - 统一接口，内部自适应API选择"""
        provider = params.get("provider", self.default_provider)
        
        if provider not in self.providers:
            raise ToolError(f"图像生成服务 {provider} 未配置", self.metadata.name)
        
        provider_config = self.providers[provider]
        display_name = provider_config.get("display_name", provider)
        
        # 透明日志：显示使用的服务
        self.logger.info(f"🎨 正在使用 {display_name} 生成图像...")
        self.logger.info(f"📝 提示词: {params.get('prompt', '')[:100]}...")
        
        try:
            if provider == "glm":
                result = await self._glm_generate_image(params)
            elif provider == "openai":
                result = await self._openai_generate_image(params)
            elif provider == "stability":
                result = await self._stability_generate_image(params)
            elif provider == "tongyi":
                result = await self._tongyi_generate_image(params)
            else:
                raise ToolError(f"图像生成服务 {provider} 未实现", self.metadata.name)
            
            self.logger.info(f"✅ {display_name} 图像生成成功")
            return result
            
        except Exception as e:
            self.logger.error(f"❌ {display_name} 图像生成失败: {str(e)}")
            raise
    
    async def _glm_generate_image(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """使用智谱AI CogView生成图像"""
        try:
            provider_config = self.providers["glm"]
            
            # 使用zhipuai SDK
            import zhipuai
            client = zhipuai.ZhipuAI(api_key=provider_config['api_key'])
            
            response = client.images.generations(
                model=params.get("model", "cogview-3"),
                prompt=params["prompt"],
                size=params.get("size", "1024x1024")
            )
            
            return {
                "provider": "glm",
                "model": params.get("model", "cogview-3"),
                "images": [
                    {
                        "url": response.data[0].url,
                        "revised_prompt": getattr(response.data[0], 'revised_prompt', params["prompt"])
                    }
                ],
                "prompt": params["prompt"],
                "generation_params": {
                    "model": params.get("model", "cogview-3"),
                    "size": params.get("size", "1024x1024")
                }
            }
            
        except Exception as e:
            raise ToolError(f"智谱AI CogView图像生成失败: {str(e)}", self.metadata.name)
    
    async def _stability_generate_image(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """使用Stability AI生成图像"""
        try:
            provider_config = self.providers["stability"]
            
            payload = {
                "text_prompts": [
                    {"text": params["prompt"], "weight": 1}
                ],
                "cfg_scale": params.get("cfg_scale", 7),
                "height": int(params.get("size", "1024x1024").split("x")[1]),
                "width": int(params.get("size", "1024x1024").split("x")[0]),
                "samples": 1,
                "steps": params.get("steps", 30)
            }
            
            if params.get("negative_prompt"):
                payload["text_prompts"].append({
                    "text": params["negative_prompt"],
                    "weight": -1
                })
            
            if params.get("seed"):
                payload["seed"] = params["seed"]
            
            model = params.get("model", "sdxl-1.0")
            
            headers = {
                "Authorization": f"Bearer {provider_config['api_key']}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{provider_config['base_url']}/v1/generation/{model}/text-to-image",
                    headers=headers,
                    json=payload
                )
                
                if response.status_code != 200:
                    error_detail = response.text
                    raise ToolError(f"Stability AI error: {response.status_code} - {error_detail}", self.metadata.name)
                
                result = response.json()
                
                return {
                    "provider": "stability",
                    "model": model,
                    "images": [
                        {
                            "base64": artifact["base64"],
                            "seed": artifact["seed"],
                            "finish_reason": artifact["finishReason"]
                        }
                        for artifact in result["artifacts"]
                    ],
                    "prompt": params["prompt"],
                    "generation_params": payload
                }
                
        except Exception as e:
            raise ToolError(f"Stability AI generation failed: {str(e)}", self.metadata.name)
    
    async def _openai_generate_image(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """使用OpenAI DALL-E生成图像"""
        try:
            provider_config = self.providers["openai"]
            
            payload = {
                "model": params.get("model", "dall-e-3"),
                "prompt": params["prompt"],
                "size": params.get("size", "1024x1024"),
                "quality": params.get("quality", "standard"),
                "n": 1
            }
            
            if params.get("style"):
                payload["style"] = params["style"]
            
            headers = {
                "Authorization": f"Bearer {provider_config['api_key']}",
                "Content-Type": "application/json"
            }
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{provider_config['base_url']}/images/generations",
                    headers=headers,
                    json=payload
                )
                
                if response.status_code != 200:
                    error_detail = response.text
                    raise ToolError(f"OpenAI DALL-E error: {response.status_code} - {error_detail}", self.metadata.name)
                
                result = response.json()
                
                return {
                    "provider": "openai",
                    "model": payload["model"],
                    "images": [
                        {
                            "url": img["url"],
                            "revised_prompt": img.get("revised_prompt")
                        }
                        for img in result["data"]
                    ],
                    "prompt": params["prompt"],
                    "generation_params": payload
                }
                
        except Exception as e:
            raise ToolError(f"OpenAI DALL-E generation failed: {str(e)}", self.metadata.name)
    
    
    async def _tongyi_generate_image(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """使用通义万相生成图像"""
        try:
            provider_config = self.providers["tongyi"]
            
            payload = {
                "model": params.get("model", "wanx-v1"),
                "input": {
                    "prompt": params["prompt"],
                    "size": params.get("size", "1024*1024"),
                    "n": 1
                },
                "parameters": {
                    "style": params.get("style", "<auto>"),
                    "size": params.get("size", "1024*1024")
                }
            }
            
            if params.get("negative_prompt"):
                payload["input"]["negative_prompt"] = params["negative_prompt"]
            
            headers = {
                "Authorization": f"Bearer {provider_config['api_key']}",
                "Content-Type": "application/json"
            }
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{provider_config['base_url']}/services/aigc/text2image/image-synthesis",
                    headers=headers,
                    json=payload
                )
                
                if response.status_code != 200:
                    error_detail = response.text
                    raise ToolError(f"Tongyi error: {response.status_code} - {error_detail}", self.metadata.name)
                
                result = response.json()
                
                return {
                    "provider": "tongyi",
                    "model": payload["model"],
                    "images": result["output"]["results"],
                    "prompt": params["prompt"],
                    "generation_params": payload
                }
                
        except Exception as e:
            raise ToolError(f"Tongyi generation failed: {str(e)}", self.metadata.name)
    
    async def _batch_generate_images(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """批量生成图像"""
        try:
            prompts = params["prompts"]
            batch_size = params.get("batch_size", len(prompts))
            common_params = params.get("common_params", {})
            
            results = []
            
            # 分批处理
            for i in range(0, len(prompts), batch_size):
                batch_prompts = prompts[i:i+batch_size]
                batch_results = []
                
                for prompt in batch_prompts:
                    try:
                        single_params = {**common_params, "prompt": prompt}
                        result = await self._generate_image(single_params)
                        batch_results.append({
                            "success": True,
                            "prompt": prompt,
                            "result": result
                        })
                    except Exception as e:
                        batch_results.append({
                            "success": False,
                            "prompt": prompt,
                            "error": str(e)
                        })
                
                results.extend(batch_results)
            
            return {
                "batch_results": results,
                "total_prompts": len(prompts),
                "successful_generations": sum(1 for r in results if r["success"]),
                "failed_generations": sum(1 for r in results if not r["success"])
            }
            
        except Exception as e:
            raise ToolError(f"Batch generation failed: {str(e)}", self.metadata.name)
    
    async def _image_to_image(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """图像到图像转换"""
        provider = params.get("provider", self.default_provider)
        
        if provider == "stability":
            return await self._stability_image_to_image(params)
        else:
            raise ToolError(f"Image-to-image not supported for provider {provider}", self.metadata.name)
    
    async def _stability_image_to_image(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Stability AI图像到图像"""
        try:
            provider_config = self.providers["stability"]
            
            # 处理输入图像
            image_data = params["image_url"]
            if image_data.startswith("data:image"):
                # Base64图像
                image_data = image_data.split(",")[1]
            else:
                # URL图像 - 需要下载
                async with httpx.AsyncClient() as client:
                    img_response = await client.get(params["image_url"])
                    image_data = base64.b64encode(img_response.content).decode()
            
            files = {
                "init_image": ("image.png", base64.b64decode(image_data), "image/png"),
                "text_prompts[0][text]": (None, params["prompt"]),
                "text_prompts[0][weight]": (None, "1"),
                "cfg_scale": (None, str(params.get("cfg_scale", 7))),
                "image_strength": (None, str(1 - params.get("strength", 0.35))),
                "steps": (None, str(params.get("steps", 30))),
                "samples": (None, "1")
            }
            
            headers = {
                "Authorization": f"Bearer {provider_config['api_key']}",
                "Accept": "application/json"
            }
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{provider_config['base_url']}/v1/generation/stable-diffusion-xl-1024-v1-0/image-to-image",
                    headers=headers,
                    files=files
                )
                
                if response.status_code != 200:
                    error_detail = response.text
                    raise ToolError(f"Stability AI image-to-image error: {response.status_code} - {error_detail}", self.metadata.name)
                
                result = response.json()
                
                return {
                    "provider": "stability",
                    "images": [
                        {
                            "base64": artifact["base64"],
                            "seed": artifact["seed"],
                            "finish_reason": artifact["finishReason"]
                        }
                        for artifact in result["artifacts"]
                    ],
                    "prompt": params["prompt"],
                    "strength": params.get("strength", 0.35)
                }
                
        except Exception as e:
            raise ToolError(f"Image-to-image generation failed: {str(e)}", self.metadata.name)
    
    async def _upscale_image(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """图像放大"""
        # 这里可以集成Real-ESRGAN或其他放大服务
        raise ToolError("Image upscaling not implemented yet", self.metadata.name)
    
    async def _get_generation_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """获取生成状态（用于异步任务）"""
        # 用于查询长时间运行任务的状态
        task_id = params.get("task_id")
        provider = params.get("provider", self.default_provider)
        
        # 实现状态查询逻辑
        return {
            "task_id": task_id,
            "status": "completed",  # processing, completed, failed
            "provider": provider
        }
    
    def _list_providers(self) -> Dict[str, Any]:
        """列出可用的服务提供商"""
        return {
            "available_providers": list(self.providers.keys()),
            "default_provider": self.default_provider,
            "provider_details": {
                name: {
                    "models": config.get("models", []),
                    "configured": True
                }
                for name, config in self.providers.items()
            }
        }
    
    def _get_provider_models(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """获取提供商支持的模型"""
        provider = params.get("provider")
        
        if provider and provider in self.providers:
            return {
                "provider": provider,
                "models": self.providers[provider].get("models", [])
            }
        else:
            return {
                "all_providers": {
                    name: config.get("models", [])
                    for name, config in self.providers.items()
                }
            }
    
    def _validate_action_parameters(self, action: str, parameters: Dict[str, Any]):
        """验证操作参数"""
        if action == "generate_image":
            if not parameters.get("prompt"):
                raise ToolValidationError("prompt is required for generate_image")
        
        elif action == "batch_generate_images":
            if not parameters.get("prompts"):
                raise ToolValidationError("prompts are required for batch_generate_images")
        
        elif action == "image_to_image":
            if not parameters.get("image_url"):
                raise ToolValidationError("image_url is required for image_to_image")
            if not parameters.get("prompt"):
                raise ToolValidationError("prompt is required for image_to_image")
        
        elif action == "upscale_image":
            if not parameters.get("image_url"):
                raise ToolValidationError("image_url is required for upscale_image")