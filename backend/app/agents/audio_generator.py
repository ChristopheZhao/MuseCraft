"""
Audio Generator Agent - Generates background music and audio for videos
ReAct 版：先规划，再调用工具，失败可重试。
"""
import asyncio
from typing import Dict, Any, List
import json
from sqlalchemy.orm import Session

from .react_agent import ReActAgent, AgentError
from ..models import Task, AgentType, Resource, ResourceType
 
from ..core.config import settings
from .utils.artifacts import extract_tool_payload
from .utils.memory_helpers import write_shared_fact


class AudioGeneratorAgent(ReActAgent):
    """
    Audio Generator Agent creates background music and audio tracks for videos
    """
    
    def __init__(self, llms=None, memory_services=None):
        super().__init__(
            agent_type=AgentType.AUDIO_GENERATOR,
            agent_name="audio_generator",
            timeout_seconds=600,  # 10 minutes for audio generation
            max_retries=2,
            # 明确声明所需工具：生成音乐 + 持久化 + 媒体合成/处理
            tools=["suno_client", "file_storage_tool", "ffmpeg_tool", "audio_processor", "audio_analysis_tool"],
            llms=llms,
            memory_services=memory_services,
        )
        
        # 记录视频的实际时长用于音频匹配
        self._target_video_duration = None
    
    async def _execute_impl(
        self,
        task: Task,
        input_data: Dict[str, Any],
        db: Session = None
    ) -> Dict[str, Any]:
        """Delegate to ReAct loop (ReActAgent)."""
        return await super()._execute_impl(task, input_data, db)


    async def _think_and_plan(self, current_state: Dict[str, Any], task: Task, iteration: int) -> Dict[str, Any]:
        """PLAN：使用模板和分区化上下文生成 FC 规划。"""
        # current_state 已包含 orchestrator 组装的上下文（task/static/iteration 分区）；
        # Agent 内不再二次拼装/覆盖，避免双轨事实源。
        messages = self.build_plan_messages(current_state or {})
        # 仅规划：调用 llm_function_call 获取 tool_calls，不执行
        fc_plan = await self.llm_function_call(
            messages=messages,
            context_description="audio background generation planning",
            temperature=0.2,
            tools_override=None,
        )
        planned_calls = []
        if isinstance(fc_plan, dict):
            planned_calls = list(fc_plan.get("tool_calls") or [])
        plan_llm = fc_plan.get("llm_response") if isinstance(fc_plan, dict) else None
        if not planned_calls:
            return {"action": "noop", "plan_llm": plan_llm, "reason": "no_calls_planned"}
        return {
            "action": "execute_planned_calls",
            "tool_calls": planned_calls,
            "plan_llm": plan_llm,
        }

    async def _execute_action(self, action_plan: Dict[str, Any], input_data: Dict[str, Any], db: Session, iteration: int) -> Dict[str, Any]:
        """ACT：只执行规划的 call_tools；不在 Agent 内自组参数直接 use_tool。"""
        # 不在 Agent 内对 action 做白名单判断；
        # 执行层只关心是否存在规划的 call_tools，权限/范围由工具系统与 schema 控制。
        act = (action_plan or {}).get("action")
        # 读取计划的工具调用
        params = (action_plan or {}).get("parameters", {})
        call_tools = list(action_plan.get("tool_calls") or params.get("call_tools") or [])
        plan_llm = action_plan.get("plan_llm") or params.get("plan_llm")
        if act == "noop" or not call_tools:
            return {
                "success": True,
                "generation_results": [],
                "executed_calls": [],
                "plan_llm": plan_llm,
            }
        # 统一执行工具调用
        executed_calls = await self.execute_tool_calls(call_tools)
        audio_url: str = ""
        audio_path: str = ""
        title: str = ""
        duration: float = 0.0
        style: str = ""
        mood: str = ""
        for call in (executed_calls or []):
            if not isinstance(call, dict):
                continue
            payload = extract_tool_payload(call.get("result"))
            if not isinstance(payload, dict):
                continue
            if not audio_url:
                candidate = payload.get("audio_url") or payload.get("url") or ""
                if isinstance(candidate, str) and candidate.strip():
                    audio_url = candidate.strip()
            if not audio_path:
                candidate = payload.get("audio_path") or payload.get("file_path") or payload.get("local_path") or ""
                if isinstance(candidate, str) and candidate.strip():
                    audio_path = candidate.strip()
            if not title and isinstance(payload.get("title"), str):
                title = payload.get("title") or ""
            if not style and isinstance(payload.get("style"), str):
                style = payload.get("style") or ""
            if not mood and isinstance(payload.get("mood"), str):
                mood = payload.get("mood") or ""
            if not duration:
                try:
                    duration = float(payload.get("duration") or payload.get("duration_sec") or 0.0)
                except Exception:
                    duration = duration or 0.0

        ok = bool(audio_url or audio_path)
        background_music = {
            "audio_url": audio_url or "",
            "audio_path": audio_path or "",
            "title": title or "",
            "duration": float(duration or 0.0),
            "style": style or "",
            "mood": mood or "",
            "available": bool(audio_url or audio_path),
        }
        if ok:
            workflow_id = str(input_data.get("workflow_state_id") or self.workflow_state_id or "")
            if workflow_id:
                # MAS SoT: cross-agent deliverable
                try:
                    write_shared_fact(
                        workflow_id,
                        "project.background_music",
                        dict(background_music),
                        service=self.short_term_service,
                    )
                except Exception as exc:
                    self.logger.warning(
                        "MAS write failed: project.background_music agent=%s wf_id=%s err=%s",
                        self.agent_name,
                        workflow_id,
                        exc,
                        exc_info=True,
                    )
                # Optional: normalized artifact receipt (for audit/debug)
                try:
                    tool_name = ""
                    for call in reversed(executed_calls or []):
                        if isinstance(call, dict) and isinstance(call.get("tool"), str) and call.get("tool"):
                            tool_name = call.get("tool") or ""
                            break
                    self.write_shared_artifact(
                        kind="audio",
                        stage="bgm",
                        payload={
                            "file_path": audio_path,
                            "url": audio_url,
                            "duration_sec": float(duration or 0.0),
                            "metadata": {
                                "title": title or "",
                                "style": style or "",
                                "mood": mood or "",
                            },
                        },
                        scene_number=None,
                        tool=tool_name or "audio_generator",
                        workflow_state_id=workflow_id,
                    )
                except Exception:
                    pass
        # 注意：此处不做“任务是否完成”的硬编码裁决（task_complete 由 PLAN 合同 + 事实上下文决定）。
        # action_result 仅回报“本轮执行结果”与“产物索引”（用于写入 OBS→WM→下一轮上下文）。
        return {
            "success": ok,
            "action_performed": "bgm_generation",
            "background_music": background_music,
            "generation_results": [{"success": ok, **background_music}],
            "orchestration_report": {
                "status": "completed" if ok else "partial",
                "boundary_event": "audio_completed",
                "gate_triggers": [],
                "artifacts": [{"kind": "shared_fact", "ref": "project.background_music"}],
                "reflection": {
                    "completion_state": "completed" if ok else "partial",
                    "reported_gaps": [] if ok else ["background_music_generation_failed"],
                    "reported_hints": [],
                },
            },
            "executed_calls": executed_calls,
            "plan_llm": plan_llm,
        }

    async def _reflect_on_results(self, action_result: Dict[str, Any], current_state: Dict[str, Any], task: Task, iteration: int) -> Dict[str, Any]:
        ok = bool(action_result.get("success"))
        summary = "音频生成成功" if ok else "音频生成未成功"
        return {"success": ok, "reflection_summary": summary}
    
    async def _generate_background_music_from_concept(
        self, 
        concept_plan: Dict[str, Any],
        scenes_data: List,
        video_metadata: Dict[str, Any],
        execution: Any
    ) -> Dict[str, Any]:
        """Deprecated legacy path. Tools must be executed via PLAN→ACT."""
        raise AgentError("Deprecated: _generate_background_music_from_concept is not used; use FC-planned calls.")
    
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
        execution: Any
    ) -> str:
        """Deprecated legacy helper. Use FC-planned storage calls in ACT."""
        raise AgentError("Deprecated: _save_music_file is not used; use FC-planned calls.")
    
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
    
    # Removed legacy duration/processing helpers: use FC-planned calls in ACT instead.

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
    
    # Removed _get_video_duration: duration来自上游或 timeline 推导；如需查询由 PLAN 产出工具调用。
    
    # Removed legacy method _generate_background_music_for_video: tool calls are planned in PLAN and executed in ACT.
    
    # Removed legacy method _compose_video_with_audio
    
    # Removed legacy _create_audio_only_result
