"""
FFmpeg Video Processing Tool - FFmpeg视频处理工具
提供视频合成、转换、剪辑等功能
"""

import os
import subprocess
import tempfile
import json
import re
import asyncio
import uuid
from typing import Dict, Any, List, Optional, Union
from pathlib import Path

from ..base_tool import AsyncTool, ToolMetadata, ToolType, ToolInput, ToolError, ToolValidationError
try:
    from ....core.config import settings as _app_settings
except Exception:
    _app_settings = None


class FFmpegTool(AsyncTool):
    """
    FFmpeg视频处理工具
    
    支持功能：
    - 视频合成和拼接
    - 视频格式转换
    - 添加音频背景
    - 视频剪辑和裁剪
    - 视频质量调整
    - 添加字幕和水印
    """
    
    @classmethod
    def get_metadata(cls) -> ToolMetadata:
        return ToolMetadata(
            name="ffmpeg_tool",
            version="1.0.0",
            description="FFmpeg视频处理工具，支持视频合成、转换、剪辑等功能",
            tool_type=ToolType.MEDIA_PROCESSING,
            author="system",
            tags=["video", "ffmpeg", "media", "processing", "composition"],
            capabilities=[
                "video_composition",
                "format_conversion",
                "audio_mixing",
                "video_editing",
                "quality_adjustment",
                "subtitle_overlay",
                "watermark_overlay"
            ],
            limitations=[
                "requires_ffmpeg_installed",
                "processing_time_varies",
                "disk_space_required",
                "cpu_intensive"
            ]
        )
    
    def _initialize(self):
        """初始化FFmpeg工具"""
        # 检查FFmpeg是否安装
        try:
            result = subprocess.run(
                ["ffmpeg", "-version"], 
                capture_output=True, 
                text=True, 
                timeout=10
            )
            if result.returncode != 0:
                raise ToolError("FFmpeg not found or not working properly", self.metadata.name)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            raise ToolError("FFmpeg not installed or not in PATH", self.metadata.name)
        
        # 配置参数（默认落盘到项目的 TEMP_PATH 下，保持与存储工具一致）
        default_base = None
        try:
            if _app_settings is not None and getattr(_app_settings, 'TEMP_PATH', None):
                default_base = _app_settings.TEMP_PATH
        except Exception:
            default_base = None
        if not default_base:
            default_base = "/tmp"
        default_output_dir = os.path.join(default_base, "video_output")
        default_temp_dir = os.path.join(default_base, "ffmpeg_temp")

        self.output_dir = self.config.get("output_dir", default_output_dir)
        self.temp_dir = self.config.get("temp_dir", default_temp_dir)
        self.max_resolution = self.config.get("max_resolution", "1920x1080")
        self.default_fps = self.config.get("default_fps", 30)
        self.default_bitrate = self.config.get("default_bitrate", "2M")
        self.timeout = self.config.get("timeout", 600)  # 10分钟超时
        
        # 创建目录
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.temp_dir, exist_ok=True)
        
        self.logger.info(f"Initialized FFmpeg tool with output dir: {self.output_dir}")

    def _resolve_output_path(self, output_filename: str) -> str:
        output_name = str(output_filename or "").strip()
        if not output_name:
            raise ToolValidationError("output_filename is required", self.metadata.name)
        candidate = Path(output_name)
        if candidate.is_absolute() or candidate.parent != Path("."):
            output_path = candidate
        else:
            output_path = Path(self.output_dir) / candidate
        output_path.parent.mkdir(parents=True, exist_ok=True)
        return str(output_path)
    
    def get_available_actions(self) -> List[str]:
        return [
            "compose_video",
            "convert_format", 
            "add_audio",
            "extract_last_frame",
            "extract_frames",
            "create_slideshow",
            "concat_audio",
            "add_subtitles",
            "add_watermark",
            "adjust_quality",
            "get_video_info",
            "trim_video",
            "merge_videos",
            "create_transitions"
        ]
    
    def get_action_schema(self, action: str) -> Dict[str, Any]:
        schemas = {
            "extract_last_frame": {
                "type": "object",
                "properties": {
                    "video_path": {"type": "string", "description": "本地视频路径"},
                    "video_url": {"type": "string", "description": "可下载的视频URL（与video_path二选一）"},
                    "output_format": {"type": "string", "enum": ["jpg", "png"], "default": "jpg"},
                    "output_quality": {"type": "integer", "minimum": 2, "maximum": 31, "default": 2, "description": "jpg质量（qscale），数值越小质量越高"},
                    "resize_width": {"type": "integer", "description": "可选，缩放宽度"},
                    "resize_height": {"type": "integer", "description": "可选，缩放高度"},
                    "time_tolerance": {"type": "number", "default": 0.1, "description": "尾帧时间容忍（秒），避免容器尾部空白"},
                    "output_filename": {"type": "string", "description": "输出文件名（可选）"}
                },
                "required": []
            },
            "compose_video": {
                "type": "object",
                "properties": {
                    "video_clips": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "视频片段文件路径列表"
                    },
                    "audio_file": {"type": "string", "description": "背景音频文件路径"},
                    "output_filename": {"type": "string", "description": "输出文件名"},
                    "resolution": {"type": "string", "description": "输出分辨率，如1920x1080"},
                    "fps": {"type": "integer", "description": "帧率"},
                    "bitrate": {"type": "string", "description": "比特率，如2M"},
                    "transitions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "转场效果列表"
                    }
                },
                "required": ["video_clips", "output_filename"]
            },
            "convert_format": {
                "type": "object",
                "properties": {
                    "input_file": {"type": "string", "description": "输入视频文件"},
                    "output_format": {"type": "string", "enum": ["mp4", "avi", "mov", "webm", "mkv"]},
                    "output_filename": {"type": "string"},
                    "quality": {"type": "string", "enum": ["high", "medium", "low"]}
                },
                "required": ["input_file", "output_format", "output_filename"]
            },
            "add_audio": {
                "type": "object",
                "properties": {
                    "video_file": {"type": "string", "description": "视频文件路径"},
                    "audio_file": {"type": "string", "description": "音频文件路径"},
                    "output_filename": {"type": "string"},
                    "audio_volume": {"type": "number", "description": "音频音量 0.0-1.0"},
                    "video_volume": {"type": "number", "description": "原视频音量 0.0-1.0"}
                },
                "required": ["video_file", "audio_file", "output_filename"]
            },
            "create_slideshow": {
                "type": "object",
                "properties": {
                    "images": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "图片文件路径列表"
                    },
                    "duration_per_image": {"type": "number", "description": "每张图片显示时长(秒)"},
                    "audio_file": {"type": "string", "description": "背景音乐"},
                    "output_filename": {"type": "string"},
                    "transition_effect": {"type": "string", "enum": ["fade", "slide", "zoom", "none"]}
                },
                "required": ["images", "output_filename"]
            },
            "concat_audio": {
                "type": "object",
                "properties": {
                    "audio_files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "按时间顺序排列的音频文件路径"
                    },
                    "output_filename": {
                        "type": "string",
                        "description": "输出文件名，例如 voice_track.wav"
                    }
                },
                "required": ["audio_files"]
            }
        }
        
        return schemas.get(action, {})
    
    async def _execute_impl(self, tool_input: ToolInput) -> Any:
        """执行FFmpeg操作"""
        action = tool_input.action
        params = tool_input.parameters
        
        if action == "compose_video":
            return await self._compose_video(params)
        elif action == "convert_format":
            return await self._convert_format(params)
        elif action == "add_audio":
            return await self._add_audio(params)
        elif action == "extract_last_frame":
            return await self._extract_last_frame(params)
        elif action == "extract_frames":
            return await self._extract_frames(params)
        elif action == "create_slideshow":
            return await self._create_slideshow(params)
        elif action == "add_subtitles":
            return await self._add_subtitles(params)
        elif action == "add_watermark":
            return await self._add_watermark(params)
        elif action == "adjust_quality":
            return await self._adjust_quality(params)
        elif action == "get_video_info":
            return await self._get_video_info(params)
        elif action == "trim_video":
            return await self._trim_video(params)
        elif action == "merge_videos":
            return await self._merge_videos(params)
        elif action == "create_transitions":
            return await self._create_transitions(params)
        elif action == "concat_audio":
            return await self._concat_audio(params)
        else:
            raise ToolValidationError(f"Unknown action: {action}", self.metadata.name)
    
    async def _compose_video(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """合成视频"""
        try:
            video_clips = params["video_clips"]
            output_filename = params["output_filename"]
            audio_file = params.get("audio_file")
            resolution = params.get("resolution", self.max_resolution)
            fps = params.get("fps", self.default_fps)
            bitrate = params.get("bitrate", self.default_bitrate)
            
            # 验证输入文件
            for clip in video_clips:
                if not os.path.exists(clip):
                    raise ToolError(f"Video clip not found: {clip}", self.metadata.name)
            
            # 创建临时文件列表
            temp_file_list = os.path.join(self.temp_dir, f"filelist_{os.getpid()}.txt")
            with open(temp_file_list, 'w') as f:
                for clip in video_clips:
                    f.write(f"file '{os.path.abspath(clip)}'\n")
            
            output_path = self._resolve_output_path(output_filename)
            
            # 构建FFmpeg命令
            cmd = [
                "ffmpeg", "-y",  # 覆盖输出文件
                "-f", "concat",
                "-safe", "0",
                "-i", temp_file_list,
                "-vf", f"scale={resolution}",
                "-r", str(fps),
                "-b:v", bitrate,
                "-c:v", "libx264",
                "-preset", "medium",
                "-crf", "23"
            ]
            
            # 添加音频
            if audio_file and os.path.exists(audio_file):
                cmd.extend([
                    "-i", audio_file,
                    "-c:a", "aac",
                    "-b:a", "128k",
                    "-shortest"  # 以较短的流为准
                ])
            else:
                cmd.extend(["-an"])  # 无音频
            
            cmd.append(output_path)
            
            # 执行命令
            self.logger.info(f"Running FFmpeg command: {' '.join(cmd)}")
            
            return {
                "output_file": output_path,
                "file_size": file_size,
                "video_info": video_info,
                "clips_processed": len(video_clips),
                "has_audio": audio_file is not None
            }
            
        except asyncio.TimeoutError:
            raise ToolError("Video composition timeout", self.metadata.name)
        except Exception as e:
            raise ToolError(f"Video composition failed: {str(e)}", self.metadata.name)
    
    async def _convert_format(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """格式转换"""
        try:
            input_file = params["input_file"]
            output_format = params["output_format"]
            output_filename = params["output_filename"]
            quality = params.get("quality", "medium")
            
            if not os.path.exists(input_file):
                raise ToolError(f"Input file not found: {input_file}", self.metadata.name)
            
            output_path = self._resolve_output_path(output_filename)
            
            # 质量设置
            quality_settings = {
                "high": {"crf": "18", "preset": "slow"},
                "medium": {"crf": "23", "preset": "medium"},
                "low": {"crf": "28", "preset": "fast"}
            }
            
            settings = quality_settings[quality]
            
            cmd = [
                "ffmpeg", "-y",
                "-i", input_file,
                "-c:v", "libx264",
                "-crf", settings["crf"],
                "-preset", settings["preset"],
                "-c:a", "aac",
                "-b:a", "128k",
                output_path
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.timeout
            )
            
            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown FFmpeg error"
                raise ToolError(f"Format conversion failed: {error_msg}", self.metadata.name)
            
            file_size = os.path.getsize(output_path)
            
            return {
                "output_file": output_path,
                "input_format": os.path.splitext(input_file)[1][1:],
                "output_format": output_format,
                "file_size": file_size,
                "quality": quality
            }
            
        except Exception as e:
            raise ToolError(f"Format conversion failed: {str(e)}", self.metadata.name)
    
    async def _add_audio(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """添加音频"""
        try:
            video_file = params["video_file"]
            audio_file = params["audio_file"]
            output_filename = params["output_filename"]
            audio_volume = float(params.get("audio_volume", 0.5))
            video_volume = float(params.get("video_volume", 0.3))
            ducking = bool(params.get("ducking", False))
            ducking_params = params.get("ducking_params") or {}
            if not isinstance(ducking_params, dict):
                ducking_params = {}
            mix_strategy = params.get("mix_strategy", "default")
            
            for file_path in [video_file, audio_file]:
                if not os.path.exists(file_path):
                    raise ToolError(f"File not found: {file_path}", self.metadata.name)
            
            output_path = self._resolve_output_path(output_filename)
            
            # 检查视频是否包含音频流
            def _resolve_audio_stream_ref(path: str) -> Optional[str]:
                try:
                    probe = subprocess.run(
                        [
                            "ffprobe",
                            "-v",
                            "error",
                            "-select_streams",
                            "a",
                            "-show_entries",
                            "stream=index",
                            "-of",
                            "json",
                            path,
                        ],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    if probe.returncode != 0:
                        return None
                    data = json.loads(probe.stdout or "{}")
                    indexes = data.get("streams") or []
                    if not indexes:
                        return None
                    first_idx = indexes[0].get("index")
                    if first_idx is None:
                        return None
                    return f"0:{first_idx}"
                except Exception:
                    # 退化：尝试通过 ffmpeg -i 输出判断
                    try:
                        p = subprocess.run(["ffmpeg", "-i", path], capture_output=True, text=True)
                        out = (p.stderr or "") + (p.stdout or "")
                        if "Audio:" in out:
                            # 尝试提取 "Stream #0:x" 格式
                            import re
                            match = re.search(r"Stream #0:(\d+).*Audio", out)
                            if match:
                                return f"0:{match.group(1)}"
                            return "0:1"
                        return None
                    except Exception:
                        return None

            audio_stream_ref = _resolve_audio_stream_ref(video_file)
            video_has_audio = bool(audio_stream_ref)

            # 当需要 ducking 时，若视频没有音轨则降级为普通混音
            effective_ducking = ducking and video_has_audio

            def _fmt(value: float) -> str:
                return f"{value:.6f}".rstrip("0").rstrip(".") if isinstance(value, float) else str(value)

            def _build_simple_mix_cmd() -> tuple[list[str], str]:
                if video_has_audio:
                    simple_filter = (
                        f"[{audio_stream_ref}]volume={_fmt(video_volume)}[va];"
                        f"[1:a]volume={_fmt(audio_volume)}[bg];"
                        "[va][bg]amix=inputs=2:duration=first[a]"
                    )
                    return ([
                        "ffmpeg", "-y",
                        "-i", video_file,
                        "-i", audio_file,
                        "-filter_complex", simple_filter,
                        "-map", "0:v",
                        "-map", "[a]",
                        "-c:v", "copy",
                        "-c:a", "aac",
                        "-shortest",
                        output_path
                    ], "voice+bgm amix")

                bg_filter = f"[1:a]volume={_fmt(audio_volume)}[bg]"
                return ([
                    "ffmpeg", "-y",
                    "-i", video_file,
                    "-i", audio_file,
                    "-filter_complex", bg_filter,
                    "-map", "0:v",
                    "-map", "[bg]",
                    "-c:v", "copy",
                    "-c:a", "aac",
                    "-shortest",
                    output_path
                ], "bgm only mix")

            fallback_cmd: list[str] | None = None
            fallback_desc = ""

            if effective_ducking:
                threshold = float(ducking_params.get("threshold", 0.05))
                ratio = float(ducking_params.get("ratio", 6.0))
                attack = float(ducking_params.get("attack", 5.0))
                release = float(ducking_params.get("release", 250.0))
                makeup = float(ducking_params.get("makeup", 1.0))
                if makeup < 1.0:
                    makeup = 1.0
                    ducking_params["makeup"] = makeup
                recovery = float(ducking_params.get("recovery", 2.0))

                filter_complex = (
                    f"[{audio_stream_ref}]volume={_fmt(video_volume)}[voice];"
                    f"[1:a]volume={_fmt(audio_volume)}[bg];"
                    f"[bg][voice]sidechaincompress=threshold={_fmt(threshold)}:ratio={_fmt(ratio)}:"
                    f"attack={_fmt(attack)}:release={_fmt(release)}:makeup={_fmt(makeup)}[bgduck];"
                    f"[voice][bgduck]amix=inputs=2:duration=first:dropout_transition={_fmt(recovery)}[a]"
                )
                cmd = [
                    "ffmpeg", "-y",
                    "-i", video_file,
                    "-i", audio_file,
                    "-filter_complex", filter_complex,
                    "-map", "0:v",
                    "-map", "[a]",
                    "-c:v", "copy",
                    "-c:a", "aac",
                    "-shortest",
                    output_path,
                ]
                fallback_cmd, fallback_desc = _build_simple_mix_cmd()
            else:
                cmd, _ = _build_simple_mix_cmd()

            async def _run_ffmpeg(command: list[str]) -> tuple[int, bytes, bytes]:
                proc = await asyncio.create_subprocess_exec(
                    *command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                out, err = await asyncio.wait_for(proc.communicate(), timeout=self.timeout)
                return proc.returncode, out, err

            returncode, stdout, stderr = await _run_ffmpeg(cmd)

            if returncode != 0:
                stderr_text = (stderr or b"").decode(errors="ignore")

                if effective_ducking and fallback_cmd is not None:
                    self.logger.warning(
                        "Audio ducking mix failed (exit %s): %s. Falling back to %s.",
                        returncode,
                        stderr_text.strip() or "no stderr",
                        fallback_desc,
                    )
                    if os.path.exists(output_path):
                        try:
                            os.remove(output_path)
                        except OSError:
                            pass

                    fallback_rc, fb_stdout, fb_stderr = await _run_ffmpeg(fallback_cmd)
                    if fallback_rc != 0:
                        fallback_text = (fb_stderr or b"").decode(errors="ignore")
                        raise ToolError(
                            f"Audio mixing failed after fallback: {fallback_text or stderr_text or 'ffmpeg execution error'}",
                            self.metadata.name
                        )
                    effective_ducking = False
                else:
                    raise ToolError(
                        f"Audio mixing failed: {stderr_text or 'ffmpeg execution error'}",
                        self.metadata.name
                    )

            return {
                "output_file": output_path,
                "file_size": os.path.getsize(output_path),
                "audio_volume": audio_volume,
                "video_volume": video_volume,
                "ducking": effective_ducking,
                "mix_strategy": mix_strategy,
            }
            
        except Exception as e:
            raise ToolError(f"Audio mixing failed: {str(e)}", self.metadata.name)
    
    async def _create_slideshow(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """创建图片幻灯片视频"""
        try:
            images = params["images"]
            output_filename = params["output_filename"]
            duration_per_image = params.get("duration_per_image", 3.0)
            audio_file = params.get("audio_file")
            transition_effect = params.get("transition_effect", "fade")
            
            # 验证图片文件
            for img in images:
                if not os.path.exists(img):
                    raise ToolError(f"Image not found: {img}", self.metadata.name)
            
            if len(images) == 0:
                raise ToolError("No images provided for slideshow", self.metadata.name)
            
            output_path = self._resolve_output_path(output_filename)
            
            # 如果只有一张图片，简单处理
            if len(images) == 1:
                cmd = [
                    "ffmpeg", "-y",
                    "-loop", "1",
                    "-t", str(duration_per_image),
                    "-i", images[0],
                    "-c:v", "libx264",
                    "-pix_fmt", "yuv420p",
                    "-r", str(self.default_fps)
                ]
                
                if audio_file and os.path.exists(audio_file):
                    cmd.extend(["-i", audio_file, "-c:a", "aac", "-shortest"])
                else:
                    cmd.extend(["-an"])  # 无音频
                
                cmd.append(output_path)
            
            else:
                # 多张图片，使用更稳定的实现
                inputs = []
                for i, img in enumerate(images):
                    inputs.extend(["-loop", "1", "-t", str(duration_per_image), "-i", img])
                
                cmd = ["ffmpeg", "-y"] + inputs
                
                # 根据转场效果选择不同的filter
                if transition_effect == "fade" and len(images) > 1:
                    # 构建xfade链式转场
                    fade_duration = 0.5
                    fade_offset = duration_per_image - fade_duration
                    
                    # 构建filter_complex链
                    filter_parts = []
                    current_label = "[0:v]"
                    
                    for i in range(1, len(images)):
                        next_label = f"[v{i}]" if i < len(images) - 1 else "[out]"
                        filter_parts.append(f"{current_label}[{i}:v]xfade=transition=fade:duration={fade_duration}:offset={fade_offset}{next_label}")
                        current_label = f"[v{i}]"
                    
                    filter_complex = ";".join(filter_parts)
                    cmd.extend(["-filter_complex", filter_complex, "-map", "[out]"])
                else:
                    # 简单拼接，无转场
                    cmd.extend(["-filter_complex", f"concat=n={len(images)}:v=1:a=0[v]", "-map", "[v]"])
                
                # 添加音频
                if audio_file and os.path.exists(audio_file):
                    cmd.extend(["-i", audio_file, "-c:a", "aac", "-shortest"])
                else:
                    cmd.extend(["-an"])  # 无音频
                
                cmd.extend([
                    "-c:v", "libx264",
                    "-pix_fmt", "yuv420p",
                    "-r", str(self.default_fps),
                    output_path
                ])
            
            self.logger.info(f"Creating slideshow with command: {' '.join(cmd[:10])}...")
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.timeout
            )
            
            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown FFmpeg error"
                self.logger.error(f"Slideshow creation failed: {error_msg}")
                raise ToolError(f"Slideshow creation failed: {error_msg}", self.metadata.name)
            
            return {
                "output_file": output_path,
                "file_size": os.path.getsize(output_path),
                "image_count": len(images),
                "duration_per_image": duration_per_image,
                "total_duration": len(images) * duration_per_image,
                "has_audio": audio_file is not None,
                "transition_effect": transition_effect
            }
            
        except Exception as e:
            self.logger.error(f"Slideshow creation error: {str(e)}")
            raise ToolError(f"Slideshow creation failed: {str(e)}", self.metadata.name)
    
    async def _get_video_info(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """获取视频信息"""
        try:
            file_path = params["file_path"]
            
            if not os.path.exists(file_path):
                raise ToolError(f"Video file not found: {file_path}", self.metadata.name)
            
            cmd = [
                "ffprobe", 
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                file_path
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown ffprobe error"
                raise ToolError(f"Video info extraction failed: {error_msg}", self.metadata.name)
            
            info = json.loads(stdout.decode())
            
            # 提取关键信息
            video_stream = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
            audio_stream = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
            
            result = {
                "file_path": file_path,
                "file_size": int(info["format"]["size"]),
                "duration": float(info["format"]["duration"]),
                "format_name": info["format"]["format_name"],
                "bit_rate": int(info["format"]["bit_rate"]),
            }
            
            if video_stream:
                result.update({
                    "width": int(video_stream["width"]),
                    "height": int(video_stream["height"]),
                    "fps": eval(video_stream["r_frame_rate"]),
                    "video_codec": video_stream["codec_name"],
                    "pixel_format": video_stream["pix_fmt"]
                })
            
            if audio_stream:
                result.update({
                    "audio_codec": audio_stream["codec_name"],
                    "sample_rate": int(audio_stream["sample_rate"]),
                    "channels": int(audio_stream["channels"])
                })
            
            return result
            
        except Exception as e:
            raise ToolError(f"Video info extraction failed: {str(e)}", self.metadata.name)
    
    def _validate_action_parameters(self, action: str, parameters: Dict[str, Any]):
        """验证操作参数"""
        if action == "compose_video":
            if not parameters.get("video_clips"):
                raise ToolValidationError("video_clips are required for compose_video")
            if not parameters.get("output_filename"):
                raise ToolValidationError("output_filename is required for compose_video")
        
        elif action == "convert_format":
            if not parameters.get("input_file"):
                raise ToolValidationError("input_file is required for convert_format")
            if not parameters.get("output_format"):
                raise ToolValidationError("output_format is required for convert_format")
            if not parameters.get("output_filename"):
                raise ToolValidationError("output_filename is required for convert_format")
        
        elif action == "add_audio":
            for param in ["video_file", "audio_file", "output_filename"]:
                if not parameters.get(param):
                    raise ToolValidationError(f"{param} is required for add_audio")
        
        elif action == "create_slideshow":
            if not parameters.get("images"):
                raise ToolValidationError("images are required for create_slideshow")
            if not parameters.get("output_filename"):
                raise ToolValidationError("output_filename is required for create_slideshow")
        
        elif action == "get_video_info":
            if not parameters.get("file_path"):
                raise ToolValidationError("file_path is required for get_video_info")
        
        elif action == "extract_last_frame":
            if not parameters.get("video_path") and not parameters.get("video_url"):
                raise ToolValidationError("video_path or video_url is required for extract_last_frame")

    async def _extract_last_frame(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """提取视频尾帧（或接近尾帧的一帧）"""
        try:
            video_path = params.get("video_path")
            video_url = params.get("video_url")
            output_format = params.get("output_format", "jpg")
            q = int(params.get("output_quality", 2))
            resize_w = params.get("resize_width")
            resize_h = params.get("resize_height")
            tol = float(params.get("time_tolerance", 0.1))
            output_filename = params.get("output_filename")

            # 若提供URL，下载到临时文件
            temp_input = None
            if video_url and not video_path:
                import urllib.request
                tmp_fd, tmp_path = tempfile.mkstemp(dir=self.temp_dir, suffix=".mp4")
                os.close(tmp_fd)
                urllib.request.urlretrieve(video_url, tmp_path)
                video_path = tmp_path
                temp_input = tmp_path

            if not video_path or not os.path.exists(video_path):
                raise ToolError("Video file not found", self.metadata.name)

            # 探测时长
            info = await self._get_video_info({"file_path": video_path})
            duration = float(info.get("duration", 0.0))
            ts = max(duration - tol, 0.0)

            # 输出文件
            if not output_filename:
                base = os.path.splitext(os.path.basename(video_path))[0]
                output_filename = f"{base}_last_frame.{output_format}"
            out_path = self._resolve_output_path(output_filename)

            # 构建vf
            vf = None
            if resize_w and resize_h:
                vf = f"scale={resize_w}:{resize_h}"
            elif resize_w:
                vf = f"scale={resize_w}:-1:force_original_aspect_ratio=decrease"
            elif resize_h:
                vf = f"scale=-1:{resize_h}:force_original_aspect_ratio=decrease"

            cmd = [
                "ffmpeg", "-y",
                "-ss", f"{ts}",
                "-i", video_path,
                "-frames:v", "1",
            ]
            if output_format == "jpg":
                cmd += ["-q:v", str(q)]
            if vf:
                cmd += ["-vf", vf]
            cmd += [out_path]

            self.logger.info(f"Extract last frame: {' '.join(cmd)}")
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=self.timeout)
            if process.returncode != 0:
                raise ToolError(f"FFmpeg frame extraction failed: {stderr.decode()}", self.metadata.name)

            # 获取图片信息（尺寸可从视频info近似或二次读取）
            result = {
                "image_path": out_path,
                "duration": duration,
                "frame_ts": ts,
                "width": info.get("width"),
                "height": info.get("height")
            }

            # 清理临时下载
            if temp_input:
                try:
                    os.unlink(temp_input)
                except Exception:
                    pass

            return result
        except asyncio.TimeoutError:
            raise ToolError("Frame extraction timeout", self.metadata.name)
        except Exception as e:
            raise ToolError(f"Extract last frame failed: {str(e)}", self.metadata.name)

    async def _concat_audio(self, params: Dict[str, Any]) -> Dict[str, Any]:
        audio_files = params.get("audio_files") or []
        if not audio_files:
            raise ToolValidationError("audio_files is required for concat_audio", self.metadata.name)

        for file_path in audio_files:
            if not os.path.exists(file_path):
                raise ToolError(f"Audio file not found: {file_path}", self.metadata.name)

        output_filename = params.get("output_filename") or f"concat_{uuid.uuid4().hex}.wav"
        output_path = self._resolve_output_path(output_filename)

        tmp_file = tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt", dir=self.temp_dir)
        try:
            for file_path in audio_files:
                tmp_file.write(f"file '{os.path.abspath(file_path)}'\n")
            tmp_file.flush()
            tmp_file.close()

            cmd = [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", tmp_file.name,
                "-c", "copy",
                output_path
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            if process.returncode != 0:
                error_msg = (stderr or b"").decode(errors="ignore")
                raise ToolError(f"Audio concat failed: {error_msg}", self.metadata.name)

            file_size = os.path.getsize(output_path)
            return {
                "output_file": output_path,
                "input_files": audio_files,
                "file_size": file_size,
            }
        finally:
            try:
                tmp_file.close()
            except Exception:
                pass
            try:
                os.unlink(tmp_file.name)
            except Exception:
                pass

    async def _merge_videos(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """拼接多个视频片段为一个视频（可选保留音轨）。"""
        try:
            video_clips = params.get("video_clips") or []
            output_filename = params.get("output_filename") or "merged_output.mp4"
            preserve_audio = bool(params.get("preserve_audio", False))
            if not video_clips or not isinstance(video_clips, list):
                raise ToolValidationError("video_clips is required and must be a list", self.metadata.name)

            # 校验输入文件存在
            for clip in video_clips:
                if not os.path.exists(clip):
                    raise ToolError(f"Video clip not found: {clip}", self.metadata.name)

            output_path = self._resolve_output_path(output_filename)

            # 单文件：直接复制到输出目录
            if len(video_clips) == 1:
                import shutil
                shutil.copy2(video_clips[0], output_path)
                return {
                    "output_path": output_path,
                    "clips_processed": 1
                }

            # 多文件：使用 concat demuxer 并统一编码，避免编码不一致导致失败
            temp_file_list = os.path.join(self.temp_dir, f"filelist_{os.getpid()}.txt")
            with open(temp_file_list, 'w') as f:
                for clip in video_clips:
                    f.write(f"file '{os.path.abspath(clip)}'\n")

            cmd = [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", temp_file_list,
                "-c:v", "libx264",
                "-preset", "medium",
                "-crf", "23",
                "-r", str(self.default_fps),
            ]
            if preserve_audio:
                cmd.extend(["-c:a", "aac"])
            else:
                cmd.append("-an")
            cmd.append(output_path)

            self.logger.info(f"Merging videos: {' '.join(cmd)}")
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=self.timeout)

            # 清理临时文件
            try:
                os.unlink(temp_file_list)
            except Exception:
                pass

            if process.returncode != 0:
                err = stderr.decode() if stderr else "Unknown FFmpeg error"
                raise ToolError(f"FFmpeg merge failed: {err}", self.metadata.name)

            # 可选：为合成结果注入静音轨（配置开关），便于后续统一混音流程
            try:
                from ....core.config import settings as _app_settings
                inject_silent = bool(getattr(_app_settings, 'COMPOSER_INJECT_SILENT_AUDIO', False))
                sr = int(getattr(_app_settings, 'COMPOSER_SILENT_AUDIO_SAMPLE_RATE', 48000))
                ch = int(getattr(_app_settings, 'COMPOSER_SILENT_AUDIO_CHANNELS', 2))
            except Exception:
                inject_silent = False
                sr, ch = 48000, 2

            def _has_audio_stream(path: str) -> bool:
                try:
                    probe = subprocess.run(
                        ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=index", "-of", "csv=p=0", path],
                        capture_output=True, text=True, timeout=10
                    )
                    return probe.returncode == 0 and bool((probe.stdout or "").strip())
                except Exception:
                    return False

            if inject_silent and not _has_audio_stream(output_path):
                temp_out = os.path.join(os.path.dirname(output_path), f"temp_{os.path.basename(output_path)}")
                cmd2 = [
                    "ffmpeg", "-y",
                    "-i", output_path,
                    "-f", "lavfi",
                    "-i", f"anullsrc=channel_layout={'stereo' if ch==2 else 'mono'}:sample_rate={sr}",
                    "-shortest",
                    "-map", "0:v",
                    "-map", "1:a",
                    "-c:v", "copy",
                    "-c:a", "aac",
                    temp_out
                ]
                proc2 = await asyncio.create_subprocess_exec(
                    *cmd2, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )
                _, err2 = await asyncio.wait_for(proc2.communicate(), timeout=self.timeout)
                if proc2.returncode == 0:
                    try:
                        os.replace(temp_out, output_path)
                    except Exception:
                        pass
                else:
                    self.logger.warning(f"Inject silent audio failed: {err2.decode() if err2 else ''}")

            return {"output_path": output_path, "clips_processed": len(video_clips)}
        except asyncio.TimeoutError:
            raise ToolError("Video merge timeout", self.metadata.name)
        except Exception as e:
            raise ToolError(f"Video merge failed: {str(e)}", self.metadata.name)
