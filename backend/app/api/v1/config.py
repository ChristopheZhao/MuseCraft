"""
Configuration API endpoints for video generation system
"""
from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ...core.video_config_manager import get_video_config


router = APIRouter()


class ProviderSwitchRequest(BaseModel):
    provider_name: str


class DurationValidationRequest(BaseModel):
    duration: int


@router.get("/video-providers", response_model=Dict[str, Any])
async def get_video_providers():
    """获取所有可用的视频生成提供商"""
    video_config = get_video_config()
    
    return {
        "available_providers": video_config.get_available_providers(),
        "current_provider": video_config._current_provider,
        "comparison_matrix": video_config.get_comparison_matrix()
    }


@router.get("/video-providers/current", response_model=Dict[str, Any])
async def get_current_video_provider():
    """获取当前视频生成提供商的详细配置"""
    video_config = get_video_config()
    
    return {
        "provider_config": video_config.get_provider_specific_config(),
        "system_capability": video_config.get_system_duration_capability()
    }


@router.post("/video-providers/switch", response_model=Dict[str, Any])
async def switch_video_provider(request: ProviderSwitchRequest):
    """切换视频生成提供商"""
    video_config = get_video_config()
    
    success = video_config.set_current_provider(request.provider_name)
    
    if not success:
        available = video_config.get_available_providers()
        raise HTTPException(
            status_code=400,
            detail=f"Provider '{request.provider_name}' not available. Available providers: {available}"
        )
    
    # 返回切换后的配置
    return {
        "success": True,
        "new_provider": request.provider_name,
        "provider_config": video_config.get_provider_specific_config(),
        "system_capability": video_config.get_system_duration_capability()
    }


@router.post("/duration/validate", response_model=Dict[str, Any])
async def validate_duration(request: DurationValidationRequest):
    """验证视频时长是否在当前提供商支持范围内"""
    video_config = get_video_config()
    
    validation = video_config.validate_duration_request(request.duration)
    optimal_scenes = video_config.calculate_optimal_scene_count(request.duration)
    
    return {
        **validation,
        "optimal_scene_count": optimal_scenes,
        "provider": video_config._current_provider
    }


@router.get("/duration/capability", response_model=Dict[str, Any])
async def get_duration_capability():
    """获取当前系统的视频时长能力"""
    video_config = get_video_config()
    
    capability = video_config.get_system_duration_capability()
    current_config = video_config.get_current_provider_config()
    
    return {
        "system_capability": capability,
        "provider_details": {
            "name": current_config.provider_name,
            "model": current_config.model_name,
            "single_clip_duration": f"{current_config.default_duration}-{current_config.max_duration}s",
            "amplification_ratio": current_config.amplification_ratio,
            "supports_first_last_frame": current_config.supports_first_last_frame,
            "resolution_options": current_config.resolution_options,
            "frame_rate_options": current_config.frame_rate_options
        }
    }


@router.get("/scene/optimal-count/{duration}", response_model=Dict[str, Any])
async def get_optimal_scene_count(duration: int):
    """根据目标时长计算最优场景数量"""
    video_config = get_video_config()
    
    if duration < 1:
        raise HTTPException(status_code=400, detail="Duration must be positive")
    
    optimal_scenes = video_config.calculate_optimal_scene_count(duration)
    validation = video_config.validate_duration_request(duration)
    
    return {
        "target_duration": duration,
        "optimal_scene_count": optimal_scenes,
        "duration_validation": validation,
        "provider": video_config._current_provider
    }


@router.get("/test/configuration", response_model=Dict[str, Any])
async def test_configuration_system():
    """测试配置系统完整性（调试用）"""
    video_config = get_video_config()
    
    # 测试所有提供商
    provider_tests = {}
    original_provider = video_config._current_provider
    
    for provider_name in video_config.get_available_providers():
        video_config.set_current_provider(provider_name)
        config = video_config.get_current_provider_config()
        capability = video_config.get_system_duration_capability()
        
        provider_tests[provider_name] = {
            "config": {
                "model_name": config.model_name,
                "duration_capabilities": config.duration_capabilities,
                "max_duration": config.max_duration,
                "supports_first_last_frame": config.supports_first_last_frame,
                "amplification_ratio": config.amplification_ratio
            },
            "system_capability": capability,
            "test_duration_30s": video_config.validate_duration_request(30),
            "optimal_scenes_for_60s": video_config.calculate_optimal_scene_count(60)
        }
    
    # 恢复原始提供商
    video_config.set_current_provider(original_provider)
    
    return {
        "test_results": provider_tests,
        "current_provider": original_provider,
        "configuration_injection": video_config.get_provider_specific_config()
    }