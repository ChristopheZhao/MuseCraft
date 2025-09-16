"""
Audio Processing Tool - 音频后处理工具
处理音频时长调整、循环、淡入淡出等
"""

import os
import subprocess
import tempfile
import asyncio
from typing import Dict, Any, List, Optional
from ..base_tool import AsyncTool, ToolMetadata, ToolType, ToolInput, ToolError


class AudioProcessorTool(AsyncTool):
    """
    音频处理工具 - 专门处理背景音乐的时长调整和循环
    
    功能:
    - 音频时长调整（裁剪或循环扩展）
    - 淡入淡出效果
    - 音量调整
    - 音频循环
    """
    
    @classmethod
    def get_metadata(cls) -> ToolMetadata:
        return ToolMetadata(
            name="audio_processor",
            version="1.0.0",
            description="音频后处理工具，用于时长调整、循环、淡入淡出等",
            tool_type=ToolType.MEDIA_PROCESSING,
            author="system",
            tags=["audio", "ffmpeg", "processing", "background-music"],
            capabilities=[
                "duration_adjustment",
                "audio_looping", 
                "fade_effects",
                "volume_control",
                "audio_trimming"
            ],
            # 依赖于 ffmpeg_tool（工具系统内依赖），不要声明系统二进制名
            dependencies=["ffmpeg_tool"],
            limitations=[
                "requires_ffmpeg",
                "input_file_required",
                "processing_time_varies"
            ]
        )
    
    def __init__(self, metadata: ToolMetadata = None, config: Dict[str, Any] = None):
        if metadata is None:
            metadata = self.get_metadata()
        super().__init__(metadata, config)
    
    def _initialize(self):
        """初始化音频处理工具"""
        # 检查FFmpeg是否可用
        try:
            subprocess.run(["ffmpeg", "-version"], 
                         capture_output=True, check=True)
            self._functional = True
            self.logger.info("FFmpeg available for audio processing")
        except (subprocess.CalledProcessError, FileNotFoundError):
            self._functional = False
            self.logger.warning("FFmpeg not found - audio processing will be limited")
    
    def get_available_actions(self) -> List[str]:
        return [
            "adjust_duration",
            "create_loop",
            "add_fade_effects",
            "adjust_volume",
            "trim_audio",
            "adjust_duration_smart",
            "apply_edit_plan"
        ]
    
    def get_action_schema(self, action: str) -> Dict[str, Any]:
        schemas = {
            "adjust_duration": {
                "type": "object",
                "properties": {
                    "input_path": {"type": "string", "description": "输入音频文件路径"},
                    "target_duration": {"type": "number", "description": "目标时长（秒）"},
                    "method": {
                        "type": "string", 
                        "enum": ["trim", "loop", "stretch"],
                        "default": "loop",
                        "description": "调整方法：trim(裁剪), loop(循环), stretch(拉伸)"
                    },
                    "output_path": {"type": "string", "description": "输出文件路径（可选）"},
                    "fade_in": {"type": "number", "default": 1.0, "description": "淡入时长（秒）"},
                    "fade_out": {"type": "number", "default": 1.0, "description": "淡出时长（秒）"}
                },
                "required": ["input_path", "target_duration"]
            },
            "create_loop": {
                "type": "object",
                "properties": {
                    "input_path": {"type": "string", "description": "输入音频文件路径"},
                    "loop_count": {"type": "integer", "description": "循环次数"},
                    "crossfade": {"type": "number", "default": 0.5, "description": "交叉淡入淡出时长（秒）"},
                    "output_path": {"type": "string", "description": "输出文件路径（可选）"}
                },
                "required": ["input_path", "loop_count"]
            },
            "add_fade_effects": {
                "type": "object", 
                "properties": {
                    "input_path": {"type": "string", "description": "输入音频文件路径"},
                    "fade_in": {"type": "number", "default": 1.0, "description": "淡入时长（秒）"},
                    "fade_out": {"type": "number", "default": 1.0, "description": "淡出时长（秒）"},
                    "output_path": {"type": "string", "description": "输出文件路径（可选）"}
                },
                "required": ["input_path"]
            },
            "adjust_duration_smart": {
                "type": "object",
                "properties": {
                    "input_path": {"type": "string", "description": "输入音频文件路径"},
                    "target_duration": {"type": "number"},
                    "fade_in": {"type": "number", "default": 0.5},
                    "fade_out": {"type": "number", "default": 1.0},
                    "crossfade": {"type": "number", "default": 0.5},
                    "output_path": {"type": "string"}
                },
                "required": ["input_path", "target_duration"]
            },
            "apply_edit_plan": {
                "type": "object",
                "properties": {
                    "input_path": {"type": "string"},
                    "plan": {"type": "object"},
                    "output_path": {"type": "string"}
                },
                "required": ["input_path", "plan"]
            }
        }
        return schemas.get(action, {})
    
    async def _execute_impl(self, tool_input: ToolInput) -> Any:
        """执行音频处理操作"""
        if not self._functional:
            raise ToolError("Audio processor not functional - FFmpeg required", self.metadata.name)
        
        action = tool_input.action
        params = tool_input.parameters
        
        if action == "adjust_duration":
            return await self._adjust_duration(params)
        elif action == "create_loop":
            return await self._create_loop(params)
        elif action == "add_fade_effects":
            return await self._add_fade_effects(params)
        elif action == "adjust_duration_smart":
            return await self._adjust_duration_smart(params)
        elif action == "apply_edit_plan":
            return await self._apply_edit_plan(params)
        else:
            raise ToolError(f"Unknown action: {action}", self.metadata.name)
    
    async def _adjust_duration(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """调整音频时长以匹配视频"""
        input_path = params["input_path"]
        target_duration = float(params["target_duration"])
        method = params.get("method", "loop")
        output_path = params.get("output_path")
        fade_in = params.get("fade_in", 1.0)
        fade_out = params.get("fade_out", 1.0)
        
        if not os.path.exists(input_path):
            raise ToolError(f"Input audio file not found: {input_path}", self.metadata.name)
        
        # 获取原始音频时长
        original_duration = await self._get_audio_duration(input_path)
        
        self.logger.info(f"🎵 Adjusting audio duration: {original_duration:.1f}s → {target_duration:.1f}s")
        
        # 生成输出路径
        if not output_path:
            base_name = os.path.splitext(os.path.basename(input_path))[0]
            output_dir = os.path.dirname(input_path)
            output_path = os.path.join(output_dir, f"{base_name}_adjusted_{int(target_duration)}s.mp3")
        
        try:
            if method == "trim" and original_duration > target_duration:
                # 裁剪音频
                result = await self._trim_audio(input_path, target_duration, output_path, fade_out)
            
            elif method == "loop" and original_duration < target_duration:
                # 循环音频到目标时长
                result = await self._loop_to_duration(input_path, target_duration, output_path, fade_in, fade_out)
            
            elif method == "stretch":
                # 拉伸/压缩音频（改变播放速度）
                result = await self._stretch_audio(input_path, target_duration, output_path)
            
            else:
                # 时长已经匹配或接近，只添加淡入淡出
                result = await self._add_fade_effects({
                    "input_path": input_path,
                    "fade_in": fade_in,
                    "fade_out": fade_out,
                    "output_path": output_path
                })
            
            # 验证输出文件
            if os.path.exists(output_path):
                final_duration = await self._get_audio_duration(output_path)
                file_size = os.path.getsize(output_path)
                
                self.logger.info(f"✅ Audio duration adjusted successfully: {final_duration:.1f}s")
                
                return {
                    "success": True,
                    "output_path": output_path,
                    "original_duration": original_duration,
                    "final_duration": final_duration,
                    "target_duration": target_duration,
                    "method_used": method,
                    "file_size_kb": file_size // 1024,
                    "duration_match": abs(final_duration - target_duration) < 2.0  # 2秒误差内
                }
            else:
                raise ToolError("Output file was not created", self.metadata.name)
                
        except subprocess.CalledProcessError as e:
            self.logger.error(f"FFmpeg processing failed: {e}")
            raise ToolError(f"Audio processing failed: {str(e)}", self.metadata.name)
    
    async def _loop_to_duration(
        self, 
        input_path: str, 
        target_duration: float, 
        output_path: str,
        fade_in: float = 1.0,
        fade_out: float = 1.0
    ) -> Dict[str, Any]:
        """循环音频到指定时长"""
        
        # 创建临时文件用于循环
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_file:
            temp_loop_path = temp_file.name
        
        try:
            # 使用FFmpeg循环音频
            # 计算需要循环多少次
            original_duration = await self._get_audio_duration(input_path)
            loop_count = int(target_duration / original_duration) + 1
            
            # 创建循环音频
            loop_cmd = [
                "ffmpeg", "-y",
                "-stream_loop", str(loop_count),
                "-i", input_path,
                "-t", str(target_duration),
                "-c", "copy",
                temp_loop_path
            ]
            
            self.logger.info(f"🔄 Creating {loop_count} loops for {target_duration}s duration")
            await asyncio.create_subprocess_exec(*loop_cmd, 
                                               stdout=subprocess.DEVNULL,
                                               stderr=subprocess.DEVNULL)
            
            # 添加淡入淡出效果
            fade_cmd = [
                "ffmpeg", "-y",
                "-i", temp_loop_path,
                "-af", f"afade=t=in:ss=0:d={fade_in},afade=t=out:st={target_duration-fade_out}:d={fade_out}",
                "-c:a", "libmp3lame",
                output_path
            ]
            
            process = await asyncio.create_subprocess_exec(*fade_cmd,
                                                         stdout=subprocess.PIPE,
                                                         stderr=subprocess.PIPE)
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown FFmpeg error"
                raise ToolError(f"FFmpeg fade processing failed: {error_msg}", self.metadata.name)
            
            return {"success": True, "method": "loop_with_fade"}
            
        finally:
            # 清理临时文件
            if os.path.exists(temp_loop_path):
                os.unlink(temp_loop_path)
    
    async def _trim_audio(
        self, 
        input_path: str, 
        duration: float, 
        output_path: str,
        fade_out: float = 1.0
    ) -> Dict[str, Any]:
        """裁剪音频到指定时长"""
        
        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-t", str(duration),
            "-af", f"afade=t=out:st={duration-fade_out}:d={fade_out}",
            "-c:a", "libmp3lame",
            output_path
        ]
        
        process = await asyncio.create_subprocess_exec(*cmd,
                                                     stdout=subprocess.PIPE,
                                                     stderr=subprocess.PIPE)
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            error_msg = stderr.decode() if stderr else "Unknown FFmpeg error"
            raise ToolError(f"FFmpeg trim processing failed: {error_msg}", self.metadata.name)
        
        return {"success": True, "method": "trim_with_fade"}

    async def _adjust_duration_smart(self, params: Dict[str, Any]) -> Dict[str, Any]:
        input_path = params["input_path"]
        target = float(params["target_duration"])
        fade_in = float(params.get("fade_in", 0.5))
        fade_out = float(params.get("fade_out", 1.0))
        crossfade = float(params.get("crossfade", 0.5))
        out_path = params.get("output_path")
        if not out_path:
            base = os.path.splitext(os.path.basename(input_path))[0]
            out_path = os.path.join(os.path.dirname(input_path), f"{base}_smart_{int(target)}.mp3")
        orig = await self._get_audio_duration(input_path)
        if orig <= 0.0:
            raise ToolError("unable to read duration", self.metadata.name)
        if orig > target + 0.1:
            # trim with fade out at target
            return await self._trim_audio(input_path, target, out_path, fade_out)
        elif orig < target - 0.1:
            # loop to target with crossfade
            return await self._loop_to_duration(input_path, target, out_path, fade_in, fade_out)
        else:
            # already close, just apply subtle fades
            return await self._add_fade_effects({"input_path": input_path, "fade_in": fade_in, "fade_out": fade_out, "output_path": out_path})

    async def _apply_edit_plan(self, params: Dict[str, Any]) -> Dict[str, Any]:
        input_path = params["input_path"]
        plan = params.get("plan") or {}
        out_path = params.get("output_path")
        method = (plan.get("method") or "trim").lower()
        fade_out = float(plan.get("fade_out", 1.0))
        if not out_path:
            base = os.path.splitext(os.path.basename(input_path))[0]
            out_path = os.path.join(os.path.dirname(input_path), f"{base}_edit.mp3")
        if method == "trim":
            cut_at = float(plan.get("cut_at") or 0)
            if cut_at <= 0:
                raise ToolError("invalid cut_at in plan", self.metadata.name)
            return await self._trim_audio(input_path, cut_at, out_path, fade_out)
        # fallback to smart adjust
        td = float(plan.get("target_duration") or 0)
        if td <= 0:
            td = await self._get_audio_duration(input_path)
        return await self._adjust_duration_smart({
            "input_path": input_path,
            "target_duration": td,
            "output_path": out_path
        })
    
    async def _add_fade_effects(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """添加淡入淡出效果"""
        input_path = params["input_path"]
        fade_in = params.get("fade_in", 1.0)
        fade_out = params.get("fade_out", 1.0) 
        output_path = params.get("output_path")
        
        if not output_path:
            base_name = os.path.splitext(os.path.basename(input_path))[0]
            output_dir = os.path.dirname(input_path)
            output_path = os.path.join(output_dir, f"{base_name}_faded.mp3")
        
        # 获取音频时长以计算淡出开始时间
        duration = await self._get_audio_duration(input_path)
        fade_out_start = max(0, duration - fade_out)
        
        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-af", f"afade=t=in:ss=0:d={fade_in},afade=t=out:st={fade_out_start}:d={fade_out}",
            "-c:a", "libmp3lame",
            output_path
        ]
        
        process = await asyncio.create_subprocess_exec(*cmd,
                                                     stdout=subprocess.PIPE, 
                                                     stderr=subprocess.PIPE)
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            error_msg = stderr.decode() if stderr else "Unknown FFmpeg error"
            raise ToolError(f"FFmpeg fade processing failed: {error_msg}", self.metadata.name)
        
        return {
            "success": True,
            "output_path": output_path,
            "fade_in": fade_in,
            "fade_out": fade_out
        }
    
    async def _get_audio_duration(self, audio_path: str) -> float:
        """获取音频文件时长"""
        cmd = [
            "ffprobe", "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "csv=p=0",
            audio_path
        ]
        
        try:
            process = await asyncio.create_subprocess_exec(*cmd,
                                                         stdout=subprocess.PIPE,
                                                         stderr=subprocess.PIPE)
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                duration_str = stdout.decode().strip()
                return float(duration_str)
            else:
                self.logger.warning(f"Could not get audio duration for {audio_path}")
                return 0.0
                
        except Exception as e:
            self.logger.warning(f"Error getting audio duration: {e}")
            return 0.0
    
    async def _stretch_audio(
        self, 
        input_path: str, 
        target_duration: float, 
        output_path: str
    ) -> Dict[str, Any]:
        """拉伸或压缩音频时长（改变播放速度）"""
        
        original_duration = await self._get_audio_duration(input_path)
        speed_ratio = original_duration / target_duration
        
        # FFmpeg的atempo滤镜有限制，需要分步处理极端比率
        if speed_ratio > 2.0 or speed_ratio < 0.5:
            self.logger.warning(f"Speed ratio {speed_ratio:.2f} is extreme, may affect quality")
        
        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-af", f"atempo={speed_ratio:.3f}",
            "-c:a", "libmp3lame",
            output_path
        ]
        
        process = await asyncio.create_subprocess_exec(*cmd,
                                                     stdout=subprocess.PIPE,
                                                     stderr=subprocess.PIPE)
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            error_msg = stderr.decode() if stderr else "Unknown FFmpeg error"
            raise ToolError(f"FFmpeg stretch processing failed: {error_msg}", self.metadata.name)
        
        return {"success": True, "method": "stretch", "speed_ratio": speed_ratio}
