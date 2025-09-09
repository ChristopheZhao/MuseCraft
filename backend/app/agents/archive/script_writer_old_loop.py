"""
Script Writer Agent - Generates detailed scripts for video scenes
"""
import json
from typing import Dict, Any, List
from sqlalchemy.orm import Session

from .base import BaseAgent, AgentError
from ..models import Task, AgentExecution, AgentType, Scene
from ..services.ai_client import AIClient
from ..core.workflow_state import WorkflowState, SceneData


class ScriptWriterAgent(BaseAgent):
    """
    Script Writer Agent generates detailed scripts, narratives, and voice-over
    text for each scene based on the concept plan
    """
    
    def __init__(self):
        super().__init__(
            agent_type=AgentType.SCRIPT_WRITER,
            agent_name="script_writer",
            timeout_seconds=600,
            max_retries=2,
            tools=[
                # 纯文本生成无需工具；但场景连续性分析需要工具支持
                "scene_continuity_analysis_tool"
            ]
        )
        # 移除直接AI客户端依赖

    async def execute(
        self,
        task: Task,
        input_data: Dict[str, Any],
        db: Session,
        execution_order: int = 0
    ) -> Dict[str, Any]:
        """Override to set dynamic timeout based on scene count before waiting."""
        try:
            from ..core.config import settings
            scene_count = 0
            # Prefer workflow_state scenes if available
            workflow_state_id = input_data.get("workflow_state_id")
            if workflow_state_id:
                try:
                    from ..core.workflow_state import workflow_manager
                    ws = workflow_manager.get_workflow(workflow_state_id)
                    if ws and getattr(ws, 'scenes', None):
                        scene_count = len(ws.scenes)
                except Exception:
                    pass
            # Fallback: infer from concept_plan if present
            if scene_count == 0:
                try:
                    cp = input_data.get("concept_plan") or {}
                    scenes = cp.get("scenes") or []
                    scene_count = len(scenes)
                except Exception:
                    scene_count = 0

            base = int(getattr(settings, 'SCRIPT_WRITER_TIMEOUT_BASE', 180))
            per_scene = int(getattr(settings, 'SCRIPT_WRITER_TIMEOUT_PER_SCENE', 30))
            max_cap = int(getattr(settings, 'SCRIPT_WRITER_TIMEOUT_MAX', 900))
            dynamic_timeout = min(base + per_scene * max(1, scene_count), max_cap)
            if dynamic_timeout != self.timeout_seconds:
                self.logger.info(
                    f"⏱️ ScriptWriter dynamic timeout: scenes={scene_count}, timeout={dynamic_timeout}s"
                )
                self.timeout_seconds = dynamic_timeout
        except Exception as e:
            self.logger.warning(f"Failed to set dynamic timeout: {e}")

        return await super().execute(task, input_data, db, execution_order)
    
    async def _execute_impl(
        self, 
        task: Task, 
        input_data: Dict[str, Any], 
        execution: AgentExecution,
        db: Session
    ) -> Dict[str, Any]:
        """Generate scripts for all scenes"""
        
        # Validate input
        self._validate_input(input_data, ["concept_plan", "workflow_state_id"])
        
        concept_plan = input_data["concept_plan"]
        workflow_state_id = input_data["workflow_state_id"]
        
        # 🧠 Phase 1.2 - 实现MAS记忆共享：ScriptWriter检索创意指导
        try:
            retrieved_guidance = await self.retrieve_creative_guidance(workflow_state_id)
            if retrieved_guidance:
                # 使用检索到的创意指导增强概念计划
                self.logger.info(f"🧠 ScriptWriter: 成功检索到创意指导，增强概念理解")
                # 合并检索到的指导信息
                concept_plan.update(retrieved_guidance)
            else:
                self.logger.warning(f"⚠️ ScriptWriter: 未找到创意指导记忆，使用原始概念计划")
        except Exception as e:
            self.logger.warning(f"⚠️ ScriptWriter: 记忆检索失败 - {e}")
        
        # 通过 workflow_manager 获取 WorkflowState
        from ..core.workflow_state import workflow_manager
        workflow_state = workflow_manager.get_workflow(workflow_state_id)
        if not workflow_state:
            raise AgentError(f"WorkflowState {workflow_state_id} not found")
        
        await self._update_progress(execution, 10, "Loading scenes", db)
        
        # Get scenes from WorkflowState instead of database
        scenes = workflow_state.scenes
        
        if not scenes:
            raise AgentError("No scenes found in workflow state")
        
        await self._update_progress(execution, 20, "Generating scripts", db)
        
        script_results = []
        total_scenes = len(scenes)
        
        for i, scene_data in enumerate(scenes):
            scene_progress = 20 + int((i / total_scenes) * 60)
            await self._update_progress(
                execution, 
                scene_progress, 
                f"Writing script for scene {scene_data.scene_number}",
                db
            )
            
            # Generate script for this scene
            scene_script = await self._generate_scene_script_from_data(scene_data, concept_plan, execution)
            
            # Update scene data in WorkflowState with enhanced scene design elements
            workflow_state.update_scene(scene_data.scene_number, 
                script_text=scene_script.get("script_text", ""),
                voice_over_text=scene_script.get("script_text", ""),  # 🔧 修复：使用script_text作为voice_over_text
                narrative_description=scene_script.get("narrative_description", scene_data.narrative_description),
                background_music_style=scene_script.get("background_music_style", ""),
                sound_effects=scene_script.get("sound_effects", []),
                # 新增：ScriptWriter专注的场景设计元素
                scene_design_elements=scene_script.get("scene_design_elements", {}),
                narrative_structure=scene_script.get("narrative_structure", {}),
                audio_design=scene_script.get("audio_design", {}),
                pacing_and_timing=scene_script.get("pacing_and_timing", {}),
                content_development_arc=scene_script.get("content_development_arc", {})
            )
            
            script_results.append({
                "scene_number": scene_data.scene_number,
                "script": scene_script
            })
        
        await self._update_progress(execution, 85, "Generating overall narrative", db)
        
        # Generate overall video narrative using WorkflowState scenes
        overall_narrative = await self._generate_overall_narrative_from_state(
            workflow_state.scenes, concept_plan
        )
        
        # Update workflow state with overall narrative
        workflow_state.overall_narrative = overall_narrative.get("story_arc", "")
        workflow_state.script_themes = self._extract_themes(script_results)
        workflow_state.voice_over_instructions = self._generate_voice_instructions(concept_plan)
        workflow_state.estimated_word_count = sum(
            len(script["script"]["script_text"].split()) 
            for script in script_results
        )
        workflow_state.estimated_reading_time = self._calculate_reading_time(script_results)
        
        await self._update_progress(execution, 88, "Analyzing scene continuity", db)
        
        # 🔗 新增：场景连续性分析
        await self._analyze_and_set_scene_continuity(workflow_state, overall_narrative, execution)
        
        await self._update_progress(execution, 95, "Finalizing scripts", db)
        
        # 🧠 Phase 1.2 - 实现MAS记忆共享：ScriptWriter存储场景引用数据
        try:
            for scene_script in script_results:
                scene_number = scene_script["scene_number"]
                scene_references = {
                    "scene_design": scene_script.get("scene_design", {}),
                    "narrative_structure": scene_script.get("narrative_structure", {}),
                    "visual_style_notes": scene_script.get("visual_style_notes", ""),
                    "composition_requirements": scene_script.get("composition_requirements", ""),
                    "overall_narrative": overall_narrative
                }
                
                memory_stored = await self.store_scene_references(
                    workflow_id=workflow_state_id,
                    scene_number=scene_number,
                    scene_references=scene_references
                )
                self.logger.info(f"🧠 ScriptWriter: 场景{scene_number}引用数据已存储 (success={memory_stored})")
        except Exception as e:
            self.logger.warning(f"⚠️ ScriptWriter: 场景引用存储失败 - {e}")
        
        # Prepare output data
        output_data = {
            "scripts": script_results,
            "overall_narrative": overall_narrative,
            "total_scenes": len(scenes),
            "estimated_word_count": workflow_state.estimated_word_count,
            "estimated_reading_time": workflow_state.estimated_reading_time,
            "script_themes": workflow_state.script_themes,
            "voice_over_instructions": workflow_state.voice_over_instructions,
            "workflow_state_id": workflow_state_id  # 返回状态ID而不是对象
        }
        
        await self._update_progress(execution, 100, "Script writing completed", db)
        
        return output_data
    
    async def _generate_scene_script_from_data(
        self, 
        scene_data: SceneData, 
        concept_plan: Dict[str, Any],
        execution: AgentExecution
    ) -> Dict[str, Any]:
        """Generate script for a single scene"""
        
        # 使用新的提示词模板系统，从80+行硬编码减少到简单的模板调用
        script_prompt = self.render_prompt(
            "scene_script_generation",
            scene_number=scene_data.scene_number,
            scene_type=scene_data.scene_type,
            scene_title=scene_data.title,
            scene_duration=scene_data.duration,
            scene_description=scene_data.description,
            visual_description=scene_data.visual_description,
            mood_and_atmosphere=scene_data.mood_and_atmosphere,
            camera_angle=scene_data.camera_angle,
            character_descriptions=scene_data.character_descriptions,
            props_and_objects=scene_data.props_and_objects,
            concept_overview=concept_plan.get('overview', ''),
            target_audience=concept_plan.get('target_audience', ''),
            key_messages=concept_plan.get('key_messages', []),
            visual_style=concept_plan.get('visual_style', ''),
            mood_and_tone=concept_plan.get('mood_and_tone', '')
        )
        
        try:
            # 使用AI配置管理器获取适合的模型
            from ..core.ai_config import get_ai_config
            ai_config_manager = get_ai_config()
            script_model = ai_config_manager.get_model_for_agent("script_writer")
            model_config = ai_config_manager.get_model_config(script_model)
            # 🚀 试点：使用 FC 由 LLM 决策是否调用脚本生成工具
            fc_result = await self.llm_function_call(
                messages=[{"role": "user", "content": script_prompt}],
                context_description=f"为场景{scene_data.scene_number}生成中文脚本（JSON），如需要可以调用脚本生成工具",
                model=script_model,
                temperature=model_config.temperature if model_config else 0.3
            )

            # 工具路径：LLM返回tool_calls并已执行
            if fc_result.get("approach") == "function_call" and fc_result.get("tool_calls"):
                first = fc_result["tool_calls"][0]
                tool_out = first.get("result", {}) or {}
                if isinstance(tool_out, dict) and tool_out.get("script_text"):
                    return {
                        "script_text": tool_out.get("script_text", ""),
                        "visual_guidance": tool_out.get("visual_guidance", ""),
                        "emotional_tone": tool_out.get("emotional_tone", ""),
                        "keywords": tool_out.get("keywords", []),
                        "duration": tool_out.get("duration", scene_data.duration),
                        "duration_reasoning": tool_out.get("duration_reasoning", ""),
                        "success": tool_out.get("success", True)
                    }
                # 工具未返回结构化脚本，尝试content路径
                response_content = (tool_out.get("content") or "") if isinstance(tool_out, dict) else ""
            else:
                # 文本路径：LLM直接在content返回脚本JSON或文本
                response_content = fc_result.get("content", "")

            # 解析文本路径（JSON优先）
            return self._parse_script_response(response_content)
            
        except Exception as e:
            self.logger.error(f"Failed to generate script for scene {scene_data.scene_number}: {str(e)}")
            # Return fallback script
            return self._generate_fallback_script_from_data(scene_data)
    
    def _parse_script_response(self, response_content: str) -> Dict[str, Any]:
        """Parse AI response into structured script data"""
        
        try:
            # Clean response if needed
            content = response_content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
            
            script_data = json.loads(content)
            
            # Validate required fields
            required_fields = ["script_text", "voice_over_text", "narrative_description"]
            for field in required_fields:
                if field not in script_data:
                    script_data[field] = script_data.get("script_text", "")
            
            # Ensure scene design elements exist
            if "scene_design_elements" not in script_data:
                script_data["scene_design_elements"] = {
                    "key_subjects": [],
                    "scene_setting": script_data.get("narrative_description", ""),
                    "visual_style_notes": "Standard visual style",
                    "composition_requirements": "Balanced composition",
                    "continuity_elements": []
                }
            
            if "narrative_structure" not in script_data:
                script_data["narrative_structure"] = {
                    "opening_state": "Scene beginning",
                    "main_action": script_data.get("narrative_description", ""),
                    "closing_state": "Scene completion",
                    "story_function": "Narrative progression"
                }
                
            if "audio_design" not in script_data:
                script_data["audio_design"] = {
                    "background_music_style": script_data.get("background_music_style", "ambient"),
                    "sound_effects": script_data.get("sound_effects", []),
                    "audio_pacing": "moderate"
                }
            
            if "content_development_arc" not in script_data:
                script_data["content_development_arc"] = {
                    "scene_concept_duration": "based on content complexity",
                    "narrative_progression": script_data.get("narrative_description", ""),
                    "emotional_journey": script_data.get("emotional_tone", "neutral"),
                    "action_sequence": "scene actions"
                }
            
            return script_data
            
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse script JSON: {str(e)}")
            raise AgentError(f"Invalid script format: {str(e)}")
    
    def _generate_fallback_script_from_data(self, scene_data: SceneData) -> Dict[str, Any]:
        """Generate fallback script when AI generation fails"""
        
        return {
            "script_text": scene_data.description or f"Scene {scene_data.scene_number}",
            "voice_over_text": scene_data.description or f"Scene {scene_data.scene_number}",
            "narrative_description": scene_data.visual_description or scene_data.description or "",
            "content_development_arc": {
                "scene_concept_duration": f"Dynamic duration for scene {scene_data.scene_number}",
                "narrative_progression": scene_data.description or "Scene progression",
                "emotional_journey": scene_data.mood_and_atmosphere or "neutral emotional flow",
                "action_sequence": "Basic scene actions",
                "scene_transition": "Standard transition to next scene"
            },
            "scene_design_elements": {
                "key_subjects": scene_data.props_and_objects or [],
                "scene_setting": scene_data.description or "Scene environment",
                "visual_style_notes": scene_data.mood_and_atmosphere or "neutral visual style",
                "composition_requirements": "Balanced composition with clear focus",
                "continuity_elements": scene_data.props_and_objects or []
            },
            "narrative_structure": {
                "opening_state": f"Scene {scene_data.scene_number} beginning context",
                "main_action": scene_data.description or "Basic scene action",
                "closing_state": f"Scene {scene_data.scene_number} completion",
                "story_function": "Sequential narrative progression"
            },
            "audio_design": {
                "background_music_style": "ambient",
                "sound_effects": [],
                "audio_pacing": "moderate"
            },
            "pacing_and_timing": {
                "narrative_tempo": "medium",
                "key_timing_moments": [],
                "transition_timing": "standard"
            },
            "emotional_tone": scene_data.mood_and_atmosphere or "neutral",
            "key_words": []
        }
    
    async def _generate_overall_narrative_from_state(
        self, 
        scenes: List[SceneData], 
        concept_plan: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate overall narrative structure for the video"""
        
        scenes_summary = []
        for scene_data in scenes:
            scenes_summary.append({
                "scene_number": scene_data.scene_number,
                "title": scene_data.title,
                "duration": scene_data.duration,
                "script": scene_data.script_text[:200] if scene_data.script_text else "",
                "narrative": scene_data.narrative_description[:200] if scene_data.narrative_description else ""
            })
        
        # 使用新的提示词模板系统 - 整体叙事结构
        narrative_prompt = self.render_prompt(
            "overall_narrative_structure",
            concept_overview=concept_plan.get('overview', ''),
            total_scenes=len(scenes),
            scenes_summary=json.dumps(scenes_summary, indent=2)
        )
        
        try:
            # 使用AI配置管理器获取适合的模型
            from ..core.ai_config import get_ai_config
            ai_config_manager = get_ai_config()
            script_model = ai_config_manager.get_model_for_agent("script_writer")
            model_config = ai_config_manager.get_model_config(script_model)
            
            # 🚀 纯 FC：由 LLM 自主决定是否调用工具；无需工具时直接在 content 返回中文 JSON
            fc = await self.llm_function_call(
                messages=[{"role": "user", "content": narrative_prompt}],
                context_description="生成整体叙事结构（JSON，中文），若无需工具直接在content返回",
                model=script_model,
                temperature=model_config.temperature if model_config else 0.6
            )
            
            content = (fc.get("content") or "").strip() if fc.get("approach") == "text_response" else ""
            if not content and fc.get("approach") == "function_call" and fc.get("tool_calls"):
                first = fc["tool_calls"][0]
                r = first.get("result", {}) or {}
                if isinstance(r, dict):
                    content = (r.get("content") or r.get("json") or "").strip()
                else:
                    content = str(r).strip()
            
            return json.loads(content.strip()) if content else {
                "story_arc": "Standard progression",
                "main_message": concept_plan.get("overview", ""),
                "narrative_flow": "Sequential scene progression"
            }
            
        except Exception as e:
            self.logger.warning(f"Failed to generate overall narrative: {str(e)}")
            return {
                "story_arc": "Standard progression",
                "main_message": concept_plan.get("overview", ""),
                "narrative_flow": "Sequential scene progression"
            }
    
    def _calculate_reading_time(self, script_results: List[Dict]) -> int:
        """Calculate estimated reading time in seconds"""
        
        total_words = sum(
            len(script["script"]["script_text"].split()) 
            for script in script_results
        )
        
        # Average reading speed: 150-160 words per minute for voice-over
        words_per_second = 2.5
        return int(total_words / words_per_second)
    
    def _extract_themes(self, script_results: List[Dict]) -> List[str]:
        """Extract main themes from all scripts"""
        
        themes = set()
        
        for script_result in script_results:
            script = script_result["script"]
            
            # Extract keywords
            keywords = script.get("key_words", [])
            themes.update(keywords)
            
            # Extract from emotional tones
            emotional_tone = script.get("emotional_tone", "")
            if emotional_tone:
                themes.add(emotional_tone)
        
        return list(themes)[:10]  # Return top 10 themes
    
    def _generate_voice_instructions(self, concept_plan: Dict[str, Any]) -> Dict[str, Any]:
        """Generate voice-over instructions for the entire video"""
        
        return {
            "overall_tone": concept_plan.get("mood_and_tone", "professional"),
            "pace": "moderate",
            "style": "conversational and engaging",
            "target_audience": concept_plan.get("target_audience", "general"),
            "pronunciation_notes": [],
            "emphasis_points": concept_plan.get("key_messages", []),
            "pauses_and_timing": "Natural pauses between scenes"
        }
    
    async def _analyze_and_set_scene_continuity(
        self, 
        workflow_state: WorkflowState, 
        overall_narrative: Dict[str, Any],
        execution: AgentExecution
    ) -> None:
        """
        分析所有场景的连续性需求并设置连续性策略
        基于完整脚本 + 整体叙事判断场景间的连续性
        """
        
        try:
            scenes = workflow_state.scenes
            if not scenes or len(scenes) <= 1:
                return
            
            self.logger.info(f"🔗 开始分析 {len(scenes)} 个场景的连续性")
            
            # 调用连续性分析工具
            continuity_analysis = await self.use_tool(
                "scene_continuity_analysis_tool",
                "analyze_all_scenes_continuity", 
                {
                    "scenes": [
                        {
                            "scene_number": scene.scene_number,
                            "title": scene.title,
                            "description": scene.description,
                            "script_text": scene.script_text,
                            "narrative_description": scene.narrative_description,
                            "mood_and_atmosphere": scene.mood_and_atmosphere
                        }
                        for scene in scenes
                    ],
                    "overall_narrative": overall_narrative.get("story_arc", ""),
                    "narrative_flow": overall_narrative.get("narrative_flow", ""),
                    "main_message": overall_narrative.get("main_message", "")
                }
            )
            
            # 处理分析结果
            if hasattr(continuity_analysis, 'result'):
                analysis_result = continuity_analysis.result
            else:
                analysis_result = continuity_analysis
                
            if not isinstance(analysis_result, dict):
                self.logger.warning(f"Unexpected continuity analysis result type: {type(analysis_result)}")
                return
                
            # 应用连续性策略到各个场景
            continuity_decisions = analysis_result.get("continuity_decisions", {})
            
            for scene in scenes:
                scene_key = str(scene.scene_number)
                if scene_key in continuity_decisions:
                    decision = continuity_decisions[scene_key]
                    
                    # 设置图像生成策略
                    scene.image_generation_strategy = decision.get("strategy", "new")
                    
                    # 设置依赖关系
                    if decision.get("strategy") == "continue_from_previous" and scene.scene_number > 1:
                        scene.depends_on_scene = scene.scene_number - 1
                        scene.continuity_reason = decision.get("reason", "")
                        scene.continuity_confidence = decision.get("confidence", 0.8)
                        
                        self.logger.info(
                            f"🔗 Scene {scene.scene_number} 设置连续性策略: "
                            f"continue_from_scene_{scene.depends_on_scene} "
                            f"(confidence: {scene.continuity_confidence})"
                        )
                    else:
                        scene.depends_on_scene = None
                        scene.continuity_reason = decision.get("reason", "Independent scene")
                        scene.continuity_confidence = decision.get("confidence", 0.9)
                        
                        self.logger.info(
                            f"🆕 Scene {scene.scene_number} 设置独立生成策略: new"
                        )
                        
            self.logger.info(f"🔗 场景连续性分析完成")
            
        except Exception as e:
            self.logger.error(f"Scene continuity analysis failed: {e}")
            # 不抛出异常，使用默认策略（所有场景独立生成）
            for scene in workflow_state.scenes:
                scene.image_generation_strategy = "new"
                scene.depends_on_scene = None
"""
DEPRECATION NOTICE (archived)
Legacy module archived. Do not import in production.
"""
import warnings as _warnings
raise ImportError(
    "Archived legacy module 'script_writer_old_loop'. Do not import in production."
)
