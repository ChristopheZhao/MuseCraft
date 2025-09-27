"""
智谱AI (GLM) Client Tool - 智谱AI API集成
"""

import json
import httpx
import asyncio
from typing import Dict, Any, List, Optional, Union
import base64
import io

from ..base_tool import AsyncTool, ToolMetadata, ToolType, ToolInput, ToolError, ToolValidationError
from ....core.config import settings


class ZhipuClientTool(AsyncTool):
    """
    智谱AI (GLM) API客户端工具
    
    支持功能：
    - GLM-4.5 文本生成和对话
    - GLM-4V 视觉理解
    - 图像生成 (CogView)
    - 视频生成 (CogVideoX)
    - 代码生成 (CodeGeeX)
    """
    
    @classmethod
    def get_metadata(cls) -> ToolMetadata:
        return ToolMetadata(
            name="zhipu_client",
            version="1.0.0",
            description="智谱AI (GLM) API客户端，支持GLM-4.5、图像生成、视频生成等功能",
            tool_type=ToolType.AI_SERVICE,
            author="system",
            tags=["llm", "ai", "zhipu", "glm", "chinese", "image-generation", "video-generation"],
            capabilities=[
                "text_generation",
                "chat_completion",
                "vision_analysis", 
                "image_generation",
                "video_generation",
                "code_generation",
                "chinese_optimization"
            ],
            limitations=[
                "requires_api_key",
                "rate_limited",
                "token_limits",
                "cost_per_usage"
            ]
        )
    
    def __init__(self, metadata: ToolMetadata = None, config: Dict[str, Any] = None):
        if metadata is None:
            metadata = self.get_metadata()
        super().__init__(metadata, config)
    
    def _initialize(self):
        """初始化智谱AI客户端"""
        # 尝试从配置获取API key，如果没有则从环境变量获取
        api_key = self.config.get("api_key")
        if not api_key:
            import os
            api_key = os.getenv("GLM_API_KEY") or os.getenv("ZHIPU_API_KEY")
        
        # 工具可以在没有API key时创建，但在使用时会检查
        self.api_key = api_key
        self.base_url = self.config.get("base_url", "https://open.bigmodel.cn/api/paas/v4")
        self.timeout = self.config.get("timeout", 120)
        
        # 标记是否功能可用
        self._functional = bool(api_key)
        if not self._functional:
            self.logger.warning(f"ZhipuClientTool initialized without API key - tool will not be functional")
        
        # 支持的模型列表
        self.text_models = [
            "glm-4.5",           # GLM-4.5 最新一代
            "glm-4.5-air",       # GLM-4.5 Air 轻量版本
            "glm-4-plus",        # GLM-4 Plus
            "glm-4-0520",        # GLM-4
            "glm-4-long",        # GLM-4 长文本
            "glm-4-airx",        # GLM-4 Air
            "glm-4-air",         # GLM-4 Air
            "glm-4-flash",       # GLM-4 Flash
            "glm-3-turbo",       # GLM-3 Turbo
        ]
        
        self.vision_models = [
            "glm-4v",            # GLM-4V 视觉模型
            "glm-4v-plus",       # GLM-4V Plus
        ]
        
        self.image_models = [
            "cogview-4",         # CogView-4 最新图像生成模型
            "cogview-3",         # CogView-3 图像生成
            "cogview-3-plus",    # CogView-3 Plus
        ]
        
        self.video_models = [
            "cogvideox",         # CogVideoX 视频生成
            "cogvideox-3",       # CogVideoX-3 支持首尾帧
        ]
        
        self.code_models = [
            "codegeex-4",        # CodeGeeX-4 代码生成
        ]
        
        # 优先级：工具配置 > 环境变量/设置 > 硬编码默认
        self.default_model = (
            self.config.get("default_model") or
            "glm-4.5"
        )
        default_max_tokens = self.config.get("default_max_tokens")
        if default_max_tokens is None:
            default_max_tokens = settings.LLM_MAX_TOKENS_STANDARD
        self.default_max_tokens = int(default_max_tokens)
        self.default_temperature = self.config.get("default_temperature", 0.7)
        
        self.logger.info(f"Initialized Zhipu AI client with model: {self.default_model}")
    
    def get_available_actions(self) -> List[str]:
        return [
            "chat_completion",
            "generate_text", 
            "analyze_image",
            "generate_image",
            "generate_video",
            "generate_code",
            "chinese_writing",
            "json_completion",
            "function_call"
        ]
    
    def get_action_schema(self, action: str) -> Dict[str, Any]:
        # 动态读取视频能力（时长选项）以避免写死
        try:
            from ....core.video_config_manager import get_video_config
            _vcaps = get_video_config().get_current_provider_config().duration_capabilities
        except Exception:
            _vcaps = [5, 10]
        schemas = {
            "chat_completion": {
                "type": "object",
                "properties": {
                    "messages": {
                        "type": "array",
                        "items": {
                            "type": "object", 
                            "properties": {
                                "role": {"type": "string", "enum": ["system", "user", "assistant"]},
                                "content": {"type": "string"}
                            },
                            "required": ["role", "content"]
                        }
                    },
                    "model": {"type": "string", "enum": self.text_models},
                    "max_tokens": {"type": "integer"},
                    "temperature": {"type": "number"},
                    "top_p": {"type": "number"},
                    "stream": {"type": "boolean"}
                },
                "required": ["messages"]
            },
            "analyze_image": {
                "type": "object",
                "properties": {
                    "image_url": {"type": "string", "description": "图片URL或base64数据"},
                    "prompt": {"type": "string", "description": "分析提示"},
                    "model": {"type": "string", "enum": self.vision_models}
                },
                "required": ["image_url", "prompt"]
            },
            "generate_image": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "图像生成提示"},
                    "model": {"type": "string", "enum": self.image_models},
                    "size": {"type": "string", "enum": ["1024x1024", "768x1344", "864x1152", "1344x768", "1152x864", "1440x720", "720x1440"]},
                    "quality": {"type": "string", "enum": ["standard", "hd"]},
                    "style": {"type": "string", "enum": ["vivid", "natural"]}
                },
                "required": ["prompt"]
            },
            "generate_video": {
                "type": "object", 
                "properties": {
                    "prompt": {"type": "string", "description": "视频生成提示"},
                    "image_url": {"type": "string", "description": "参考图片URL（可选）"},
                    "first_frame_image": {"type": "string", "description": "首帧图片URL（CogVideoX-3首尾帧模式）"},
                    "last_frame_image": {"type": "string", "description": "尾帧图片URL（CogVideoX-3首尾帧模式）"},
                    "model": {"type": "string", "enum": self.video_models},
                    "duration": {"type": "integer", "description": "视频时长（秒），取值受当前提供商能力限制", "enum": _vcaps}
                },
                "required": ["prompt"]
            },
            "generate_code": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "代码生成需求"},
                    "language": {"type": "string", "description": "编程语言"},
                    "model": {"type": "string", "enum": self.code_models}
                },
                "required": ["prompt"]
            },
            "function_call": {
                "type": "object",
                "properties": {
                    "messages": {
                        "type": "array",
                        "items": {
                            "type": "object", 
                            "properties": {
                                "role": {"type": "string", "enum": ["system", "user", "assistant"]},
                                "content": {"type": "string"}
                            },
                            "required": ["role", "content"]
                        }
                    },
                    "tools": {
                        "type": "array",
                        "description": "可用的工具列表"
                    },
                    "tool_choice": {
                        "type": "string",
                        "description": "工具选择策略",
                        "enum": ["auto", "none"]
                    },
                    "model": {"type": "string", "enum": self.text_models},
                    "temperature": {"type": "number"}
                },
                "required": ["messages", "tools"]
            }
        }
        
        return schemas.get(action, {})
    
    async def _execute_impl(self, tool_input: ToolInput) -> Any:
        """执行智谱AI API调用"""
        # 检查工具是否功能可用
        if not self._functional:
            raise ToolError("ZhipuClientTool not functional - API key required", self.metadata.name)
        
        action = tool_input.action
        params = tool_input.parameters
        
        if action == "chat_completion":
            return await self._chat_completion(params)
        elif action == "generate_text":
            return await self._generate_text(params)
        elif action == "analyze_image":
            return await self._analyze_image(params)
        elif action == "generate_image":
            return await self._generate_image(params)
        elif action == "generate_video":
            return await self._generate_video(params)
        elif action == "generate_code":
            return await self._generate_code(params)
        elif action == "chinese_writing":
            return await self._chinese_writing(params)
        elif action == "json_completion":
            return await self._json_completion(params)
        else:
            raise ToolValidationError(f"Unknown action: {action}", self.metadata.name)
    
    async def _chat_completion(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """对话完成"""
        try:
            payload = {
                "model": params.get("model", self.default_model),
                "messages": params["messages"],
                "max_tokens": params.get("max_tokens", self.default_max_tokens),
                "temperature": params.get("temperature", self.default_temperature),
                "top_p": params.get("top_p", 0.7),
                "stream": params.get("stream", False)
            }
            # 透传 thinking 配置（不强制关闭）
            if "thinking" in params:
                payload["thinking"] = params["thinking"]
            # 透传 do_sample（如调用方提供）
            if "do_sample" in params:
                payload["do_sample"] = params["do_sample"]
            
            # 添加 response_format 参数支持
            if "response_format" in params:
                payload["response_format"] = params["response_format"]
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload
                )
                
                if response.status_code != 200:
                    error_detail = response.text
                    raise ToolError(f"Zhipu AI API error: {response.status_code} - {error_detail}", self.metadata.name)
                
                result = response.json()

                # 提前提取关键字段用于调试日志
                try:
                    choice0 = (result.get("choices") or [{}])[0]
                    message = choice0.get("message") or {}
                    content = message.get("content", "")
                    finish_reason = choice0.get("finish_reason", "")
                    content_len = len(content) if isinstance(content, str) else 0
                    # 记录一次关键调试信息，帮助定位“空内容”场景
                    self.logger.info(
                        f"Chat completion parsed: model={result.get('model')}, "
                        f"finish_reason={finish_reason}, content_len={content_len}, "
                        f"content_preview={repr((content or '')[:80])}"
                    )
                except Exception:
                    # 忽略调试日志异常，避免影响主流程
                    pass

                return {
                    "content": result["choices"][0]["message"]["content"],
                    "model": result["model"],
                    "usage": result.get("usage", {}),
                    "finish_reason": result["choices"][0]["finish_reason"]
                }
                
        except httpx.TimeoutException:
            raise ToolError("Zhipu AI API request timeout", self.metadata.name)
        except Exception as e:
            raise ToolError(f"Chat completion failed: {str(e)}", self.metadata.name)
    
    async def _generate_text(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """文本生成"""
        try:
            messages = [
                {"role": "user", "content": params["prompt"]}
            ]
            
            chat_params = {
                "messages": messages,
                "model": params.get("model", self.default_model),
                "max_tokens": params.get("max_tokens", self.default_max_tokens),
                "temperature": params.get("temperature", self.default_temperature)
            }
            
            # 传递 response_format 参数
            if "response_format" in params:
                chat_params["response_format"] = params["response_format"]
            
            return await self._chat_completion(chat_params)
            
        except Exception as e:
            raise ToolError(f"Text generation failed: {str(e)}", self.metadata.name)
    
    async def _analyze_image(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """图像分析"""
        try:
            image_url = params["image_url"]
            prompt = params["prompt"]
            model = params.get("model", "glm-4v")
            
            # 构建视觉消息
            if image_url.startswith("data:image"):
                # Base64图片
                image_content = {
                    "type": "image_url",
                    "image_url": {"url": image_url}
                }
            else:
                # URL图片
                image_content = {
                    "type": "image_url", 
                    "image_url": {"url": image_url}
                }
            
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        image_content
                    ]
                }
            ]
            
            payload = {
                "model": model,
                "messages": messages,
                "max_tokens": 2000,
                "temperature": 0.3
            }
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload
                )
                
                if response.status_code != 200:
                    error_detail = response.text
                    raise ToolError(f"Image analysis failed: {response.status_code} - {error_detail}", self.metadata.name)
                
                result = response.json()
                
                return {
                    "analysis": result["choices"][0]["message"]["content"],
                    "model": result["model"],
                    "usage": result.get("usage", {})
                }
                
        except Exception as e:
            raise ToolError(f"Image analysis failed: {str(e)}", self.metadata.name)
    
    async def _generate_image(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """图像生成"""
        try:
            payload = {
                "model": params.get("model", "cogview-4"),
                "prompt": params["prompt"],
                "size": params.get("size", "1024x1024"),
                "quality": params.get("quality", "standard"),
                "style": params.get("style", "vivid")
            }

            self.logger.info(f"Image generation payload: {payload}")
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            async with httpx.AsyncClient(timeout=300) as client:  # 图像生成需要更长时间
                response = await client.post(
                    f"{self.base_url}/images/generations",
                    headers=headers,
                    json=payload
                )
                
                if response.status_code != 200:
                    error_detail = response.text
                    raise ToolError(f"Image generation failed: {response.status_code} - {error_detail}", self.metadata.name)
                
                result = response.json()
                
                # 提取第一张图片的URL（智谱AI CogView通常返回一张图片）
                images = result.get("data", [])
                image_url = ""


                if images and len(images) > 0:
                    # 智谱AI API返回格式：{"data": [{"url": "image_url"}]}
                    first_image = images[0]
                    if isinstance(first_image, dict):
                        image_url = first_image.get("url", "")
                    elif isinstance(first_image, str):
                        image_url = first_image
                
                self.logger.info(f"Generated image URL: {image_url[:100]}..." if image_url else "No image URL extracted")
                
                return {
                    "images": images,
                    "image_url": image_url,  # 添加单独的image_url字段供ImageGenerator使用
                    "model": payload["model"],
                    "prompt": params["prompt"],
                    "generation_params": {
                        "size": payload["size"],
                        "quality": payload["quality"],
                        "style": payload["style"]
                    }
                }
                
        except Exception as e:
            raise ToolError(f"Image generation failed: {str(e)}", self.metadata.name)
    
    async def _generate_video(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """视频生成 - 支持首尾帧模式"""
        try:
            payload = {
                "model": params.get("model", "cogvideox"),
                "prompt": params["prompt"]
            }
            
            # 添加视频时长参数（如果API支持）
            duration = params.get("duration")
            if duration:
                payload["duration"] = duration
            
            # 优先使用首尾帧模式（CogVideoX-3）
            if params.get("first_frame_image") and params.get("last_frame_image"):
                # payload["first_frame_image"] = params["first_frame_image"]
                # payload["last_frame_image"] = params["last_frame_image"]
                payload["image_url"] = [params["first_frame_image"], params["last_frame_image"]]
                # 强制使用CogVideoX-3模型
                payload["model"] = "cogvideox-3"
                self.logger.info("Using CogVideoX-3 first/last frame mode")
            
            # 添加参考图片（传统单图模式）
            elif params.get("image_url"):
                payload["image_url"] = params["image_url"]
                self.logger.info("Using traditional single image mode")
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            async with httpx.AsyncClient(timeout=600) as client:  # 视频生成需要很长时间
                response = await client.post(
                    f"{self.base_url}/videos/generations", 
                    headers=headers,
                    json=payload
                )
                
                if response.status_code != 200:
                    error_detail = response.text
                    raise ToolError(f"Video generation failed: {response.status_code} - {error_detail}", self.metadata.name)
                
                result = response.json()
                
                # 智谱AI视频生成返回任务ID，需要轮询获取结果
                video_id = result.get("id")
                if not video_id:
                    raise ToolError("No video ID returned from Zhipu API", self.metadata.name)
                
                self.logger.info(f"Video generation task started: {video_id}")
                
                # 轮询获取视频生成结果
                video_url = await self._poll_video_result(video_id)
                
                # 处理轮询结果
                if video_url:
                    status = "completed"
                else:
                    status = "timeout"
                    self.logger.warning(f"Video {video_id} generation timed out, returning partial result")
                
                return {
                    "video_id": video_id,
                    "status": status,
                    "video_url": video_url,
                    "model": payload["model"],
                    "prompt": params["prompt"],
                    "generation_mode": "first_last_frame" if payload.get("first_frame_image") else "single_image",
                    "duration": params.get("duration", 5.0),  # 使用传入的duration，默认5秒
                    "usage": result.get("usage", {}),
                    "timeout": status == "timeout"  # 添加超时标记
                }
                
        except Exception as e:
            raise ToolError(f"Video generation failed: {str(e)}", self.metadata.name)
    
    async def _poll_video_result(self, video_id: str) -> str:
        """轮询视频生成结果"""
        import time
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        max_attempts = 18  # 最多轮询3分钟 (18次 * 10秒) - 适合Celery任务超时
        attempt = 0
        
        while attempt < max_attempts:
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    response = await client.get(
                        f"{self.base_url}/async-result/{video_id}",
                        headers=headers
                    )
                    
                    if response.status_code != 200:
                        self.logger.warning(f"Failed to get video status: {response.status_code}")
                        await asyncio.sleep(10)
                        attempt += 1
                        continue
                    
                    result = response.json()
                    task_status = result.get("task_status", "processing")
                    
                    if task_status == "SUCCESS":
                        # 详细记录SUCCESS响应以便调试
                        self.logger.info(f"SUCCESS Response: {result}")
                        
                    elif task_status == "processing":
                        # 正常处理中，只记录轮询进度
                        pass
                    else:
                        # 其他状态记录详细信息
                        self.logger.info(f"Status {task_status}: {result}")
                    
                    if task_status == "SUCCESS":
                        # 智谱AI实际的API格式：video_result[0].url
                        video_url = None
                        
                        # 正确的字段路径
                        video_result = result.get("video_result", [])
                        if video_result and len(video_result) > 0:
                            video_url = video_result[0].get("url")
                        
                        if video_url:
                            self.logger.info(f"Video generation completed: {video_url[:50]}...")
                            return video_url
                        else:
                            self.logger.error(f"Video SUCCESS but no URL in video_result - Response: {result}")
                            # 检查是否有video_result但格式不对
                            if video_result:
                                self.logger.error(f"video_result structure: {video_result}")
                            else:
                                self.logger.error("video_result field is missing or empty")
                    
                    elif task_status == "FAIL":
                        error_msg = result.get("message", "Video generation failed")
                        raise ToolError(f"Video generation failed: {error_msg}", self.metadata.name)
                    
                    # 仍在处理中，等待后重试
                    self.logger.info(f"Video generation in progress... ({attempt + 1}/{max_attempts})")
                    await asyncio.sleep(10)  # 等待10秒
                    attempt += 1
                    
            except httpx.TimeoutException:
                self.logger.warning("Timeout checking video status, retrying...")
                await asyncio.sleep(10)
                attempt += 1
                continue
            except Exception as e:
                self.logger.error(f"Error polling video result: {e}")
                await asyncio.sleep(10)
                attempt += 1
                continue
        
        # 超时处理：返回空URL，让系统降级处理
        self.logger.warning(f"Video generation timeout after {max_attempts * 10} seconds, video will be marked as pending")
        return ""  # 返回空字符串，让VideoGenerator处理
    
    async def _generate_code(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """代码生成"""
        try:
            prompt = params["prompt"]
            language = params.get("language", "python")
            
            system_prompt = f"""你是一个专业的{language}代码生成助手。请根据用户需求生成高质量、可运行的代码。
            
要求：
1. 代码要简洁、高效
2. 包含必要的注释
3. 遵循最佳实践
4. 考虑错误处理"""
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ]
            
            chat_params = {
                "messages": messages,
                "model": params.get("model", "codegeex-4"),
                "max_tokens": 4000,
                "temperature": 0.2  # 代码生成使用较低温度
            }
            
            result = await self._chat_completion(chat_params)
            result["language"] = language
            
            return result
            
        except Exception as e:
            raise ToolError(f"Code generation failed: {str(e)}", self.metadata.name)
    
    async def _chinese_writing(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """中文写作"""
        try:
            topic = params["topic"]
            style = params.get("style", "professional")
            length = params.get("length", "medium")
            
            system_prompt = f"""你是一位专业的中文写作助手。请根据主题"{topic}"创作高质量的中文内容。

写作要求：
- 语言表达准确、生动
- 逻辑结构清晰
- 内容有深度和见解
- 适合中文读者阅读习惯"""
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"请以'{topic}'为主题进行创作"}
            ]
            
            chat_params = {
                "messages": messages,
                "model": self.default_model,
                "temperature": 0.8
            }
            
            return await self._chat_completion(chat_params)
            
        except Exception as e:
            raise ToolError(f"Chinese writing failed: {str(e)}", self.metadata.name)
    
    async def _json_completion(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """JSON格式完成"""
        try:
            prompt = params["prompt"]
            schema = params.get("schema")
            
            system_prompt = "你是一个专业的JSON数据生成助手。请根据用户需求生成符合要求的JSON数据，只返回有效的JSON格式。"
            
            if schema:
                system_prompt += f"\n\n请确保返回的JSON符合以下结构：\n{json.dumps(schema, indent=2, ensure_ascii=False)}"
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ]
            
            max_tokens = params.get("max_tokens", self.default_max_tokens)

            chat_params = {
                "messages": messages,
                "model": self.default_model,
                "temperature": 0.3,
                "max_tokens": max_tokens
            }
            
            result = await self._chat_completion(chat_params)
            
            # 尝试解析JSON
            try:
                json_result = json.loads(result["content"])
                result["json_result"] = json_result
                result["valid_json"] = True
            except json.JSONDecodeError:
                # 尝试提取JSON
                import re
                json_match = re.search(r'\{.*\}', result["content"], re.DOTALL)
                if json_match:
                    try:
                        json_result = json.loads(json_match.group())
                        result["json_result"] = json_result
                        result["valid_json"] = True
                    except:
                        result["valid_json"] = False
                        result["error"] = "Failed to parse JSON from response"
                else:
                    result["valid_json"] = False
                    result["error"] = "No JSON found in response"
            
            return result
            
        except Exception as e:
            raise ToolError(f"JSON completion failed: {str(e)}", self.metadata.name)
    
    def _validate_action_parameters(self, action: str, parameters: Dict[str, Any]):
        """验证操作参数"""
        if action == "chat_completion":
            messages = parameters.get("messages", [])
            if not messages:
                raise ToolValidationError("messages are required for chat_completion")
            
            for msg in messages:
                if "role" not in msg or "content" not in msg:
                    raise ToolValidationError("Each message must have 'role' and 'content'")
        
        elif action == "analyze_image":
            if not parameters.get("image_url"):
                raise ToolValidationError("image_url is required for analyze_image")
            if not parameters.get("prompt"):
                raise ToolValidationError("prompt is required for analyze_image")
        
        elif action == "generate_image":
            if not parameters.get("prompt"):
                raise ToolValidationError("prompt is required for generate_image")
        
        elif action == "generate_video":
            if not parameters.get("prompt"):
                raise ToolValidationError("prompt is required for generate_video")
        
        elif action == "generate_code":
            if not parameters.get("prompt"):
                raise ToolValidationError("prompt is required for generate_code")
