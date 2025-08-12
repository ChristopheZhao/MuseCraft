"""
Video Composer Agent - Combines individual video clips into final video
"""
import asyncio
import os
import subprocess
from typing import Dict, Any, List
from sqlalchemy.orm import Session

from .base import BaseAgent, AgentError
from ..models import Task, AgentExecution, AgentType, Scene, Resource, ResourceType
from ..services.file_storage import FileStorageService
from ..core.config import settings


class VideoComposerAgent(BaseAgent):
    """
    Video Composer Agent combines individual scene videos into a final cohesive video
    with transitions, audio, and effects
    """
    
    def __init__(self):
        super().__init__(
            agent_type=AgentType.VIDEO_COMPOSER,
            agent_name="video_composer",
            timeout_seconds=600,  # 10 minutes for video composition
            max_retries=2
        )
        self.file_storage = FileStorageService()
    
    async def _execute_impl(
        self, 
        task: Task, 
        input_data: Dict[str, Any], 
        execution: AgentExecution,
        db: Session
    ) -> Dict[str, Any]:
        """Compose final video from individual scene videos"""
        
        # Validate input
        self._validate_input(input_data, ["workflow_state_id"])
        
        workflow_state_id = input_data["workflow_state_id"]
        
        # 通过 workflow_manager 获取 WorkflowState
        from ..core.workflow_state import workflow_manager
        workflow_state = workflow_manager.get_workflow(workflow_state_id)
        if not workflow_state:
            raise AgentError(f"WorkflowState {workflow_state_id} not found")
        
        await self._update_progress(execution, 10, "Loading video clips", db)
        
        # Get scenes from WorkflowState
        scenes_data = workflow_state.scenes
        if not scenes_data:
            raise AgentError("No scenes found in workflow state")
        
        # Filter scenes with successful video generation  
        successful_scenes = [scene for scene in scenes_data if scene.video_path or scene.video_url]
        
        # 降级处理：如果没有成功的视频，尝试创建图像轮播
        if not successful_scenes:
            self.logger.warning("No successful video clips found, creating image slideshow as fallback")
            return await self._create_image_slideshow(scenes_data, workflow_state_id, execution, db)
        
        await self._update_progress(execution, 20, "Preparing composition timeline", db)
        
        # Create composition timeline
        composition_timeline = await self._create_composition_timeline_from_data(
            successful_scenes
        )
        
        await self._update_progress(execution, 60, "Composing final video", db)
        
        # Compose the final video (video-only, no audio yet)
        final_video_path = await self._compose_final_video_from_data(
            composition_timeline, workflow_state.concept_plan, execution
        )
        
        await self._update_progress(execution, 85, "Saving final video", db)
        
        # Update workflow state with final video information
        workflow_state.final_video_path = final_video_path
        workflow_state.final_video_url = self.file_storage.get_public_url(final_video_path) if final_video_path else ""
        
        await self._update_progress(execution, 95, "Generating video metadata", db)
        
        # Generate video metadata and statistics
        video_metadata = await self._generate_video_metadata_from_data(
            final_video_path, composition_timeline, successful_scenes
        )
        
        # Update workflow state with metadata
        workflow_state.video_metadata = video_metadata
        
        output_data = {
            "final_video_url": workflow_state.final_video_url,
            "final_video_path": final_video_path,
            "composition_timeline": composition_timeline,
            "video_metadata": video_metadata,
            "total_scenes_composed": len(successful_scenes),
            "composition_summary": self._create_composition_summary_from_data(
                composition_timeline, video_metadata
            ),
            "workflow_state_id": workflow_state_id  # 传递给下一个Agent
        }
        
        await self._update_progress(execution, 100, "Video composition completed", db)
        
        return output_data
    
    async def _create_image_slideshow(
        self, 
        scenes_data: List,
        workflow_state_id: str, 
        execution: AgentExecution, 
        db: Session
    ) -> Dict[str, Any]:
        """创建图像轮播作为降级方案"""
        
        await self._update_progress(execution, 30, "Creating image slideshow fallback", db)
        
        # 收集所有可用的图像
        available_images = []
        total_duration = 0.0
        
        for scene in scenes_data:
            scene_duration = scene.duration or settings.DEFAULT_SCENE_DURATION
            total_duration += scene_duration
            
            # 优先使用首帧图像，然后尾帧，最后普通图像
            image_path = None
            if scene.first_frame_path:
                image_path = scene.first_frame_path
            elif scene.last_frame_path:
                image_path = scene.last_frame_path
            elif scene.image_path:
                image_path = scene.image_path
            
            if image_path:
                available_images.append({
                    "scene_number": scene.scene_number,
                    "image_path": image_path,
                    "duration": scene_duration,
                    "title": getattr(scene, 'title', f'Scene {scene.scene_number}'),
                    "description": getattr(scene, 'visual_description', '')
                })
        
        if not available_images:
            self.logger.error("No images available for slideshow creation")
            raise AgentError("No images or videos available for composition")
        
        await self._update_progress(execution, 50, f"Composing slideshow from {len(available_images)} images", db)
        
        try:
            # 使用FFmpeg工具创建图像轮播
            slideshow_result = await self._create_slideshow_with_ffmpeg(available_images, total_duration)
            
            await self._update_progress(execution, 90, "Finalizing slideshow composition", db)
            
            output_data = {
                "composition_type": "image_slideshow",
                "final_video_path": slideshow_result.get("output_path", ""),
                "final_video_url": slideshow_result.get("output_url", ""),
                "total_duration": total_duration,
                "scenes_count": len(available_images),
                "successful_clips": 0,  # 没有视频clips
                "slideshow_images": len(available_images),
                "composition_summary": {
                    "type": "fallback_slideshow",
                    "reason": "no_successful_videos",
                    "images_used": len(available_images),
                    "total_duration": total_duration,
                    "average_scene_duration": total_duration / len(available_images) if available_images else 0
                },
                "technical_specs": {
                    "resolution": "1920x1080",
                    "format": "mp4",
                    "codec": "h264",
                    "frame_rate": 30,
                    "composition_method": "image_slideshow_with_transitions"
                },
                "workflow_state_id": workflow_state_id
            }
            
            await self._update_progress(execution, 100, "Image slideshow completed", db)
            return output_data
            
        except Exception as e:
            self.logger.error(f"Failed to create image slideshow: {str(e)}")
            # 最终降级：返回第一张图像作为静态视频
            if available_images:
                return await self._create_static_video_fallback(available_images[0], workflow_state_id)
            else:
                raise AgentError(f"Complete composition failure: {str(e)}")
    
    async def _create_slideshow_with_ffmpeg(self, images: List[Dict], total_duration: float) -> Dict[str, Any]:
        """使用FFmpeg创建图像轮播"""
        
        # 构建简单的轮播配置
        slideshow_config = {
            "images": images,
            "total_duration": total_duration,
            "transition_type": "fade",
            "transition_duration": settings.TRANSITION_DURATION
        }
        
        try:
            # 尝试使用FFmpeg工具
            if "ffmpeg_tool" in self._available_tools:
                result = await self.use_tool(
                    tool_name="ffmpeg_tool",
                    action="create_slideshow",
                    parameters=slideshow_config
                )
                
                if hasattr(result, 'result'):
                    return result.result or {}
                else:
                    return result or {}
            else:
                # 如果没有FFmpeg工具，生成占位符结果
                self.logger.warning("FFmpeg tool not available, creating placeholder result")
                return {
                    "output_path": "",
                    "output_url": "",
                    "status": "placeholder",
                    "message": "Slideshow creation requires FFmpeg tool"
                }
                
        except Exception as e:
            self.logger.error(f"FFmpeg slideshow creation failed: {str(e)}")
            return {
                "output_path": "",
                "output_url": "",
                "status": "failed",
                "error": str(e)
            }
    
    async def _create_static_video_fallback(self, image_info: Dict, workflow_state_id: str) -> Dict[str, Any]:
        """最终降级方案：创建静态视频"""
        
        self.logger.warning("Creating static video fallback from first available image")
        
        return {
            "composition_type": "static_image",
            "final_video_path": "",
            "final_video_url": "",
            "total_duration": image_info.get("duration", settings.DEFAULT_SCENE_DURATION),
            "scenes_count": 1,
            "successful_clips": 0,
            "slideshow_images": 1,
            "composition_summary": {
                "type": "static_fallback",
                "reason": "slideshow_creation_failed",
                "image_used": image_info.get("image_path", ""),
                "scene_number": image_info.get("scene_number", 1)
            },
            "technical_specs": {
                "resolution": "unknown",
                "format": "placeholder",
                "composition_method": "static_image_fallback"
            },
            "workflow_state_id": workflow_state_id,
            "fallback_message": "Video composition failed, static image placeholder created"
        }
    
    async def _create_composition_timeline(
        self, 
        successful_videos: List[Dict], 
        scenes: List[Scene],
        scripts_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Create timeline for video composition"""
        
        timeline = []
        current_time = 0.0
        
        # Sort videos by scene number
        sorted_videos = sorted(successful_videos, key=lambda x: x["scene_number"])
        
        for i, video_data in enumerate(sorted_videos):
            scene_id = video_data["scene_id"]
            scene = next((s for s in scenes if s.id == scene_id), None)
            
            if not scene:
                continue
            
            # Get script for this scene
            scene_script = self._find_scene_script(scene_id, scripts_data)
            
            timeline_entry = {
                "scene_number": video_data["scene_number"],
                "scene_id": scene_id,
                "video_resource_id": video_data["resource_id"],
                "video_url": video_data["video_url"],
                "start_time": current_time,
                "duration": video_data.get("duration", scene.duration),
                "end_time": current_time + video_data.get("duration", scene.duration),
                
                # Scene metadata
                "scene_title": scene.title,
                "scene_type": scene.scene_type.value,
                "mood": scene.mood_and_atmosphere,
                
                # Script data
                "voice_over_text": scene_script.get("voice_over_text", ""),
                "background_music_style": scene_script.get("background_music_style", "ambient"),
                "sound_effects": scene_script.get("sound_effects", []),
                
                # Transition settings
                "transition_in": self._get_transition_type(i, len(sorted_videos), "in"),
                "transition_out": self._get_transition_type(i, len(sorted_videos), "out"),
                "transition_duration": settings.TRANSITION_DURATION if i > 0 else 0.0
            }
            
            current_time = timeline_entry["end_time"]
            timeline.append(timeline_entry)
        
        return timeline
    
    def _find_scene_script(self, scene_id: int, scripts_data: Dict[str, Any]) -> Dict[str, Any]:
        """Find script data for a specific scene"""
        
        scripts = scripts_data.get("scripts", [])
        
        for script_result in scripts:
            if script_result["scene_id"] == scene_id:
                return script_result["script"]
        
        return {}
    
    def _get_transition_type(self, index: int, total: int, direction: str) -> str:
        """Determine transition type for scene"""
        
        if direction == "in":
            if index == 0:
                return "fade_in"  # First scene
            else:
                return "cross_fade"
        else:  # direction == "out"
            if index == total - 1:
                return "fade_out"  # Last scene
            else:
                return "cross_fade"
    
    async def _prepare_audio_elements(
        self, 
        scenes: List[Scene], 
        scripts_data: Dict[str, Any],
        concept_plan: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Prepare audio elements for the video"""
        
        # For now, return placeholder audio settings
        # In a full implementation, this would generate or select:
        # - Voice-over audio files
        # - Background music
        # - Sound effects
        
        return {
            "voice_over": {
                "enabled": True,
                "style": concept_plan.get("mood_and_tone", "professional"),
                "scenes": [
                    {
                        "scene_id": scene.id,
                        "text": scene.voice_over_text or "",
                        "duration": scene.duration,
                        "start_time": scene.start_time
                    }
                    for scene in scenes if scene.voice_over_text
                ]
            },
            "background_music": {
                "enabled": True,
                "style": "ambient",
                "volume": 0.3,
                "fade_in": 2.0,
                "fade_out": 2.0
            },
            "sound_effects": {
                "enabled": False,  # Disabled for simplicity
                "effects": []
            }
        }
    
    async def _compose_final_video(
        self, 
        timeline: List[Dict], 
        audio_elements: Dict[str, Any],
        concept_plan: Dict[str, Any],
        execution: AgentExecution
    ) -> str:
        """Compose the final video using FFmpeg"""
        
        if not timeline:
            raise AgentError("No timeline entries for video composition")
        
        # Create output filename
        output_filename = f"final_video_{execution.task_id}_{int(asyncio.get_event_loop().time())}.mp4"
        output_path = os.path.join(self.file_storage._ensure_directories(), "generated", output_filename)
        
        try:
            # Use simple concat method for video-only composition
            self.logger.info(f"🎬 Composing {len(valid_video_paths)} videos into final video")
            
            # Create temporary concat file
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
                concat_file_path = f.name
                for video_path in valid_video_paths:
                    abs_path = os.path.abspath(video_path)
                    f.write(f"file '{abs_path}'\n")
            
            self.logger.info(f"🔧 Created concat file: {concat_file_path}")
            
            # Build simple FFmpeg concat command (video-only)
            ffmpeg_cmd = [
                "ffmpeg", "-y",  # -y to overwrite output file
                "-f", "concat", 
                "-safe", "0",
                "-i", concat_file_path,
                "-c", "copy",  # Copy streams without re-encoding (faster)
                output_path
            ]
            
            self.logger.info(f"🎬 Running FFmpeg: {' '.join(ffmpeg_cmd)}")
            
            # Execute FFmpeg command
            process = await asyncio.create_subprocess_exec(
                *ffmpeg_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            # Clean up temporary file
            try:
                os.unlink(concat_file_path)
            except:
                pass
            
            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown FFmpeg error"
                self.logger.error(f"FFmpeg error output: {error_msg}")
                raise AgentError(f"FFmpeg concatenation failed: {error_msg}")
            
            self.logger.info("✅ FFmpeg concatenation successful")
            
            # Verify output file exists
            if not os.path.exists(output_path):
                raise AgentError("Final video file was not created")
            
            self.logger.info(f"✅ Video composition successful: {output_path}")
            return output_path
            
        except Exception as e:
            self.logger.error(f"Video composition failed: {str(e)}")
            raise AgentError(f"Failed to compose video: {str(e)}") from e
    
    async def _build_ffmpeg_command(
        self, 
        timeline: List[Dict], 
        audio_elements: Dict[str, Any],
        output_path: str
    ) -> List[str]:
        """Build FFmpeg command for video composition with background music"""
        
        # Start with basic FFmpeg command
        cmd = ["ffmpeg", "-y"]  # -y to overwrite output file
        
        # Add video input files
        input_files = []
        for entry in timeline:
            video_url = entry["video_url"]
            if video_url and not video_url.startswith("http"):
                # Local file path
                cmd.extend(["-i", video_url])
                input_files.append(video_url)
        
        # Add background music input if available
        background_music = audio_elements.get("background_music", {})
        has_background_music = background_music.get("enabled", False)
        music_input_index = -1
        
        if has_background_music:
            music_path = background_music.get("path")
            if music_path and os.path.exists(music_path):
                cmd.extend(["-i", music_path])
                music_input_index = len(input_files)  # Index of the music input
                input_files.append(music_path)
                self.logger.info(f"🎵 Added background music: {background_music.get('title', 'Unknown')}")
            else:
                has_background_music = False
                self.logger.warning("⚠️ Background music path not found or invalid")
        
        if not input_files:
            raise AgentError("No valid input video files found")
        
        # Calculate total video duration
        total_video_duration = sum(entry.get("duration", settings.DEFAULT_SCENE_DURATION) for entry in timeline)
        
        # Build filter complex for video concatenation and audio mixing
        if has_background_music:
            filter_complex = self._build_filter_complex_with_music(
                timeline, len(input_files) - 1, music_input_index, total_video_duration, 
                audio_elements.get("audio_mixing", {})
            )
        else:
            filter_complex = self._build_filter_complex(timeline, len(input_files))
        
        if filter_complex:
            cmd.extend(["-filter_complex", filter_complex])
            
        # Output mapping based on whether we have background music
        if has_background_music:
            cmd.extend(["-map", "[outv]", "-map", "[outa]"])
        else:
            cmd.extend(["-map", "[outv]", "-map", "[outa]"])
        
        # Add output settings
        cmd.extend([
            "-c:v", "libx264",  # Video codec
            "-preset", "medium",  # Encoding speed vs compression
            "-crf", "23",  # Quality (lower = better quality)
            "-c:a", "aac",  # Audio codec
            "-b:a", "128k",  # Audio bitrate
            "-movflags", "+faststart",  # Optimize for web streaming
            output_path
        ])
        
        return cmd
    
    def _build_filter_complex_with_music(
        self, 
        timeline: List[Dict], 
        num_video_inputs: int, 
        music_input_index: int,
        total_duration: float,
        audio_mixing: Dict[str, Any]
    ) -> str:
        """Build FFmpeg filter complex with background music mixing"""
        
        # Get audio mixing settings
        music_volume = audio_mixing.get("music_volume", 0.25)
        fade_in = audio_mixing.get("fade_in_duration", 1.0)
        fade_out = audio_mixing.get("fade_out_duration", 1.0)
        
        if num_video_inputs == 1:
            # Single video with background music
            filter_parts = []
            
            # Process background music: loop and adjust volume
            filter_parts.append(f"[{music_input_index}:a]aloop=loop=-1:size=2e+09,atrim=duration={total_duration}")
            filter_parts.append(f"volume={music_volume}")
            filter_parts.append(f"afade=t=in:st=0:d={fade_in}")
            filter_parts.append(f"afade=t=out:st={total_duration-fade_out}:d={fade_out}[music]")
            
            # Mix original audio with background music
            filter_parts.append("[0:a][music]amix=inputs=2:duration=first:dropout_transition=2[outa]")
            
            # Video passthrough
            filter_parts.append("[0:v]copy[outv]")
            
            return ";".join(filter_parts)
        
        else:
            # Multiple videos with background music
            filter_parts = []
            
            # Concatenate videos first
            concat_v_inputs = "".join(f"[{i}:v]" for i in range(num_video_inputs))
            concat_a_inputs = "".join(f"[{i}:a]" for i in range(num_video_inputs))
            filter_parts.append(f"{concat_v_inputs}concat=n={num_video_inputs}:v=1:a=1[vconcat][aconcat]")
            
            # Process background music
            filter_parts.append(f"[{music_input_index}:a]aloop=loop=-1:size=2e+09,atrim=duration={total_duration}")
            filter_parts.append(f"volume={music_volume}")
            filter_parts.append(f"afade=t=in:st=0:d={fade_in}")
            filter_parts.append(f"afade=t=out:st={total_duration-fade_out}:d={fade_out}[music]")
            
            # Mix concatenated audio with background music
            filter_parts.append("[aconcat][music]amix=inputs=2:duration=first:dropout_transition=2[outa]")
            
            # Video output
            filter_parts.append("[vconcat]copy[outv]")
            
            return ";".join(filter_parts)
    
    def _build_filter_complex(self, timeline: List[Dict], num_inputs: int) -> str:
        """Build FFmpeg filter complex for video concatenation with transitions"""
        
        if num_inputs == 1:
            return "[0:v][0:a]concat=n=1:v=1:a=1[outv][outa]"
        
        # For multiple inputs, create simple concatenation
        # In a full implementation, this would include transitions
        concat_inputs = ""
        for i in range(num_inputs):
            concat_inputs += f"[{i}:v][{i}:a]"
        
        return f"{concat_inputs}concat=n={num_inputs}:v=1:a=1[outv][outa]"
    
    async def _save_final_video_resource(
        self, 
        task: Task, 
        video_path: str, 
        timeline: List[Dict],
        db: Session
    ) -> Resource:
        """Save final video and create resource record"""
        
        # Get file info
        file_info = await self.file_storage.get_file_info(video_path)
        
        # Calculate total duration
        total_duration = sum(entry["duration"] for entry in timeline)
        
        # Create resource record
        resource = Resource(
            task_id=task.id,
            filename=os.path.basename(video_path),
            original_filename=os.path.basename(video_path),
            file_path=video_path,
            resource_type=ResourceType.VIDEO,
            mime_type="video/mp4",
            file_size=file_info["size"],
            duration=int(total_duration),
            processing_status="completed",
            is_generated=True,
            is_final_output=True,
            generation_parameters={
                "composition_method": "ffmpeg",
                "total_scenes": len(timeline),
                "total_duration": total_duration
            }
        )
        
        db.add(resource)
        db.commit()
        db.refresh(resource)
        
        return resource
    
    async def _generate_video_metadata(
        self, 
        video_path: str, 
        timeline: List[Dict],
        successful_videos: List[Dict]
    ) -> Dict[str, Any]:
        """Generate metadata for the final video"""
        
        file_info = await self.file_storage.get_file_info(video_path)
        total_duration = sum(entry["duration"] for entry in timeline)
        
        return {
            "filename": os.path.basename(video_path),
            "file_size": file_info["size"],
            "file_size_mb": file_info["size"] / (1024 * 1024),
            "duration": total_duration,
            "total_scenes": len(timeline),
            "resolution": "1024x576",  # Typical output resolution
            "format": "mp4",
            "codec": "h264",
            "frame_rate": 24,
            "created_at": file_info["created_at"],
            "composition_method": "ffmpeg_concat",
            "scenes_included": [entry["scene_number"] for entry in timeline]
        }
    
    def _create_composition_summary(
        self, 
        timeline: List[Dict], 
        metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create summary of video composition"""
        
        return {
            "total_scenes": len(timeline),
            "total_duration": metadata["duration"],
            "file_size_mb": metadata["file_size_mb"],
            "resolution": metadata["resolution"],
            "composition_success": True,
            "scene_breakdown": [
                {
                    "scene_number": entry["scene_number"],
                    "duration": entry["duration"],
                    "transition_in": entry["transition_in"],
                    "transition_out": entry["transition_out"]
                }
                for entry in timeline
            ],
            "technical_specs": {
                "format": metadata["format"],
                "codec": metadata["codec"],
                "frame_rate": metadata["frame_rate"]
            }
        }
    
    # New methods for WorkflowState pattern
    async def _create_composition_timeline_from_data(
        self, 
        successful_scenes: List
    ) -> List[Dict[str, Any]]:
        """Create timeline from SceneData objects"""
        
        timeline = []
        current_time = 0.0
        
        for scene_data in successful_scenes:
            timeline_entry = {
                "scene_number": scene_data.scene_number,
                "video_path": scene_data.video_path or scene_data.video_url,
                "start_time": current_time,
                "duration": scene_data.duration,
                "end_time": current_time + scene_data.duration,
                "transition_in": "fade" if scene_data.scene_number > 1 else "none",
                "transition_out": "fade" if scene_data.scene_number < len(successful_scenes) else "none",
                "transition_duration": settings.TRANSITION_DURATION
            }
            timeline.append(timeline_entry)
            current_time += scene_data.duration
        
        return timeline
    
    def _get_background_music_from_workflow(self, workflow_state) -> Dict[str, Any]:
        """从WorkflowState获取背景音乐信息"""
        
        return {
            "audio_url": workflow_state.background_music_url,
            "audio_path": workflow_state.background_music_path,
            "title": workflow_state.background_music_title,
            "duration": workflow_state.background_music_duration,
            "style": workflow_state.background_music_style,
            "available": bool(workflow_state.background_music_url or workflow_state.background_music_path)
        }
    
    async def _prepare_audio_elements_from_data(
        self, 
        scenes_data: List, 
        concept_plan: Dict[str, Any],
        background_music: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Prepare audio elements from SceneData and background music"""
        
        # Default audio mixing settings
        audio_mixing = {
            "voice_volume": 0.8,
            "music_volume": 0.25,  # 背景音乐音量较低，不干扰内容
            "effects_volume": 0.5,
            "fade_in_duration": settings.AUDIO_FADE_IN_DURATION,   # 音乐淡入
            "fade_out_duration": settings.AUDIO_FADE_OUT_DURATION,  # 音乐淡出
            "crossfade_duration": settings.TRANSITION_DURATION  # 场景过渡交叉淡化
        }
        
        # Background music configuration
        background_music_config = {
            "enabled": background_music and background_music.get("available", False),
            "path": background_music.get("audio_path", "") if background_music else "",
            "url": background_music.get("audio_url", "") if background_music else "",
            "title": background_music.get("title", "") if background_music else "",
            "style": background_music.get("style", "ambient") if background_music else "",
            "duration": background_music.get("duration", 0) if background_music else 0,
            "loop": True,  # 背景音乐循环播放
            "start_offset": 0.0  # 音乐开始偏移量
        }
        
        self.logger.info(f"🎵 Background music configured: {background_music_config['enabled']} - {background_music_config.get('title', 'None')}")
        
        return {
            "voice_over": [],  # Voice-over tracks from scene scripts (future feature)
            "background_music": background_music_config,
            "sound_effects": [],  # Sound effects from scene data (future feature)
            "audio_mixing": audio_mixing
        }
    
    async def _compose_final_video_from_data(
        self, 
        timeline: List[Dict], 
        concept_plan: Dict[str, Any],
        execution: AgentExecution
    ) -> str:
        """Compose final video using FFmpeg to combine all scene videos"""
        
        if not timeline:
            self.logger.error("No timeline entries for video composition")
            return ""
        
        try:
            final_video_filename = f"final_video_{execution.id}.mp4"
            final_video_path = self.file_storage.get_output_path(final_video_filename)
            
            # 收集所有有效的视频文件路径
            valid_video_paths = []
            for entry in timeline:
                video_path = entry.get("video_path")
                if video_path and os.path.exists(video_path):
                    valid_video_paths.append(video_path)
                    self.logger.info(f"📹 Adding scene {entry.get('scene_number')} video: {video_path}")
                else:
                    self.logger.warning(f"⚠️ Scene {entry.get('scene_number')} video not found: {video_path}")
            
            if not valid_video_paths:
                self.logger.error("No valid video files found for composition")
                return ""
            
            if len(valid_video_paths) == 1:
                # 只有一个视频，直接复制
                import shutil
                shutil.copy(valid_video_paths[0], final_video_path)
                self.logger.info(f"🎬 Single video composition: copied {valid_video_paths[0]}")
                return final_video_path
            
            # 多个视频，使用FFmpeg合成
            self.logger.info(f"🎬 Composing {len(valid_video_paths)} videos into final video")
            success = await self._ffmpeg_concat_videos(valid_video_paths, final_video_path)
            
            if success and os.path.exists(final_video_path):
                self.logger.info(f"✅ Video composition successful: {final_video_path}")
                return final_video_path
            else:
                self.logger.error("❌ Video composition failed")
                return ""
            
        except Exception as e:
            self.logger.error(f"Failed to compose final video: {str(e)}")
            return ""
    
    async def _ffmpeg_concat_videos(self, video_paths: List[str], output_path: str) -> bool:
        """Use FFmpeg to concatenate multiple videos"""
        
        try:
            # 检查FFmpeg是否可用
            try:
                process = await asyncio.create_subprocess_exec(
                    "ffmpeg", "-version",
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL
                )
                await process.communicate()
                if process.returncode != 0:
                    raise FileNotFoundError("FFmpeg not working")
            except (FileNotFoundError, OSError):
                self.logger.error("❌ FFmpeg is required for video composition but not found!")
                self.logger.error("Please install FFmpeg: sudo apt install ffmpeg (Ubuntu/Debian) or download from https://ffmpeg.org/")
                raise AgentError("FFmpeg is required for video composition. Please install FFmpeg and try again.")
            
            # 创建临时的concat文件列表
            import tempfile
            concat_file_path = None
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
                concat_file_path = f.name
                for video_path in video_paths:
                    # 确保使用绝对路径
                    abs_path = os.path.abspath(video_path)
                    f.write(f"file '{abs_path}'\n")
            
            self.logger.info(f"🔧 Created concat file: {concat_file_path}")
            
            # 构建FFmpeg命令
            ffmpeg_cmd = [
                "ffmpeg", "-y",  # -y 覆盖输出文件
                "-f", "concat", 
                "-safe", "0",
                "-i", concat_file_path,
                "-c", "copy",  # 复制流，不重新编码（更快）
                output_path
            ]
            
            self.logger.info(f"🎬 Running FFmpeg: {' '.join(ffmpeg_cmd)}")
            
            # 执行FFmpeg命令
            process = await asyncio.create_subprocess_exec(
                *ffmpeg_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            # 清理临时文件
            if concat_file_path and os.path.exists(concat_file_path):
                os.unlink(concat_file_path)
            
            if process.returncode == 0:
                self.logger.info("✅ FFmpeg concatenation successful")
                return True
            else:
                error_msg = stderr.decode() if stderr else "Unknown FFmpeg error"
                self.logger.error(f"❌ FFmpeg failed (return code {process.returncode}): {error_msg}")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ FFmpeg concatenation failed: {str(e)}")
            # 清理临时文件
            if concat_file_path and os.path.exists(concat_file_path):
                try:
                    os.unlink(concat_file_path)
                except:
                    pass
            return False
    
    async def _generate_video_metadata_from_data(
        self, 
        video_path: str, 
        timeline: List[Dict], 
        successful_scenes: List
    ) -> Dict[str, Any]:
        """Generate metadata from SceneData"""
        
        total_duration = sum(scene.duration for scene in successful_scenes)
        
        return {
            "duration": total_duration,
            "scenes_count": len(successful_scenes),
            "file_size_mb": 0.0,  # Would calculate from actual file
            "resolution": "1920x1080",
            "frame_rate": 30,
            "format": "mp4",
            "codec": "h264"
        }
    
    def _create_composition_summary_from_data(
        self, 
        timeline: List[Dict], 
        metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create summary from SceneData"""
        
        return {
            "total_scenes": len(timeline),
            "total_duration": metadata["duration"],
            "file_size_mb": metadata["file_size_mb"],
            "resolution": metadata["resolution"],
            "composition_success": True,
            "scene_breakdown": [
                {
                    "scene_number": entry["scene_number"],
                    "duration": entry["duration"],
                    "transition_in": entry["transition_in"],
                    "transition_out": entry["transition_out"]
                }
                for entry in timeline
            ],
            "technical_specs": {
                "format": metadata["format"],
                "codec": metadata["codec"],
                "frame_rate": metadata["frame_rate"]
            }
        }