"""
Video Composer Tool - 视频合成工具
统一的视频合成、编辑和处理工具
"""

import os
import json
import asyncio
from typing import Dict, Any, List, Optional, Union
from pathlib import Path

from ..base_tool import AsyncTool, ToolMetadata, ToolType, ToolInput, ToolError, ToolValidationError
from ..video_processing.ffmpeg_tool import FFmpegTool
from ..storage.file_storage_tool import FileStorageTool


class VideoComposerTool(AsyncTool):
    """
    视频合成工具
    
    提供高级视频合成功能：
    - 场景视频合成
    - 智能转场效果
    - 音频同步
    - 字幕添加
    - 质量优化
    - 自动化编辑
    """
    
    @classmethod
    def get_metadata(cls) -> ToolMetadata:
        return ToolMetadata(
            name="video_composer_tool",
            version="1.0.0",
            description="统一的视频合成工具，支持场景合成、转场效果、音频同步等",
            tool_type=ToolType.MEDIA_PROCESSING,
            author="system",
            tags=["video", "composition", "editing", "automation", "scenes"],
            capabilities=[
                "scene_composition",
                "smart_transitions",
                "audio_synchronization", 
                "subtitle_integration",
                "quality_optimization",
                "batch_processing",
                "template_based_editing"
            ],
            limitations=[
                "requires_ffmpeg",
                "processing_intensive",
                "storage_dependent",
                "quality_vs_speed_tradeoff"
            ]
        )
    
    def _initialize(self):
        """初始化视频合成工具"""
        # 初始化依赖工具
        ffmpeg_config = self.config.get("ffmpeg", {})
        storage_config = self.config.get("storage", {})
        
        self.ffmpeg_tool = FFmpegTool(ffmpeg_config)
        self.storage_tool = FileStorageTool(storage_config)
        
        # 合成配置
        self.output_dir = self.config.get("output_dir", "/tmp/video_composition")
        self.temp_dir = self.config.get("temp_dir", "/tmp/composition_temp")
        self.quality_preset = self.config.get("quality_preset", "medium")
        self.default_transition_duration = self.config.get("default_transition_duration", 1.0)
        
        # 创建目录
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.temp_dir, exist_ok=True)
        
        # 转场效果配置
        self.transition_effects = {
            "fade": {"type": "xfade", "transition": "fade"},
            "dissolve": {"type": "xfade", "transition": "dissolve"},
            "wipeleft": {"type": "xfade", "transition": "wipeleft"},
            "slideright": {"type": "xfade", "transition": "slideright"},
            "smoothleft": {"type": "xfade", "transition": "smoothleft"},
            "circleopen": {"type": "xfade", "transition": "circleopen"},
            "rectcrop": {"type": "xfade", "transition": "rectcrop"},
            "distance": {"type": "xfade", "transition": "distance"}
        }
        
        self.logger.info(f"Initialized video composer tool with quality preset: {self.quality_preset}")
    
    def get_available_actions(self) -> List[str]:
        return [
            "compose_story_video",
            "compose_scene_sequence", 
            "add_smart_transitions",
            "synchronize_audio",
            "add_subtitles_batch",
            "optimize_for_platform",
            "create_video_template",
            "apply_video_template",
            "batch_process_scenes",
            "generate_preview",
            "analyze_composition_quality"
        ]
    
    def get_action_schema(self, action: str) -> Dict[str, Any]:
        schemas = {
            "compose_story_video": {
                "type": "object",
                "properties": {
                    "scenes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "video_file": {"type": "string", "description": "场景视频文件"},
                                "duration": {"type": "number", "description": "场景时长"},
                                "audio_file": {"type": "string", "description": "场景音频"},
                                "subtitle_text": {"type": "string", "description": "字幕文本"},
                                "transition_in": {"type": "string", "description": "入场转场效果"},
                                "transition_out": {"type": "string", "description": "出场转场效果"}
                            },
                            "required": ["video_file"]
                        }
                    },
                    "background_music": {"type": "string", "description": "背景音乐文件"},
                    "output_filename": {"type": "string", "description": "输出文件名"},
                    "style": {"type": "string", "enum": ["cinematic", "documentary", "social_media", "presentation"]},
                    "target_duration": {"type": "number", "description": "目标总时长"},
                    "resolution": {"type": "string", "description": "输出分辨率"}
                },
                "required": ["scenes", "output_filename"]
            },
            "compose_scene_sequence": {
                "type": "object",
                "properties": {
                    "scene_clips": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "场景片段文件列表"
                    },
                    "transition_style": {"type": "string", "enum": list(self.transition_effects.keys())},
                    "transition_duration": {"type": "number", "description": "转场时长"},
                    "audio_track": {"type": "string", "description": "音频轨道"},
                    "output_filename": {"type": "string"}
                },
                "required": ["scene_clips", "output_filename"]
            },
            "synchronize_audio": {
                "type": "object",
                "properties": {
                    "video_file": {"type": "string", "description": "视频文件"},
                    "audio_tracks": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "file": {"type": "string"},
                                "volume": {"type": "number"},
                                "start_time": {"type": "number"},
                                "fade_in": {"type": "number"},
                                "fade_out": {"type": "number"}
                            }
                        }
                    },
                    "output_filename": {"type": "string"}
                },
                "required": ["video_file", "audio_tracks", "output_filename"]
            },
            "optimize_for_platform": {
                "type": "object",
                "properties": {
                    "input_video": {"type": "string", "description": "输入视频文件"},
                    "platform": {"type": "string", "enum": ["youtube", "tiktok", "instagram", "twitter", "linkedin"]},
                    "output_filename": {"type": "string"}
                },
                "required": ["input_video", "platform", "output_filename"]
            }
        }
        
        return schemas.get(action, {})
    
    async def _execute_impl(self, tool_input: ToolInput) -> Any:
        """执行视频合成操作"""
        action = tool_input.action
        params = tool_input.parameters
        
        if action == "compose_story_video":
            return await self._compose_story_video(params)
        elif action == "compose_scene_sequence":
            return await self._compose_scene_sequence(params)
        elif action == "add_smart_transitions":
            return await self._add_smart_transitions(params)
        elif action == "synchronize_audio":
            return await self._synchronize_audio(params)
        elif action == "add_subtitles_batch":
            return await self._add_subtitles_batch(params)
        elif action == "optimize_for_platform":
            return await self._optimize_for_platform(params)
        elif action == "create_video_template":
            return await self._create_video_template(params)
        elif action == "apply_video_template":
            return await self._apply_video_template(params)
        elif action == "batch_process_scenes":
            return await self._batch_process_scenes(params)
        elif action == "generate_preview":
            return await self._generate_preview(params)
        elif action == "analyze_composition_quality":
            return await self._analyze_composition_quality(params)
        else:
            raise ToolValidationError(f"Unknown action: {action}", self.metadata.name)
    
    async def _compose_story_video(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """合成故事视频"""
        try:
            scenes = params["scenes"]
            output_filename = params["output_filename"]
            background_music = params.get("background_music")
            style = params.get("style", "cinematic")
            target_duration = params.get("target_duration")
            resolution = params.get("resolution", "1920x1080")
            
            self.logger.info(f"Composing story video with {len(scenes)} scenes")
            
            # 处理每个场景
            processed_scenes = []
            total_duration = 0
            
            for i, scene in enumerate(scenes):
                self.logger.info(f"Processing scene {i+1}/{len(scenes)}")
                
                scene_result = await self._process_single_scene(scene, i, style)
                processed_scenes.append(scene_result)
                total_duration += scene_result["duration"]
            
            # 应用时长调整（如果指定了目标时长）
            if target_duration and target_duration != total_duration:
                processed_scenes = await self._adjust_scene_durations(
                    processed_scenes, target_duration
                )
                total_duration = target_duration
            
            # 合成最终视频
            composition_params = {
                "video_clips": [scene["processed_file"] for scene in processed_scenes],
                "output_filename": output_filename,
                "resolution": resolution
            }
            
            if background_music:
                composition_params["audio_file"] = background_music
            
            final_result = await self.ffmpeg_tool.execute(
                ToolInput(action="compose_video", parameters=composition_params)
            )
            
            # 上传到存储
            upload_result = await self.storage_tool.execute(
                ToolInput(
                    action="upload_file",
                    parameters={
                        "file_path": final_result["output_file"],
                        "metadata": {
                            "type": "story_video",
                            "style": style,
                            "scene_count": len(scenes),
                            "total_duration": total_duration,
                            "resolution": resolution
                        }
                    }
                )
            )
            
            # 清理临时文件
            await self._cleanup_temp_files([scene["processed_file"] for scene in processed_scenes])
            
            return {
                "output_file": final_result["output_file"],
                "storage_url": upload_result["url"],
                "file_key": upload_result["file_key"],
                "scenes_processed": len(scenes),
                "total_duration": total_duration,
                "file_size": final_result["file_size"],
                "style": style,
                "resolution": resolution
            }
            
        except Exception as e:
            raise ToolError(f"Story video composition failed: {str(e)}", self.metadata.name)
    
    async def _process_single_scene(self, scene: Dict[str, Any], scene_index: int, style: str) -> Dict[str, Any]:
        """处理单个场景"""
        try:
            video_file = scene["video_file"]
            duration = scene.get("duration")
            audio_file = scene.get("audio_file")
            subtitle_text = scene.get("subtitle_text")
            
            # 获取视频信息
            video_info = await self.ffmpeg_tool.execute(
                ToolInput(action="get_video_info", parameters={"file_path": video_file})
            )
            
            original_duration = video_info["duration"]
            processed_file = os.path.join(self.temp_dir, f"scene_{scene_index}_processed.mp4")
            
            # 应用样式特效
            style_effects = self._get_style_effects(style)
            
            # 构建处理命令
            processing_steps = []
            
            # 1. 时长调整
            if duration and duration != original_duration:
                processing_steps.append({
                    "action": "trim_video",
                    "params": {
                        "input_file": video_file,
                        "output_filename": f"scene_{scene_index}_trimmed.mp4",
                        "duration": duration
                    }
                })
                current_file = f"scene_{scene_index}_trimmed.mp4"
            else:
                current_file = video_file
                duration = original_duration
            
            # 2. 添加音频（如果有）
            if audio_file:
                processing_steps.append({
                    "action": "add_audio",
                    "params": {
                        "video_file": current_file,
                        "audio_file": audio_file,
                        "output_filename": f"scene_{scene_index}_with_audio.mp4"
                    }
                })
                current_file = f"scene_{scene_index}_with_audio.mp4"
            
            # 3. 添加字幕（如果有）
            if subtitle_text:
                processing_steps.append({
                    "action": "add_subtitles",
                    "params": {
                        "video_file": current_file,
                        "subtitle_text": subtitle_text,
                        "output_filename": f"scene_{scene_index}_with_subs.mp4"
                    }
                })
                current_file = f"scene_{scene_index}_with_subs.mp4"
            
            # 执行处理步骤
            for step in processing_steps:
                step_result = await self.ffmpeg_tool.execute(
                    ToolInput(action=step["action"], parameters=step["params"])
                )
                current_file = step_result["output_file"]
            
            # 如果没有处理步骤，直接复制原文件
            if not processing_steps:
                import shutil
                shutil.copy2(video_file, processed_file)
                current_file = processed_file
            else:
                # 移动最终文件到指定位置
                if current_file != processed_file:
                    import shutil
                    shutil.move(current_file, processed_file)
            
            return {
                "scene_index": scene_index,
                "processed_file": processed_file,
                "duration": duration,
                "original_file": video_file,
                "has_audio": audio_file is not None,
                "has_subtitles": subtitle_text is not None
            }
            
        except Exception as e:
            raise ToolError(f"Scene {scene_index} processing failed: {str(e)}", self.metadata.name)
    
    async def _compose_scene_sequence(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """合成场景序列"""
        try:
            scene_clips = params["scene_clips"]
            output_filename = params["output_filename"]
            transition_style = params.get("transition_style", "fade")
            transition_duration = params.get("transition_duration", self.default_transition_duration)
            audio_track = params.get("audio_track")
            
            # 验证输入文件
            for clip in scene_clips:
                if not os.path.exists(clip):
                    raise ToolError(f"Scene clip not found: {clip}", self.metadata.name)
            
            # 应用转场效果
            if len(scene_clips) > 1 and transition_style != "none":
                transition_result = await self._apply_transitions(
                    scene_clips, transition_style, transition_duration
                )
                composed_video = transition_result["output_file"]
            else:
                # 简单拼接
                compose_params = {
                    "video_clips": scene_clips,
                    "output_filename": f"temp_{output_filename}"
                }
                
                compose_result = await self.ffmpeg_tool.execute(
                    ToolInput(action="compose_video", parameters=compose_params)
                )
                composed_video = compose_result["output_file"]
            
            # 添加音频轨道
            if audio_track:
                final_params = {
                    "video_file": composed_video,
                    "audio_file": audio_track,
                    "output_filename": output_filename
                }
                
                final_result = await self.ffmpeg_tool.execute(
                    ToolInput(action="add_audio", parameters=final_params)
                )
                
                output_file = final_result["output_file"]
            else:
                output_file = composed_video
            
            # 获取最终视频信息
            video_info = await self.ffmpeg_tool.execute(
                ToolInput(action="get_video_info", parameters={"file_path": output_file})
            )
            
            return {
                "output_file": output_file,
                "scenes_count": len(scene_clips),
                "transition_style": transition_style,
                "transition_duration": transition_duration,
                "total_duration": video_info["duration"],
                "file_size": video_info["file_size"],
                "has_audio": audio_track is not None
            }
            
        except Exception as e:
            raise ToolError(f"Scene sequence composition failed: {str(e)}", self.metadata.name)
    
    async def _apply_transitions(self, clips: List[str], transition_style: str, duration: float) -> Dict[str, Any]:
        """应用转场效果"""
        try:
            if transition_style not in self.transition_effects:
                raise ToolError(f"Unsupported transition style: {transition_style}", self.metadata.name)
            
            transition_config = self.transition_effects[transition_style]
            
            # 使用FFmpeg的xfade滤镜实现转场
            output_file = os.path.join(self.temp_dir, "transitioned_video.mp4")
            
            # 构建复杂的滤镜链
            filter_complex_parts = []
            input_labels = []
            
            for i, clip in enumerate(clips):
                input_labels.append(f"[{i}:v]")
            
            # 构建转场滤镜链
            current_label = input_labels[0]
            for i in range(1, len(clips)):
                next_label = input_labels[i]
                output_label = f"[v{i}]" if i < len(clips) - 1 else "[vout]"
                
                filter_part = f"{current_label}{next_label}xfade=transition={transition_config['transition']}:duration={duration}:offset=0{output_label}"
                filter_complex_parts.append(filter_part)
                current_label = output_label
            
            # 这里需要使用更复杂的FFmpeg命令，暂时使用简单拼接
            # 实际实现需要计算每段视频的偏移时间
            compose_params = {
                "video_clips": clips,
                "output_filename": "transitioned_video.mp4"
            }
            
            result = await self.ffmpeg_tool.execute(
                ToolInput(action="compose_video", parameters=compose_params)
            )
            
            return result
            
        except Exception as e:
            raise ToolError(f"Transition application failed: {str(e)}", self.metadata.name)
    
    async def _optimize_for_platform(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """针对平台优化视频"""
        try:
            input_video = params["input_video"]
            platform = params["platform"]
            output_filename = params["output_filename"]
            
            if not os.path.exists(input_video):
                raise ToolError(f"Input video not found: {input_video}", self.metadata.name)
            
            # 平台特定设置
            platform_settings = {
                "youtube": {
                    "resolution": "1920x1080",
                    "fps": 30,
                    "bitrate": "8M",
                    "format": "mp4",
                    "aspect_ratio": "16:9"
                },
                "tiktok": {
                    "resolution": "1080x1920",
                    "fps": 30,
                    "bitrate": "6M",
                    "format": "mp4",
                    "aspect_ratio": "9:16"
                },
                "instagram": {
                    "resolution": "1080x1080",
                    "fps": 30,
                    "bitrate": "5M",
                    "format": "mp4",
                    "aspect_ratio": "1:1"
                },
                "twitter": {
                    "resolution": "1280x720",
                    "fps": 30,
                    "bitrate": "4M",
                    "format": "mp4",
                    "aspect_ratio": "16:9"
                },
                "linkedin": {
                    "resolution": "1920x1080",
                    "fps": 25,
                    "bitrate": "6M",
                    "format": "mp4",
                    "aspect_ratio": "16:9"
                }
            }
            
            if platform not in platform_settings:
                raise ToolError(f"Unsupported platform: {platform}", self.metadata.name)
            
            settings = platform_settings[platform]
            
            # 应用平台设置
            convert_params = {
                "input_file": input_video,
                "output_format": settings["format"],
                "output_filename": output_filename,
                "quality": "high"
            }
            
            result = await self.ffmpeg_tool.execute(
                ToolInput(action="convert_format", parameters=convert_params)
            )
            
            result.update({
                "platform": platform,
                "optimized_settings": settings
            })
            
            return result
            
        except Exception as e:
            raise ToolError(f"Platform optimization failed: {str(e)}", self.metadata.name)
    
    def _get_style_effects(self, style: str) -> Dict[str, Any]:
        """获取样式特效配置"""
        style_configs = {
            "cinematic": {
                "color_grading": "cinema",
                "aspect_ratio": "21:9",
                "fade_in": True,
                "fade_out": True
            },
            "documentary": {
                "color_grading": "natural",
                "aspect_ratio": "16:9", 
                "stabilization": True
            },
            "social_media": {
                "color_grading": "vibrant",
                "aspect_ratio": "9:16",
                "quick_cuts": True
            },
            "presentation": {
                "color_grading": "professional",
                "aspect_ratio": "16:9",
                "clean_transitions": True
            }
        }
        
        return style_configs.get(style, {})
    
    async def _cleanup_temp_files(self, temp_files: List[str]):
        """清理临时文件"""
        for temp_file in temp_files:
            try:
                if os.path.exists(temp_file):
                    os.unlink(temp_file)
            except Exception as e:
                self.logger.warning(f"Failed to cleanup temp file {temp_file}: {e}")
    
    def _validate_action_parameters(self, action: str, parameters: Dict[str, Any]):
        """验证操作参数"""
        if action == "compose_story_video":
            if not parameters.get("scenes"):
                raise ToolValidationError("scenes are required for compose_story_video")
            if not parameters.get("output_filename"):
                raise ToolValidationError("output_filename is required for compose_story_video")
        
        elif action == "compose_scene_sequence":
            if not parameters.get("scene_clips"):
                raise ToolValidationError("scene_clips are required for compose_scene_sequence")
            if not parameters.get("output_filename"):
                raise ToolValidationError("output_filename is required for compose_scene_sequence")
        
        elif action == "optimize_for_platform":
            if not parameters.get("input_video"):
                raise ToolValidationError("input_video is required for optimize_for_platform")
            if not parameters.get("platform"):
                raise ToolValidationError("platform is required for optimize_for_platform")
            if not parameters.get("output_filename"):
                raise ToolValidationError("output_filename is required for optimize_for_platform")