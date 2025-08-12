"""
Suno AI Music Generation Client Tool
"""

import json
import httpx
import asyncio
import uuid
from typing import Dict, Any, List, Optional

from ..base_tool import AsyncTool, ToolMetadata, ToolType, ToolInput, ToolError, ToolValidationError
from ....services.redis_service import redis_service
from ....core.config import settings


class SunoClientTool(AsyncTool):
    """
    Suno AI Music Generation API客户端工具
    
    支持功能：
    - Text-to-Music：从文本描述生成音乐
    - 背景音乐生成：专门用于视频配乐
    - 纯音乐生成：不含歌词的背景音乐
    - 风格控制：支持多种音乐风格和情绪
    """
    
    @classmethod
    def get_metadata(cls) -> ToolMetadata:
        return ToolMetadata(
            name="suno_client",
            version="1.0.0",
            description="Suno AI音乐生成API客户端，专门用于背景音乐和配乐生成",
            tool_type=ToolType.AI_SERVICE,
            author="system",
            tags=["music", "ai", "suno", "audio", "background-music", "soundtrack"],
            capabilities=[
                "text_to_music",
                "background_music_generation", 
                "instrumental_music",
                "mood_based_generation",
                "style_control",
                "commercial_licensing"
            ],
            limitations=[
                "requires_api_key",
                "rate_limited",
                "10s_to_5min_duration",
                "cost_per_generation"
            ]
        )
    
    def __init__(self, metadata: ToolMetadata = None, config: Dict[str, Any] = None):
        if metadata is None:
            metadata = self.get_metadata()
        super().__init__(metadata, config)
    
    def _initialize(self):
        """初始化Suno AI客户端"""
        # 尝试从配置获取API key
        api_key = self.config.get("api_key")
        if not api_key:
            api_key = settings.SUNO_API_KEY
            if not api_key:
                import os
                api_key = os.getenv("SUNO_API_KEY")
        
        self.api_key = api_key
        self.base_url = self.config.get("base_url", settings.SUNO_BASE_URL)
        self.timeout = self.config.get("timeout", 120)
        
        # 标记是否功能可用
        self._functional = bool(api_key)
        if not self._functional:
            self.logger.warning("SunoClientTool initialized without API key - tool will not be functional")
        
        # 支持的音乐风格
        self.music_styles = [
            "cinematic", "ambient", "electronic", "orchestral", "acoustic",
            "jazz", "classical", "pop", "rock", "folk", "world", "corporate",
            "uplifting", "dramatic", "peaceful", "energetic", "emotional"
        ]
        
        # 支持的情绪类型
        self.mood_types = [
            "happy", "sad", "excited", "calm", "mysterious", "epic",
            "romantic", "adventurous", "peaceful", "intense", "playful", "serious"
        ]
        
        # 默认参数
        self.default_duration = self.config.get("default_duration", 30)  # 30秒
        self.default_style = self.config.get("default_style", "cinematic")
        
        self.logger.info(f"Initialized Suno AI client with base URL: {self.base_url}")
    
    def get_available_actions(self) -> List[str]:
        return [
            "generate_background_music",
            "generate_custom_music", 
            "generate_instrumental",
            "get_generation_status",
            "list_generations"
        ]
    
    def get_action_schema(self, action: str) -> Dict[str, Any]:
        schemas = {
            "generate_background_music": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string", 
                        "description": "音乐描述，例如：'轻松愉快的背景音乐，适合旅行视频'"
                    },
                    "mood": {
                        "type": "string", 
                        "enum": self.mood_types,
                        "description": "音乐情绪"
                    },
                    "style": {
                        "type": "string", 
                        "enum": self.music_styles,
                        "description": "音乐风格"
                    },
                    "duration": {
                        "type": "integer", 
                        "minimum": 10, 
                        "maximum": 300,
                        "description": "音乐时长（秒），10-300秒"
                    },
                    "instrumental": {
                        "type": "boolean", 
                        "default": True,
                        "description": "是否生成纯音乐（无歌词）"
                    },
                    "title": {
                        "type": "string",
                        "description": "音乐标题（可选）"
                    }
                },
                "required": ["description"]
            },
            "generate_custom_music": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "详细的音乐生成提示"},
                    "custom_mode": {"type": "boolean", "default": True},
                    "title": {"type": "string"},
                    "tags": {"type": "string", "description": "音乐标签，例如：'ambient, electronic, chill'"}
                },
                "required": ["prompt"]
            },
            "get_generation_status": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "生成任务ID"}
                },
                "required": ["task_id"]
            }
        }
        
        return schemas.get(action, {})
    
    async def _execute_impl(self, tool_input: ToolInput) -> Any:
        """执行Suno AI API调用"""
        if not self._functional:
            raise ToolError("SunoClientTool not functional - API key required", self.metadata.name)
        
        action = tool_input.action
        params = tool_input.parameters
        
        if action == "generate_background_music":
            return await self._generate_background_music(params)
        elif action == "generate_custom_music":
            return await self._generate_custom_music(params)
        elif action == "generate_instrumental":
            return await self._generate_instrumental(params)
        elif action == "get_generation_status":
            return await self._get_generation_status(params)
        elif action == "list_generations":
            return await self._list_generations(params)
        else:
            raise ToolValidationError(f"Unknown action: {action}", self.metadata.name)
    
    async def _generate_background_music(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """生成背景音乐（专门为视频配乐优化）"""
        try:
            # 构建音乐描述
            description = params["description"]
            mood = params.get("mood", "")
            style = params.get("style", self.default_style)
            duration = params.get("duration", self.default_duration)
            instrumental = params.get("instrumental", True)
            title = params.get("title", "Background Music")
            
            # 构建优化的提示词
            enhanced_prompt = self._build_background_music_prompt(
                description, mood, style, instrumental
            )
            
            # 生成唯一任务ID用于回调跟踪
            callback_task_id = str(uuid.uuid4())
            
            # 检查是否在开发环境（localhost）
            is_dev_environment = "localhost" in settings.PUBLIC_API_URL or "127.0.0.1" in settings.PUBLIC_API_URL
            
            # 构建时长提示 - Suno通过prompt控制时长
            duration_hint = ""
            if duration <= 30:
                duration_hint = "short 30-second track"
            elif duration <= 60:
                duration_hint = "1-minute track"
            elif duration <= 120:
                duration_hint = "2-minute track"
            else:
                duration_hint = f"approximately {duration//60}-minute track"
            
            # 将时长提示加入enhanced_prompt
            enhanced_prompt_with_duration = f"{enhanced_prompt}, {duration_hint}"
            
            payload = {
                "prompt": enhanced_prompt_with_duration,
                "customMode": True,  # 注意：官方API使用customMode而不是custom_mode
                "title": title,
                "style": f"{style}, background music, instrumental, {mood}".strip(", "),
                "instrumental": instrumental,
                "model": "V3_5",  # 使用官方推荐的模型版本
            }
            
            # API要求必须提供callBackUrl，但在开发环境我们使用虚拟URL然后用轮询获取结果
            if not is_dev_environment and self.config.get("use_callback", True):
                payload["callBackUrl"] = await self._generate_callback_url(callback_task_id)
                self.logger.info("使用回调模式（生产环境）")
            else:
                # 开发环境：提供虚拟回调URL但实际使用轮询
                payload["callBackUrl"] = f"http://localhost:8000/api/v1/callbacks/suno/{callback_task_id}"
                self.logger.info("使用轮询模式（开发环境，提供虚拟回调URL）")
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            async with httpx.AsyncClient(timeout=httpx.Timeout(connect=30.0, read=300.0, write=30.0, pool=30.0)) as client:  # 5分钟读取超时
                response = await client.post(
                    f"{self.base_url}/api/v1/generate",
                    headers=headers,
                    json=payload
                )
                
                if response.status_code != 200:
                    error_detail = response.text
                    raise ToolError(f"Suno AI API error: {response.status_code} - {error_detail}", self.metadata.name)
                
                result = response.json()
                
                # 调试：打印完整响应
                self.logger.info(f"Suno API Response: {result}")
                
                # 根据官方API响应格式处理结果
                if result.get("code") == 200:
                    data = result.get("data", {})
                    api_task_id = data.get("taskId", "") or data.get("task_id", "")
                    
                    if api_task_id:
                        # 在开发环境或禁用回调时，直接使用轮询
                        if is_dev_environment or not self.config.get("use_callback", True):
                            self.logger.info(f"使用轮询方式获取结果 (task_id: {api_task_id})")
                            audio_result = await self._poll_generation_status(api_task_id)
                            audio_url = audio_result.get("audio_url", "") if audio_result else ""
                        else:
                            # 生产环境使用回调，失败则降级为轮询
                            try:
                                self.logger.info(f"尝试使用回调方式等待结果 (callback_task_id: {callback_task_id})")
                                audio_result = await self._wait_for_callback_result(callback_task_id)
                                audio_url = audio_result.get("audio_url", "") if audio_result else ""
                            except Exception as callback_error:
                                self.logger.warning(f"回调方式失败，切换到轮询方式: {callback_error}")
                                # 降级为轮询方式
                                audio_result = await self._poll_generation_status(api_task_id)
                                audio_url = audio_result.get("audio_url", "") if audio_result else ""
                        
                        # 更新返回的task_id为API返回的ID
                        callback_task_id = api_task_id
                    else:
                        raise ToolError("No task ID returned from Suno API", self.metadata.name)
                else:
                    error_msg = result.get("msg", "Unknown error")
                    raise ToolError(f"Suno API error: {error_msg}", self.metadata.name)
                
                return {
                    "audio_url": audio_url,
                    "task_id": callback_task_id,
                    "title": title,
                    "duration": duration,
                    "style": style,
                    "mood": mood,
                    "instrumental": instrumental,
                    "prompt_used": enhanced_prompt,
                    "generation_mode": "background_music",
                    "file_format": "mp3",
                    "quality": "128kbps",
                    "commercial_license": True
                }
                
        except httpx.TimeoutException:
            raise ToolError("Suno AI API request timeout", self.metadata.name)
        except Exception as e:
            raise ToolError(f"Background music generation failed: {str(e)}", self.metadata.name)
    
    async def _generate_callback_url(self, task_id: str = None) -> str:
        """生成动态回调URL"""
        if task_id is None:
            task_id = str(uuid.uuid4())
        
        # 构建回调URL，使用配置的公开API URL
        # 在生产环境中，这应该是外部可访问的URL
        base_url = settings.PUBLIC_API_URL
        callback_url = f"{base_url}/api/v1/callbacks/suno/{task_id}"
        
        self.logger.info(f"Generated callback URL for task {task_id}: {callback_url}")
        return callback_url
    
    async def _wait_for_callback_result(self, task_id: str, timeout: int = 300) -> Optional[Dict[str, Any]]:
        """等待回调结果"""
        try:
            self.logger.info(f"Waiting for callback result for task {task_id}")
            
            # 等待回调事件
            event_received = await redis_service.wait_for_callback_event(
                task_id=task_id,
                timeout=timeout,
                check_interval=0.5
            )
            
            if not event_received:
                self.logger.warning(f"Callback timeout for task {task_id}, falling back to polling")
                # 如果回调超时，降级到轮询方式
                return await self._poll_generation_status(task_id, max_attempts=5)
            
            # 获取回调结果
            callback_result = await redis_service.get_callback_result(task_id)
            if not callback_result:
                self.logger.warning(f"No callback result found for task {task_id}, trying polling")
                return await self._poll_generation_status(task_id, max_attempts=5)
            
            # 解析回调结果
            if callback_result.get("status") == "complete":
                # 从回调数据中提取音频信息
                data = callback_result.get("data", {})
                if isinstance(data, dict) and "data" in data:
                    songs = data["data"]
                    if songs and len(songs) > 0:
                        first_song = songs[0]
                        return {
                            "audio_url": first_song.get("audio_url", ""),
                            "title": first_song.get("title", ""),
                            "duration": first_song.get("duration", 0),
                            "task_id": task_id
                        }
                
                # 如果格式不符合预期，尝试直接返回data
                if callback_result.get("code") == 200 and data:
                    return {
                        "audio_url": data.get("audio_url", ""),
                        "title": data.get("title", ""),
                        "duration": data.get("duration", 0),
                        "task_id": task_id
                    }
            
            elif callback_result.get("status") == "failed":
                error_msg = callback_result.get("message", "Music generation failed")
                raise ToolError(f"Suno AI generation failed: {error_msg}", self.metadata.name)
            
            # 其他状态或解析失败，尝试轮询
            self.logger.warning(f"Unexpected callback result format for task {task_id}, falling back to polling")
            return await self._poll_generation_status(task_id, max_attempts=5)
        
        except Exception as e:
            self.logger.error(f"Error waiting for callback result {task_id}: {e}")
            # 发生错误时降级到轮询
            try:
                return await self._poll_generation_status(task_id, max_attempts=5)
            except:
                return None
        
        finally:
            # 清理回调数据
            try:
                await redis_service.cleanup_callback_data(task_id)
            except Exception as e:
                self.logger.warning(f"Failed to cleanup callback data for task {task_id}: {e}")
    
    def _build_background_music_prompt(
        self, 
        description: str, 
        mood: str, 
        style: str, 
        instrumental: bool
    ) -> str:
        """构建背景音乐专用提示词"""
        
        prompt_elements = [
            f"Create {style} background music",
            description
        ]
        
        if mood:
            prompt_elements.append(f"with {mood} mood")
        
        if instrumental:
            prompt_elements.append("instrumental only, no vocals, no lyrics")
        
        # 添加背景音乐特定要求
        background_music_specs = [
            "suitable for video soundtrack",
            "non-distracting",
            "professional quality",
            "seamless looping potential",
            "balanced frequency range"
        ]
        
        prompt_elements.extend(background_music_specs)
        
        enhanced_prompt = ", ".join(prompt_elements)
        
        # 限制提示词长度
        if len(enhanced_prompt) > 400:
            enhanced_prompt = enhanced_prompt[:397] + "..."
        
        return enhanced_prompt
    
    async def _generate_custom_music(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """生成自定义音乐"""
        try:
            payload = {
                "prompt": params["prompt"],
                "custom_mode": params.get("custom_mode", True),
                "title": params.get("title", "Custom Music"),
                "tags": params.get("tags", "custom"),
                "wait_audio": True
            }
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            async with httpx.AsyncClient(timeout=300) as client:
                response = await client.post(
                    f"{self.base_url}/music/custom",
                    headers=headers,
                    json=payload
                )
                
                if response.status_code != 200:
                    error_detail = response.text
                    raise ToolError(f"Custom music generation failed: {response.status_code} - {error_detail}", self.metadata.name)
                
                result = response.json()
                
                return {
                    "audio_url": result.get("audio_url", ""),
                    "task_id": result.get("id", ""),
                    "title": payload["title"],
                    "prompt_used": params["prompt"],
                    "generation_mode": "custom",
                    "tags": payload["tags"]
                }
                
        except Exception as e:
            raise ToolError(f"Custom music generation failed: {str(e)}", self.metadata.name)
    
    async def _poll_generation_status(self, task_id: str, max_attempts: int = 15) -> Dict[str, Any]:
        """轮询音乐生成状态"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        for attempt in range(max_attempts):
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    response = await client.get(
                        f"{self.base_url}/api/v1/generate/record-info?taskId={task_id}",
                        headers=headers
                    )
                    
                    if response.status_code != 200:
                        self.logger.warning(f"Failed to get music status: {response.status_code}")
                        await asyncio.sleep(10)
                        continue
                    
                    result = response.json()
                    
                    # 调试：打印轮询响应
                    self.logger.info(f"Poll response for task {task_id}: {result}")
                    
                    # 根据官方API响应格式检查状态
                    if result.get("code") == 200:
                        data = result.get("data", {})
                        status = data.get("status", "PROCESSING")
                        
                        if status == "SUCCESS" or status == "TEXT_SUCCESS":
                            # 任务完成，提取音频URL
                            # 检查多种可能的响应格式
                            response_data = data.get("response", {})
                            songs = (response_data.get("sunoData", []) or 
                                   response_data.get("data", []) or 
                                   data.get("data", []))
                            
                            if songs and len(songs) > 0:
                                # 取第一首歌的音频URL - 检查多种可能的字段
                                first_song = songs[0]
                                audio_url = (first_song.get("audio_url") or 
                                           first_song.get("audioUrl") or 
                                           first_song.get("streamAudioUrl") or 
                                           first_song.get("stream_audio_url") or "")
                                
                                if audio_url:
                                    self.logger.info(f"Music generation completed: {audio_url[:50]}...")
                                    return {
                                        "audio_url": audio_url,
                                        "title": first_song.get("title", ""),
                                        "duration": first_song.get("duration", 0),
                                        "task_id": task_id,
                                        "tags": first_song.get("tags", ""),
                                        "id": first_song.get("id", "")
                                    }
                            else:
                                self.logger.warning(f"No songs found in response: {data}")
                        
                        elif status == "ERROR" or status == "error":
                            error_msg = data.get("msg", "Music generation failed")
                            raise ToolError(f"Music generation failed: {error_msg}", self.metadata.name)
                        
                        elif status == "GENERATING":
                            self.logger.info(f"Task {task_id} still generating...")
                        elif status == "PROCESSING":
                            self.logger.info(f"Task {task_id} still processing...")
                    
                    else:
                        # API返回错误
                        error_msg = result.get("msg", "Unknown error")
                        self.logger.error(f"API query error: {error_msg}")
                    
                    # 仍在处理中，等待后重试
                    self.logger.info(f"Music generation in progress... ({attempt + 1}/{max_attempts})")
                    await asyncio.sleep(30)
                    
            except httpx.TimeoutException:
                self.logger.warning("Timeout checking music status, retrying...")
                await asyncio.sleep(30)
                continue
            except Exception as e:
                self.logger.error(f"Error polling music result: {e}")
                await asyncio.sleep(30)
                continue
        
        # 超时处理
        self.logger.warning(f"Music generation timeout after {max_attempts * 30} seconds")
        raise ToolError(f"Music generation timeout after {max_attempts * 30} seconds", self.metadata.name)
    
    async def _get_generation_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """获取生成状态"""
        task_id = params["task_id"]
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    f"{self.base_url}/music/{task_id}",
                    headers=headers
                )
                
                if response.status_code != 200:
                    raise ToolError(f"Failed to get status: {response.status_code}", self.metadata.name)
                
                return response.json()
                
        except Exception as e:
            raise ToolError(f"Status check failed: {str(e)}", self.metadata.name)
    
    async def _list_generations(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """列出历史生成记录"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    f"{self.base_url}/music/list",
                    headers=headers
                )
                
                if response.status_code != 200:
                    raise ToolError(f"Failed to list generations: {response.status_code}", self.metadata.name)
                
                return response.json()
                
        except Exception as e:
            raise ToolError(f"List generations failed: {str(e)}", self.metadata.name)
    
    def _validate_action_parameters(self, action: str, parameters: Dict[str, Any]):
        """验证操作参数"""
        if action == "generate_background_music":
            if not parameters.get("description"):
                raise ToolValidationError("description is required for background music generation")
            
            duration = parameters.get("duration", 30)
            if not (10 <= duration <= 300):
                raise ToolValidationError("duration must be between 10 and 300 seconds")
        
        elif action == "generate_custom_music":
            if not parameters.get("prompt"):
                raise ToolValidationError("prompt is required for custom music generation")
        
        elif action == "get_generation_status":
            if not parameters.get("task_id"):
                raise ToolValidationError("task_id is required for status check")