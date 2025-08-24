"""
智谱AI服务具体实现 - 基于分层抽象接口
"""

import json
import httpx
import asyncio
from typing import Dict, Any, List, Optional, Union
import logging

from .service_interfaces import LLMServiceInterface, VLMServiceInterface, VideoModelServiceInterface, ServiceProvider


class ZhipuLLMService(LLMServiceInterface):
    """
    智谱AI LLM服务实现
    
    支持模型：
    - GLM-4.5, GLM-4-plus (推理能力强)
    - GLM-4-air, GLM-4-flash (快速响应)
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # 配置初始化
        self.api_key = self._get_api_key()
        self.base_url = self.config.get("base_url", "https://open.bigmodel.cn/api/paas/v4")
        self.timeout = self.config.get("timeout", 120)
        
        # 支持的模型
        self.supported_models = [
            "glm-4.5", "glm-4.5-air", "glm-4-plus", 
            "glm-4-0520", "glm-4-air", "glm-4-flash"
        ]
        self.default_model = self.config.get("default_model", "glm-4.5")
    
    def _get_api_key(self) -> Optional[str]:
        """获取API密钥"""
        api_key = self.config.get("api_key")
        if not api_key:
            import os
            api_key = os.getenv("GLM_API_KEY") or os.getenv("ZHIPU_API_KEY")
        return api_key
    
    def is_available(self) -> bool:
        """检查服务是否可用"""
        return bool(self.api_key)
    
    def get_provider_name(self) -> str:
        """获取供应商名称"""
        return ServiceProvider.ZHIPU.value
    
    def get_supported_models(self) -> List[str]:
        """获取支持的LLM模型列表"""
        return self.supported_models.copy()
    
    async def chat_completion(
        self, 
        messages: List[Dict[str, Any]], 
        model: str = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        **kwargs
    ) -> Dict[str, Any]:
        """基础对话完成"""
        
        if not self.is_available():
            raise RuntimeError("ZhipuLLMService not available - API key required")
        
        payload = {
            "model": model or self.default_model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": kwargs.get("top_p", 0.7),
            "stream": kwargs.get("stream", False)
        }
        
        # 添加 response_format 参数支持
        if "response_format" in kwargs:
            payload["response_format"] = kwargs["response_format"]
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload
                )
                
                if response.status_code != 200:
                    error_detail = response.text
                    raise RuntimeError(f"Zhipu LLM API error: {response.status_code} - {error_detail}")
                
                result = response.json()
                
                return {
                    "content": result["choices"][0]["message"]["content"],
                    "model": result["model"],
                    "usage": result.get("usage", {}),
                    "finish_reason": result["choices"][0]["finish_reason"],
                    "provider": self.get_provider_name()
                }
                
        except httpx.TimeoutException:
            raise RuntimeError("Zhipu LLM API request timeout")
        except Exception as e:
            raise RuntimeError(f"Zhipu LLM chat completion failed: {str(e)}")
    
    async def function_call(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]], 
        tool_choice: str = "auto",
        model: str = None,
        temperature: float = 0.3,
        **kwargs
    ) -> Dict[str, Any]:
        """Function Call功能 - 核心智能决策能力"""
        
        if not self.is_available():
            raise RuntimeError("ZhipuLLMService not available - API key required")
        
        payload = {
            "model": model or self.default_model,
            "messages": messages,
            "tools": tools,
            "tool_choice": tool_choice,
            "temperature": temperature,
            "max_tokens": kwargs.get("max_tokens", 2000)
        }
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload
                )
                
                if response.status_code != 200:
                    error_detail = response.text
                    raise RuntimeError(f"Zhipu Function Call API error: {response.status_code} - {error_detail}")
                
                result = response.json()
                choice = result["choices"][0]
                
                # 解析Function Call响应
                response_data = {
                    "model": result["model"],
                    "usage": result.get("usage", {}),
                    "finish_reason": choice["finish_reason"],
                    "provider": self.get_provider_name()
                }
                
                if choice["finish_reason"] == "tool_calls" and choice["message"].get("tool_calls"):
                    # 有Function Call
                    tool_calls = choice["message"]["tool_calls"]
                    response_data.update({
                        "tool_calls": tool_calls,
                        "has_function_call": True
                    })
                else:
                    # 普通文本响应
                    response_data.update({
                        "content": choice["message"]["content"],
                        "has_function_call": False
                    })
                
                return response_data
                
        except httpx.TimeoutException:
            raise RuntimeError("Zhipu Function Call API request timeout")
        except Exception as e:
            raise RuntimeError(f"Zhipu Function Call failed: {str(e)}")
    
    async def structured_generation(
        self,
        prompt: str,
        schema: Dict[str, Any] = None,
        model: str = None,
        **kwargs  
    ) -> Dict[str, Any]:
        """结构化内容生成（JSON等）"""
        
        system_prompt = "你是一个专业的结构化数据生成助手。请根据用户需求生成符合要求的JSON数据，只返回有效的JSON格式。"
        
        if schema:
            system_prompt += f"\n\n请确保返回的JSON符合以下结构：\n{json.dumps(schema, indent=2, ensure_ascii=False)}"
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]
        
        result = await self.chat_completion(
            messages=messages,
            model=model,
            temperature=kwargs.get("temperature", 0.3)
        )
        
        # 尝试解析JSON
        try:
            json_result = json.loads(result["content"])
            result.update({
                "structured_data": json_result,
                "valid_json": True
            })
        except json.JSONDecodeError:
            # 尝试提取JSON
            import re
            json_match = re.search(r'\{.*\}', result["content"], re.DOTALL)
            if json_match:
                try:
                    json_result = json.loads(json_match.group())
                    result.update({
                        "structured_data": json_result,
                        "valid_json": True
                    })
                except:
                    result.update({
                        "valid_json": False,
                        "error": "Failed to parse JSON from response"
                    })
            else:
                result.update({
                    "valid_json": False,
                    "error": "No JSON found in response"
                })
        
        return result


class ZhipuVLMService(VLMServiceInterface):
    """
    智谱AI VLM服务实现
    
    支持功能：
    - 图像理解：GLM-4V, GLM-4V-plus
    - 图像生成：CogView-3, CogView-4
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # 配置初始化
        self.api_key = self._get_api_key()
        self.base_url = self.config.get("base_url", "https://open.bigmodel.cn/api/paas/v4")
        self.timeout = self.config.get("timeout", 300)  # 图像生成需要更长时间
        
        # 支持的模型
        self.vision_models = ["glm-4v", "glm-4v-plus"]
        self.generation_models = ["cogview-3", "cogview-3-plus", "cogview-4"]
    
    def _get_api_key(self) -> Optional[str]:
        """获取API密钥"""
        api_key = self.config.get("api_key")
        if not api_key:
            import os
            api_key = os.getenv("GLM_API_KEY") or os.getenv("ZHIPU_API_KEY")
        return api_key
    
    def is_available(self) -> bool:
        """检查服务是否可用"""
        return bool(self.api_key)
    
    def get_provider_name(self) -> str:
        """获取供应商名称"""
        return ServiceProvider.ZHIPU.value
    
    def get_supported_models(self) -> Dict[str, List[str]]:
        """获取支持的VLM模型列表 - 按功能分类"""
        return {
            "vision": self.vision_models.copy(),
            "generation": self.generation_models.copy()
        }
    
    async def image_understanding(
        self,
        image_input: Union[str, bytes],
        prompt: str,
        model: str = None,
        **kwargs
    ) -> Dict[str, Any]:
        """图像理解和分析"""
        
        if not self.is_available():
            raise RuntimeError("ZhipuVLMService not available - API key required")
        
        # 构建视觉消息
        if isinstance(image_input, str) and image_input.startswith("data:image"):
            # Base64图片
            image_content = {
                "type": "image_url",
                "image_url": {"url": image_input}
            }
        else:
            # URL图片
            image_content = {
                "type": "image_url", 
                "image_url": {"url": image_input}
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
            "model": model or "glm-4v",
            "messages": messages,
            "max_tokens": 2000,
            "temperature": kwargs.get("temperature", 0.3)
        }
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload
                )
                
                if response.status_code != 200:
                    error_detail = response.text
                    raise RuntimeError(f"Zhipu VLM API error: {response.status_code} - {error_detail}")
                
                result = response.json()
                
                return {
                    "analysis": result["choices"][0]["message"]["content"],
                    "model": result["model"],
                    "usage": result.get("usage", {}),
                    "provider": self.get_provider_name()
                }
                
        except httpx.TimeoutException:
            raise RuntimeError("Zhipu VLM API request timeout")
        except Exception as e:
            raise RuntimeError(f"Zhipu image understanding failed: {str(e)}")
    
    async def image_generation(
        self,
        prompt: str,
        model: str = None,
        size: str = "1024x1024",
        style: str = "vivid",
        quality: str = "standard",
        **kwargs
    ) -> Dict[str, Any]:
        """图像生成"""
        
        if not self.is_available():
            raise RuntimeError("ZhipuVLMService not available - API key required")
        
        payload = {
            "model": model or "cogview-4",
            "prompt": prompt,
            "size": size,
            "quality": quality,
            "style": style
        }
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/images/generations",
                    headers=headers,
                    json=payload
                )
                
                if response.status_code != 200:
                    error_detail = response.text
                    raise RuntimeError(f"Zhipu image generation API error: {response.status_code} - {error_detail}")
                
                result = response.json()
                
                # 提取图片URL
                images = result.get("data", [])
                image_url = ""
                
                if images and len(images) > 0:
                    first_image = images[0]
                    if isinstance(first_image, dict):
                        image_url = first_image.get("url", "")
                    elif isinstance(first_image, str):
                        image_url = first_image
                
                return {
                    "images": images,
                    "image_url": image_url,
                    "model": payload["model"],
                    "prompt": prompt,
                    "generation_params": {
                        "size": size,
                        "quality": quality,
                        "style": style
                    },
                    "provider": self.get_provider_name()
                }
                
        except httpx.TimeoutException:
            raise RuntimeError("Zhipu image generation API request timeout")
        except Exception as e:
            raise RuntimeError(f"Zhipu image generation failed: {str(e)}")
    
    async def image_editing(
        self,
        image_input: Union[str, bytes],
        prompt: str,
        model: str = None,
        **kwargs
    ) -> Dict[str, Any]:
        """图像编辑（智谱AI暂不支持，返回未实现错误）"""
        raise NotImplementedError("Image editing not yet supported by Zhipu AI")


class ZhipuVideoService(VideoModelServiceInterface):
    """
    智谱AI 视频服务实现
    
    支持模型：
    - CogVideoX, CogVideoX-3 (支持首尾帧模式)
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # 配置初始化
        self.api_key = self._get_api_key()
        self.base_url = self.config.get("base_url", "https://open.bigmodel.cn/api/paas/v4")
        self.timeout = self.config.get("timeout", 600)  # 视频生成需要很长时间
        
        # 支持的模型和能力
        self.supported_models = ["cogvideox", "cogvideox-3"]
        self.duration_capabilities = [5, 10]  # CogVideoX支持的时长
        self.supports_first_last = True  # CogVideoX-3支持首尾帧模式
    
    def _get_api_key(self) -> Optional[str]:
        """获取API密钥"""
        api_key = self.config.get("api_key")
        if not api_key:
            import os
            api_key = os.getenv("GLM_API_KEY") or os.getenv("ZHIPU_API_KEY")
        return api_key
    
    def is_available(self) -> bool:
        """检查服务是否可用"""
        return bool(self.api_key)
    
    def get_provider_name(self) -> str:
        """获取供应商名称"""
        return ServiceProvider.ZHIPU.value
    
    def get_supported_models(self) -> List[str]:
        """获取支持的视频模型列表"""
        return self.supported_models.copy()
    
    def get_duration_capabilities(self) -> List[int]:
        """获取支持的视频时长选项"""
        return self.duration_capabilities.copy()
    
    def supports_first_last_frame(self) -> bool:
        """是否支持首尾帧模式"""
        return self.supports_first_last
    
    async def generate_video(
        self,
        prompt: str,
        model: str = None,
        duration: int = 5,
        image_url: str = None,
        first_frame_image: str = None,
        last_frame_image: str = None,
        **kwargs
    ) -> Dict[str, Any]:
        """视频生成 - 支持多种输入模式"""
        
        if not self.is_available():
            raise RuntimeError("ZhipuVideoService not available - API key required")
        
        payload = {
            "model": model or "cogvideox",
            "prompt": prompt
        }
        
        # 添加视频时长参数
        if duration:
            payload["duration"] = duration
        
        # 优先使用首尾帧模式（CogVideoX-3）
        if first_frame_image and last_frame_image:
            payload["image_url"] = [first_frame_image, last_frame_image]
            # 强制使用CogVideoX-3模型
            payload["model"] = "cogvideox-3"
            generation_mode = "first_last_frame"
            self.logger.info("Using CogVideoX-3 first/last frame mode")
        
        # 添加参考图片（传统单图模式）
        elif image_url:
            payload["image_url"] = image_url
            generation_mode = "single_image"
            self.logger.info("Using traditional single image mode")
        else:
            generation_mode = "text_only"
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/videos/generations", 
                    headers=headers,
                    json=payload
                )
                
                if response.status_code != 200:
                    error_detail = response.text
                    raise RuntimeError(f"Zhipu video generation API error: {response.status_code} - {error_detail}")
                
                result = response.json()
                
                # 智谱AI视频生成返回任务ID，需要轮询获取结果
                video_id = result.get("id")
                if not video_id:
                    raise RuntimeError("No video ID returned from Zhipu API")
                
                self.logger.info(f"Video generation task started: {video_id}")
                
                # 轮询获取视频生成结果
                video_url = await self._poll_video_result(video_id)
                
                # 处理轮询结果
                if video_url:
                    status = "completed"
                else:
                    status = "timeout"
                    self.logger.warning(f"Video {video_id} generation timed out")
                
                return {
                    "video_id": video_id,
                    "status": status,
                    "video_url": video_url,
                    "model": payload["model"],
                    "prompt": prompt,
                    "generation_mode": generation_mode,
                    "duration": duration,
                    "usage": result.get("usage", {}),
                    "timeout": status == "timeout",
                    "provider": self.get_provider_name()
                }
                
        except httpx.TimeoutException:
            raise RuntimeError("Zhipu video generation API request timeout")
        except Exception as e:
            raise RuntimeError(f"Zhipu video generation failed: {str(e)}")
    
    async def get_generation_status(
        self,
        task_id: str,
        **kwargs
    ) -> Dict[str, Any]:
        """获取视频生成状态（异步任务）"""
        
        if not self.is_available():
            raise RuntimeError("ZhipuVideoService not available - API key required")
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    f"{self.base_url}/async-result/{task_id}",
                    headers=headers
                )
                
                if response.status_code != 200:
                    raise RuntimeError(f"Failed to get video status: {response.status_code}")
                
                result = response.json()
                task_status = result.get("task_status", "processing")
                
                status_info = {
                    "task_id": task_id,
                    "status": task_status,
                    "provider": self.get_provider_name()
                }
                
                if task_status == "SUCCESS":
                    video_result = result.get("video_result", [])
                    if video_result and len(video_result) > 0:
                        status_info["video_url"] = video_result[0].get("url")
                
                elif task_status == "FAIL":
                    status_info["error"] = result.get("message", "Video generation failed")
                
                return status_info
                
        except Exception as e:
            raise RuntimeError(f"Failed to get video status: {str(e)}")
    
    async def _poll_video_result(self, video_id: str) -> str:
        """轮询视频生成结果"""
        
        max_attempts = 18  # 最多轮询3分钟 (18次 * 10秒)
        attempt = 0
        
        while attempt < max_attempts:
            try:
                status_info = await self.get_generation_status(video_id)
                
                if status_info["status"] == "SUCCESS":
                    video_url = status_info.get("video_url")
                    if video_url:
                        self.logger.info(f"Video generation completed: {video_url[:50]}...")
                        return video_url
                    else:
                        self.logger.error(f"Video SUCCESS but no URL - Response: {status_info}")
                
                elif status_info["status"] == "FAIL":
                    error_msg = status_info.get("error", "Video generation failed")
                    raise RuntimeError(f"Video generation failed: {error_msg}")
                
                # 仍在处理中，等待后重试
                self.logger.info(f"Video generation in progress... ({attempt + 1}/{max_attempts})")
                await asyncio.sleep(10)  # 等待10秒
                attempt += 1
                
            except Exception as e:
                self.logger.error(f"Error polling video result: {e}")
                await asyncio.sleep(10)
                attempt += 1
                continue
        
        # 超时处理：返回空URL，让系统降级处理
        self.logger.warning(f"Video generation timeout after {max_attempts * 10} seconds")
        return ""  # 返回空字符串，让调用方处理