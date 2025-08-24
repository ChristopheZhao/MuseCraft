"""
AI模型服务抽象接口 - 按模型类型分层设计
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Union
from enum import Enum


class ServiceProvider(Enum):
    """AI服务供应商枚举"""
    ZHIPU = "zhipu"
    OPENAI = "openai" 
    ANTHROPIC = "anthropic"
    STABILITY = "stability"
    RUNWAY = "runway"
    PIKA = "pika"
    MINIMAX = "minimax"


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
    
    @abstractmethod
    async def structured_generation(
        self,
        prompt: str,
        schema: Dict[str, Any] = None,
        model: str = None,
        **kwargs  
    ) -> Dict[str, Any]:
        """结构化内容生成（JSON等）"""
        pass
    
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
        """获取VLM服务实例"""
        target_provider = provider or self._default_vlm_provider
        
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
        """获取视频服务实例"""
        target_provider = provider or self._default_video_provider
        
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
    
    # 注册zhipu服务（当前唯一实现）
    try:
        from .zhipu_services import ZhipuLLMService, ZhipuVLMService, ZhipuVideoService
        
        # 注册LLM服务
        zhipu_llm = ZhipuLLMService()
        if zhipu_llm.is_available():
            manager.register_llm_service(ServiceProvider.ZHIPU, zhipu_llm)
        
        # 注册VLM服务
        zhipu_vlm = ZhipuVLMService()
        if zhipu_vlm.is_available():
            manager.register_vlm_service(ServiceProvider.ZHIPU, zhipu_vlm)
        
        # 注册视频服务
        zhipu_video = ZhipuVideoService()
        if zhipu_video.is_available():
            manager.register_video_service(ServiceProvider.ZHIPU, zhipu_video)
            
    except ImportError as e:
        print(f"Warning: Failed to initialize Zhipu services: {e}")
    
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