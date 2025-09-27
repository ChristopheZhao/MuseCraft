"""
AI模型服务抽象接口 - 按模型类型分层设计
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass, field
from enum import Enum


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


@dataclass
class VideoCapabilities:
    prompt: Optional[PromptCapability] = None
    resolution: Optional[EnumCapability] = None
    ratio: Optional[EnumCapability] = None


class ServiceProvider(Enum):
    """AI服务供应商枚举"""
    ZHIPU = "zhipu"
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
        size: str = "1024x1024",
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
        
        if target_provider not in self._llm_services:
            raise ValueError(f"LLM Provider {target_provider} not available")
        
        service = self._llm_services[target_provider]
        if not service.is_available():
            # 尝试回退到其他可用的LLM供应商
            for backup_provider, backup_service in self._llm_services.items():
                if backup_service.is_available():
                    return backup_service
            raise RuntimeError("No LLM services available")
        
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


# 便捷函数
def get_llm_service(provider: ServiceProvider = None) -> LLMServiceInterface:
    """获取LLM服务"""
    return get_service_manager().get_llm_service(provider)


def get_vlm_service(provider: ServiceProvider = None) -> VLMServiceInterface:
    """获取VLM服务"""
    return get_service_manager().get_vlm_service(provider)


def get_video_service(provider: ServiceProvider = None) -> VideoModelServiceInterface:
    """获取视频服务"""
    return get_service_manager().get_video_service(provider)
