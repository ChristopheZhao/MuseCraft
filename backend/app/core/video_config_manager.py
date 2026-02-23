"""
Video Configuration Manager - 管理不同视频生成API的配置
"""
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from .config import settings


@dataclass
class VideoProviderConfig:
    """视频生成提供商配置"""
    provider_name: str
    model_name: str
    duration_capabilities: List[int]  # 支持的视频时长（秒）
    max_duration: int                 # 最大单次生成时长
    default_duration: int             # 默认时长
    amplification_ratio: int          # 放大倍数（通过多次调用实现更长视频）
    supports_first_last_frame: bool   # 是否支持首尾帧模式
    resolution_options: List[str]      # 支持的分辨率
    frame_rate_options: List[int]      # 支持的帧率
    prompt_max_length: int = 500      # 视频提示词最大长度
    prompt_limits: Dict[str, Any] = field(default_factory=dict)
    resolution_aliases: Dict[str, str] = field(default_factory=dict)
    ratio_options: List[str] = field(default_factory=list)
    ratio_aliases: Dict[str, str] = field(default_factory=dict)
    mode_model_mapping: Dict[str, str] = field(default_factory=dict)
    supports_native_audio: bool = False
    native_audio_param_name: str = "generate_audio"
    native_audio_default_enabled: Optional[bool] = None


class VideoConfigManager:
    """
    视频配置管理器
    
    支持多种视频生成API的配置管理和动态切换
    """
    
    def __init__(self):
        self._providers = self._initialize_providers()
        self._current_provider = settings.VIDEO_GENERATION_PROVIDER
    
    def _initialize_providers(self) -> Dict[str, VideoProviderConfig]:
        """初始化支持的视频生成提供商配置"""
        
        providers = {
            # CogVideoX-3 (智谱AI)
            "cogvideox-3": VideoProviderConfig(
                provider_name="cogvideox-3",
                model_name=settings.COGVIDEOX3_MODEL,
                # 从配置读取可用离散时长，避免写死 [5,10]
                duration_capabilities=getattr(settings, "AVAILABLE_SCENE_DURATIONS", [5, 10]),
                max_duration=10,
                default_duration=settings.COGVIDEOX_DEFAULT_DURATION,
                amplification_ratio=settings.VIDEO_AMPLIFICATION_RATIO,
                supports_first_last_frame=True,
                resolution_options=[
                    "1280x720",
                    "720x1280",
                    "1024x1024",
                    "1920x1080",
                    "1080x1920",
                    "2048x1080",
                    "3840x2160"
                ],
                frame_rate_options=[24, 30],
                prompt_limits={
                    "max_bytes": 512,
                    "approx_chinese_chars": 170,
                    "approx_english_chars": 340,
                    "note": "智谱接口限制提示词大约170个中文字符（或340个英文字符）以内，超出将被拒绝",
                    "enforce": True,
                },
                resolution_aliases={
                    "720p": "1280x720",
                    "1080p": "1920x1080",
                    "2k": "2048x1080",
                    "4k": "3840x2160",
                    "vertical-720p": "720x1280",
                    "vertical-1080p": "1080x1920",
                    "square-1k": "1024x1024",
                }
            ),
            
            # CogVideoX-2 (智谱AI 旧版)
            "cogvideox-2": VideoProviderConfig(
                provider_name="cogvideox-2",
                model_name=settings.COGVIDEOX2_MODEL,
                duration_capabilities=[6],
                max_duration=6,
                default_duration=6,
                amplification_ratio=settings.VIDEO_AMPLIFICATION_RATIO,
                supports_first_last_frame=False,
                resolution_options=["1024x576"],
                frame_rate_options=[24]
            ),
            
            # Runway (备用)
            "runway": VideoProviderConfig(
                provider_name="runway",
                model_name=settings.RUNWAY_VIDEO_MODEL,
                duration_capabilities=[4, 10],
                max_duration=10,
                default_duration=4,
                amplification_ratio=3,  # 4秒 * 3 = 12秒基础能力
                supports_first_last_frame=True,
                resolution_options=["1280x768", "1920x1080"],
                frame_rate_options=[24, 30]
            ),
            
            # Pika Labs (备用)
            "pika": VideoProviderConfig(
                provider_name="pika",
                model_name=settings.PIKA_VIDEO_MODEL,
                duration_capabilities=[3],
                max_duration=3,
                default_duration=3,
                amplification_ratio=8,  # 3秒 * 8 = 24秒基础能力
                supports_first_last_frame=False,
                resolution_options=["1024x576"],
                frame_rate_options=[24]
            ),
            
            # Minimax (备用)
            "minimax": VideoProviderConfig(
                provider_name="minimax",
                model_name=settings.MINIMAX_VIDEO_MODEL,
                duration_capabilities=[6],
                max_duration=6,
                default_duration=6,
                amplification_ratio=settings.VIDEO_AMPLIFICATION_RATIO,
                supports_first_last_frame=False,
                resolution_options=["1280x720"],
                frame_rate_options=[25]
            )
            ,
            # Doubao (Volcengine Seedance)
            "doubao": VideoProviderConfig(
                provider_name="doubao",
                model_name=settings.DOUBAO_T2V_MODEL,
                duration_capabilities=getattr(settings, "AVAILABLE_SCENE_DURATIONS", [5, 10]),
                max_duration=10,
                default_duration=getattr(settings, "DEFAULT_SCENE_DURATION", 5),
                amplification_ratio=settings.VIDEO_AMPLIFICATION_RATIO,
                # 豆包支持首/尾帧（由工具按成本选择合适模型：lite-i2v 处理FLF，pro/pronew 处理单图/文本）
                supports_first_last_frame=True,
                resolution_options=["1280x720", "1920x1080"],
                frame_rate_options=[24, 30],
                resolution_aliases={
                    "720p": "1280x720",
                    "1080p": "1920x1080",
                },
                ratio_options=["16:9", "9:16", "1:1", "adaptive"],
                ratio_aliases={
                    "default": "adaptive",
                },
                mode_model_mapping={
                    "text_to_video": settings.DOUBAO_T2V_MODEL,
                    "image_to_video": settings.DOUBAO_I2V_SINGLE_MODEL,
                    "image_to_video_fallback": settings.DOUBAO_I2V_SINGLE_ALTER_MODEL,
                    "first_last_frame": settings.DOUBAO_I2V_FLF_MODEL,
                },
                supports_native_audio=True,
                native_audio_param_name="generate_audio",
                native_audio_default_enabled=True,
            )
        }
        
        return providers
    
    def get_current_provider_config(self) -> VideoProviderConfig:
        """获取当前提供商的配置"""
        return self._providers.get(self._current_provider, self._providers["cogvideox-3"])
    
    def get_provider_config(self, provider_name: str) -> Optional[VideoProviderConfig]:
        """获取指定提供商的配置"""
        return self._providers.get(provider_name)

    @staticmethod
    def _collect_supported_models(config: Optional[VideoProviderConfig]) -> List[str]:
        models: List[str] = []
        seen = set()
        if not config:
            return models

        def _append(candidate: Any) -> None:
            if not isinstance(candidate, str):
                return
            value = candidate.strip()
            if not value or value in seen:
                return
            seen.add(value)
            models.append(value)

        _append(config.model_name)
        for value in (config.mode_model_mapping or {}).values():
            _append(value)
        return models

    def get_provider_supported_models(self, provider_name: str) -> List[str]:
        """返回提供商的模型清单（主模型 + 模式映射模型）。"""
        config = self.get_provider_config(provider_name)
        if config is None:
            return []
        return self._collect_supported_models(config)

    def get_provider_audio_capability(self, provider_name: str) -> Dict[str, Any]:
        """返回 provider 的原生音频能力声明。"""
        config = self.get_provider_config(provider_name) if provider_name else None
        if config is None:
            config = self.get_current_provider_config()
        if config is None:
            return {
                "supports_native_audio": False,
                "native_audio_param_name": "generate_audio",
                "native_audio_default_enabled": None,
            }
        return {
            "supports_native_audio": bool(config.supports_native_audio),
            "native_audio_param_name": str(config.native_audio_param_name or "generate_audio"),
            "native_audio_default_enabled": config.native_audio_default_enabled,
        }

    def resolve_model_for_mode(
        self,
        provider_name: str,
        *,
        mode: str,
        explicit_model: Optional[str] = None,
        default_model: Optional[str] = None,
    ) -> Optional[str]:
        """根据 provider+mode 解析最终模型名。"""
        if isinstance(explicit_model, str) and explicit_model.strip():
            return explicit_model.strip()

        config = self.get_provider_config(provider_name) if provider_name else None
        if config is None:
            config = self.get_current_provider_config()
        if config is None:
            return default_model.strip() if isinstance(default_model, str) and default_model.strip() else None

        mode_key = str(mode or "").strip().lower()
        mapping = config.mode_model_mapping or {}
        candidate = mapping.get(mode_key)
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()

        if isinstance(config.model_name, str) and config.model_name.strip():
            return config.model_name.strip()

        if isinstance(default_model, str) and default_model.strip():
            return default_model.strip()
        return None
    
    def set_current_provider(self, provider_name: str) -> bool:
        """设置当前使用的视频生成提供商"""
        if provider_name in self._providers:
            self._current_provider = provider_name
            return True
        return False
    
    def get_available_providers(self) -> List[str]:
        """获取所有可用的提供商列表"""
        return list(self._providers.keys())
    
    def get_system_duration_capability(self) -> Dict[str, int]:
        """获取系统级别的总体时长能力

        计算方法：
        - 单次最大时长 * 最小场景数 作为系统最小可达时长
        - 单次最大时长 * 最大场景数 作为系统最大可达时长
        最终再与系统配置的 MIN/MAX 进行裁剪。
        """
        config = self.get_current_provider_config()
        
        # 计算系统总体能力 = 单次最大时长 * 场景数量
        min_scenes = settings.SCENE_COUNT_RANGE_MIN
        max_scenes = settings.SCENE_COUNT_RANGE_MAX
        single_max = config.max_duration

        system_min = single_max * min_scenes
        system_max = single_max * max_scenes

        return {
            "min_duration": max(system_min, settings.SYSTEM_DURATION_CAPABILITY_MIN),
            "max_duration": min(system_max, settings.SYSTEM_DURATION_CAPABILITY_MAX),
            "provider": config.provider_name,
            "amplification_ratio": config.amplification_ratio
        }

    def calculate_optimal_scene_count(self, target_duration: int) -> int:
        """根据目标时长计算最优场景数量"""
        config = self.get_current_provider_config()

        # 单个场景的可达时长由提供商的 duration_capabilities 决定
        if config.duration_capabilities:
            per_scene_duration = max(config.duration_capabilities)
        else:
            per_scene_duration = config.max_duration or config.default_duration

        per_scene_duration = max(1, per_scene_duration)

        needed_scenes = max(1, -(-target_duration // per_scene_duration))  # 向上取整

        # 限制在配置范围内
        min_scenes = settings.SCENE_COUNT_RANGE_MIN
        max_scenes = settings.SCENE_COUNT_RANGE_MAX

        return max(min_scenes, min(needed_scenes, max_scenes))
    
    def get_provider_specific_config(self) -> Dict[str, Any]:
        """获取当前提供商的特定配置，用于注入到其他组件"""
        config = self.get_current_provider_config()
        
        return {
            # 基础配置
            "provider_name": config.provider_name,
            "model_name": config.model_name,
            "mode_model_mapping": dict(config.mode_model_mapping or {}),
            "supports_native_audio": bool(config.supports_native_audio),
            "native_audio_param_name": str(config.native_audio_param_name or "generate_audio"),
            "native_audio_default_enabled": config.native_audio_default_enabled,
            "default_duration": config.default_duration,
            "max_duration": config.max_duration,
            "amplification_ratio": config.amplification_ratio,
            
            # 能力配置
            "duration_capabilities": config.duration_capabilities,
            "supports_first_last_frame": config.supports_first_last_frame,
            "resolution_options": config.resolution_options,
            "frame_rate_options": config.frame_rate_options,
            
            # 系统级配置
            "system_duration_capability": self.get_system_duration_capability(),
            "optimal_scene_count": lambda target: self.calculate_optimal_scene_count(target),
            
            # 场景配置 - 使用provider配置而不是固定值
            "default_scene_duration": settings.DEFAULT_SCENE_DURATION,
            "min_scene_duration": 3.0,  # 最小场景时长
            "max_scene_duration": 15.0,  # 最大场景时长
            "transition_duration": settings.TRANSITION_DURATION,
            
            # 音频配置
            "audio_fade_in_duration": settings.AUDIO_FADE_IN_DURATION,
            "audio_fade_out_duration": settings.AUDIO_FADE_OUT_DURATION,
            "default_audio_duration": settings.DEFAULT_AUDIO_DURATION,
            "min_audio_duration": settings.MIN_AUDIO_DURATION,
            "max_audio_duration": settings.MAX_AUDIO_DURATION
        }
    
    def validate_duration_request(self, requested_duration: int) -> Dict[str, Any]:
        """验证时长请求是否在当前提供商能力范围内"""
        capability = self.get_system_duration_capability()
        
        is_valid = capability["min_duration"] <= requested_duration <= capability["max_duration"]
        
        return {
            "is_valid": is_valid,
            "requested_duration": requested_duration,
            "min_supported": capability["min_duration"],
            "max_supported": capability["max_duration"],
            "provider": capability["provider"],
            "suggestion": max(capability["min_duration"], min(requested_duration, capability["max_duration"]))
        }
    
    def get_comparison_matrix(self) -> Dict[str, Dict[str, Any]]:
        """获取所有提供商的对比矩阵，便于选择"""
        matrix = {}
        
        for name, config in self._providers.items():
            system_capability = config.max_duration * settings.SCENE_COUNT_RANGE_MAX
            
            matrix[name] = {
                "provider_name": config.provider_name,
                "single_clip_duration": f"{config.default_duration}-{config.max_duration}s",
                "system_capability": f"up to {system_capability}s",
                "supports_first_last_frame": config.supports_first_last_frame,
                "amplification_ratio": config.amplification_ratio,
                "resolution": config.resolution_options[0] if config.resolution_options else "unknown",
                "recommended_for": self._get_recommendation(config)
            }
        
        return matrix
    
    def _get_recommendation(self, config: VideoProviderConfig) -> str:
        """为提供商生成推荐使用场景"""
        if config.supports_first_last_frame and config.max_duration >= 10:
            return "高质量长视频，支持首尾帧控制"
        elif config.max_duration >= 6:
            return "中等长度视频，平衡质量和速度"
        elif config.amplification_ratio >= 6:
            return "短片段组合，适合快速生成"
        else:
            return "基础视频生成"


# 全局配置管理器实例
video_config_manager = VideoConfigManager()


def get_video_config() -> VideoConfigManager:
    """获取全局视频配置管理器"""
    return video_config_manager


def inject_video_config() -> Dict[str, Any]:
    """注入当前视频配置到需要的组件"""
    return video_config_manager.get_provider_specific_config()
