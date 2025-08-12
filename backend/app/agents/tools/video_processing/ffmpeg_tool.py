"""
FFmpeg Video Processing Tool - FFmpeg视频处理工具
提供视频合成、转换、剪辑等功能
"""

import os
import subprocess
import tempfile
import json
import asyncio
from typing import Dict, Any, List, Optional, Union
from pathlib import Path

from ..base_tool import AsyncTool, ToolMetadata, ToolType, ToolInput, ToolError, ToolValidationError


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
        
        # 配置参数
        self.output_dir = self.config.get("output_dir", "/tmp/video_output")
        self.temp_dir = self.config.get("temp_dir", "/tmp/ffmpeg_temp")
        self.max_resolution = self.config.get("max_resolution", "1920x1080")
        self.default_fps = self.config.get("default_fps", 30)
        self.default_bitrate = self.config.get("default_bitrate", "2M")
        self.timeout = self.config.get("timeout", 600)  # 10分钟超时
        
        # 创建目录
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.temp_dir, exist_ok=True)
        
        self.logger.info(f"Initialized FFmpeg tool with output dir: {self.output_dir}")
    
    def get_available_actions(self) -> List[str]:
        return [
            "compose_video",
            "convert_format", 
            "add_audio",
            "extract_frames",
            "create_slideshow",
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
            
            output_path = os.path.join(self.output_dir, output_filename)
            
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
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), 
                timeout=self.timeout
            )
            
            # 清理临时文件
            try:
                os.unlink(temp_file_list)
            except:
                pass
            
            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown FFmpeg error"
                raise ToolError(f"FFmpeg composition failed: {error_msg}", self.metadata.name)
            
            # 获取输出文件信息
            file_size = os.path.getsize(output_path)
            video_info = await self._get_video_info({"file_path": output_path})
            
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
            
            output_path = os.path.join(self.output_dir, output_filename)
            
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
            audio_volume = params.get("audio_volume", 0.5)
            video_volume = params.get("video_volume", 0.3)
            
            for file_path in [video_file, audio_file]:
                if not os.path.exists(file_path):
                    raise ToolError(f"File not found: {file_path}", self.metadata.name)
            
            output_path = os.path.join(self.output_dir, output_filename)
            
            cmd = [
                "ffmpeg", "-y",
                "-i", video_file,
                "-i", audio_file,
                "-filter_complex", 
                f"[0:a]volume={video_volume}[va];[1:a]volume={audio_volume}[bg];[va][bg]amix=inputs=2:duration=first[a]",
                "-map", "0:v",
                "-map", "[a]",
                "-c:v", "copy",
                "-c:a", "aac",
                "-shortest",
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
                raise ToolError(f"Audio mixing failed: {error_msg}", self.metadata.name)
            
            return {
                "output_file": output_path,
                "file_size": os.path.getsize(output_path),
                "audio_volume": audio_volume,
                "video_volume": video_volume
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
            
            output_path = os.path.join(self.output_dir, output_filename)
            
            # 创建图片输入列表
            inputs = []
            filter_complex = []
            
            for i, img in enumerate(images):
                inputs.extend(["-loop", "1", "-t", str(duration_per_image), "-i", img])
                
                # 添加转场效果
                if i > 0 and transition_effect != "none":
                    if transition_effect == "fade":
                        filter_complex.append(f"[{i-1}:v][{i}:v]xfade=transition=fade:duration=0.5:offset={duration_per_image-0.5}[v{i}]")
            
            cmd = ["ffmpeg", "-y"] + inputs
            
            if filter_complex:
                cmd.extend(["-filter_complex", ";".join(filter_complex)])
                cmd.extend(["-map", f"[v{len(images)-1}]"])
            else:
                # 简单拼接
                cmd.extend(["-filter_complex", f"concat=n={len(images)}:v=1:a=0[v]", "-map", "[v]"])
            
            # 添加音频
            if audio_file and os.path.exists(audio_file):
                cmd.extend(["-i", audio_file, "-c:a", "aac", "-shortest"])
            
            cmd.extend([
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-r", str(self.default_fps),
                output_path
            ])
            
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
                raise ToolError(f"Slideshow creation failed: {error_msg}", self.metadata.name)
            
            return {
                "output_file": output_path,
                "file_size": os.path.getsize(output_path),
                "image_count": len(images),
                "duration_per_image": duration_per_image,
                "total_duration": len(images) * duration_per_image,
                "has_audio": audio_file is not None
            }
            
        except Exception as e:
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