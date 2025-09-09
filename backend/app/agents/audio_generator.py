"""
Audio Generator Agent - Generates background music and audio for videos
"""
import asyncio
import os
from typing import Dict, Any, List
from sqlalchemy.orm import Session

from .base import BaseAgent, AgentError
from ..models import Task, AgentExecution, AgentType, Resource, ResourceType
 
from ..core.config import settings


class AudioGeneratorAgent(BaseAgent):
    """
    Audio Generator Agent creates background music and audio tracks for videos
    """
    
    def __init__(self, llms=None):
        super().__init__(
            agent_type=AgentType.AUDIO_GENERATOR,
            agent_name="audio_generator",
            timeout_seconds=600,  # 10 minutes for audio generation
            max_retries=2,
            # 明确声明所需工具：生成音乐 + 持久化 + 媒体合成/处理
            tools=["suno_client", "file_storage_tool", "ffmpeg_tool", "audio_processor"],
            llms=llms
        )
        
        # 记录视频的实际时长用于音频匹配
        self._target_video_duration = None
    
    async def _execute_impl(
        self, 
        task: Task, 
        input_data: Dict[str, Any], 
        execution: AgentExecution,
        db: Session
    ) -> Dict[str, Any]:
        """Generate background music for the video"""
        
        # Validate input
        self._validate_input(input_data, ["workflow_state_id"])
        
        workflow_state_id = input_data["workflow_state_id"]
        
        # 通过 workflow_manager 获取 WorkflowState
        from ..core.workflow_state import workflow_manager
        workflow_state = workflow_manager.get_workflow(workflow_state_id)
        if not workflow_state:
            raise AgentError(f"WorkflowState {workflow_state_id} not found")
        
        await self._update_progress(execution, 10, "Analyzing final video for music generation", db)
        
        # Get final video path from WorkflowState
        final_video_path = workflow_state.final_video_path
        if not final_video_path or not os.path.exists(final_video_path):
            # Handle case where no final video is available (e.g., video generation failed)
            self.logger.warning(f"Final video not found: {final_video_path}. Creating audio-only result.")
            return await self._create_audio_only_result(workflow_state, input_data, execution, db)
        
        # Get concept plan and scenes data for context
        concept_plan = workflow_state.concept_plan
        scenes_data = workflow_state.scenes
        
        if not concept_plan:
            raise AgentError("No concept plan found for audio generation")
        
        await self._update_progress(execution, 30, "Generating background music", db)
        
        # Get actual video duration using FFprobe
        actual_video_duration = await self._get_video_duration(final_video_path)
        
        # Generate background music based on final video
        music_result = await self._generate_background_music_for_video(
            final_video_path, actual_video_duration, concept_plan, scenes_data, execution
        )
        
        await self._update_progress(execution, 70, "Processing and saving audio files", db)
        
        # Save and process music file
        music_file_path = ""
        if music_result.get("audio_url"):
            # 先下载原始音频
            original_music_path = await self._save_music_file(
                music_result, task.id, execution
            )
            
            # 音频时长匹配实际视频时长
            video_duration = actual_video_duration
            
            # 检查音频时长是否需要调整
            if original_music_path and abs(music_result.get("duration", 0) - video_duration) > 2:
                self.logger.info(f"🎵 Audio duration adjustment needed: {music_result.get('duration')}s → {video_duration}s")
                
                # 尝试调整音频时长（如果可能的话）
                try:
                    adjusted_path = await self._adjust_audio_duration(
                        original_music_path, video_duration, task.id
                    )
                    music_file_path = adjusted_path if adjusted_path else original_music_path
                except Exception as e:
                    self.logger.warning(f"Audio duration adjustment failed: {e}, using original")
                    music_file_path = original_music_path
            else:
                music_file_path = original_music_path
        
        await self._update_progress(execution, 85, "Composing final video with background music", db)
        
        # Create final video with background music
        final_video_with_audio_path = ""
        if music_file_path and final_video_path:
            final_video_with_audio_path = await self._compose_video_with_audio(
                final_video_path, music_file_path, actual_video_duration, execution
            )
        
        await self._update_progress(execution, 90, "Updating workflow state with audio", db)
        
        # Update WorkflowState with audio information and new final video
        workflow_state.update_background_music(
            music_url=music_result.get("audio_url", ""),
            music_path=music_file_path,
            music_title=music_result.get("title", ""),
            music_duration=music_result.get("duration", 0),
            music_style=music_result.get("style", ""),
            music_generation_params=music_result.get("generation_params", {})
        )
        
        # Update final video path if audio composition was successful
        if final_video_with_audio_path:
            workflow_state.final_video_path = final_video_with_audio_path
            try:
                upload = await self.use_tool(
                    "file_storage_tool",
                    "upload_file",
                    {
                        "file_path": final_video_with_audio_path,
                        "destination_key": f"final_videos/final_with_audio_{execution.id}.mp4",
                        "content_type": "video/mp4",
                        "public": True,
                        "metadata": {"execution_id": execution.id}
                    }
                )
                payload = getattr(upload, 'result', upload)
                if isinstance(payload, dict):
                    workflow_state.final_video_url = payload.get("url", "")
            except Exception as e:
                self.logger.warning(f"Failed to upload composed video: {e}")
        
        # Generate audio summary
        audio_summary = self._create_audio_summary(music_result, len(scenes_data))
        
        output_data = {
            "background_music": {
                "audio_url": music_result.get("audio_url", ""),
                "audio_path": music_file_path,
                "title": music_result.get("title", ""),
                "duration": music_result.get("duration", 0),
                "style": music_result.get("style", ""),
                "mood": music_result.get("mood", ""),
                "file_format": music_result.get("file_format", "mp3"),
                "commercial_license": music_result.get("commercial_license", True)
            },
            "final_video": {
                "original_video_path": final_video_path,
                "video_with_audio_path": final_video_with_audio_path or final_video_path,
                "audio_composition_success": bool(final_video_with_audio_path),
                "video_duration": actual_video_duration
            },
            "audio_summary": audio_summary,
            "generation_model": "suno-ai",
            "generation_parameters": music_result.get("generation_params", {}),
            "workflow_state_id": workflow_state_id
        }
        
        await self._update_progress(execution, 100, "Audio generation completed", db)
        
        return output_data
    
    async def _generate_background_music_from_concept(
        self, 
        concept_plan: Dict[str, Any],
        scenes_data: List,
        video_metadata: Dict[str, Any],
        execution: AgentExecution
    ) -> Dict[str, Any]:
        """Generate background music based on video concept and scenes"""
        
        try:
            # Extract music requirements from concept plan
            music_requirements = self._extract_music_requirements(
                concept_plan, scenes_data, video_metadata
            )
            
            # Build music generation prompt
            music_description = self._build_music_description(music_requirements)
            
            # Determine music parameters
            music_params = {
                "description": music_description,
                "mood": music_requirements["mood"],
                "style": music_requirements["style"],
                "duration": music_requirements["duration"],
                "instrumental": True,  # 背景音乐默认为纯音乐
                "title": music_requirements["title"]
            }
            
            self.logger.info(f"🎵 Generating background music: {music_description[:50]}...")
            
            # Use Suno AI tool to generate music (with extended timeout for Suno API)
            result = await self.use_tool(
                "suno_client",
                "generate_background_music", 
                music_params,
                timeout=180  # 3 minutes for Suno music generation
            )
            
            # Extract result from tool output and handle failures
            if hasattr(result, 'success') and not result.success:
                # Tool execution failed
                error_msg = getattr(result, 'error', 'Unknown tool error')
                self.logger.warning(f"🎵 Music generation failed: {error_msg}")
                raise Exception(f"Suno tool execution failed: {error_msg}")
            
            if hasattr(result, 'result'):
                music_result = result.result or {}
            else:
                music_result = result or {}
            
            # Check if we got a valid audio URL
            if not music_result.get("audio_url"):
                self.logger.warning("🎵 No audio URL received from Suno API")
                raise Exception("No audio URL returned from music generation")
            
            # Add our processing metadata
            music_result["generation_params"] = music_params
            music_result["requirements"] = music_requirements
            
            self.logger.info(f"✅ Background music generated: {music_result.get('title', 'Unknown')}")
            
            return music_result
            
        except Exception as e:
            self.logger.error(f"Background music generation failed: {str(e)}")
            
            # Return fallback result for graceful degradation
            return {
                "audio_url": "",
                "title": "Background Music (Generation Failed)",
                "duration": video_metadata.get("duration", settings.DEFAULT_AUDIO_DURATION),
                "style": "ambient",
                "mood": "neutral",
                "error": str(e),
                "is_placeholder": True
            }
    
    def _extract_music_requirements(
        self, 
        concept_plan: Dict[str, Any],
        scenes_data: List,
        video_metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Extract music requirements from video concept and metadata"""
        
        # Get video duration with more precise calculation
        total_duration = video_metadata.get("duration", settings.DEFAULT_AUDIO_DURATION)
        
        # Calculate from scenes data if available
        if scenes_data:
            scene_durations = 0
            for scene in scenes_data:
                if hasattr(scene, 'final_duration'):
                    scene_durations += scene.final_duration
                elif hasattr(scene, 'duration'):
                    scene_durations += scene.duration
                else:
                    scene_durations += settings.DEFAULT_SCENE_DURATION  # default scene duration
            
            if scene_durations > 0:
                total_duration = scene_durations
                self.logger.info(f"🎵 Calculated total video duration from scenes: {total_duration:.1f}s")
            else:
                self.logger.info(f"🎵 Using default video duration: {total_duration}s")
        
        # Extract mood from concept plan
        target_audience = concept_plan.get("target_audience", "general")
        creative_approach = concept_plan.get("creative_approach", {})
        visual_style = concept_plan.get("visual_style", "professional")
        
        # Determine music mood based on content analysis
        mood = self._analyze_content_mood(concept_plan, scenes_data)
        
        # Determine music style based on video style and audience
        style = self._determine_music_style(visual_style, target_audience, creative_approach)
        
        # Generate music title
        video_topic = concept_plan.get("core_message", "").split(".")[0] or "Video"
        title = f"Background Music - {video_topic}"
        
        return {
            "duration": min(max(total_duration, settings.MIN_AUDIO_DURATION), settings.MAX_AUDIO_DURATION),  # 限制在配置范围内
            "mood": mood,
            "style": style,
            "title": title,
            "target_audience": target_audience,
            "visual_style": visual_style,
            "video_topic": video_topic
        }
    
    def _analyze_content_mood(
        self, 
        concept_plan: Dict[str, Any], 
        scenes_data: List
    ) -> str:
        """分析内容情绪，确定音乐情绪"""
        
        # 从概念计划中提取关键词
        core_message = concept_plan.get("core_message", "").lower()
        creative_approach = str(concept_plan.get("creative_approach", {})).lower()
        
        # 从场景数据中分析情绪
        scene_moods = []
        if scenes_data:
            for scene in scenes_data:
                if hasattr(scene, 'mood_and_atmosphere') and scene.mood_and_atmosphere:
                    scene_moods.append(scene.mood_and_atmosphere.lower())
        
        combined_text = f"{core_message} {creative_approach} {' '.join(scene_moods)}"
        
        # 情绪关键词映射
        mood_keywords = {
            "happy": ["happy", "joy", "celebration", "success", "achievement", "positive", "upbeat"],
            "excited": ["exciting", "energy", "dynamic", "action", "adventure", "thrilling"],
            "calm": ["peaceful", "relaxing", "calm", "serene", "meditation", "tranquil"],
            "epic": ["epic", "grand", "heroic", "powerful", "magnificent", "dramatic"],
            "emotional": ["emotional", "touching", "heartfelt", "moving", "sentimental"],
            "mysterious": ["mysterious", "suspense", "intrigue", "unknown", "secret"],
            "playful": ["fun", "playful", "cheerful", "lighthearted", "amusing"],
            "serious": ["professional", "business", "formal", "corporate", "serious"]
        }
        
        # 计算每种情绪的匹配度
        mood_scores = {}
        for mood, keywords in mood_keywords.items():
            score = sum(1 for keyword in keywords if keyword in combined_text)
            if score > 0:
                mood_scores[mood] = score
        
        # 返回得分最高的情绪，默认为calm
        if mood_scores:
            return max(mood_scores, key=mood_scores.get)
        else:
            return "calm"
    
    def _determine_music_style(
        self, 
        visual_style: str, 
        target_audience: str, 
        creative_approach: Dict[str, Any]
    ) -> str:
        """根据视觉风格和目标受众确定音乐风格"""
        
        # 视觉风格映射
        style_mapping = {
            "cinematic": "cinematic",
            "professional": "corporate",
            "modern": "electronic",
            "classic": "classical",
            "artistic": "ambient",
            "documentary": "ambient",
            "commercial": "corporate",
            "casual": "acoustic",
            "dramatic": "orchestral"
        }
        
        # 目标受众映射
        audience_mapping = {
            "business": "corporate",
            "youth": "electronic",
            "general": "cinematic",
            "professional": "corporate",
            "creative": "ambient",
            "family": "acoustic"
        }
        
        # 首先尝试从视觉风格映射
        music_style = style_mapping.get(visual_style.lower(), "cinematic")
        
        # 考虑目标受众调整
        audience_style = audience_mapping.get(target_audience.lower())
        if audience_style and audience_style != music_style:
            # 组合风格或选择更合适的
            if audience_style == "corporate" or music_style == "corporate":
                music_style = "corporate"
            elif audience_style == "electronic" and music_style in ["cinematic", "ambient"]:
                music_style = "electronic"
        
        return music_style
    
    def _build_music_description(self, requirements: Dict[str, Any]) -> str:
        """构建音乐生成描述"""
        
        style = requirements["style"]
        mood = requirements["mood"]
        topic = requirements.get("video_topic", "video")
        audience = requirements.get("target_audience", "general")
        
        # 构建描述性文本
        description_parts = [
            f"Create {style} background music",
            f"with {mood} mood",
            f"suitable for {topic} content",
            f"targeting {audience} audience"
        ]
        
        # 添加具体要求
        specific_requirements = [
            "professional quality",
            "suitable for video background",
            "non-distracting",
            "seamless loop potential"
        ]
        
        description = ", ".join(description_parts + specific_requirements)
        
        return description
    
    async def _save_music_file(
        self, 
        music_result: Dict[str, Any], 
        task_id: int,
        execution: AgentExecution
    ) -> str:
        """Save generated music file and return file path"""
        
        try:
            audio_url = music_result.get("audio_url")
            if not audio_url:
                self.logger.warning("No audio URL provided for saving")
                return ""
            
            # Generate filename
            title = music_result.get("title", "background_music")
            safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).rstrip()
            filename = f"{safe_title}_{task_id}.mp3"
            
            # Download via storage tool and persist locally
            upload = await self.use_tool(
                "file_storage_tool",
                "upload_from_url",
                {
                    "url": audio_url,
                    "destination_key": f"audio/{filename}",
                    "metadata": {"task_id": task_id, "source": "audio_generation"}
                }
            )
            payload = getattr(upload, 'result', upload)
            file_path = payload.get("local_path") if isinstance(payload, dict) else ""
            
            self.logger.info(f"Saved background music: {file_path}")
            return file_path
            
        except Exception as e:
            self.logger.error(f"Failed to save music file: {str(e)}")
            return ""
    
    def _create_audio_summary(
        self, 
        music_result: Dict[str, Any], 
        total_scenes: int
    ) -> Dict[str, Any]:
        """Create summary of audio generation results"""
        
        has_audio = bool(music_result.get("audio_url") and not music_result.get("is_placeholder"))
        
        return {
            "background_music_generated": has_audio,
            "music_title": music_result.get("title", ""),
            "music_duration": music_result.get("duration", 0),
            "music_style": music_result.get("style", ""),
            "music_mood": music_result.get("mood", ""),
            "file_format": music_result.get("file_format", "mp3"),
            "commercial_license": music_result.get("commercial_license", True),
            "generation_model": "suno-ai",
            "total_scenes_analyzed": total_scenes,
            "error": music_result.get("error"),
            "generation_time_estimate": "30-120 seconds"
        }
    
    async def _adjust_audio_duration(
        self,
        original_path: str,
        target_duration: float,
        task_id: int
    ) -> str:
        """使用音频处理工具调整音频时长以匹配视频时长"""
        try:
            result = await self.use_tool(
                "audio_processor",
                "adjust_duration",
                {
                    "input_path": original_path,
                    "target_duration": float(target_duration),
                    "method": "loop",
                    "fade_in": float(getattr(settings, 'AUDIO_FADE_IN_DURATION', 1.0)),
                    "fade_out": float(getattr(settings, 'AUDIO_FADE_OUT_DURATION', 1.0))
                }
            )
            payload = getattr(result, 'result', result)
            if isinstance(payload, dict) and payload.get("output_path"):
                return payload["output_path"]
            return original_path
        except Exception as e:
            self.logger.error(f"Audio duration adjustment failed: {e}")
            return original_path
    
    async def _trim_audio_to_duration(self, input_path: str, duration: float, output_path: str):
        """裁剪音频到指定时长（改为调用 audio_processor 工具）"""
        try:
            result = await self.use_tool(
                "audio_processor",
                "adjust_duration",
                {
                    "input_path": input_path,
                    "target_duration": float(duration),
                    "method": "trim",
                    "output_path": output_path,
                    "fade_out": float(getattr(settings, 'AUDIO_FADE_OUT_DURATION', 1.0))
                }
            )
            if hasattr(result, 'success') and not result.success:
                raise Exception(getattr(result, 'error', 'audio_processor.adjust_duration failed'))
        except Exception as e:
            raise Exception(f"Audio trim failed via tool: {e}")
    
    async def _loop_audio_to_duration(self, input_path: str, duration: float, output_path: str):
        """循环音频到指定时长（改为调用 audio_processor 工具）"""
        try:
            result = await self.use_tool(
                "audio_processor",
                "adjust_duration",
                {
                    "input_path": input_path,
                    "target_duration": float(duration),
                    "method": "loop",
                    "output_path": output_path,
                    "fade_in": float(getattr(settings, 'AUDIO_FADE_IN_DURATION', 1.0)),
                    "fade_out": float(getattr(settings, 'AUDIO_FADE_OUT_DURATION', 1.0))
                }
            )
            if hasattr(result, 'success') and not result.success:
                raise Exception(getattr(result, 'error', 'audio_processor.adjust_duration failed'))
        except Exception as e:
            raise Exception(f"Audio loop failed via tool: {e}")
    
    async def _add_fade_to_audio(self, input_path: str, output_path: str):
        """为音频添加淡入淡出效果（改为调用 audio_processor 工具）"""
        try:
            result = await self.use_tool(
                "audio_processor",
                "add_fade_effects",
                {
                    "input_path": input_path,
                    "fade_in": float(getattr(settings, 'AUDIO_FADE_IN_DURATION', 1.0)),
                    "fade_out": float(getattr(settings, 'AUDIO_FADE_OUT_DURATION', 1.0)),
                    "output_path": output_path
                }
            )
            if hasattr(result, 'success') and not result.success:
                raise Exception(getattr(result, 'error', 'audio_processor.add_fade_effects failed'))
        except Exception as e:
            raise Exception(f"Audio fade processing failed via tool: {e}")

    async def _create_placeholder_audio(self, duration: int) -> Dict[str, Any]:
        """Create placeholder audio information when generation fails"""
        
        return {
            "audio_url": "",
            "title": "Background Music (Placeholder)",
            "duration": duration,
            "style": "ambient",
            "mood": "neutral",
            "file_format": "mp3",
            "commercial_license": False,
            "is_placeholder": True,
            "error": "Audio generation not available"
        }
    
    async def _get_video_duration(self, video_path: str) -> float:
        """通过 ffmpeg_tool 获取视频时长"""
        try:
            info = await self.use_tool(
                "ffmpeg_tool",
                "get_video_info",
                {"file_path": video_path}
            )
            payload = getattr(info, 'result', info)
            dur = float(payload.get("duration")) if isinstance(payload, dict) and payload.get("duration") is not None else None
            if dur:
                self.logger.info(f"🎥 Detected video duration: {dur:.1f}s")
                return dur
            raise ValueError("duration missing")
        except Exception as e:
            self.logger.warning(f"Failed to get video duration: {e}, using fallback")
            return 30.0
    
    async def _generate_background_music_for_video(
        self, 
        video_path: str,
        video_duration: float,
        concept_plan: Dict[str, Any],
        scenes_data: List,
        execution: AgentExecution
    ) -> Dict[str, Any]:
        """Generate background music based on final video file and concept"""
        
        try:
            # Extract music requirements from concept plan (reuse existing logic)
            music_requirements = self._extract_music_requirements(
                concept_plan, scenes_data, {"duration": video_duration}
            )
            
            # Update duration to match actual video
            music_requirements["duration"] = min(max(video_duration, settings.MIN_AUDIO_DURATION), settings.MAX_AUDIO_DURATION)  # 限制在配置范围内
            
            # Build music generation prompt
            music_description = self._build_music_description(music_requirements)
            
            # Determine music parameters
            music_params = {
                "description": music_description,
                "mood": music_requirements["mood"],
                "style": music_requirements["style"],
                "duration": music_requirements["duration"],
                "instrumental": True,  # 背景音乐默认为纯音乐
                "title": music_requirements["title"]
            }
            
            self.logger.info(f"🎵 Generating background music for video: {video_duration:.1f}s - {music_description[:50]}...")
            
            # Use Suno AI tool to generate music (with extended timeout for Suno API)
            result = await self.use_tool(
                "suno_client",
                "generate_background_music", 
                music_params,
                timeout=180  # 3 minutes for Suno music generation
            )
            
            # Extract result from tool output and handle failures
            if hasattr(result, 'success') and not result.success:
                # Tool execution failed
                error_msg = getattr(result, 'error', 'Unknown tool error')
                self.logger.warning(f"🎵 Music generation failed: {error_msg}")
                raise Exception(f"Suno tool execution failed: {error_msg}")
            
            if hasattr(result, 'result'):
                music_result = result.result or {}
            else:
                music_result = result or {}
            
            # Check if we got a valid audio URL
            if not music_result.get("audio_url"):
                self.logger.warning("🎵 No audio URL received from Suno API")
                raise Exception("No audio URL returned from music generation")
            
            # Add our processing metadata
            music_result["generation_params"] = music_params
            music_result["requirements"] = music_requirements
            music_result["video_duration"] = video_duration
            
            self.logger.info(f"✅ Background music generated for video: {music_result.get('title', 'Unknown')}")
            
            return music_result
            
        except Exception as e:
            self.logger.error(f"Background music generation failed: {str(e)}")
            
            # Return fallback result for graceful degradation
            return {
                "audio_url": "",
                "title": "Background Music (Generation Failed)",
                "duration": video_duration,
                "style": "ambient",
                "mood": "neutral",
                "error": str(e),
                "is_placeholder": True
            }
    
    async def _compose_video_with_audio(
        self,
        video_path: str,
        audio_path: str,
        video_duration: float,
        execution: AgentExecution
    ) -> str:
        """使用 ffmpeg_tool 合成视频与背景音乐，返回输出路径"""
        try:
            output_filename = f"final_video_with_audio_{execution.id}.mp4"
            result = await self.use_tool(
                "ffmpeg_tool",
                "add_audio",
                {
                    "video_file": video_path,
                    "audio_file": audio_path,
                    "output_filename": output_filename
                }
            )
            payload = getattr(result, 'result', result)
            # ffmpeg_tool.add_audio 返回键名可能为 output_file（与其他动作对齐），做兼容
            out_path = None
            if isinstance(payload, dict):
                out_path = payload.get("output_path") or payload.get("output_file")
            if out_path and os.path.exists(out_path):
                self.logger.info(f"✅ Video with background music created: {out_path}")
                return out_path
            raise Exception("ffmpeg_tool.add_audio returned no output_path")
        except Exception as e:
            self.logger.error(f"Video audio composition failed: {str(e)}")
            return video_path
    
    async def _create_audio_only_result(
        self, 
        workflow_state, 
        input_data: Dict[str, Any], 
        execution: AgentExecution,
        db: Session
    ) -> Dict[str, Any]:
        """Create audio-only result when no final video is available"""
        
        workflow_state_id = input_data["workflow_state_id"]
        concept_plan = workflow_state.concept_plan
        scenes_data = workflow_state.scenes
        
        if not concept_plan:
            raise AgentError("No concept plan found for audio generation")
        
        await self._update_progress(execution, 30, "Generating background music without video", db)
        
        # Generate background music based on concept plan and scenes
        # Since we don't have actual video metadata, create a minimal one
        video_metadata = {"duration": sum(getattr(scene, 'duration', 5) for scene in scenes_data)}
        music_result = await self._generate_background_music_from_concept(
            concept_plan, scenes_data, video_metadata, execution
        )
        
        await self._update_progress(execution, 70, "Processing and saving audio files", db)
        
        # Save and process music file
        # 使用执行记录中的 task_id 保存文件，并生成可公开访问的 URL
        music_path = await self._save_music_file(music_result, execution.task_id, execution)
        music_url = self.file_storage.get_public_url(music_path) if music_path else ""
        
        await self._update_progress(execution, 90, "Creating audio summary", db)
        
        # Create audio summary and metadata
        audio_summary = self._create_audio_summary(music_result, len(scenes_data))
        
        # Store audio file info in workflow state
        workflow_state.background_audio_path = music_path or ""
        workflow_state.background_audio_url = music_url or ""
        
        # Prepare output data for audio-only result
        output_data = {
            "audio_generation_type": "audio_only",
            "final_video_path": "",  # No video available
            "final_video_url": "",
            "background_audio_path": music_path or "",
            "background_audio_url": music_url or "", 
            "audio_duration": music_result.get("duration", 30),
            "audio_summary": audio_summary,
            "music_style": music_result.get("style", "ambient"),
            "music_mood": music_result.get("mood", "neutral"),
            "audio_files": {
                "background_music_path": music_path or "",
                "background_music_url": music_url or ""
            },
            "workflow_state_id": workflow_state_id,
            "fallback_reason": "no_final_video_available"
        }
        
        await self._update_progress(execution, 100, "Audio-only generation completed", db)
        
        return output_data
