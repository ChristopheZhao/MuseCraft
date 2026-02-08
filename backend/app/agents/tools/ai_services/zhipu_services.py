"""
智谱AI服务具体实现 - 基于分层抽象接口
"""

import json
import httpx
import asyncio
from typing import Dict, Any, List, Optional, Union
import logging

from .service_interfaces import (
    LLMServiceInterface,
    VLMServiceInterface,
    VideoModelServiceInterface,
    ServiceProvider,
    PromptCapability,
    VideoCapabilities,
    EnumCapability,
)
from ....core.config import settings


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
            "glm-4.7", "glm-4.5", "glm-4.5-air", "glm-4-plus",
            "glm-4-0520", "glm-4-air", "glm-4-flash"
        ]
        self.default_model = self.config.get("default_model", "glm-4.5")
    
    def _get_api_key(self) -> Optional[str]:
        """获取API密钥（配置 > 环境变量 > settings）"""
        api_key = self.config.get("api_key")
        if not api_key:
            import os
            api_key = os.getenv("GLM_API_KEY") or os.getenv("ZHIPU_API_KEY")
        if not api_key:
            try:
                from ....core.config import settings
                api_key = settings.GLM_API_KEY or os.getenv("ZHIPU_API_KEY")
            except Exception:
                pass
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
        # 透传 thinking（GLM-4.5+ 支持），例如 {"type": "disabled"}
        if "thinking" in kwargs and kwargs["thinking"] is not None:
            payload["thinking"] = kwargs["thinking"]
        
        # 透传 response_format（若供应商支持则生效）
        if "response_format" in kwargs and kwargs["response_format"]:
            payload["response_format"] = kwargs["response_format"]
            try:
                rf = payload.get("response_format")
                self.logger.info(f"Zhipu.chat_completion using response_format={rf} max_tokens={payload.get('max_tokens')}")
            except Exception:
                pass
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # 计算本次请求的有效超时：优先 request_timeout；否则按模型配置；最后退回 provider 级
        effective_timeout = None
        try:
            req_to = kwargs.get("request_timeout")
            if req_to is not None:
                effective_timeout = float(req_to)
            else:
                # 尝试读取模型级超时
                if model:
                    try:
                        from ....core.ai_config import get_ai_config  # type: ignore
                        mc = get_ai_config().get_model_config(model)
                        if mc and getattr(mc, 'timeout', None):
                            effective_timeout = float(mc.timeout)
                    except Exception:
                        pass
            if effective_timeout is None:
                effective_timeout = float(self.timeout)
            else:
                # 不超过provider默认；也允许更小，以适配回退场景的剩余时间
                effective_timeout = max(5.0, min(float(self.timeout), effective_timeout))
            try:
                self.logger.info(f"Zhipu.chat_completion using response_format={payload.get('response_format')} max_tokens={payload.get('max_tokens')} timeout={effective_timeout}")
            except Exception:
                pass
        except Exception:
            effective_timeout = float(self.timeout)

        # 统一：遵循系统/进程代理（trust_env=True），使用单一超时；读超时下先同配置重试一次，再按需直连兜底
        async def _post_once(timeout_val: float, trust_env: bool = True):
            async with httpx.AsyncClient(timeout=timeout_val, trust_env=trust_env) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions", headers=headers, json=payload
                )
                if resp.status_code != 200:
                    raise RuntimeError(
                        f"Zhipu LLM API error: {resp.status_code} - {resp.text}"
                    )
                return resp.json()

        # 简化版：一次按系统代理请求，超时则（可选）再直连一次；不做时间切分
        try:
            result = await _post_once(float(effective_timeout), True)
        except httpx.TimeoutException:
            if getattr(settings, 'NETWORK_DIRECT_FALLBACK_ON_TIMEOUT', False):
                try:
                    try:
                        self.logger.warning(
                            f"Zhipu.chat_completion proxy timeout; fallback direct with timeout={float(effective_timeout):.1f}s"
                        )
                    except Exception:
                        pass
                    result = await _post_once(float(effective_timeout), False)
                except httpx.TimeoutException:
                    raise RuntimeError("Zhipu LLM API request timeout")
                except Exception as e2:
                    raise RuntimeError(f"Zhipu LLM chat completion failed: {str(e2)}")
            else:
                raise RuntimeError("Zhipu LLM API request timeout")
        except httpx.ConnectError as conn_err:
            if getattr(settings, 'NETWORK_DIRECT_FALLBACK_ON_TIMEOUT', False):
                try:
                    try:
                        self.logger.warning(
                            f"Zhipu.chat_completion proxy connect error; fallback direct with timeout={float(effective_timeout):.1f}s ({conn_err})"
                        )
                    except Exception:
                        pass
                    result = await _post_once(float(effective_timeout), False)
                except Exception as e2:
                    raise RuntimeError(f"Zhipu LLM chat completion failed: {str(e2)}")
            else:
                raise RuntimeError(f"Zhipu LLM chat completion connection failed: {str(conn_err)}")
        except Exception as e:
            raise RuntimeError(f"Zhipu LLM chat completion failed: {str(e)}")

        # 统一解析返回
        try:
            choice = result["choices"][0]
            msg = choice.get("message", {}) or {}
            content = msg.get("content")
            reasoning = msg.get("reasoning_content")
            try:
                # 诊断：记录 content 与 reasoning_content 的长度
                clen = len(content or "") if isinstance(content, str) else 0
                rlen = len(reasoning or "") if isinstance(reasoning, str) else 0
                self.logger.info(f"Zhipu.chat_completion result lens: content={clen} reasoning={rlen} finish_reason={choice.get('finish_reason')}")
            except Exception:
                pass
            return {
                "content": content,
                "reasoning_content": reasoning,
                "model": result.get("model"),
                "usage": result.get("usage", {}),
                "finish_reason": choice.get("finish_reason"),
                "provider": self.get_provider_name()
            }
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
        if "thinking" in kwargs and kwargs["thinking"] is not None:
            payload["thinking"] = kwargs["thinking"]

        # response_format 透传（若供应商支持则生效）。
        # 是否允许在 tools 非空时使用 response_format 由协议层（调用方）约束；本层不做“静默忽略”。
        rf = kwargs.get("response_format")
        # 协议约束：tools 非空时不要携带 response_format（在部分供应商/模式下会抑制 tool_calls）。
        if rf and tools:
            try:
                self.logger.warning(
                    "Zhipu.function_call: dropping response_format because tools are present (to avoid suppressing tool_calls): %s",
                    rf,
                )
            except Exception:
                pass
            rf = None
        if rf:
            try:
                payload["response_format"] = rf
                self.logger.info(
                    "Zhipu.function_call using response_format=%s max_tokens=%s",
                    payload.get("response_format"),
                    payload.get("max_tokens"),
                )
            except Exception:
                pass
        # 诊断：打印工具schema数量与前几个函数名
        try:
            tlist = payload.get("tools") or []
            fnames = []
            for t in tlist[:3]:
                try:
                    fn = (t or {}).get("function", {}).get("name")
                    if fn:
                        fnames.append(fn)
                except Exception:
                    continue
            self.logger.info(f"Zhipu.function_call tools_count={len(tlist)} names={fnames}")
        except Exception:
            pass
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # 计算本次请求的有效超时：优先 request_timeout；否则按模型配置；最后退回 provider 级
        effective_timeout = None
        try:
            req_to = kwargs.get("request_timeout")
            if req_to is not None:
                effective_timeout = float(req_to)
            else:
                if model:
                    try:
                        from ....core.ai_config import get_ai_config  # type: ignore
                        mc = get_ai_config().get_model_config(model)
                        if mc and getattr(mc, 'timeout', None):
                            effective_timeout = float(mc.timeout)
                    except Exception:
                        pass
            if effective_timeout is None:
                effective_timeout = float(self.timeout)
            else:
                effective_timeout = max(5.0, min(float(self.timeout), effective_timeout))
            try:
                self.logger.info(f"Zhipu.function_call using response_format={payload.get('response_format')} max_tokens={payload.get('max_tokens')} timeout={effective_timeout}")
            except Exception:
                pass
        except Exception:
            effective_timeout = float(self.timeout)

        async def _post_once(timeout_val: float, trust_env: bool = True):
            async with httpx.AsyncClient(timeout=timeout_val, trust_env=trust_env) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions", headers=headers, json=payload
                )
                if resp.status_code != 200:
                    raise RuntimeError(
                        f"Zhipu Function Call API error: {resp.status_code} - {resp.text}"
                    )
                return resp.json()

        # 简化版：一次按系统代理请求，超时则（可选）再直连一次
        try:
            result = await _post_once(float(effective_timeout), True)
        except httpx.TimeoutException:
            if getattr(settings, 'NETWORK_DIRECT_FALLBACK_ON_TIMEOUT', False):
                try:
                    try:
                        self.logger.warning(
                            f"Zhipu.function_call proxy timeout; fallback direct with timeout={float(effective_timeout):.1f}s"
                        )
                    except Exception:
                        pass
                    result = await _post_once(float(effective_timeout), False)
                except httpx.TimeoutException:
                    raise RuntimeError("Zhipu Function Call API request timeout")
                except Exception as e2:
                    raise RuntimeError(f"Zhipu Function Call failed: {str(e2)}")
            else:
                raise RuntimeError("Zhipu Function Call API request timeout")
        except httpx.ConnectError as conn_err:
            if getattr(settings, 'NETWORK_DIRECT_FALLBACK_ON_TIMEOUT', False):
                try:
                    try:
                        self.logger.warning(
                            f"Zhipu.function_call proxy connect error; fallback direct with timeout={float(effective_timeout):.1f}s ({conn_err})"
                        )
                    except Exception:
                        pass
                    result = await _post_once(float(effective_timeout), False)
                except Exception as e2:
                    raise RuntimeError(f"Zhipu Function Call failed: {str(e2)}")
            else:
                raise RuntimeError(f"Zhipu Function Call connection failed: {str(conn_err)}")
        except Exception as e:
            raise RuntimeError(f"Zhipu Function Call failed: {str(e)}")

        # 统一解析
        try:
            choice = result["choices"][0]
            msg = choice.get("message", {}) or {}
            content = msg.get("content")
            reasoning = msg.get("reasoning_content")

            response_data = {
                "model": result.get("model"),
                "usage": result.get("usage", {}),
                "finish_reason": choice.get("finish_reason"),
                "provider": self.get_provider_name(),
                "content": content,
                "reasoning_content": reasoning,
                "has_function_call": False,
            }

            tool_calls = msg.get("tool_calls")
            if tool_calls:
                # 兼容：部分供应商在 response_format/特定模式下可能仍返回 tool_calls 但 finish_reason=stop
                response_data["tool_calls"] = tool_calls
                response_data["has_function_call"] = True
                try:
                    if choice.get("finish_reason") != "tool_calls":
                        self.logger.info(
                            "Zhipu.function_call: tool_calls present but finish_reason=%s",
                            choice.get("finish_reason"),
                        )
                except Exception:
                    pass

            try:
                clen = len(content or "") if isinstance(content, str) else 0
                rlen = len(reasoning or "") if isinstance(reasoning, str) else 0
                self.logger.info(
                    f"Zhipu.function_call(text) lens: content={clen} reasoning={rlen} finish_reason={choice.get('finish_reason')}"
                )
            except Exception:
                pass

            return response_data
        except Exception as e:
            raise RuntimeError(f"Zhipu Function Call failed: {str(e)}")
    
    # structured_generation 已移除：改用 chat_completion + response_format 实现结构化输出


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
        """获取API密钥（配置 > 环境变量 > settings）"""
        api_key = self.config.get("api_key")
        if not api_key:
            import os
            api_key = os.getenv("GLM_API_KEY") or os.getenv("ZHIPU_API_KEY")
        if not api_key:
            try:
                from ....core.config import settings
                api_key = settings.GLM_API_KEY or os.getenv("ZHIPU_API_KEY")
            except Exception:
                pass
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
    
    PROMPT_MAX_BYTES: int = 512

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # 配置初始化
        self.api_key = self._get_api_key()
        self.base_url = self.config.get("base_url", "https://open.bigmodel.cn/api/paas/v4")
        self.timeout = self.config.get("timeout", 600)  # 视频生成需要很长时间
        
        # 支持的模型和能力
        self.supported_models = ["cogvideox", "cogvideox-3"]
        # CogVideoX支持的离散时长，从配置读取，避免写死
        self.duration_capabilities = getattr(settings, "AVAILABLE_SCENE_DURATIONS", [5, 10])
        self.supports_first_last = True  # CogVideoX-3支持首尾帧模式
        provider_key = self.config.get("provider_key") or getattr(settings, "ZHIPU_VIDEO_PROVIDER_KEY", None)
        if not provider_key or not str(provider_key).strip():
            provider_key = "cogvideox-3"
        self.provider_key = str(provider_key).strip()
    
    def _get_api_key(self) -> Optional[str]:
        """获取API密钥（配置 > 环境变量 > settings）"""
        api_key = self.config.get("api_key")
        if not api_key:
            import os
            api_key = os.getenv("GLM_API_KEY") or os.getenv("ZHIPU_API_KEY")
        if not api_key:
            try:
                from ....core.config import settings
                api_key = settings.GLM_API_KEY or os.getenv("ZHIPU_API_KEY")
            except Exception:
                pass
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

    def _get_provider_config(self):
        try:
            from ....core.video_config_manager import get_video_config

            cfg = None
            if self.provider_key:
                cfg = get_video_config().get_provider_config(self.provider_key)
            if cfg is None:
                cfg = get_video_config().get_current_provider_config()
            return cfg
        except Exception:
            return None

    def get_capabilities(self) -> VideoCapabilities:
        caps = VideoCapabilities()
        provider_cfg = self._get_provider_config()
        prompt_limits = getattr(provider_cfg, "prompt_limits", {}) if provider_cfg else {}

        max_bytes = prompt_limits.get("max_bytes") or self.PROMPT_MAX_BYTES
        approx_cn = prompt_limits.get("approx_chinese_chars")
        approx_en = prompt_limits.get("approx_english_chars")
        enforce = bool(prompt_limits.get("enforce", True)) if max_bytes else False
        note = prompt_limits.get("note")

        if max_bytes:
            desc_parts: List[str] = []
            if approx_cn and approx_en:
                desc_parts.append(f"约{approx_cn}个中文或{approx_en}个英文字符以内")
            elif approx_cn:
                desc_parts.append(f"约{approx_cn}个中文字符以内")
            elif approx_en:
                desc_parts.append(f"约{approx_en}个英文字符以内")
            if note and note not in desc_parts:
                desc_parts.append(note)
            description_suffix = "，".join(desc_parts) if desc_parts else None
            extra_meta = {
                k: v
                for k, v in prompt_limits.items()
                if k not in {"approx_chinese_chars", "approx_english_chars", "note", "enforce"}
            }
            caps.prompt = PromptCapability(
                max_bytes=max_bytes,
                approx_chinese_chars=approx_cn,
                approx_english_chars=approx_en,
                description_suffix=description_suffix,
                note=note,
                enforce=enforce,
                extra=extra_meta,
            )

        if provider_cfg and provider_cfg.resolution_options:
            caps.resolution = EnumCapability(
                options=list(provider_cfg.resolution_options),
                aliases=dict(provider_cfg.resolution_aliases or {}),
                description_suffix="支持的分辨率列表，别名将自动映射为实际尺寸",
            )

        if provider_cfg and provider_cfg.ratio_options:
            caps.ratio = EnumCapability(
                options=list(provider_cfg.ratio_options),
                aliases=dict(provider_cfg.ratio_aliases or {}),
                description_suffix="画幅比例支持列表",
            )

        return caps
    
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

        provider_cfg = self._get_provider_config()
        resolution_aliases = dict(getattr(provider_cfg, "resolution_aliases", {}) or {})
        prompt_limits = getattr(provider_cfg, "prompt_limits", {}) if provider_cfg else {}

        size_param = kwargs.get("resolution") or kwargs.get("size")
        if isinstance(size_param, str) and size_param.strip():
            normalized_size = size_param.strip()
            payload["size"] = resolution_aliases.get(normalized_size, normalized_size)

        target_model = payload["model"]
        prompt_bytes = prompt.encode("utf-8") if isinstance(prompt, str) else b""
        limit_bytes = prompt_limits.get("max_bytes") or self.PROMPT_MAX_BYTES
        approx_cn = prompt_limits.get("approx_chinese_chars")
        approx_en = prompt_limits.get("approx_english_chars")

        if (
            target_model in {"cogvideox", "cogvideox-3"}
            and limit_bytes
            and len(prompt_bytes) > int(limit_bytes)
        ):
            hint_parts: List[str] = []
            if approx_cn:
                hint_parts.append(f"约{approx_cn}个中文字符")
            if approx_en:
                hint_parts.append(f"{approx_en}个英文字符")
            hint = "或".join(hint_parts) if hint_parts else f"{limit_bytes}字节"
            raise RuntimeError(
                f"Prompt exceeds provider limit ({hint}以内)"
            )

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
