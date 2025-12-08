"""
Audio Generator Agent - Generates background music and audio for videos
ReAct 版：先规划，再调用工具，失败可重试。
"""
import asyncio
import os
from typing import Dict, Any, List
import json
from sqlalchemy.orm import Session

from .react_agent import ReActAgent, AgentError
from ..models import Task, AgentType, Resource, ResourceType
 
from ..core.config import settings
from .utils.artifacts import (
    pick_artifact_path_from_results,
    persist_scene_outputs,
    finalize_scene_outputs,
)
from .utils.memory_helpers import get_mas_working_memory


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
        """PLAN：仅产生 call_tools（不执行），ACT 统一执行 BaseAgent.execute_tool_calls。"""
        # 中立观察快照，避免在提示中泄漏工具名/参数名
        style_guidance = {}
        try:
            cp = current_state.get("concept_plan", {})
            if isinstance(cp, dict):
                style_guidance = cp.get("intelligent_style_design") or {}
        except Exception:
            style_guidance = {}
        observation_json = json.dumps({
            "timeline": current_state.get("timeline", []),
            "duration": current_state.get("summary", {}).get("duration", 0.0),
            "style_guidance": style_guidance,
        }, ensure_ascii=False)
        messages = [
            {"role": "system", "content": (
                "你是配乐设计与执行代理。目标：生成与视频总时长一致、风格与情绪一致的背景音乐。"
                "如需执行，请直接使用函数调用；若仅规划，可简要说明。"
                f"观察：{observation_json}"
            )},
            {"role": "user", "content": "准备好就进行函数调用，不要输出解释性文本。"},
        ]
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
                "subtask_state": "complete",
                "loop_end_reason": "noop",
                "plan_llm": plan_llm,
            }
        # 提前解析 workflow_state_id，供后续 Shared WM 使用
        wf_id = str(input_data.get("workflow_state_id") or "")
        if not wf_id:
            raise AgentError("Shared WM write failed (background_music): missing workflow_state_id")
        # 统一执行工具调用
        executed_calls = await self.execute_tool_calls(call_tools)
        # 优先从 WorkingMemory 的最近产物索引读取（kind=audio），再回退到 last_round_results / executed_calls
        audio_url: str = ""
        music_path: str = ""
        wm = self.wm
        if wm is not None:
            try:
                latest = wm.latest_iteration_artifacts(kind="audio", limit=1)
                if latest:
                    rec = latest[0]
                    music_path = rec.get("file_path") or ""
                    audio_url = rec.get("url") or ""
            except Exception:
                pass
        if not (music_path or audio_url):
            music_path = pick_artifact_path_from_results(executed_calls, kind="audio", require_local=True) or ""
            if not audio_url:
                for rec in (executed_calls or []):
                    if not isinstance(rec, dict):
                        continue
                    payload = rec.get("result")
                    if hasattr(payload, "result"):
                        payload = getattr(payload, "result")
                    if isinstance(payload, dict) and isinstance(payload.get("audio_url"), str) and payload.get("audio_url"):
                        audio_url = payload.get("audio_url")
                        break
        # 推断时长与风格信息
        # 计算总时长：优先从 Shared WM 时间线推导
        total_duration = 0.0
        try:
            from .utils.memory_helpers import get_mas_working_memory
            overview = get_mas_working_memory(wf_id, service=self.short_term_service).get("scene_overview", {}) or {}
            tl = []
            cursor = 0.0
            for scene in overview.get("scenes", []) or []:
                if not isinstance(scene, dict):
                    continue
                try:
                    sn = int(scene.get("scene_number"))
                except Exception:
                    continue
                dur = float(scene.get("duration") or 0.0)
                tl.append({"scene_number": sn, "start": cursor, "end": cursor + dur, "duration": dur})
                cursor += dur
            total_duration = cursor
        except Exception:
            total_duration = 0.0
        # 写回 WM（失败抛错）
        style_name = ""
        try:
            from .utils.memory_helpers import read_shared_fact
            concept_plan = read_shared_fact(wf_id, "project.concept_plan", {}, service=self.short_term_service) or {}
            if isinstance(concept_plan, dict):
                sg = concept_plan.get("intelligent_style_design") or {}
                style_name = (sg or {}).get("style_name", "")
        except Exception:
            style_name = ""
        bgm_facts = {
            "audio_url": audio_url or "",
            "audio_path": music_path or "",
            "title": "Background Music",
            "duration": float(total_duration or 0),
            "style": style_name,
            "available": bool(audio_url or music_path),
        }
        # 统一写回：artifacts 时间线记录 BGM 阶段产物
        try:
            self.write_shared_artifact(
                kind="audio",
                stage="bgm",
                payload={
                    "file_path": music_path or "",
                    "url": audio_url or "",
                    "duration_sec": float(total_duration or 0),
                    "metadata": {"source": "audio_generator"},
                },
                scene_number=None,
                tool="suno_client",
                workflow_state_id=wf_id,
            )
        except Exception:
            pass
        stored_results: List[Dict[str, Any]] = []
        if ok:
            shared_wm = get_mas_working_memory(wf_id, service=self.short_term_service) if wf_id else None
            stored_results = await persist_scene_outputs(
                artifacts=[
                    {
                        "scene_number": 0,
                        "audio_url": audio_url or "",
                        "audio_path": music_path or "",
                        "duration_sec": float(total_duration or 0),
                        "metadata": {"source": "audio_generator"},
                    }
                ],
                kind="audio",
                agent_memory=None,
                shared_memory=shared_wm,
                include_prompt=False,
            )

        ok = bool(audio_url or music_path)
        return {
            "success": ok,
            "generation_results": stored_results
            if stored_results
            else [{"success": ok, "audio_url": audio_url, "file_path": music_path}],
            "executed_calls": executed_calls,
            "subtask_state": "complete" if ok else "partial",
            "loop_end_reason": "natural_complete" if ok else "incomplete",
            "plan_llm": plan_llm,
        }

    async def _finalize_success_results(
        self,
        final_action_result: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        base = await super()._finalize_success_results(final_action_result, context)
        wf_id = context.get("workflow_state_id") or self.workflow_state_id
        finals, failed = finalize_scene_outputs(
            kind="audio",
            workflow_id=str(wf_id) if wf_id else None,
            agent_memory=self.wm,
        )
        result = dict(base or {})
        result["final_completed_scenes"] = finals
        result["final_failed_scenes"] = failed
        return result

    async def _reflect_on_results(self, action_result: Dict[str, Any], current_state: Dict[str, Any], task: Task, iteration: int) -> Dict[str, Any]:
        ok = bool(action_result.get("success"))
        if (not ok) and iteration == 0:
            return {
                "task_complete": False,
                "reflection_summary": "Retry with stronger energy and negative tags",
            }
        return {
            "task_complete": True,
            "reflection_summary": "Audio generation completed" if ok else "Audio generation incomplete",
            "completed_reason": "Audio generation completed" if ok else None,
        }
    
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
