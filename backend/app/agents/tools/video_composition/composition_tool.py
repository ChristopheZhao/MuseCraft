"""
Composition Tool - 组合式视频合成工具

职责边界（简洁说明）：
- 仅封装“确定性顺序”的媒体合成/混流（如合片、配音混流）；
- 不执行上传/发布；不写 Working Memory；无副作用；
- 返回本地 output_path 等结果；发布由 PLAN 决策另行调用存储类工具；
- 作为普通工具参与 FC 暴露与策略守卫，由 Agent 自主选择是否调用。
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

from ..base_tool import AsyncTool, ToolMetadata, ToolType, ToolInput, ToolError
from ....services.file_storage import FileStorageService


class CompositionTool(AsyncTool):
    """高阶合成工具：封装常见、确定性的步骤序列，供 LLM 直接调用。"""

    @staticmethod
    def _normalize_audio_strategy(value: Any) -> str:
        raw = str(value or "").strip().lower()
        alias_map = {
            "adaptive": "adaptive",
            "auto": "adaptive",
            "prefer_native": "adaptive",
            "provider_only": "provider_only",
            "native_only": "provider_only",
            "mas_only": "mas_only",
            "agent_only": "mas_only",
        }
        return alias_map.get(raw, "adaptive")

    @staticmethod
    def _normalize_int(value: Any) -> Any:
        try:
            if value in (None, ""):
                return None
            return int(value)
        except Exception:
            return None

    async def _probe_clip_audio_profile(self, ffmpeg_tool, clip_path: str) -> Any:
        """Return audio profile dict when probe succeeds, None when unknown."""
        if not isinstance(clip_path, str) or not clip_path.strip():
            return None
        normalized = clip_path.strip()
        if normalized.startswith("file://"):
            normalized = normalized[7:]
        if not os.path.exists(normalized):
            return None
        try:
            res = await ffmpeg_tool.execute(
                ToolInput(action="get_video_info", parameters={"file_path": normalized})
            )
            payload = getattr(res, "result", res) or {}
            if not isinstance(payload, dict):
                return None

            codec_raw = payload.get("audio_codec")
            audio_codec = codec_raw.strip().lower() if isinstance(codec_raw, str) and codec_raw.strip() else None
            sample_rate = self._normalize_int(payload.get("sample_rate"))
            channels = self._normalize_int(payload.get("channels"))
            has_audio = bool(audio_codec or sample_rate or channels)
            return {
                "has_audio": has_audio,
                "audio_codec": audio_codec,
                "sample_rate": sample_rate,
                "channels": channels,
            }
        except Exception:
            return None

    async def _probe_clip_has_audio(self, ffmpeg_tool, clip_path: str) -> Any:
        """Return True/False when probe succeeds, None when unknown."""
        profile = await self._probe_clip_audio_profile(ffmpeg_tool, clip_path)
        if profile is None:
            return None
        return bool(profile.get("has_audio"))

    @staticmethod
    def _are_audio_profiles_compatible(audio_profiles: List[Dict[str, Any]]) -> bool:
        if not audio_profiles:
            return False

        baseline: Dict[str, Any] | None = None
        for profile in audio_profiles:
            if not profile.get("has_audio"):
                return False

            current: Dict[str, Any] = {}
            for key in ("audio_codec", "sample_rate", "channels"):
                value = profile.get(key)
                if value in (None, ""):
                    return False
                current[key] = value

            if baseline is None:
                baseline = current
                continue
            if current != baseline:
                return False
        return True

    async def _resolve_preserve_source_audio(
        self,
        params: Dict[str, Any],
        *,
        clips: List[str],
        ffmpeg_tool,
    ) -> bool:
        """Resolve preserve_audio from policy + runtime clip audio facts."""
        explicit = params.get("preserve_audio")
        if isinstance(explicit, bool):
            return explicit
        if isinstance(explicit, str):
            lowered = explicit.strip().lower()
            if lowered in {"true", "1", "yes", "on"}:
                return True
            if lowered in {"false", "0", "no", "off"}:
                return False

        try:
            from ....core.config import settings as _cfg  # type: ignore
            strategy = self._normalize_audio_strategy(getattr(_cfg, "VIDEO_AUDIO_STRATEGY", "adaptive"))
            fallback_default = bool(getattr(_cfg, "COMPOSER_PRESERVE_SOURCE_AUDIO_DEFAULT", False))
        except Exception:
            strategy = "adaptive"
            fallback_default = False

        if strategy == "mas_only":
            return False

        checked = 0
        with_audio = 0
        unknown = 0
        without_audio = 0
        audio_profiles: List[Dict[str, Any]] = []
        for clip in clips or []:
            profile = await self._probe_clip_audio_profile(ffmpeg_tool, clip)
            if profile is None:
                unknown += 1
                continue
            checked += 1
            if bool(profile.get("has_audio")):
                with_audio += 1
                audio_profiles.append(profile)
            else:
                without_audio += 1

        all_have_audio = bool(
            clips
            and checked == len(clips)
            and with_audio == len(clips)
            and without_audio == 0
            and unknown == 0
        )
        audio_compatible = all_have_audio and self._are_audio_profiles_compatible(audio_profiles)
        if strategy in {"provider_only", "adaptive"}:
            # Conservative guard: preserve only when every clip has audio and profiles are compatible.
            return audio_compatible
        return fallback_default

    def _resolve_final_output_path(self, output_filename: str) -> str:
        """将输出落在最终目录，避免临时路径进入审计与上下文。"""
        safe_name = Path(output_filename or "").name.strip()
        if not safe_name:
            safe_name = "final_video.mp4"
        if not Path(safe_name).suffix:
            safe_name = f"{safe_name}.mp4"
        storage = FileStorageService()
        final_dir = storage.get_final_output_dir("video")
        candidate = final_dir / safe_name
        if candidate.exists():
            stem = candidate.stem
            suffix = candidate.suffix or ".mp4"
            counter = 1
            while candidate.exists():
                candidate = final_dir / f"{stem}_{counter}{suffix}"
                counter += 1
        return str(candidate.resolve())

    def _load_scene_media_ref(self, scene_media_ref: str) -> List[Dict[str, Any]]:
        if not scene_media_ref:
            return []
        path = Path(scene_media_ref)
        if not path.is_absolute():
            backend_root = Path(__file__).resolve().parents[4]
            path = backend_root / path
        if not path.exists():
            raise ToolError(f"scene_media_ref not found: {path}", self.metadata.name)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
        except Exception as exc:
            raise ToolError(f"scene_media_ref parse failed: {exc}", self.metadata.name)
        if isinstance(payload, dict):
            payload = payload.get("scenes", [])
        if not isinstance(payload, list):
            raise ToolError("scene_media_ref must contain a scenes list", self.metadata.name)
        return payload

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
                "description": "将单个视频与单条音轨混流为新视频（不拼接、不做多轨混音）",
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
                "description": "按顺序合成多场景视频；若提供场景清单引用则优先使用该清单；如 scenes 含 audio_file，则先逐场景混音再拼接成片",
                "properties": {
                    "scene_media_ref": {
                        "type": "string",
                        "description": "场景合成清单引用（包含场景视频/时长/可选配音）；提供时优先使用",
                    },
                    "scenes": {
                        "type": "array",
                        "description": "场景列表（无引用清单时使用）",
                        "items": {
                            "type": "object",
                            "properties": {
                                "video_file": {"type": "string"},
                                "audio_file": {"type": "string"},
                                "duration": {"type": "number"},
                            },
                            "required": ["video_file"],
                        },
                    },
                    "output_filename": {"type": "string", "description": "输出文件名，例如 final_story.mp4"},
                    "preserve_audio": {
                        "type": "boolean",
                        "description": "可选：拼接阶段是否保留源视频音轨；不传时按系统策略自适应",
                    },
                },
                "required": ["output_filename"],
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
            output_path = self._resolve_final_output_path(output_filename)
            add_params = {
                "video_file": video_file,
                "audio_file": audio_file,
                "output_filename": output_path,
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
            scene_media_ref = params.get("scene_media_ref") or ""
            if scene_media_ref:
                scenes = self._load_scene_media_ref(scene_media_ref)
            output_filename = params.get("output_filename")
            if not scenes or not output_filename:
                raise ToolError("scenes or scene_media_ref and output_filename are required", self.metadata.name)
            scene_items: List[Dict[str, str]] = []
            for item in scenes:
                if not isinstance(item, dict):
                    continue
                video_file = item.get("video_file")
                if not video_file:
                    continue
                scene_items.append(
                    {
                        "video_file": video_file,
                        "audio_file": item.get("audio_file") or "",
                    }
                )
            if not scene_items:
                raise ToolError("no scenes.video_file provided", self.metadata.name)

            ffmpeg = registry.get_tool("ffmpeg_tool")
            clips: List[str] = [item["video_file"] for item in scene_items]
            audio_files = [item.get("audio_file") or "" for item in scene_items]
            if any(audio_files) and not all(audio_files):
                raise ToolError("audio_file missing for some scenes", self.metadata.name)

            preserve_audio = await self._resolve_preserve_source_audio(
                params,
                clips=clips,
                ffmpeg_tool=ffmpeg,
            )
            if all(audio_files) and audio_files:
                processed: List[str] = []
                for idx, (video_file, audio_file) in enumerate(zip(clips, audio_files), start=1):
                    if not os.path.exists(audio_file):
                        raise ToolError(f"audio_file not found: {audio_file}", self.metadata.name)
                    add_params = {
                        "video_file": video_file,
                        "audio_file": audio_file,
                        "output_filename": f"scene_{idx}_with_audio.mp4",
                    }
                    res = await ffmpeg.execute(ToolInput(action="add_audio", parameters=add_params))
                    payload = getattr(res, "result", res) or {}
                    output_file = payload.get("output_file") or payload.get("output_path")
                    if not output_file:
                        raise ToolError("add_audio returned no output_file", self.metadata.name)
                    processed.append(output_file)
                clips = processed
                preserve_audio = True

            output_path = self._resolve_final_output_path(output_filename)
            res = await ffmpeg.execute(
                ToolInput(
                    action="merge_videos",
                    parameters={
                        "video_clips": clips,
                        "output_filename": output_path,
                        "preserve_audio": preserve_audio,
                    },
                )
            )
            payload = getattr(res, "result", res) or {}
            return payload

        raise ToolError(f"Unknown action: {action}", self.metadata.name)
