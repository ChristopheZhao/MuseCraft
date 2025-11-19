"""
Composition Tool - 组合式视频合成工具

职责边界（简洁说明）：
- 仅封装“确定性顺序”的媒体合成/混流（如合片、配音混流）；
- 不执行上传/发布；不写 Working Memory；无副作用；
- 返回本地 output_path 等结果；发布由 PLAN 决策另行调用存储类工具；
- 作为普通工具参与 FC 暴露与策略守卫，由 Agent 自主选择是否调用。
"""
from __future__ import annotations

from typing import Any, Dict, List

from ..base_tool import AsyncTool, ToolMetadata, ToolType, ToolInput, ToolError


class CompositionTool(AsyncTool):
    """高阶合成工具：封装常见、确定性的步骤序列，供 LLM 直接调用。"""

    def _initialize(self):
        """轻量但严格的初始化：
        - 设定默认超时/配置占位；
        - 记录并校验关键依赖是否可用（不强制实例化失败）；
        - 保留执行期按需获取依赖的策略，避免注册阶段环依赖。
        """
        # 默认超时占位（与全局 DEFAULT_TOOL_TIMEOUT 对齐），供 Base 超时解析链读取
        try:
            from ....core.config import settings as _cfg  # type: ignore
            default_timeout = int(getattr(_cfg, 'DEFAULT_TOOL_TIMEOUT', 120))
        except Exception:
            default_timeout = 120
        try:
            self.config.setdefault('timeout', default_timeout)
        except Exception:
            pass

        # 关键依赖声明与可用性探测（非致命：仅日志告警，不抛错）
        self._deps = ['ffmpeg_tool']
        self._functional = True
        try:
            from ..tool_registry import get_tool_registry as _get_registry  # lazy import
            reg = _get_registry()
            try:
                # 若已注册且可实例化，将返回单例或新实例；否则抛异常
                _ = reg.get_tool('ffmpeg_tool')
            except Exception as dep_err:
                self._functional = False
                self.logger.warning(
                    "composition_tool dependency missing or unavailable: ffmpeg_tool (%s)", dep_err
                )
        except Exception as e:
            # 注册阶段可能尚未可用；保持非致命
            self.logger.debug("composition_tool registry probe skipped: %s", e)

        try:
            self.logger.info(
                "CompositionTool ready (timeout=%ss, deps=%s, functional=%s)",
                self.config.get('timeout'), self._deps, self._functional
            )
        except Exception:
            pass

    @classmethod
    def get_metadata(cls) -> ToolMetadata:
        return ToolMetadata(
            name="composition_tool",
            version="1.0.0",
            description="高阶视频合成工具：封装常见合片/混流工作流，降低规划复杂度",
            tool_type=ToolType.MEDIA_PROCESSING,
            author="system",
            tags=["video", "composition", "audio", "ffmpeg"],
            capabilities=["compose_story_video", "synchronize_audio"],
        )

    def get_fc_visibility(self) -> Dict[str, Any]:
        return {"expose": True, "allowed_actions": ["synchronize_audio", "compose_story_video"]}

    def get_available_actions(self) -> List[str]:
        return ["synchronize_audio", "compose_story_video"]

    def get_action_schema(self, action: str) -> Dict[str, Any]:
        if action == "synchronize_audio":
            return {
                "type": "object",
                "properties": {
                    "video_file": {"type": "string", "description": "输入视频文件（本地路径）"},
                    "audio_file": {"type": "string", "description": "要混入的视频音频（本地路径）"},
                    "output_filename": {"type": "string", "description": "输出文件名，例如 result_with_audio.mp4"},
                    "audio_volume": {"type": "number", "default": 1.0},
                    "video_volume": {"type": "number", "default": 1.0},
                    "ducking": {"type": "boolean", "default": False},
                    "ducking_params": {"type": "object"},
                },
                "required": ["video_file", "audio_file", "output_filename"],
            }
        if action == "compose_story_video":
            return {
                "type": "object",
                "properties": {
                    "scenes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "video_file": {"type": "string"},
                                "duration": {"type": "number"},
                            },
                            "required": ["video_file"],
                        },
                    },
                    "output_filename": {"type": "string"},
                },
                "required": ["scenes", "output_filename"],
            }
        return {}

    async def _execute_impl(self, tool_input: ToolInput) -> Any:
        action = tool_input.action
        params = tool_input.parameters or {}
        # Lazy import to avoid circular import during tool registry bootstrap
        from ..tool_registry import get_tool_registry as _get_registry
        registry = _get_registry()

        if action == "synchronize_audio":
            # 组合动作：视频+音轨混流；不做上传/发布；仅返回本地产物
            # 直接委派到 ffmpeg_tool.add_audio（保持中立，不做复杂时长/多轨处理）
            video_file = params.get("video_file")
            audio_file = params.get("audio_file")
            output_filename = params.get("output_filename")
            if not (video_file and audio_file and output_filename):
                raise ToolError("video_file/audio_file/output_filename is required", self.metadata.name)
            ffmpeg = registry.get_tool("ffmpeg_tool")
            add_params = {
                "video_file": video_file,
                "audio_file": audio_file,
                "output_filename": output_filename,
                "audio_volume": params.get("audio_volume", 1.0),
                "video_volume": params.get("video_volume", 1.0),
                "ducking": bool(params.get("ducking", False)),
                "ducking_params": params.get("ducking_params", {}),
            }
            res = await ffmpeg.execute(ToolInput(action="add_audio", parameters=add_params))
            payload = getattr(res, "result", res) or {}
            return payload

        if action == "compose_story_video":
            # 组合动作：多段视频合片；不做上传/发布；仅返回本地产物
            scenes = params.get("scenes") or []
            output_filename = params.get("output_filename")
            if not scenes or not output_filename:
                raise ToolError("scenes/output_filename is required", self.metadata.name)
            clips: List[str] = []
            for item in scenes:
                if isinstance(item, dict) and item.get("video_file"):
                    clips.append(item["video_file"])
            if not clips:
                raise ToolError("no scenes.video_file provided", self.metadata.name)

            ffmpeg = registry.get_tool("ffmpeg_tool")
            res = await ffmpeg.execute(
                ToolInput(action="merge_videos", parameters={"video_clips": clips, "output_filename": output_filename})
            )
            payload = getattr(res, "result", res) or {}
            return payload

        raise ToolError(f"Unknown action: {action}", self.metadata.name)
