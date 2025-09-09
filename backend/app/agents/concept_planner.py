"""
Concept Planner Agent - Analyzes requirements and creates video concept plan
"""
import json
import asyncio
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from .base import BaseAgent, AgentError
from ..core.config import settings
from ..models import Task, AgentExecution, AgentType, Scene, SceneType
from ..services.ai_client import AIClient
from .utils import SceneDurationCalculator


class ConceptPlannerAgent(BaseAgent):
    """
    Concept Planner Agent analyzes user requirements and creates a detailed
    video concept plan with scene breakdowns and visual descriptions
    """
    
    def __init__(self, llms=None):
        super().__init__(
            agent_type=AgentType.CONCEPT_PLANNER,
            agent_name="concept_planner",
            timeout_seconds=120,
            max_retries=2,
            llms=llms
            # ConceptPlanner使用LLM原生能力，不需要外部工具
        )
        # 使用LLM原生FC能力进行概念生成和智能风格设计
    
    async def _execute_impl(
        self, 
        task: Task, 
        input_data: Dict[str, Any], 
        execution: AgentExecution,
        db: Session
    ) -> Dict[str, Any]:
        """Generate video concept plan from user requirements"""
        
        # Validate input - ConceptPlanner自主生成智能风格，不需要外部video_style
        self._validate_input(input_data, ["user_prompt", "duration", "workflow_state_id"])
        
        user_prompt = input_data["user_prompt"]
        # 移除video_style外部依赖，ConceptPlanner将自主生成智能风格设计
        style_preference = input_data.get("style_preference", None)  # 可选的用户风格偏好
        
        # 使用配置化的总体时长设置
        from ..core.video_config_manager import get_video_config
        video_config = get_video_config()
        
        # 获取系统duration能力
        duration_capability = video_config.get_system_duration_capability()
        default_duration = (duration_capability["min_duration"] + duration_capability["max_duration"]) // 2
        duration = input_data.get("duration", default_duration)  # seconds
        
        # 验证duration请求
        validation = video_config.validate_duration_request(duration)
        if not validation["is_valid"]:
            self.logger.warning(f"🎭 Requested duration {duration}s not supported by {validation['provider']}, "
                              f"using {validation['suggestion']}s instead")
            duration = validation["suggestion"]
        aspect_ratio = input_data.get("aspect_ratio", "16:9")
        workflow_state_id = input_data["workflow_state_id"]
        
        # 获取 WorkflowState
        from ..core.workflow_state import workflow_manager, SceneData
        workflow_state = workflow_manager.get_workflow(workflow_state_id)
        if not workflow_state:
            raise AgentError(f"WorkflowState {workflow_state_id} not found")
        
        await self._update_progress(execution, 10, "Analyzing requirements", db)
        
        # Prepare concept planning prompt - 智能风格设计
        concept_prompt = self._build_intelligent_concept_prompt(
            user_prompt, style_preference, duration, aspect_ratio
        )
        
        await self._update_progress(execution, 30, "Generating concept plan", db)
        
        try:
            # 使用LLM原生FC能力生成概念计划和智能风格设计
            from ..core.ai_config import get_ai_config
            ai_config_manager = get_ai_config()
            concept_model = ai_config_manager.get_model_for_agent("concept_planner")
            model_config = ai_config_manager.get_model_config(concept_model)
            
            # 构建系统+用户消息（不暴露工具名/参数；仅角色与事实）
            messages = []
            try:
                from ..core.prompt_manager import get_prompt_manager
                pm = get_prompt_manager()
                mas_sys = pm.render_template("mas_system", "system", variables={}, use_cache=True, auto_reload=False)
                agent_sys = pm.render_template("concept_planner", "system", variables={}, use_cache=True, auto_reload=False)
                sys_text = ((mas_sys or "").strip() + "\n\n" + (agent_sys or "").strip()).strip()
                if isinstance(sys_text, str) and sys_text.strip():
                    messages.append({"role": "system", "content": sys_text})
            except Exception:
                pass
            messages.append({"role": "user", "content": concept_prompt})
            
            # 使用LLM原生FC能力进行概念生成
            concept_response = await self.llm_function_call(
                messages=messages,
                model=concept_model,
                context_description=f"Generate intelligent video concept with style design for: {user_prompt[:100]}...",
                temperature=model_config.temperature if model_config else 0.7,
                max_tokens=model_config.max_tokens if model_config else 4000,
                response_format={"type": "json_object"}
            )
            
            # 解析LLM响应
            if not concept_response or "content" not in concept_response:
                raise AgentError("LLM failed to generate concept response")
            
            # 提取token使用信息
            usage_info = concept_response.get("usage", {})
            self._update_token_usage(execution, usage_info.get("total_tokens", 0))
            
            await self._update_progress(execution, 60, "Parsing concept plan", db)
            
            # Parse the concept plan - concept_response["content"] 是AI生成的JSON字符串
            concept_plan = self._parse_concept_response(concept_response["content"])
            
            # 关键日志：检查生成的场景描述
            self.logger.info(f"🎭 ConceptPlanner: user_prompt='{user_prompt}', scenes_count={len(concept_plan.get('scenes', []))}")
            for i, scene in enumerate(concept_plan.get("scenes", [])):
                visual_desc = scene.get('visual_description', '')
                desc = scene.get('description', '')
                self.logger.info(f"   Scene {i+1}: visual_description='{visual_desc}', description='{desc}'")
            await self._update_progress(execution, 80, "Creating scene breakdowns", db)
            
            # 使用动态时长优化场景
            optimized_scenes = SceneDurationCalculator.optimize_scene_durations(
                concept_plan.get("scenes", []),
                duration
            )
            concept_plan["scenes"] = optimized_scenes
            
            # Create scene data in WorkflowState (不直接操作数据库)
            scenes_data = await self._create_scenes_in_workflow_state(workflow_state, concept_plan)
            
            await self._update_progress(execution, 95, "Finalizing concept", db)
            
            # 更新 WorkflowState 的概念计划
            workflow_state.concept_plan = concept_plan
            
            # 🧠 Phase 1.2 - 实现MAS记忆共享：ConceptPlanner存储创意指导
            try:
                memory_stored = await self.store_creative_guidance(
                    workflow_id=workflow_state_id,
                    concept_plan=concept_plan
                )
                self.logger.info(f"🧠 ConceptPlanner: 创意指导已存储到MAS记忆系统 (success={memory_stored})")
            except Exception as e:
                self.logger.warning(f"⚠️ ConceptPlanner: 记忆存储失败 - {e}")
            
            # Prepare output data
            output_data = {
                "concept_plan": concept_plan,
                "total_scenes": len(scenes_data),
                "estimated_duration": duration,
                "video_concept": concept_plan.get("overview", ""),
                "visual_style": self._extract_intelligent_style_summary(concept_plan),
                "target_audience": concept_plan.get("target_audience", "general"),
                "key_messages": concept_plan.get("key_messages", []),
                "workflow_state_id": workflow_state_id
            }
            
            await self._update_progress(execution, 100, "Concept planning completed", db)
            
            return output_data
            
        except Exception as e:
            error_msg = f"Failed to generate concept plan: {str(e)}"
            self.logger.error(error_msg)
            raise AgentError(error_msg) from e
    
    def _build_intelligent_concept_prompt(
        self, 
        user_prompt: str, 
        style_preference: Optional[str], 
        duration: int,
        aspect_ratio: str
    ) -> str:
        """Build intelligent concept prompt with LLM-driven style design"""
        
        # 使用智能风格设计模板 - LLM自主分析用户内容并设计合适风格
        return self.render_prompt(
            "concept_generation",
            user_prompt=user_prompt,
            style_preference=style_preference,  # 可选的用户偏好
            enable_intelligent_style=True,     # 启用智能风格设计
            duration=duration,
            aspect_ratio=aspect_ratio
        )
    
    def _parse_concept_response(self, response_content: str) -> Dict[str, Any]:
        """Parse AI response into structured concept plan with robust error handling"""
        
        try:
            # Clean response if needed
            content = response_content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
            
            # First attempt: direct JSON parsing
            try:
                concept_plan = json.loads(content)
            except json.JSONDecodeError as parse_error:
                self.logger.warning(f"Initial JSON parsing failed: {parse_error}")
                
                # Second attempt: try to fix common JSON issues
                concept_plan = self._attempt_json_repair(content, parse_error)
            
            # Validate required fields
            required_fields = ["overview", "scenes"]
            for field in required_fields:
                if field not in concept_plan:
                    raise ValueError(f"Missing required field: {field}")
            
            # Validate scenes
            if not isinstance(concept_plan["scenes"], list) or len(concept_plan["scenes"]) == 0:
                raise ValueError("Scenes must be a non-empty list")
            
            # Process scene_physics_type field if it exists
            if "scene_physics_type" in concept_plan:
                physics_type = concept_plan["scene_physics_type"]
                if isinstance(physics_type, dict):
                    # Convert string "true"/"false" to boolean if needed
                    if "is_realistic" in physics_type:
                        if isinstance(physics_type["is_realistic"], str):
                            is_realistic_str = physics_type["is_realistic"].lower()
                            if "true" in is_realistic_str:
                                physics_type["is_realistic"] = True
                            elif "false" in is_realistic_str:
                                physics_type["is_realistic"] = False
                            else:
                                # Default to true for realistic scenes
                                physics_type["is_realistic"] = True
                    
                    # Ensure physics_constraints is set correctly
                    if "physics_constraints" not in physics_type or not physics_type["physics_constraints"]:
                        physics_type["physics_constraints"] = "strict" if physics_type.get("is_realistic", True) else "basic"
                    elif "strict" in str(physics_type["physics_constraints"]).lower():
                        physics_type["physics_constraints"] = "strict"
                    elif "basic" in str(physics_type["physics_constraints"]).lower():
                        physics_type["physics_constraints"] = "basic"
            else:
                # Add default scene_physics_type if missing
                self.logger.warning("scene_physics_type missing in concept_plan, adding default")
                concept_plan["scene_physics_type"] = {
                    "is_realistic": True,
                    "physics_constraints": "strict",
                    "reasoning": "Default: assuming realistic scene"
                }
            
            return concept_plan
        
            
        except json.JSONDecodeError as e:
            # Log the problematic content for debugging
            self.logger.error(f"JSON parsing failed. Content length: {len(response_content)}")
            self.logger.error(f"Content preview: {response_content[:500]}...")
            self.logger.error(f"Content ending: ...{response_content[-200:]}")
            raise AgentError(f"Failed to parse concept plan JSON: {str(e)}")
        except Exception as e:
            raise AgentError(f"Invalid concept plan format: {str(e)}")
    
    def _attempt_json_repair(self, content: str, original_error: json.JSONDecodeError) -> Dict[str, Any]:
        """Attempt to repair malformed JSON content"""
        
        repair_strategies = [
            self._fix_unterminated_strings,
            self._fix_missing_closing_braces,
            self._extract_complete_json_object,
            self._create_fallback_concept
        ]
        
        for strategy in repair_strategies:
            try:
                repaired_content = strategy(content, original_error)
                if repaired_content:
                    concept_plan = json.loads(repaired_content)
                    self.logger.info(f"JSON repair successful using strategy: {strategy.__name__}")
                    return concept_plan
            except (json.JSONDecodeError, Exception) as e:
                self.logger.debug(f"Repair strategy {strategy.__name__} failed: {e}")
                continue
        
        # If all repair strategies fail, raise the original error
        raise original_error
    
    def _fix_unterminated_strings(self, content: str, error: json.JSONDecodeError) -> Optional[str]:
        """Try to fix unterminated string literals"""
        try:
            # Find the position of the error
            error_pos = error.pos if hasattr(error, 'pos') else len(content)
            
            # Look for the last opening quote before the error position
            content_before_error = content[:error_pos]
            last_quote_pos = content_before_error.rfind('"')
            
            if last_quote_pos != -1:
                # Check if this quote is unmatched
                quote_count = content_before_error[last_quote_pos:].count('"')
                if quote_count % 2 == 1:  # Odd number means unmatched quote
                    # Add closing quote and try to complete the JSON
                    fixed_content = content[:error_pos] + '"'
                    
                    # Try to complete the JSON structure
                    if not fixed_content.rstrip().endswith('}'):
                        fixed_content += '}'
                    
                    return fixed_content
            
            return None
            
        except Exception:
            return None
    
    def _fix_missing_closing_braces(self, content: str, error: json.JSONDecodeError) -> Optional[str]:
        """Try to fix missing closing braces"""
        try:
            # Count opening and closing braces
            open_braces = content.count('{')
            close_braces = content.count('}')
            open_brackets = content.count('[')
            close_brackets = content.count(']')
            
            # Add missing closing characters
            fixed_content = content
            missing_braces = open_braces - close_braces
            missing_brackets = open_brackets - close_brackets
            
            if missing_braces > 0:
                fixed_content += '}' * missing_braces
            
            if missing_brackets > 0:
                fixed_content += ']' * missing_brackets
            
            return fixed_content if missing_braces > 0 or missing_brackets > 0 else None
            
        except Exception:
            return None
    
    def _extract_complete_json_object(self, content: str, error: json.JSONDecodeError) -> Optional[str]:
        """Try to extract a complete JSON object from the beginning"""
        try:
            # Look for the first complete JSON object
            brace_count = 0
            start_pos = content.find('{')
            
            if start_pos == -1:
                return None
            
            for i, char in enumerate(content[start_pos:], start_pos):
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        # Found complete object
                        return content[start_pos:i+1]
            
            return None
            
        except Exception:
            return None
    
    def _create_fallback_concept(self, content: str, error: json.JSONDecodeError) -> Optional[str]:
        """Create a minimal fallback concept plan"""
        try:
            # Extract any text content to use as overview
            import re
            
            # Try to extract overview text
            overview_match = re.search(r'"overview":\s*"([^"]*)', content)
            overview = overview_match.group(1) if overview_match else "Generated video concept"
            
            # Create minimal valid concept
            fallback_concept = {
                "overview": overview,
                "scenes": [
                    {
                        "scene_number": 1,
                        "description": "Main video content",
                        "visual_description": "Visual representation of the video content",
                        "duration": settings.DEFAULT_SCENE_DURATION,
                        "key_elements": ["main content"]
                    }
                ],
                "visual_style": "professional",
                "target_audience": "general",
                "key_messages": ["main message"]
            }
            
            self.logger.warning("Using fallback concept plan due to JSON parsing failure")
            return json.dumps(fallback_concept)
            
        except Exception:
            return None
    
    async def _create_scenes(
        self, 
        task: Task, 
        concept_plan: Dict[str, Any], 
        db: Session
    ) -> List[Scene]:
        """Create scene records in database"""
        
        scenes = []
        current_start_time = 0.0
        
        for scene_data in concept_plan["scenes"]:
            scene = Scene(
                task_id=task.id,
                scene_number=scene_data.get("scene_number", len(scenes) + 1),
                scene_type=self._map_scene_type(scene_data.get("scene_type", "main_content")),
                title=scene_data.get("title", f"Scene {len(scenes) + 1}"),
                description=scene_data.get("description", ""),
                
                # Content
                narrative_description=scene_data.get("narrative_description", ""),
                visual_description=scene_data.get("visual_description", ""),
                
                # Timing - 使用动态计算的时长
                duration=float(scene_data.get("final_duration", scene_data.get("duration", 5))),
                start_time=current_start_time,
                duration_reasoning=scene_data.get("duration_reasoning", ""),
                
                # Visual elements
                background_prompt=scene_data.get("visual_description", ""),
                character_descriptions=scene_data.get("characters", []),
                props_and_objects=scene_data.get("props", []),
                mood_and_atmosphere=scene_data.get("mood", "")[:100],  # Truncate to fit DB
                
                # Camera and style
                camera_angle=scene_data.get("camera_angle", "medium shot")[:50],
                lighting_style=scene_data.get("lighting", "natural")[:50],
                art_style=concept_plan.get("visual_style", "realistic")[:100],  # Truncate to fit DB
                color_palette=concept_plan.get("color_palette", [])
            )
            
            scene.end_time = current_start_time + scene.duration
            current_start_time = scene.end_time
            
            db.add(scene)
            scenes.append(scene)
        
        db.commit()
        
        # Refresh scenes to get IDs
        for scene in scenes:
            db.refresh(scene)
        
        return scenes
    
    async def _create_scenes_in_workflow_state(
        self, 
        workflow_state, 
        concept_plan: Dict[str, Any]
    ) -> List:
        """Create scene data in WorkflowState (内存操作，不涉及数据库)"""
        
        scenes_data = []
        current_start_time = 0.0
        
        for scene_data in concept_plan["scenes"]:
            from ..core.workflow_state import SceneData
            
            scene = SceneData(
                scene_number=scene_data.get("scene_number", len(scenes_data) + 1),
                scene_type=scene_data.get("scene_type", "main_content"),
                title=scene_data.get("title", f"Scene {len(scenes_data) + 1}"),
                description=scene_data.get("description", ""),
                
                # Content
                narrative_description=scene_data.get("narrative_description", ""),
                visual_description=scene_data.get("visual_description", ""),
                
                # Timing - 使用动态计算的时长
                duration=float(scene_data.get("final_duration", scene_data.get("duration", 5))),
                start_time=current_start_time,
                duration_reasoning=scene_data.get("duration_reasoning", ""),
                
                # Visual elements
                character_descriptions=scene_data.get("characters", []),
                props_and_objects=scene_data.get("props", []),
                mood_and_atmosphere=scene_data.get("mood", ""),
                
                # Camera and style
                camera_angle=scene_data.get("camera_angle", "medium shot"),
                lighting_style=scene_data.get("lighting", "natural"),
                art_style=concept_plan.get("visual_style", "realistic"),
                color_palette=concept_plan.get("color_palette", [])
            )
            
            scene.end_time = current_start_time + scene.duration
            current_start_time = scene.end_time
            
            # 添加到 WorkflowState
            workflow_state.add_scene(scene)
            scenes_data.append(scene)
        
        return scenes_data
    
    def _map_scene_type(self, scene_type_str: str) -> SceneType:
        """Map string scene type to enum - handles both English and Chinese terms"""
        if not scene_type_str:
            return SceneType.MAIN_CONTENT
        
        scene_type_lower = scene_type_str.lower().strip()
        
        # English mappings
        english_mapping = {
            "intro": SceneType.INTRO,
            "introduction": SceneType.INTRO,
            "opening": SceneType.INTRO,
            "main_content": SceneType.MAIN_CONTENT,
            "main": SceneType.MAIN_CONTENT,
            "content": SceneType.MAIN_CONTENT,
            "body": SceneType.MAIN_CONTENT,
            "transition": SceneType.TRANSITION,
            "bridge": SceneType.TRANSITION,
            "outro": SceneType.OUTRO,
            "conclusion": SceneType.OUTRO,
            "ending": SceneType.OUTRO,
            "background": SceneType.BACKGROUND
        }
        
        # Chinese mappings for common scenario types
        chinese_mapping = {
            # 开始/起始/引入相关
            "修炼起始": SceneType.INTRO,
            "开始": SceneType.INTRO,
            "起始": SceneType.INTRO,
            "引入": SceneType.INTRO,
            "初始": SceneType.INTRO,
            "开场": SceneType.INTRO,
            # 主要内容/发展/过程
            "能量爆发": SceneType.MAIN_CONTENT,
            "主要内容": SceneType.MAIN_CONTENT,
            "发展": SceneType.MAIN_CONTENT,
            "过程": SceneType.MAIN_CONTENT,
            "进行": SceneType.MAIN_CONTENT,
            "演进": SceneType.MAIN_CONTENT,
            "修炼过程": SceneType.MAIN_CONTENT,
            # 突破/成功/结论/高潮
            "突破成功": SceneType.OUTRO,
            "突破": SceneType.OUTRO,
            "成功": SceneType.OUTRO,
            "完成": SceneType.OUTRO,
            "结束": SceneType.OUTRO,
            "结论": SceneType.OUTRO,
            "收尾": SceneType.OUTRO,
            # 过渡
            "过渡": SceneType.TRANSITION,
            "转场": SceneType.TRANSITION,
            "衔接": SceneType.TRANSITION,
            # 背景
            "背景": SceneType.BACKGROUND,
            "环境": SceneType.BACKGROUND
        }
        
        # Try English mapping first
        if scene_type_lower in english_mapping:
            return english_mapping[scene_type_lower]
        
        # Try Chinese mapping
        if scene_type_str in chinese_mapping:
            return chinese_mapping[scene_type_str]
        
        # Default fallback
        return SceneType.MAIN_CONTENT
    
    def _scene_to_dict(self, scene: Scene) -> Dict[str, Any]:
        """Convert scene model to dictionary"""
        return {
            "id": scene.id,
            "scene_number": scene.scene_number,
            "scene_type": scene.scene_type.value,
            "title": scene.title,
            "description": scene.description,
            "duration": scene.duration,
            "start_time": scene.start_time,
            "end_time": scene.end_time,
            "visual_description": scene.visual_description,
            "narrative_description": scene.narrative_description,
            "mood": scene.mood_and_atmosphere,
            "camera_angle": scene.camera_angle,
            "lighting": scene.lighting_style,
            "art_style": scene.art_style,
            "characters": scene.character_descriptions,
            "props": scene.props_and_objects,
            "color_palette": scene.color_palette
        }
    
    def _extract_intelligent_style_summary(self, concept_plan: Dict[str, Any]) -> str:
        """从智能风格设计中提取风格摘要"""
        
        # 尝试从intelligent_style_design提取风格
        if "intelligent_style_design" in concept_plan:
            style_design = concept_plan["intelligent_style_design"]
            if isinstance(style_design, dict) and "chosen_style" in style_design:
                chosen_style = style_design["chosen_style"]
                
                # 构建风格摘要
                style_parts = []
                if "presentation_form" in chosen_style:
                    style_parts.append(chosen_style["presentation_form"])
                if "narrative_style" in chosen_style:
                    style_parts.append(chosen_style["narrative_style"])
                if "emotional_tone" in chosen_style:
                    style_parts.append(chosen_style["emotional_tone"])
                
                if style_parts:
                    return " + ".join(style_parts)
        
        # Fallback: 尝试从visual_style_guidance提取
        if "visual_style_guidance" in concept_plan:
            guidance = concept_plan["visual_style_guidance"]
            if isinstance(guidance, dict) and "overall_aesthetic" in guidance:
                return guidance["overall_aesthetic"]
        
        # 最终fallback
        return "智能生成风格"
    
