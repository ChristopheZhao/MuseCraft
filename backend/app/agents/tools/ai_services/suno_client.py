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
from ....services.prompt_safety import apply_prompt_safety, sanitize_prompt, SafetyContext, sanitize_with_locks
from ....services.prompt_safety.rewrite import (
    is_sensitive_error as ps_is_sensitive_error,
    rewrite_prompt_preserving_locks as ps_rewrite_preserving_locks,
)
from ....core.consistency_policy import get_consistency_policy


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
        # 使用系统音频生成超时作为默认工具超时，提升稳健性
        try:
            default_audio_timeout = int(getattr(settings, 'AUDIO_GENERATION_TOOL_TIMEOUT', 240))
        except Exception:
            default_audio_timeout = 240
        self.timeout = int(self.config.get("timeout", default_audio_timeout))
        # 写回到配置，确保 BaseTool 的超时解析链条可读到
        try:
            self.config["timeout"] = self.timeout
        except Exception:
            pass
        
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

    def get_fc_visibility(self) -> Dict[str, Any]:
        """默认对 FC 暴露安全的合成动作，便于 ReAct 在音频代理中直接调用。
        不暴露状态查询/列表动作给 LLM，减少噪音。
        """
        return {
            "expose": True,
            "allowed_actions": ["generate_background_music"]
        }
    
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
                        "description": "音乐情绪（自由文本，参与提示词构造；例如 calm/epic/mysterious）"
                    },
                    "style": {
                        "type": "string",
                        "description": "音乐风格/体裁（自定义字符串；customMode=true 时必填；长度限制随模型）"
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
                    },
                    "model": {
                        "type": "string",
                        "enum": ["V3_5", "V4", "V4_5"],
                        "description": "Suno 模型版本，影响长度限制（默认 V3_5）"
                    },
                    "negativeTags": {
                        "type": "string",
                        "description": "要排除的风格或特征（可选）"
                    }
                },
                "required": ["description"]
            },
            "generate_custom_music": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "音乐生成提示（customMode=false 时为必填，limit=400）"},
                    "custom_mode": {"type": "boolean", "default": True, "description": "自定义模式（默认 True）"},
                    "title": {"type": "string", "description": "标题（customMode=true 时必填，≤80）"},
                    "style": {"type": "string", "description": "风格关键词（customMode=true 时必填，长度由模型决定）"},
                    "instrumental": {"type": "boolean", "description": "是否纯音乐（影响必填项）"},
                    "model": {"type": "string", "enum": ["V3_5", "V4", "V4_5"], "description": "模型版本，影响长度限制（必填）"},
                    "tags": {"type": "string", "description": "音乐标签，例如：'ambient, electronic, chill'"},
                    "negativeTags": {"type": "string", "description": "要排除的风格或特征（可选）"}
                }
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
            model = params.get("model", "V3_5")

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

            advisor_meta: Dict[str, Any] = {}
            try:
                # 获取安全建议（仅用于日志/遥测，不注入到实际提示词）
                _, advice = apply_prompt_safety(
                    enhanced_prompt_with_duration,
                    SafetyContext(
                        modality="audio",
                        provider="suno",
                        language="en",
                        metadata={
                            "action": "background_music",
                            "title": title,
                            "style": style,
                        },
                    ),
                )
                advisor_meta = (advice.metadata or {}).copy()
                sanitized = sanitize_with_locks(
                    enhanced_prompt_with_duration,
                    [],
                    {
                        "modality": "audio",
                        "tool": self.metadata.name,
                        "action": "background_music",
                        "advisor_layers": advisor_meta.get("applied_layers"),
                    },
                )
                enhanced_prompt_with_duration = sanitized.text or enhanced_prompt_with_duration
                advisor_meta["sanitized_changed"] = sanitized.changed
                advisor_meta["sanitized_matches"] = sanitized.matches
            except Exception as advisor_exc:
                try:
                    self.logger.debug("Prompt safety advisor skipped: %s", advisor_exc)
                except Exception:
                    pass

            # -------- 参数与长度校验（依据官方规则）--------
            custom_mode = True
            prompt_limit, style_limit = self._get_model_limits(model, custom_mode)
            title_limit = 80

            # 必填项校验
            if custom_mode:
                if instrumental:
                    if not style:
                        raise ToolValidationError("style is required when customMode=true and instrumental=true")
                    if not title:
                        raise ToolValidationError("title is required when customMode=true and instrumental=true")
                else:
                    if not style:
                        raise ToolValidationError("style is required when customMode=true and instrumental=false")
                    if not title:
                        raise ToolValidationError("title is required when customMode=true and instrumental=false")
                    if not enhanced_prompt_with_duration:
                        raise ToolValidationError("prompt is required when customMode=true and instrumental=false")

            # 长度限制：不做静默截断，直接报错，便于定位问题
            if len(enhanced_prompt_with_duration) > prompt_limit:
                raise ToolValidationError(
                    f"prompt exceeds limit: {len(enhanced_prompt_with_duration)}/{prompt_limit} (model={model})"
                )
            # style 字段仅使用传入的风格关键词；其他修饰已进 prompt
            style_value = style or ""
            if len(style_value) > style_limit:
                raise ToolValidationError(
                    f"style exceeds limit: {len(style_value)}/{style_limit} (model={model})"
                )
            if title and len(title) > title_limit:
                raise ToolValidationError(
                    f"title exceeds limit: {len(title)}/{title_limit}"
                )
            
            payload = {
                "prompt": enhanced_prompt_with_duration,
                "customMode": True,  # 官方字段
                "title": title,
                # style 仅使用风格关键词，避免超限；mood/instrumental 已进入 prompt
                "style": style_value,
                "instrumental": instrumental,
                "model": model,
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
                    "prompt_used": enhanced_prompt_with_duration,
                    "generation_mode": "background_music",
                    "file_format": "mp3",
                    "quality": "128kbps",
                    "commercial_license": True,
                    "prompt_safety": advisor_meta,
                }
                
        except httpx.TimeoutException as te:
            raise ToolError("Suno AI API request timeout", self.metadata.name) from te
        except ToolError as terr:
            # 仅敏感/违规错误时尝试一次轻量重写
            try:
                policy = get_consistency_policy()
                ps_cfg = getattr(policy, "prompt_safety", None)
                enable_rewrite = bool(getattr(ps_cfg, "enable_rewrite_on_sensitive_error", False))
                rewrite_model = getattr(ps_cfg, "rewrite_model", None)
            except Exception:
                enable_rewrite = False
                rewrite_model = None

            if enable_rewrite and ps_is_sensitive_error(terr):
                rewritten, telemetry = await ps_rewrite_preserving_locks(
                    enhanced_prompt_with_duration,
                    [],
                    model=rewrite_model,
                    language="en",
                    metadata={"action": "background_music", "tool": self.metadata.name},
                )
                try:
                    self.logger.info(
                        "prompt_rewrite(audio): applied=%s reason=sensitive_error model=%s tokens=%s",
                        bool(rewritten), telemetry.get("model"), telemetry.get("tokens")
                    )
                except Exception:
                    pass
                if rewritten and rewritten.strip() and rewritten.strip() != enhanced_prompt_with_duration:
                    # 重试一次
                    payload_retry = dict(payload)
                    payload_retry["prompt"] = rewritten.strip()
                    # 保留日志
                    try:
                        self.logger.info(
                            "PROMPT_COMBINED(generate_audio:rewrite): len=%d bytes text=%s",
                            len(payload_retry["prompt"].encode("utf-8")),
                            payload_retry["prompt"],
                        )
                    except Exception:
                        pass
                    async with httpx.AsyncClient(timeout=httpx.Timeout(connect=30.0, read=300.0, write=30.0, pool=30.0)) as client:
                        response = await client.post(
                            f"{self.base_url}/api/v1/generate",
                            headers=headers,
                            json=payload_retry,
                        )
                        if response.status_code != 200:
                            raise ToolError(
                                f"Suno AI API error: {response.status_code} - {response.text}", self.metadata.name
                            )
                        result = response.json()
                        if result.get("code") == 200:
                            data = result.get("data", {})
                            api_task_id = data.get("taskId", "") or data.get("task_id", "")
                            if not api_task_id:
                                raise ToolError("No task ID returned from Suno API", self.metadata.name)
                            # 回用原有分支（轮询/回调）简化：直接用轮询
                            audio_result = await self._poll_generation_status(api_task_id)
                            audio_url = audio_result.get("audio_url", "") if audio_result else ""
                            return {
                                "audio_url": audio_url,
                                "task_id": api_task_id,
                                "title": title,
                                "duration": duration,
                                "style": style,
                                "mood": mood,
                                "instrumental": instrumental,
                                "prompt_used": payload_retry["prompt"],
                                "generation_mode": "background_music",
                                "file_format": "mp3",
                                "quality": "128kbps",
                                "commercial_license": True,
                                "prompt_safety_rewrite": {
                                    "applied": True,
                                    "reason": "sensitive_error",
                                    "model": rewrite_model,
                                },
                                "prompt_safety": advisor_meta,
                            }
            # 非敏感或重写失败：交由上层
            raise
        except Exception as e:
            raise ToolError(f"Background music generation failed: {str(e)}", self.metadata.name) from e
    
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
        
        # 添加背景音乐特定要求（进入 prompt，而非 style 字段）
        background_music_specs = [
            "suitable for video soundtrack",
            "non-distracting",
            "professional quality",
            "seamless looping potential",
            "balanced frequency range"
        ]
        
        prompt_elements.extend(background_music_specs)
        
        enhanced_prompt = ", ".join(prompt_elements)
        return enhanced_prompt
    
    async def _generate_custom_music(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """生成自定义音乐"""
        try:
            # 读取参数
            custom_mode = params.get("custom_mode", True)
            instrumental = params.get("instrumental", False)
            model = params.get("model", "V3_5")
            prompt = params.get("prompt", "")
            title = params.get("title", "")
            style = params.get("style", "")
            tags = params.get("tags", "custom")

            # 规则校验（不做静默截断）
            prompt_limit, style_limit = self._get_model_limits(model, custom_mode)
            if custom_mode:
                if instrumental:
                    if not (style and title):
                        raise ToolValidationError("customMode=true & instrumental=true requires style and title")
                else:
                    if not (style and title and prompt):
                        raise ToolValidationError("customMode=true & instrumental=false requires style, title and prompt")
                if prompt and len(prompt) > prompt_limit:
                    raise ToolValidationError(f"prompt exceeds limit: {len(prompt)}/{prompt_limit} (model={model})")
                if style and len(style) > style_limit:
                    raise ToolValidationError(f"style exceeds limit: {len(style)}/{style_limit} (model={model})")
                if title and len(title) > 80:
                    raise ToolValidationError(f"title exceeds limit: {len(title)}/80")
                payload = {
                    "prompt": prompt,
                    "customMode": True,
                    "title": title,
                    "style": style,
                    "instrumental": instrumental,
                    "model": model,
                    "tags": tags,
                    "wait_audio": True
                }
            else:
                # 非自定义模式：只需要 prompt 且不超过 400，其它参数必须为空
                if not prompt:
                    raise ToolValidationError("prompt is required when customMode=false")
                if len(prompt) > prompt_limit:
                    raise ToolValidationError(f"prompt exceeds non-custom limit: {len(prompt)}/{prompt_limit}")
                for k in ("title", "style", "tags", "instrumental"):
                    if params.get(k):
                        raise ToolValidationError(f"'{k}' must be empty when customMode=false")
                payload = {
                    "prompt": prompt,
                    "customMode": False,
                    "wait_audio": True
                }
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            # 自定义模式需要回调URL；在开发环境下提供本地URL并使用轮询
            callback_task_id = str(uuid.uuid4())
            is_dev_environment = "localhost" in settings.PUBLIC_API_URL or "127.0.0.1" in settings.PUBLIC_API_URL
            if custom_mode:
                if not is_dev_environment and self.config.get("use_callback", True):
                    payload["callBackUrl"] = await self._generate_callback_url(callback_task_id)
                else:
                    payload["callBackUrl"] = f"http://localhost:8000/api/v1/callbacks/suno/{callback_task_id}"

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
                
                # 若 custom_mode=true 且在开发环境，尝试轮询获取音频链接
                audio_url = result.get("audio_url", "")
                api_task_id = result.get("id", "") or result.get("taskId", "")
                if custom_mode and (is_dev_environment or not self.config.get("use_callback", True)):
                    try:
                        if api_task_id:
                            polled = await self._poll_generation_status(api_task_id)
                            audio_url = polled.get("audio_url", audio_url)
                    except Exception as e:
                        self.logger.warning(f"Custom music polling failed: {e}")

                return {
                    "audio_url": audio_url,
                    "task_id": api_task_id or callback_task_id,
                    "title": payload.get("title", ""),
                    "prompt_used": payload.get("prompt", ""),
                    "generation_mode": "custom" if custom_mode else "non_custom",
                    "tags": payload.get("tags", "")
                }
                
        except Exception as e:
            raise ToolError(f"Custom music generation failed: {str(e)}", self.metadata.name)
    
    async def _poll_generation_status(self, task_id: str, max_attempts: Optional[int] = None) -> Dict[str, Any]:
        """轮询音乐生成状态"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        attempts = max_attempts if isinstance(max_attempts, int) and max_attempts > 0 else getattr(settings, "SUNO_POLL_MAX_ATTEMPTS", 20)
        poll_interval = max(5, getattr(settings, "SUNO_POLL_INTERVAL_SECONDS", 30))
        
        for attempt in range(attempts):
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    response = await client.get(
                        f"{self.base_url}/api/v1/generate/record-info?taskId={task_id}",
                        headers=headers
                    )
                    
                    if response.status_code != 200:
                        self.logger.warning(f"Failed to get music status: {response.status_code}")
                        await asyncio.sleep(poll_interval)
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
                    self.logger.info(f"Music generation in progress... ({attempt + 1}/{attempts})")
                    await asyncio.sleep(poll_interval)
                    
            except httpx.TimeoutException:
                self.logger.warning("Timeout checking music status, retrying...")
                await asyncio.sleep(poll_interval)
                continue
            except Exception as e:
                self.logger.error(f"Error polling music result: {e}")
                await asyncio.sleep(poll_interval)
                continue
        
        # 超时处理
        total_wait = attempts * poll_interval
        self.logger.warning(f"Music generation timeout after {total_wait} seconds")
        raise ToolError(f"Music generation timeout after {total_wait} seconds", self.metadata.name)
    
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

    def _get_model_limits(self, model: str, custom_mode: bool) -> (int, int):
        """根据官方规则返回 (prompt_limit, style_limit)。custom_mode=False 时 style_limit 无意义。"""
        m = (model or "").upper()
        if custom_mode:
            if m in ("V3_5", "V4"):
                return 3000, 200
            elif m in ("V4_5", "V4_5PLUS"):
                return 5000, 1000
            # 未知模型采用保守默认
            return 3000, 200
        else:
            # 非自定义模式仅限制 prompt=400
            return 400, 0
    
    def _validate_action_parameters(self, action: str, parameters: Dict[str, Any]):
        """验证操作参数"""
        if action == "generate_background_music":
            if not parameters.get("description"):
                raise ToolValidationError("description is required for background music generation")
            # Suno 并不支持精确 duration 参数控制；这里将其视为提示词的“倾向”而非硬约束。
            # 若传入范围外，仅记录提示，不再抛错，由上层在 prompt 中构造时长 hint，并在生成后用处理工具对齐精确时长。
            try:
                duration = int(parameters.get("duration", 30))
                if not (10 <= duration <= 300):
                    self.logger.info(
                        f"Suno duration hint out of recommended range: {duration}; proceeding as hint only"
                    )
            except Exception:
                pass
        
        elif action == "generate_custom_music":
            # customMode 规则：
            custom_mode = parameters.get("custom_mode", True)
            instrumental = parameters.get("instrumental", False)
            model = parameters.get("model", "V3_5")

            prompt = parameters.get("prompt", "")
            title = parameters.get("title", "")
            style = parameters.get("style", "")

            prompt_limit, style_limit = self._get_model_limits(model, custom_mode)

            if custom_mode:
                # 必填约束
                if instrumental:
                    if not (style and title):
                        raise ToolValidationError("customMode=true & instrumental=true requires style and title")
                else:
                    if not (style and title and prompt):
                        raise ToolValidationError("customMode=true & instrumental=false requires style, title and prompt")
                # 长度约束
                if prompt and len(prompt) > prompt_limit:
                    raise ToolValidationError(f"prompt exceeds limit: {len(prompt)}/{prompt_limit} (model={model})")
                if style and len(style) > style_limit:
                    raise ToolValidationError(f"style exceeds limit: {len(style)}/{style_limit} (model={model})")
                if title and len(title) > 80:
                    raise ToolValidationError(f"title exceeds limit: {len(title)}/80")
            else:
                # 非自定义模式：只需要 prompt，其他参数应为空
                if not prompt:
                    raise ToolValidationError("prompt is required when customMode=false")
                if len(prompt) > prompt_limit:  # 400
                    raise ToolValidationError(f"prompt exceeds non-custom limit: {len(prompt)}/{prompt_limit}")
                # 其它参数需为空
                for k in ("title", "style", "tags", "instrumental"):
                    if parameters.get(k):
                        raise ToolValidationError(f"'{k}' must be empty when customMode=false")
        
        elif action == "get_generation_status":
            if not parameters.get("task_id"):
                raise ToolValidationError("task_id is required for status check")
