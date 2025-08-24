"""
视频生成工具 - 纯粹的执行器，不包含决策逻辑
"""

from typing import Dict, Any, List, Optional
import logging

from ..base_tool import AsyncTool, ToolMetadata, ToolType, ToolInput, ToolError, ToolValidationError
from .service_interfaces import get_video_service
from ....core.video_config_manager import get_video_config


class VideoGenerationTool(AsyncTool):
    """
    视频生成工具 - 纯粹的执行器
    
    职责：
    - 根据给定参数生成视频
    - 不做任何智能决策
    - 只负责调用视频服务和返回结果
    """
    
    @classmethod
    def get_metadata(cls) -> ToolMetadata:
        return ToolMetadata(
            name="video_generation",
            version="2.0.0",
            description="根据提示词和图像生成视频，支持5秒或10秒时长，支持场景连续性",
            tool_type=ToolType.AI_SERVICE,
            author="system",
            tags=["video", "generation", "executor"],
            capabilities=[
                "text_to_video",
                "image_to_video", 
                "scene_continuity_support",
                "duration_control"
            ],
            limitations=[
                "requires_video_service",
                "rate_limited"
            ]
        )
    
    def __init__(self, metadata: ToolMetadata = None, config: Dict[str, Any] = None):
        if metadata is None:
            metadata = self.get_metadata()
        super().__init__(metadata, config)
        
        self.video_service = None
        self.video_config = get_video_config()
        
    def _initialize(self):
        """初始化视频生成工具"""
        try:
            self.video_service = get_video_service()
            self._functional = self.video_service.is_available()
        except Exception as e:
            self.logger.error(f"Failed to initialize video service: {e}")
            self._functional = False
        
        if not self._functional:
            self.logger.warning("VideoGenerationTool not functional - video service unavailable")
    
    def get_available_actions(self) -> List[str]:
        return [
            "generate_video",
            "get_capabilities"
        ]
    
    def get_action_schema(self, action: str) -> Dict[str, Any]:
        # 获取当前提供商配置用于动态schema
        provider_config = self.video_config.get_current_provider_config()
        
        schemas = {
            "generate_video": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "视频生成提示词，描述期望的视频内容和动作"
                    },
                    "duration": {
                        "type": "integer",
                        "enum": provider_config.duration_capabilities,
                        "description": f"视频时长（秒），可选：{provider_config.duration_capabilities}。简单场景选择较短时长，复杂动作场景选择较长时长"
                    },
                    "image_url": {
                        "type": "string",
                        "description": "参考图像URL或base64数据（可选）"
                    },
                    "continuity_frame": {
                        "type": "string", 
                        "description": "场景连续性帧数据（可选，用于场景间的视觉连续性）"
                    },
                    "model": {
                        "type": "string",
                        "enum": [provider_config.model_name],
                        "description": f"视频生成模型，当前支持：{provider_config.model_name}"
                    },
                    "first_frame_image": {
                        "type": "string",
                        "description": "首帧图像（可选，用于首尾帧模式）"
                    },
                    "last_frame_image": {
                        "type": "string", 
                        "description": "尾帧图像（可选，用于首尾帧模式）"
                    }
                },
                "required": ["prompt", "duration"]
            },
            "get_capabilities": {
                "type": "object",
                "properties": {},
                "description": "获取当前视频生成服务的能力信息"
            }
        }
        
        return schemas.get(action, {})
    
    async def _execute_impl(self, tool_input: ToolInput) -> Any:
        """执行视频生成工具"""
        if not self._functional:
            raise ToolError("VideoGenerationTool not functional - video service unavailable", self.metadata.name)
        
        action = tool_input.action
        params = tool_input.parameters
        
        if action == "generate_video":
            return await self._generate_video(params)
        elif action == "get_capabilities":
            return await self._get_capabilities()
        else:
            raise ToolValidationError(f"Unknown action: {action}", self.metadata.name)
    
    async def _generate_video(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """生成视频 - 纯粹的执行，不做决策"""
        
        prompt = params["prompt"]
        duration = params["duration"]
        image_url = params.get("image_url")
        continuity_frame = params.get("continuity_frame")
        model = params.get("model")
        first_frame_image = params.get("first_frame_image")
        last_frame_image = params.get("last_frame_image")
        
        # 确定最终的图像输入（优先使用连续性帧）
        final_image_input = continuity_frame if continuity_frame else image_url
        
        # 获取默认模型（如果未指定）
        if not model:
            provider_config = self.video_config.get_current_provider_config()
            model = provider_config.model_name
        
        self.logger.info(f"🎬 Generating video: duration={duration}s, model={model}")
        
        try:
            # 调用视频服务生成视频
            result = await self.video_service.generate_video(
                prompt=prompt,
                model=model,
                duration=duration,
                image_url=final_image_input,
                first_frame_image=first_frame_image,
                last_frame_image=last_frame_image
            )
            
            # 增强返回结果
            result.update({
                "tool_used": self.metadata.name,
                "execution_params": {
                    "prompt": prompt,
                    "duration": duration,
                    "model": model,
                    "has_continuity_frame": bool(continuity_frame),
                    "has_reference_image": bool(image_url),
                    "generation_mode": self._determine_generation_mode(
                        final_image_input, first_frame_image, last_frame_image
                    )
                }
            })
            
            return result
            
        except Exception as e:
            self.logger.error(f"Video generation failed: {str(e)}")
            raise ToolError(f"Video generation failed: {str(e)}", self.metadata.name)
    
    async def _get_capabilities(self) -> Dict[str, Any]:
        """获取视频生成能力信息"""
        provider_config = self.video_config.get_current_provider_config()
        
        return {
            "provider": provider_config.provider_name,
            "supported_models": [provider_config.model_name],
            "duration_options": provider_config.duration_capabilities,
            "max_duration": provider_config.max_duration,
            "default_duration": provider_config.default_duration,
            "supports_first_last_frame": provider_config.supports_first_last_frame,
            "resolution_options": provider_config.resolution_options,
            "frame_rate_options": provider_config.frame_rate_options,
            "amplification_ratio": provider_config.amplification_ratio,
            "system_capability": self.video_config.get_system_duration_capability()
        }
    
    def _determine_generation_mode(
        self, 
        image_url: str, 
        first_frame: str, 
        last_frame: str
    ) -> str:
        """确定生成模式"""
        if first_frame and last_frame:
            return "first_last_frame"
        elif image_url:
            return "image_to_video"
        else:
            return "text_to_video"
    
    def _validate_action_parameters(self, action: str, parameters: Dict[str, Any]):
        """验证操作参数"""
        if action == "generate_video":
            if not parameters.get("prompt"):
                raise ToolValidationError("prompt is required for generate_video")
            
            duration = parameters.get("duration")
            if duration is None:
                raise ToolValidationError("duration is required for generate_video")
            
            # 验证duration是否在支持范围内
            provider_config = self.video_config.get_current_provider_config()
            if duration not in provider_config.duration_capabilities:
                raise ToolValidationError(
                    f"duration must be one of {provider_config.duration_capabilities}, got {duration}"
                )