"""
MiniMax视频生成工具 - abab-video-1模型
支持文生视频和图生视频（首尾帧输入）
"""

import asyncio
import httpx
import time
from typing import Dict, Any, Optional, List, Union
from ..base_tool import AsyncTool, ToolInput, ToolError, ToolValidationError, ToolMetadata, ToolType
from ....core.config import settings


class MiniMaxVideoTool(AsyncTool):
    """MiniMax视频生成工具"""
    
    @classmethod
    def get_metadata(cls) -> ToolMetadata:
        return ToolMetadata(
            name="minimax_video",
            version="1.0.0",
            description="MiniMax abab-video-1 视频生成工具，支持文生视频和图生视频",
            tool_type=ToolType.AI_SERVICE,
            author="system",
            tags=["video-generation", "ai", "minimax"],
            capabilities=["text_to_video", "image_to_video", "check_status", "get_video"],
            limitations=["requires_api_key", "rate_limited"]
        )
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(self.get_metadata(), config)
    
    def _initialize(self):
        """Initialize tool-specific resources"""
        # 尝试从配置获取API key，如果没有则从环境变量获取
        self.api_key = getattr(settings, 'MINIMAX_API_KEY', None)
        if not self.api_key:
            import os
            self.api_key = os.getenv("MINIMAX_API_KEY")
        
        self.base_url = getattr(settings, 'MINIMAX_BASE_URL', 'https://api.minimax.chat/v1')
        self.timeout = getattr(settings, 'AI_SERVICE_TIMEOUT', 60)
        
        # 工具可以在没有API key时创建，但在使用时会检查
        self._functional = bool(self.api_key)
        if not self._functional:
            self.logger.warning("MINIMAX_API_KEY not configured, tool will not be functional")
        
        self.model = "abab-video-1"
        self.max_duration = 6  # 最大6秒视频
        self.resolution = "1280x720"  # 720p分辨率
        self.fps = 25  # 25帧每秒
    
    def get_available_actions(self) -> List[str]:
        """Get list of available actions"""
        return ["text_to_video", "image_to_video", "check_status", "get_video"]
    
    def get_action_schema(self, action: str) -> Dict[str, Any]:
        """Get input schema for a specific action"""
        schemas = {
            "text_to_video": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "视频生成提示"},
                    "duration": {"type": "integer", "minimum": 1, "maximum": 6},
                    "style": {"type": "string"},
                    "quality": {"type": "string", "enum": ["high", "medium", "low"]}
                },
                "required": ["prompt"]
            },
            "image_to_video": {
                "type": "object", 
                "properties": {
                    "prompt": {"type": "string"},
                    "image": {"type": "string", "description": "输入图像"},
                    "duration": {"type": "integer", "minimum": 1, "maximum": 6}
                },
                "required": ["prompt", "image"]
            }
        }
        return schemas.get(action, {})
    
    async def _execute_impl(self, tool_input: ToolInput) -> Any:
        """执行MiniMax视频生成操作"""
        # 检查工具是否功能可用
        if not self._functional:
            raise ToolError("MiniMaxVideoTool not functional - API key required", self.metadata.name)
            
        action = tool_input.action
        params = tool_input.parameters
        
        if action == "text_to_video":
            return await self._text_to_video(params)
        elif action == "image_to_video":
            return await self._image_to_video(params)
        elif action == "check_status":
            return await self._check_status(params)
        elif action == "get_video":
            return await self._get_video(params)
        else:
            raise ToolValidationError(f"Unsupported action: {action}", self.metadata.name)
    
    async def _text_to_video(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """文本生成视频"""
        prompt = params.get("prompt")
        duration = params.get("duration", 6)  # 默认6秒
        style = params.get("style", "realistic")  # 风格：realistic, cinematic, anime, etc.
        quality = params.get("quality", "high")  # 质量：high, medium, low
        
        if not prompt:
            raise ValueError("prompt is required for text_to_video")
        
        if duration > self.max_duration:
            duration = self.max_duration
        
        # 构建请求数据
        request_data = {
            "model": self.model,
            "prompt": prompt,
            "duration": duration,
            "resolution": self.resolution,
            "fps": self.fps,
            "style": style,
            "quality": quality
        }
        
        # 发送异步请求
        async with httpx.AsyncClient(timeout=300) as client:
            response = await client.post(
                f"{self.base_url}/video/text_to_video",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json=request_data
            )
            response.raise_for_status()
            result = response.json()
        
        return {
            "task_id": result.get("task_id"),
            "status": result.get("status", "processing"),
            "model": self.model,
            "prompt": prompt,
            "duration": duration,
            "resolution": self.resolution,
            "fps": self.fps,
            "style": style,
            "quality": quality,
            "estimated_time": result.get("estimated_time", 60)  # 预估生成时间（秒）
        }
    
    async def _image_to_video(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """图片生成视频（支持首尾帧）"""
        prompt = params.get("prompt")
        start_image = params.get("start_image")  # 首帧图片URL或base64
        end_image = params.get("end_image")    # 尾帧图片URL或base64（可选）
        duration = params.get("duration", 6)
        style = params.get("style", "realistic")
        quality = params.get("quality", "high")
        motion_strength = params.get("motion_strength", 0.7)  # 运动强度 0-1
        
        if not start_image:
            raise ValueError("start_image is required for image_to_video")
        
        if duration > self.max_duration:
            duration = self.max_duration
        
        # 构建请求数据
        request_data = {
            "model": self.model,
            "prompt": prompt or "Generate smooth video transition",
            "start_image": start_image,
            "duration": duration,
            "resolution": self.resolution,
            "fps": self.fps,
            "style": style,
            "quality": quality,
            "motion_strength": motion_strength
        }
        
        # 添加尾帧图片（如果提供）
        if end_image:
            request_data["end_image"] = end_image
            request_data["transition_mode"] = "keyframe"  # 关键帧模式
        else:
            request_data["transition_mode"] = "motion"    # 运动模式
        
        # 发送异步请求
        async with httpx.AsyncClient(timeout=300) as client:
            response = await client.post(
                f"{self.base_url}/video/image_to_video",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json=request_data
            )
            response.raise_for_status()
            result = response.json()
        
        return {
            "task_id": result.get("task_id"),
            "status": result.get("status", "processing"),
            "model": self.model,
            "prompt": prompt,
            "start_image": start_image,
            "end_image": end_image,
            "duration": duration,
            "resolution": self.resolution,
            "fps": self.fps,
            "style": style,
            "quality": quality,
            "motion_strength": motion_strength,
            "transition_mode": request_data["transition_mode"],
            "estimated_time": result.get("estimated_time", 90)
        }
    
    async def _check_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """检查视频生成状态"""
        task_id = params.get("task_id")
        
        if not task_id:
            raise ValueError("task_id is required for check_status")
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{self.base_url}/video/task/{task_id}",
                headers={
                    "Authorization": f"Bearer {self.api_key}"
                }
            )
            response.raise_for_status()
            result = response.json()
        
        status_mapping = {
            "pending": "等待中",
            "processing": "生成中", 
            "completed": "已完成",
            "failed": "失败",
            "cancelled": "已取消"
        }
        
        return {
            "task_id": task_id,
            "status": result.get("status"),
            "status_zh": status_mapping.get(result.get("status"), "未知"),
            "progress": result.get("progress", 0),  # 进度百分比
            "video_url": result.get("video_url"),
            "thumbnail_url": result.get("thumbnail_url"),
            "duration": result.get("duration"),
            "file_size": result.get("file_size"),
            "error_message": result.get("error_message"),
            "created_at": result.get("created_at"),
            "completed_at": result.get("completed_at")
        }
    
    async def _get_video(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """获取生成的视频"""
        task_id = params.get("task_id")
        download_url = params.get("download_url")  # 直接提供下载URL
        local_path = params.get("local_path")  # 本地保存路径
        
        if not task_id and not download_url:
            raise ValueError("task_id or download_url is required for get_video")
        
        # 如果没有直接URL，先获取任务状态
        if not download_url:
            status_result = await self._check_status({"task_id": task_id})
            if status_result["status"] != "completed":
                raise ToolError(
                    f"Video not ready. Status: {status_result['status_zh']}",
                    error_code="video_not_ready",
                    details={
                        "status": status_result["status"],
                        "progress": status_result["progress"],
                    },
                )
            download_url = status_result["video_url"]
        
        if not download_url:
            raise ValueError("No video URL available")
        
        # 下载视频
        async with httpx.AsyncClient(timeout=600) as client:  # 视频下载可能需要更长时间
            response = await client.get(download_url)
            response.raise_for_status()
            video_content = response.content
        
        result = {
            "task_id": task_id,
            "download_url": download_url,
            "content_length": len(video_content),
            "content_type": response.headers.get("content-type", "video/mp4")
        }
        
        # 如果指定了本地路径，保存到文件
        if local_path:
            import aiofiles
            async with aiofiles.open(local_path, 'wb') as f:
                await f.write(video_content)
            result["local_path"] = local_path
            result["saved_to_file"] = True
        else:
            result["content"] = video_content
            result["saved_to_file"] = False
        
        return result
    
    async def wait_for_completion(self, task_id: str, max_wait_time: int = 300, check_interval: int = 10) -> Dict[str, Any]:
        """等待视频生成完成"""
        start_time = time.time()
        
        while time.time() - start_time < max_wait_time:
            status_result = await self._check_status({"task_id": task_id})
            
            if status_result["status"] == "completed":
                return status_result
            elif status_result["status"] == "failed":
                raise Exception(f"Video generation failed: {status_result.get('error_message', 'Unknown error')}")
            elif status_result["status"] in ["cancelled"]:
                raise Exception(f"Video generation was cancelled")
            
            # 等待指定间隔后再次检查
            await asyncio.sleep(check_interval)
        
        raise Exception(f"Video generation timeout after {max_wait_time} seconds")
    
    def get_supported_styles(self) -> List[str]:
        """获取支持的视频风格"""
        return [
            "realistic",      # 写实风格
            "cinematic",      # 电影风格
            "anime",          # 动漫风格
            "art",            # 艺术风格
            "sci_fi",         # 科幻风格
            "fantasy",        # 奇幻风格
            "vintage",        # 复古风格
            "minimalist"      # 极简风格
        ]
    
    def get_quality_options(self) -> List[str]:
        """获取支持的质量选项"""
        return ["high", "medium", "low"]
    
    def estimate_cost(self, duration: int, quality: str = "high") -> float:
        """估算视频生成成本（人民币）"""
        # MiniMax abab-video-1 定价（2025年1月）
        base_cost_per_second = {
            "high": 0.8,      # 高质量每秒成本
            "medium": 0.6,    # 中等质量每秒成本
            "low": 0.4        # 低质量每秒成本
        }
        
        cost_per_second = base_cost_per_second.get(quality, base_cost_per_second["high"])
        total_cost = duration * cost_per_second
        
        return total_cost
    
    async def health_check(self) -> bool:
        """健康检查"""
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    f"{self.base_url}/models",
                    headers={
                        "Authorization": f"Bearer {self.api_key}"
                    }
                )
                return response.status_code == 200
        except:
            return False


# 导出工具实例
try:
    minimax_video = MiniMaxVideoTool()
except Exception as e:
    minimax_video = None
    print(f"MiniMax Video Tool initialization failed: {e}")
