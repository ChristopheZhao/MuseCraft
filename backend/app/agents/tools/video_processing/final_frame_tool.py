"""
FinalFrameTool - 提供场景尾帧的获取/提取能力（用于视频连续性执行阶段）

actions:
- get_final_frame_from_memory(scene_number): 从连续性内存读取上一参考场景的已存尾帧（base64/URL/文件路径）
- extract_final_frame_from_video(video_path, scene_number?): 从视频中提取尾帧到本地（可选返回路径）

说明：本阶段优先落地 get_final_frame_from_memory；extract 动作为备用，不强制在当前流程中使用。
"""
from __future__ import annotations

import os
import base64
from typing import Any, Dict, List, Optional
import time
import uuid

from ..base_tool import AsyncTool, ToolMetadata, ToolType, ToolInput, ToolValidationError, ToolError


class FinalFrameTool(AsyncTool):
    def _initialize(self):
        # No-op init; relies on scene continuity memory and optional ffmpeg for extraction
        self.logger.info("FinalFrameTool initialized")
    @classmethod
    def get_metadata(cls) -> ToolMetadata:
        return ToolMetadata(
            name="final_frame_tool",
            version="0.1.0",
            description="Get or extract final frame for scene continuity",
            tool_type=ToolType.MEDIA_PROCESSING,
            author="system",
            tags=["video", "continuity", "frame"],
            capabilities=["get_final_frame_from_memory", "extract_final_frame_from_video"],
            limitations=["extract requires ffmpeg availability"],
        )

    def get_available_actions(self) -> List[str]:
        return ["get_final_frame_from_memory", "extract_final_frame_from_video"]

    def get_action_schema(self, action: str) -> Dict[str, Any]:
        if action == "get_final_frame_from_memory":
            return {
                "type": "object",
                "properties": {
                    "scene_number": {"type": "integer", "minimum": 1},
                },
                "required": ["scene_number"],
            }
        if action == "extract_final_frame_from_video":
            return {
                "type": "object",
                "properties": {
                    "video_path": {"type": "string"},
                    "scene_number": {"type": ["integer", "null"]},
                    "to_base64": {"type": "boolean"},
                },
                "required": ["video_path"],
            }
        return {}

    async def _execute_impl(self, tool_input: ToolInput) -> Any:
        action = tool_input.action
        p = tool_input.parameters

        if action == "get_final_frame_from_memory":
            return await self._act_get_final_frame_from_memory(p)
        if action == "extract_final_frame_from_video":
            return await self._act_extract_final_frame_from_video(p)
        raise ToolValidationError(f"Unknown action: {action}", self.metadata.name)

    async def _act_get_final_frame_from_memory(self, p: Dict[str, Any]) -> Dict[str, Any]:
        scene_number = int(p["scene_number"])
        try:
            from ....core.scene_continuity_memory import get_scene_continuity_memory
            mem = get_scene_continuity_memory()
            data = await mem.get_previous_scene_final_frame(scene_number)
            if not data:
                return {"format": None}

            # 规范化返回：format ∈ {data_url, url, path}，并附带字段
            if isinstance(data, str) and data.startswith("data:image"):
                return {"format": "data_url", "data_url": data, "mime": "image/jpeg"}
            if isinstance(data, str) and (data.startswith("http://") or data.startswith("https://")):
                return {"format": "url", "url": data, "mime": "image/jpeg"}
            # 默认视为本地路径
            return {"format": "path", "path": str(data), "mime": "image/jpeg"}
        except Exception as e:
            raise ToolError(f"failed to get final frame from memory: {e}", self.metadata.name)

    async def _act_extract_final_frame_from_video(self, p: Dict[str, Any]) -> Dict[str, Any]:
        """通过已注册的 `ffmpeg_tool.extract_last_frame` 提取视频最后一帧。

        返回标准化结果：{"format": "path"|"data_url", ...}
        """
        scene_number = p.get("scene_number")
        video_path = p.get("video_path") or p.get("video_url")
        to_base64 = bool(p.get("to_base64", False))

        if not video_path:
            raise ToolValidationError("video_path or video_url is required", self.metadata.name)

        try:
            # 通过工具注册表获取 ffmpeg_tool 实例
            from ..tool_registry import get_tool_registry
            from ..base_tool import ToolInput
            registry = get_tool_registry()
            ffmpeg_tool = registry.get_tool("ffmpeg_tool")

            # 为避免并发写入同一路径，默认输出文件名加入时间/随机后缀
            # 若提供 scene_number，则以 scene_{n}_final_frame_{ts}.jpg 命名，便于追踪
            ts = int(time.time() * 1000)
            unique = uuid.uuid4().hex[:8]
            if scene_number:
                safe_sn = str(scene_number)
                out_name = f"scene_{safe_sn}_final_frame_{ts}_{unique}.jpg"
            else:
                out_name = f"final_frame_{ts}_{unique}.jpg"

            params: Dict[str, Any] = {
                "output_format": "jpg",
                "output_filename": out_name,
                "time_tolerance": 0.1,
            }
            # 根据输入类型设置参数
            if isinstance(video_path, str) and (video_path.startswith("http://") or video_path.startswith("https://")):
                params["video_url"] = video_path
            else:
                params["video_path"] = video_path

            result = await ffmpeg_tool.execute(ToolInput(action="extract_last_frame", parameters=params))
            payload = getattr(result, 'result', result)
            out_path = payload.get("image_path") if isinstance(payload, dict) else None
            if not out_path:
                raise ToolError("ffmpeg_tool did not return image_path", self.metadata.name)

            if to_base64:
                with open(out_path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("utf-8")
                return {"format": "data_url", "data_url": f"data:image/jpeg;base64,{b64}", "path": out_path, "mime": "image/jpeg"}
            return {"format": "path", "path": out_path, "mime": "image/jpeg"}
        except Exception as e:
            raise ToolError(f"failed to extract final frame: {e}", self.metadata.name)
