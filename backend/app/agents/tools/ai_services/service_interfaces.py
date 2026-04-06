"""
AI模型服务抽象接口 - 按模型类型分层设计
"""

from abc import ABC, abstractmethod
import logging
import os
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger("ai_service_manager")


@dataclass
class PromptCapability:
    """Provider 提供的提示词限制能力。"""

    max_bytes: Optional[int] = None
    approx_chinese_chars: Optional[int] = None
    approx_english_chars: Optional[int] = None
    description_suffix: Optional[str] = None
    note: Optional[str] = None
    enforce: bool = False
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_metadata(self) -> Dict[str, Any]:
        """统一导出 schema 需要的元数据。"""
        metadata = dict(self.extra or {})
        if self.max_bytes is not None:
            metadata.setdefault("max_bytes", self.max_bytes)
        if self.approx_chinese_chars is not None:
            metadata.setdefault("approx_chinese_chars", self.approx_chinese_chars)
        if self.approx_english_chars is not None:
            metadata.setdefault("approx_english_chars", self.approx_english_chars)
        if self.note:
            metadata.setdefault("note", self.note)
        if self.enforce:
            metadata.setdefault("enforce", True)
        return metadata


@dataclass
class EnumCapability:
    """枚举参数的能力约束（如分辨率、比例）。"""

    options: List[str] = field(default_factory=list)
    aliases: Dict[str, str] = field(default_factory=dict)
    description_suffix: Optional[str] = None
    note: Optional[str] = None

    def expand_enum(self) -> List[str]:
        expanded = list(self.options or [])
        for alias in self.aliases.keys():
            if alias not in expanded:
                expanded.append(alias)
        return expanded

    def resolve(self, value: Any) -> Optional[str]:
        """Normalize an option or alias to the canonical enum value."""
        if value is None:
            return None
        candidate = str(value).strip()
        if not candidate:
            return None

        for option in self.options or []:
            if candidate == option:
                return option
        for alias, target in (self.aliases or {}).items():
            if candidate == alias:
                return target

        lower_candidate = candidate.lower()
        for option in self.options or []:
            if isinstance(option, str) and lower_candidate == option.lower():
                return option
        for alias, target in (self.aliases or {}).items():
            if isinstance(alias, str) and lower_candidate == alias.lower():
                return target
        return None

    def default_option(self) -> Optional[str]:
        options = list(self.options or [])
        return options[0] if options else None


@dataclass
class VideoCapabilities:
    prompt: Optional[PromptCapability] = None
    resolution: Optional[EnumCapability] = None
    ratio: Optional[EnumCapability] = None


@dataclass
class ImageGenerationCapabilities:
    prompt: Optional[PromptCapability] = None
    size: Optional[EnumCapability] = None


class ServiceProvider(Enum):
    """AI服务供应商枚举"""
    ZHIPU = "zhipu"
    DEEPSEEK = "deepseek"
    OPENAI = "openai" 
    ANTHROPIC = "anthropic"
    STABILITY = "stability"
    RUNWAY = "runway"
    PIKA = "pika"
    MINIMAX = "minimax"
    DOUBAO = "doubao"


class LLMServiceInterface(ABC):
    """
    LLM服务抽象接口 - 专注文本生成、推理、Function Call
    
    功能范围：
    - 文本对话和生成
    - 逻辑推理和分析
    - Function Call决策
    - 结构化数据生成
    """
    
    @abstractmethod
    async def chat_completion(
        self, 
        messages: List[Dict[str, Any]], 
        model: str = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        **kwargs
    ) -> Dict[str, Any]:
        """基础对话完成"""
        pass
    
    @abstractmethod  
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
        pass
    
    # 取消 structured_generation：统一通过 chat_completion + response_format 获取结构化输出
    
    @abstractmethod
    def get_supported_models(self) -> List[str]:
        """获取支持的LLM模型列表"""
        pass
    
    @abstractmethod
    def get_provider_name(self) -> str:
        """获取供应商名称"""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """检查服务是否可用"""
        pass
class VLMServiceInterface(ABC):
    """
    VLM服务抽象接口 - 专注视觉理解和图像生成
    
    功能范围：
    - 图像内容理解和分析
    - 图像生成和编辑
    - 视觉问答
    - 图像描述生成
    """
    
    @abstractmethod
    async def image_understanding(
        self,
        image_input: Union[str, bytes],
        prompt: str,
        model: str = None,
        **kwargs
    ) -> Dict[str, Any]:
        """图像理解和分析"""
        pass
    
    @abstractmethod
    async def image_generation(
        self,
        prompt: str,
        model: str = None,
        size: Optional[str] = None,
        style: str = "vivid",
        quality: str = "standard",
        **kwargs
    ) -> Dict[str, Any]:
        """图像生成"""
        pass
    
    @abstractmethod
    async def image_editing(
        self,
        image_input: Union[str, bytes],
        prompt: str,
        model: str = None,
        **kwargs
    ) -> Dict[str, Any]:
        """图像编辑（可选功能）"""
        pass
    
    @abstractmethod
    def get_supported_models(self) -> Dict[str, List[str]]:
        """获取支持的VLM模型列表 - 按功能分类"""
        pass
    
    @abstractmethod
    def get_provider_name(self) -> str:
        """获取供应商名称"""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """检查服务是否可用"""
        pass

    def get_capabilities(self) -> "ImageGenerationCapabilities":
        """返回图像生成参数约束（默认无额外限制）。"""
        return ImageGenerationCapabilities()


class VideoModelServiceInterface(ABC):
    """
    视频模型服务抽象接口 - 专注视频生成
    
    功能范围：
    - 文本到视频生成
    - 图像到视频生成
    - 视频编辑和处理
    - 首尾帧控制
    """
    
    @abstractmethod
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
        pass
    
    @abstractmethod
    async def get_generation_status(
        self,
        task_id: str,
        **kwargs
    ) -> Dict[str, Any]:
        """获取视频生成状态（异步任务）"""
        pass
    
    @abstractmethod
    def get_supported_models(self) -> List[str]:
        """获取支持的视频模型列表"""
        pass
    
    @abstractmethod
    def get_duration_capabilities(self) -> List[int]:
        """获取支持的视频时长选项"""
        pass
    
    @abstractmethod
    def supports_first_last_frame(self) -> bool:
        """是否支持首尾帧模式"""
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """获取供应商名称"""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """检查服务是否可用"""
        pass

    def get_capabilities(self) -> "VideoCapabilities":
        """返回供应商特有的参数约束（默认无额外限制）"""
        return VideoCapabilities()


class ServiceManager:
    """
    AI服务管理器 - 管理多类型、多供应商的AI服务
    """
    
    def __init__(self):
        self._llm_services: Dict[ServiceProvider, LLMServiceInterface] = {}
        self._vlm_services: Dict[ServiceProvider, VLMServiceInterface] = {}
        self._video_services: Dict[ServiceProvider, VideoModelServiceInterface] = {}
        
        # 默认供应商
        self._default_llm_provider: Optional[ServiceProvider] = None
        self._default_vlm_provider: Optional[ServiceProvider] = None
        self._default_video_provider: Optional[ServiceProvider] = None
    
    # === LLM服务管理 ===
    def register_llm_service(self, provider: ServiceProvider, service: LLMServiceInterface):
        """注册LLM服务供应商"""
        self._llm_services[provider] = service
        if self._default_llm_provider is None:
            self._default_llm_provider = provider
    
    def get_llm_service(self, provider: ServiceProvider = None) -> LLMServiceInterface:
        """获取LLM服务实例"""
        target_provider = provider or self._default_llm_provider

        if target_provider is None:
            raise RuntimeError("No default LLM provider registered")

        if target_provider not in self._llm_services:
            provider_name = (
                target_provider.value if isinstance(target_provider, ServiceProvider) else str(target_provider)
            )
            available = sorted([p.value for p in self._llm_services.keys()])
            diag = _diagnose_provider_requirements(target_provider, "llm")
            raise ValueError(
                f"LLM provider '{provider_name}' is not registered; "
                f"available={available}; missing_env={diag.get('missing_required_env', [])}"
            )

        service = self._llm_services[target_provider]
        if not service.is_available():
            diag = _diagnose_provider_requirements(target_provider, "llm")
            raise RuntimeError(
                f"LLM provider '{target_provider.value}' is unavailable; "
                f"missing_env={diag.get('missing_required_env', [])}"
            )

        return service
    
    # === VLM服务管理 ===
    def register_vlm_service(self, provider: ServiceProvider, service: VLMServiceInterface):
        """注册VLM服务供应商"""
        self._vlm_services[provider] = service
        if self._default_vlm_provider is None:
            self._default_vlm_provider = provider
    
    def get_vlm_service(self, provider: ServiceProvider = None) -> VLMServiceInterface:
        """获取VLM服务实例（优先环境变量 IMAGE_GENERATION_PROVIDER；其次 ai_config.tool_provider_mapping.image_generation）。"""
        target_provider = provider
        if target_provider is None:
            try:
                from ....core.config import settings  # type: ignore
                env_name = getattr(settings, 'IMAGE_GENERATION_PROVIDER', None)
                if isinstance(env_name, str) and env_name:
                    name = env_name.strip().lower()
                    mapping = {
                        'zhipu': ServiceProvider.ZHIPU,
                        'doubao': ServiceProvider.DOUBAO,
                        'openai': ServiceProvider.OPENAI,
                    }
                    target_provider = mapping.get(name) or self._default_vlm_provider
                else:
                    # 尝试从 ai_config 读取工具提供商映射
                    try:
                        from ....core.ai_config import get_ai_config  # type: ignore
                        ai_cfg = get_ai_config()
                        name = (ai_cfg.get_tool_provider('image_generation') or '').strip().lower()
                        mapping = {
                            'zhipu': ServiceProvider.ZHIPU,
                            'doubao': ServiceProvider.DOUBAO,
                            'openai': ServiceProvider.OPENAI,
                        }
                        target_provider = mapping.get(name) or self._default_vlm_provider
                    except Exception:
                        target_provider = self._default_vlm_provider
            except Exception:
                target_provider = self._default_vlm_provider
        
        if target_provider not in self._vlm_services:
            raise ValueError(f"VLM Provider {target_provider} not available")
        
        service = self._vlm_services[target_provider]
        if not service.is_available():
            # 尝试回退到其他可用的VLM供应商
            for backup_provider, backup_service in self._vlm_services.items():
                if backup_service.is_available():
                    return backup_service
            raise RuntimeError("No VLM services available")
        
        return service

    def get_vlm_capabilities(self, provider: ServiceProvider = None) -> ImageGenerationCapabilities:
        """获取当前图像生成供应商的能力快照。"""
        service = self.get_vlm_service(provider)
        if hasattr(service, "get_capabilities"):
            caps = service.get_capabilities()
            if isinstance(caps, ImageGenerationCapabilities):
                return caps
        return ImageGenerationCapabilities()
    
    # === 视频服务管理 ===
    def register_video_service(self, provider: ServiceProvider, service: VideoModelServiceInterface):
        """注册视频服务供应商"""
        self._video_services[provider] = service
        if self._default_video_provider is None:
            self._default_video_provider = provider
    
    def get_video_service(self, provider: ServiceProvider = None) -> VideoModelServiceInterface:
        """获取视频服务实例（优先环境 VIDEO_GENERATION_PROVIDER；其次 ai_config.tool_provider_mapping.video_generation_tool）。"""
        # 允许通过环境变量/配置覆盖默认 provider（与 VideoConfigManager 的 provider 一致）
        target_provider = provider
        if target_provider is None:
            try:
                # 延迟导入，避免循环依赖
                from ....core.config import settings  # type: ignore
                env_name = getattr(settings, 'VIDEO_GENERATION_PROVIDER', None)
                if isinstance(env_name, str) and env_name:
                    # 将字符串映射到枚举值
                    name = env_name.strip().lower()
                    mapping = {
                        'zhipu': ServiceProvider.ZHIPU,
                        'openai': ServiceProvider.OPENAI,
                        'anthropic': ServiceProvider.ANTHROPIC,
                        'stability': ServiceProvider.STABILITY,
                        'runway': ServiceProvider.RUNWAY,
                        'pika': ServiceProvider.PIKA,
                        'minimax': ServiceProvider.MINIMAX,
                        'doubao': ServiceProvider.DOUBAO,
                    }
                    target_provider = mapping.get(name) or self._default_video_provider
                else:
                    # 尝试从 ai_config 读取工具提供商映射
                    try:
                        from ....core.ai_config import get_ai_config  # type: ignore
                        ai_cfg = get_ai_config()
                        name = (ai_cfg.get_tool_provider('video_generation_tool') or '').strip().lower()
                        mapping = {
                            'zhipu': ServiceProvider.ZHIPU,
                            'doubao': ServiceProvider.DOUBAO,
                            'runway': ServiceProvider.RUNWAY,
                            'pika': ServiceProvider.PIKA,
                            'minimax': ServiceProvider.MINIMAX,
                        }
                        target_provider = mapping.get(name) or self._default_video_provider
                    except Exception:
                        target_provider = self._default_video_provider
            except Exception:
                target_provider = self._default_video_provider

        if target_provider not in self._video_services:
            raise ValueError(f"Video Provider {target_provider} not available")
        
        service = self._video_services[target_provider]
        if not service.is_available():
            # 尝试回退到其他可用的视频供应商
            for backup_provider, backup_service in self._video_services.items():
                if backup_service.is_available():
                    return backup_service
            raise RuntimeError("No Video services available")
        
        return service
    
    # === 统一服务接口 ===
    async def llm_function_call(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]], 
        provider: ServiceProvider = None,
        **kwargs
    ) -> Dict[str, Any]:
        """统一的LLM Function Call接口"""
        service = self.get_llm_service(provider)
        return await service.function_call(messages, tools, **kwargs)
    
    async def vlm_image_generation(
        self,
        prompt: str,
        provider: ServiceProvider = None,
        **kwargs
    ) -> Dict[str, Any]:
        """统一的图像生成接口"""
        service = self.get_vlm_service(provider)
        return await service.image_generation(prompt, **kwargs)
    
    async def video_generation(
        self,
        prompt: str,
        provider: ServiceProvider = None,
        **kwargs
    ) -> Dict[str, Any]:
        """统一的视频生成接口"""
        service = self.get_video_service(provider)
        return await service.generate_video(prompt, **kwargs)
    
    # === 系统状态 ===
    def get_available_services(self) -> Dict[str, List[ServiceProvider]]:
        """获取所有可用服务"""
        return {
            "llm": [p for p, s in self._llm_services.items() if s.is_available()],
            "vlm": [p for p, s in self._vlm_services.items() if s.is_available()],
            "video": [p for p, s in self._video_services.items() if s.is_available()]
        }


# 全局服务管理器实例
_service_manager = None


def get_service_manager() -> ServiceManager:
    """获取全局AI服务管理器"""
    global _service_manager
    if _service_manager is None:
        _service_manager = ServiceManager()
        # 初始化默认服务
        _initialize_default_services()
    return _service_manager


def _initialize_default_services():
    """初始化默认AI服务"""
    manager = get_service_manager()
    
    # 注册zhipu服务
    try:
        from .zhipu_services import ZhipuLLMService, ZhipuVLMService, ZhipuVideoService
        # 从 ai_config 注入 provider 级超时/默认模型，避免服务内使用硬默认
        zhipu_llm_cfg = {}
        try:
            from ....core.ai_config import get_ai_config  # type: ignore
            ai_cfg = get_ai_config()
            pcfg = ai_cfg.get_provider_config('zhipu')
            if pcfg:
                if getattr(pcfg, 'timeout', None):
                    zhipu_llm_cfg['timeout'] = int(pcfg.timeout)
                if getattr(pcfg, 'default_model', None):
                    zhipu_llm_cfg['default_model'] = pcfg.default_model
        except Exception:
            pass
        zhipu_llm = ZhipuLLMService(config=zhipu_llm_cfg)
        if zhipu_llm.is_available():
            manager.register_llm_service(ServiceProvider.ZHIPU, zhipu_llm)
        zhipu_vlm = ZhipuVLMService()
        if zhipu_vlm.is_available():
            manager.register_vlm_service(ServiceProvider.ZHIPU, zhipu_vlm)
        zhipu_video = ZhipuVideoService()
        if zhipu_video.is_available():
            manager.register_video_service(ServiceProvider.ZHIPU, zhipu_video)
    except ImportError as e:
        print(f"Warning: Failed to initialize Zhipu services: {e}")

    # 注册DeepSeek（可选，LLM only）
    try:
        from .deepseek_services import DeepSeekLLMService
        deepseek_llm_cfg = {}
        try:
            from ....core.ai_config import get_ai_config  # type: ignore
            ai_cfg = get_ai_config()
            pcfg = ai_cfg.get_provider_config("deepseek")
            if pcfg:
                if getattr(pcfg, "api_key", None):
                    deepseek_llm_cfg["api_key"] = pcfg.api_key
                if getattr(pcfg, "timeout", None):
                    deepseek_llm_cfg["timeout"] = int(pcfg.timeout)
                if getattr(pcfg, "default_model", None):
                    deepseek_llm_cfg["default_model"] = pcfg.default_model
                if getattr(pcfg, "base_url", None):
                    deepseek_llm_cfg["base_url"] = pcfg.base_url
        except Exception:
            pass
        deepseek_llm = DeepSeekLLMService(config=deepseek_llm_cfg)
        if deepseek_llm.is_available():
            manager.register_llm_service(ServiceProvider.DEEPSEEK, deepseek_llm)
    except ImportError as e:
        print(f"Warning: Failed to initialize DeepSeek services: {e}")

    # 注册Doubao（可选）
    try:
        from .doubao_services import DoubaoVideoService, DoubaoVLMService
        doubao_video = DoubaoVideoService()
        if doubao_video.is_available():
            manager.register_video_service(ServiceProvider.DOUBAO, doubao_video)
        doubao_vlm = DoubaoVLMService()
        if doubao_vlm.is_available():
            manager.register_vlm_service(ServiceProvider.DOUBAO, doubao_vlm)
    except Exception as e:
        print(f"Warning: Failed to initialize Doubao services: {e}")
    
    # 未来可以注册更多供应商
    # try:
    #     from .openai_services import OpenAILLMService, OpenAIVLMService
    #     openai_llm = OpenAILLMService()
    #     if openai_llm.is_available():
    #         manager.register_llm_service(ServiceProvider.OPENAI, openai_llm)
    # except ImportError:
    #     pass
    _emit_service_registration_diagnostics(manager)


def _resolve_selected_provider(name: Optional[str], mapping: Dict[str, ServiceProvider]) -> Optional[ServiceProvider]:
    if not isinstance(name, str):
        return None
    norm = name.strip().lower()
    if not norm:
        return None
    return mapping.get(norm)


def _missing_required_env(keys: List[str]) -> List[str]:
    missing: List[str] = []
    for key in keys:
        val = os.getenv(key)
        if not isinstance(val, str) or not val.strip():
            missing.append(key)
    return missing


def _any_env_set(keys: List[str]) -> bool:
    for key in keys:
        val = os.getenv(key)
        if isinstance(val, str) and val.strip():
            return True
    return False


def _provider_config_has_value(provider_name: str, field_name: str) -> bool:
    try:
        from ....core.ai_config import get_ai_config  # type: ignore

        provider_config = get_ai_config().get_provider_config(provider_name)
        value = getattr(provider_config, field_name, None) if provider_config else None
        return bool(isinstance(value, str) and value.strip())
    except Exception:
        return False


def _diagnose_provider_requirements(provider: Optional[ServiceProvider], domain: str) -> Dict[str, Any]:
    """Return startup diagnostics for provider-level required envs."""
    result: Dict[str, Any] = {"domain": domain, "provider": provider.value if isinstance(provider, ServiceProvider) else None}
    if provider == ServiceProvider.DEEPSEEK and domain == "llm":
        result["missing_required_env"] = [] if _provider_config_has_value("deepseek", "api_key") else _missing_required_env(["DEEPSEEK_API_KEY"])
        return result
    if provider == ServiceProvider.OPENAI and domain == "llm":
        result["missing_required_env"] = [] if _provider_config_has_value("openai", "api_key") else _missing_required_env(["OPENAI_API_KEY"])
        return result
    if provider == ServiceProvider.ANTHROPIC and domain == "llm":
        result["missing_required_env"] = [] if _provider_config_has_value("anthropic", "api_key") else _missing_required_env(["ANTHROPIC_API_KEY"])
        return result
    if provider == ServiceProvider.DOUBAO and domain == "vlm":
        missing = _missing_required_env(["DOUBAO_API_KEY", "DOUBAO_IMAGE_MODEL"])
        if _provider_config_has_value("doubao", "api_key") and "DOUBAO_API_KEY" in missing:
            missing = [key for key in missing if key != "DOUBAO_API_KEY"]
        result["missing_required_env"] = missing
        return result
    if provider == ServiceProvider.DOUBAO and domain == "video":
        missing = [] if _provider_config_has_value("doubao", "api_key") else _missing_required_env(["DOUBAO_API_KEY"])
        result["missing_required_env"] = missing
        return result
    if provider == ServiceProvider.ZHIPU and domain in {"llm", "vlm", "video"}:
        # zhipu系列共用 GLM_API_KEY/ZHIPU_API_KEY，任意一个即可
        if _provider_config_has_value("zhipu", "api_key") or _any_env_set(["GLM_API_KEY", "ZHIPU_API_KEY"]):
            result["missing_required_env"] = []
        else:
            result["missing_required_env"] = ["GLM_API_KEY|ZHIPU_API_KEY"]
        return result
    result["missing_required_env"] = []
    return result


def _emit_service_registration_diagnostics(manager: ServiceManager) -> None:
    """Log provider registration matrix and startup config diagnostics."""
    try:
        llm_registered = sorted([p.value for p in manager._llm_services.keys()])
        vlm_registered = sorted([p.value for p in manager._vlm_services.keys()])
        video_registered = sorted([p.value for p in manager._video_services.keys()])
        defaults = {
            "llm": manager._default_llm_provider.value if manager._default_llm_provider else None,
            "vlm": manager._default_vlm_provider.value if manager._default_vlm_provider else None,
            "video": manager._default_video_provider.value if manager._default_video_provider else None,
        }
        logger.info(
            "AI_SERVICE_MATRIX llm=%s vlm=%s video=%s defaults=%s",
            llm_registered,
            vlm_registered,
            video_registered,
            defaults,
        )
    except Exception as exc:
        logger.warning("AI_SERVICE_MATRIX logging failed: %s", exc)
        return

    image_provider_raw = None
    video_provider_raw = None
    try:
        from ....core.config import settings  # type: ignore

        image_provider_raw = getattr(settings, "IMAGE_GENERATION_PROVIDER", None)
        video_provider_raw = getattr(settings, "VIDEO_GENERATION_PROVIDER", None)
    except Exception:
        image_provider_raw = os.getenv("IMAGE_GENERATION_PROVIDER")
        video_provider_raw = os.getenv("VIDEO_GENERATION_PROVIDER")

    image_mapping = {
        "zhipu": ServiceProvider.ZHIPU,
        "doubao": ServiceProvider.DOUBAO,
        "openai": ServiceProvider.OPENAI,
    }
    video_mapping = {
        "zhipu": ServiceProvider.ZHIPU,
        "doubao": ServiceProvider.DOUBAO,
        "openai": ServiceProvider.OPENAI,
        "anthropic": ServiceProvider.ANTHROPIC,
        "stability": ServiceProvider.STABILITY,
        "runway": ServiceProvider.RUNWAY,
        "pika": ServiceProvider.PIKA,
        "minimax": ServiceProvider.MINIMAX,
    }

    selected_vlm = _resolve_selected_provider(image_provider_raw, image_mapping) or manager._default_vlm_provider
    selected_video = _resolve_selected_provider(video_provider_raw, video_mapping) or manager._default_video_provider
    selected_llm = manager._default_llm_provider

    # 针对当前选择与默认供应商输出关键缺失配置诊断
    llm_diag = _diagnose_provider_requirements(selected_llm, "llm")
    vlm_diag = _diagnose_provider_requirements(selected_vlm, "vlm")
    video_diag = _diagnose_provider_requirements(selected_video, "video")
    logger.info(
        "AI_SERVICE_SELECTED llm=%s vlm=%s video=%s image_provider_raw=%s video_provider_raw=%s",
        llm_diag.get("provider"),
        vlm_diag.get("provider"),
        video_diag.get("provider"),
        image_provider_raw,
        video_provider_raw,
    )

    for diag in (llm_diag, vlm_diag, video_diag):
        provider = diag.get("provider")
        missing = diag.get("missing_required_env") if isinstance(diag, dict) else []
        domain = diag.get("domain") if isinstance(diag, dict) else "unknown"
        if missing:
            logger.warning(
                "AI_SERVICE_CONFIG_MISSING domain=%s provider=%s missing_env=%s",
                domain,
                provider,
                missing,
            )

    # 选择了某 provider 但未注册可用服务时，提前给出启动期告警
    try:
        if selected_vlm and selected_vlm not in manager._vlm_services:
            logger.warning(
                "AI_SERVICE_PROVIDER_UNAVAILABLE domain=vlm selected=%s available=%s",
                selected_vlm.value,
                sorted([p.value for p in manager._vlm_services.keys()]),
            )
        if selected_video and selected_video not in manager._video_services:
            logger.warning(
                "AI_SERVICE_PROVIDER_UNAVAILABLE domain=video selected=%s available=%s",
                selected_video.value,
                sorted([p.value for p in manager._video_services.keys()]),
            )
        if selected_llm and selected_llm not in manager._llm_services:
            logger.warning(
                "AI_SERVICE_PROVIDER_UNAVAILABLE domain=llm selected=%s available=%s",
                selected_llm.value,
                sorted([p.value for p in manager._llm_services.keys()]),
            )
    except Exception as exc:
        logger.warning("AI_SERVICE_PROVIDER_UNAVAILABLE logging failed: %s", exc)


_LLM_PROVIDER_MAPPING: Dict[str, ServiceProvider] = {
    "zhipu": ServiceProvider.ZHIPU,
    "deepseek": ServiceProvider.DEEPSEEK,
    "openai": ServiceProvider.OPENAI,
    "anthropic": ServiceProvider.ANTHROPIC,
    "doubao": ServiceProvider.DOUBAO,
}


def resolve_llm_provider(name: Optional[str]) -> Optional[ServiceProvider]:
    return _resolve_selected_provider(name, _LLM_PROVIDER_MAPPING)


def get_supported_llm_provider_names() -> List[str]:
    return sorted(_LLM_PROVIDER_MAPPING.keys())


# 便捷函数
def get_llm_service(provider: ServiceProvider = None) -> LLMServiceInterface:
    """获取LLM服务"""
    return get_service_manager().get_llm_service(provider)


def get_vlm_service(provider: ServiceProvider = None) -> VLMServiceInterface:
    """获取VLM服务"""
    return get_service_manager().get_vlm_service(provider)


def get_vlm_capabilities(provider: ServiceProvider = None) -> ImageGenerationCapabilities:
    """获取图像生成能力快照。"""
    return get_service_manager().get_vlm_capabilities(provider)


def get_video_service(provider: ServiceProvider = None) -> VideoModelServiceInterface:
    """获取视频服务"""
    return get_service_manager().get_video_service(provider)
