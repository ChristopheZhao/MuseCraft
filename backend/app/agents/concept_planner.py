"""
Concept Planner Agent - Analyzes requirements and creates video concept plan
"""
import json
import asyncio
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from .base import BaseAgent, AgentError
from ..models import Task, AgentExecution, AgentType, Scene, SceneType
from ..services.ai_client import AIClient
from .utils import SceneDurationCalculator


class ConceptPlannerAgent(BaseAgent):
    """
    Concept Planner Agent analyzes user requirements and creates a detailed
    video concept plan with scene breakdowns and visual descriptions
    """
    
    def __init__(self):
        super().__init__(
            agent_type=AgentType.CONCEPT_PLANNER,
            agent_name="concept_planner",
            timeout_seconds=120,
            max_retries=2
        )
        self.ai_client = AIClient()
    
    async def _execute_impl(
        self, 
        task: Task, 
        input_data: Dict[str, Any], 
        execution: AgentExecution,
        db: Session
    ) -> Dict[str, Any]:
        """Generate video concept plan from user requirements"""
        
        # Validate input
        self._validate_input(input_data, ["user_prompt", "video_style", "duration", "workflow_state_id"])
        
        user_prompt = input_data["user_prompt"]
        video_style = input_data.get("video_style", "professional")
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
        
        # Prepare concept planning prompt
        concept_prompt = self._build_concept_prompt(
            user_prompt, video_style, duration, aspect_ratio
        )
        
        await self._update_progress(execution, 30, "Generating concept plan", db)
        
        try:
            # Call AI service to generate concept plan
            # 使用AI配置管理器获取适合的模型
            from ..core.ai_config import get_ai_config
            ai_config_manager = get_ai_config()
            concept_model = ai_config_manager.get_model_for_agent("concept_planner")
            model_config = ai_config_manager.get_model_config(concept_model)
            
            concept_response = await self.ai_client.generate_text(
                prompt=concept_prompt,
                model=concept_model,
                max_tokens=model_config.max_tokens if model_config else 2000,
                temperature=model_config.temperature if model_config else 0.7,
                response_format={"type": "json_object"}  # 强制返回JSON格式
            )
            
            self._update_token_usage(execution, concept_response.get("usage", {}).get("total_tokens", 0))
            
            await self._update_progress(execution, 60, "Parsing concept plan", db)
            
            # Parse the concept plan
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
            
            # 不再直接调用记忆服务，而是在output_data中提供记忆数据供Orchestrator处理
            
            # Prepare output data - 包含概念计划和记忆数据
            output_data = {
                "concept_plan": concept_plan,
                "total_scenes": len(scenes_data),
                "estimated_duration": duration,
                "video_concept": concept_plan.get("overview", ""),
                "visual_style": concept_plan.get("visual_style", video_style),
                "target_audience": concept_plan.get("target_audience", "general"),
                "key_messages": concept_plan.get("key_messages", []),
                "workflow_state_id": workflow_state_id,
                
                # 提供记忆数据供Orchestrator存储和传递给下游Agent
                "memory_for_storage": {
                    "workflow_id": workflow_state_id,
                    "concept_plan": concept_plan,
                    "agent_name": self.agent_name
                }
            }
            
            await self._update_progress(execution, 100, "Concept planning completed", db)
            
            return output_data
            
        except Exception as e:
            error_msg = f"Failed to generate concept plan: {str(e)}"
            self.logger.error(error_msg)
            raise AgentError(error_msg) from e
    
    def _build_concept_prompt(
        self, 
        user_prompt: str, 
        video_style: str, 
        duration: int,
        aspect_ratio: str
    ) -> str:
        """Build the AI prompt for concept planning"""
        
        return f"""
你是一位专业的创意总监，在多智能体视频制作团队中工作。你的职责是创建全面的创意指导，使你的专业同事（视觉艺术家、动作导演和编辑）能够制作连贯的高质量视频内容。

作为创意总监，你明白你的决策将存储在团队共享记忆系统中，并指导下游专家。专注于提供清晰的创意方向，使团队成员能够自主决策。

用户需求：
- 提示词：{user_prompt}
- 风格：{video_style}
- 时长：{duration}秒
- 宽高比：{aspect_ratio}

**重要**：首先判断场景的物理类型（scene_physics_type），这将指导所有后续Agent的生成策略。

**关键约束**：visual_description必须遵循基础逻辑原则：
- **主体逻辑**：工具不能自主行动，动作状态必须有操作主体（如"手握刀"而非"刀位于...上方"）
- **物理合理性**：根据场景类型确定约束级别
  - **现实场景**：严格符合物理定律，物体需有合理支撑
  - **虚构场景**：可放宽物理约束，但需内部逻辑一致

请根据用户需求的本质创建创意指导方案：

**创意规划原则**：
- 分析用户需求中涉及的主要对象和动作
- **数量识别**：识别用户需求中的数量词和范围词，合理规划场景数量
- **技术约束**：单个场景时长限制为5-10秒，考虑动作复杂度和展示需求
- **忠于用户意图**：严格按照用户表达的内容范围规划场景，既不过度简化也不过度复杂
- 专注于用户明确要求的内容，避免添加用户未要求的展示性内容

**用户需求**: "{user_prompt}"

**场景规划核心原则**：

**展示需求分析**：
- 仔细分析用户想要展示的内容范围和深度
- 考虑观众的观看体验：每个重要内容都应有充分的展示时间
- 平衡内容丰富度与单场景技术限制（5-10秒）

**场景分割判断**：
- 如果用户需求涉及多个**不同类型**的展示对象，考虑为重要对象安排独立场景
- 如果是**连续流程**，按自然的步骤节点分割场景  
- 如果是**单一动作**，通常安排在一个场景内完成

**用户意图理解**：
- 关注用户的**期望效果**：如果用户希望看到"每种的效果"，通常需要多场景
- 关注**内容的重要性平等**：如果多个对象同等重要，给予相似的展示时间
- 避免过度简化：不要为了减少场景数量而牺牲内容展示质量

基于以上原则，创建最适合此需求的创意方案

请创建技术可行且符合用户需求的概念计划，用以下JSON格式：

{{
    "overview": "视频概念和创意愿景的简要概述",
    "target_audience": "目标受众描述",
    "key_messages": ["核心", "信息", "要", "传达"],
    "visual_style_guidance": {{
        "overall_aesthetic": "团队一致性的详细视觉风格描述",
        "color_philosophy": "色彩策略和调色板理念",
        "color_palette": ["主色调", "次色调", "强调色"],
        "visual_consistency_notes": "应在各场景中保持一致的关键视觉元素",
        "artistic_direction": "为视觉艺术家提供的风格解释指导",
        "composition_philosophy": "视觉构图和取景的整体方法",
        "visual_hierarchy": "如何组织视觉元素以达到最大影响",
        "brand_alignment": "视觉如何与预期品牌/信息保持一致"
    }},
    "narrative_flow_strategy": {{
        "mood_and_tone": "整体情感旅程",
        "pacing_strategy": "能量和节奏如何演变",
        "transition_philosophy": "场景连接和流动的方法",
        "story_arc_design": "三幕结构或叙事进展计划",
        "emotional_beats": "关键情感时刻及其位置",
        "audience_engagement_strategy": "如何在整个过程中保持观众注意力",
        "call_to_action_integration": "如何准备最终信息/行动号召"
    }},
    "scenes": [
        {{
            "scene_number": 1,
            "scene_type": "根据实际内容选择适当类型",
            "title": "场景标题",
            "duration": "系统将计算（请提供复杂度提示）",
            "description": "场景简要描述",
            "visual_description": "用于图像生成的详细视觉描述 - 必须遵循物理逻辑和主体约束，描述真实静态场景",
            "narrative_description": "故事背景和叙事目的",
            "creative_intent": "此场景在情感/叙事上应该实现什么"
        }}
    ],
    "agent_collaboration_guidance": {{
        "script_writer_guidance": {{
            "narrative_priorities": "脚本作家应该专注什么",
            "dialogue_style": "任何对话或画外音的首选风格",
            "scene_development_approach": "如何在概念上发展场景",
            "content_arc_strategy": "内容如何在每个场景中发展"
        }},
        "visual_artist_guidance": {{
            "creative_interpretation_scope": "视觉艺术家有多少创作自由",
            "visual_problem_solving": "如何处理视觉挑战",
            "consistency_requirements": "什么必须保持一致 vs 什么可以变化",
            "quality_standards": "视觉质量基准和期望"
        }},
        "motion_director_guidance": {{
            "movement_philosophy": "动作和动态的整体方法",
            "transition_requirements": "场景过渡的具体需求",
            "pacing_coordination": "动作如何支持叙事节奏",
            "technical_constraints": "与动作相关的技术考虑"
        }}
    }},
    "production_guidance": {{
        "technical_requirements": {{
            "resolution": "1920x1080",
            "frame_rate": 30,
            "audio_approach": "音频策略"
        }},
        "team_coordination_notes": "专业团队成员的关键指导",
        "quality_priorities": ["质量", "重点", "领域", "列表"],
        "workflow_optimization": "高效多智能体协调指导",
        "review_criteria": "什么构成此概念的成功执行"
    }},
    "scene_physics_type": {{
        "is_realistic": "请根据场景判断填写true或false",
        "physics_constraints": "请根据is_realistic填写strict或basic", 
        "reasoning": "判断场景类型的具体理由"
    }}
}}

**场景物理类型判断（scene_physics_type）**：
- 分析用户需求，判断视频是现实场景还是虚构场景
- 现实场景（is_realistic=true）：切水果、烹饪、运动、日常活动等，使用strict物理约束
- 虚构场景（is_realistic=false）：科幻、魔法、奇幻、动画、超现实等，使用basic物理约束
- 这个判断将指导所有下游Agent的生成策略，确保物理一致性

多智能体协作的增强创意指导准则：

1. **战略愿景**：像创意总监一样思考 - 提供战略指导，而不仅仅是描述
2. **叙事连贯性**：设计所有场景的视觉和叙事连贯性
3. **故事架构**：考虑每个场景如何服务于整体故事弧线和情感旅程
4. **智能体赋权**：提供每个专家可以在其专业领域内解释的具体指导
5. **无缝集成**：设计支持顺畅工作流交接的场景过渡和连接
6. **实用平衡**：在创意愿景和实际AI生成约束之间取得平衡
7. **记忆驱动协调**：你的指导将存储在团队记忆中 - 使其可操作且可参考
8. **战略推理**：关注创意决策的"为什么"，而不仅仅是"什么"
9. **专家指导**：为每种智能体类型提供清晰方向，同时允许创意解释
10. **质量基准**：为每个制作阶段建立明确的成功标准

**多智能体成功的关键**：
- 每个场景必须有详细的"visual_description"，准确描述应该看到的内容
- 为适当的MAS协调提供清晰的"agent_collaboration_guidance"
- 平衡创作自由和一致性要求
- 为专业智能体的自主决策而设计
- 使每个场景在视觉上独特且与主题相关："{user_prompt}"

**物理规则和常识约束**：
- **自然状态描述**：所有物体应处于自然、静止的状态，避免描述动作过程或意图
- **现实场景物理规律**：物体放置要符合重力、平衡等基本物理原理，严格遵循现实世界逻辑
- **虚构场景逻辑**：虽可放宽物理约束，但需保持场景内部的逻辑一致性和可信度
- **静态场景**：visual_description应描述完整的静态画面，而非动作序列
- **主体逻辑约束**：工具和被动物体不能自主行动或处于工作状态，除非有明确的操作主体或特殊说明
- **场景适应性原则**：描述的合理性标准应与scene_physics_type的判断结果匹配

**视觉描述指导原则**：
- 描述物体的自然摆放状态，而非动作准备状态
- 使用"放置在"、"位于"、"摆在"等静态描述词汇
- 避免"对准"、"瞄准"、"指向"等动作导向词汇
- 确保场景的物理合理性和视觉真实感

**物理合理性和主体逻辑示例**：
- **现实场景**：
  - ✅ "厨师刀平放在台面上，刀刃朝向水果" - 静态摆放
  - ✅ "手握着刀具，准备切割水果" - 有操作主体
  - ❌ "刀悬停在水果上方" - 违反重力定律
  - ❌ "锋利的厨师刀位于橙子中央上方" - 缺乏主体，刀具不能自主行动
- **虚构场景**：
  - ✅ "魔法师操控的刀具悬浮在空中" - 有操作主体
  - ✅ "自动切菜机器的刀刃悬停在蔬菜上方" - 有技术支撑
  - ❌ "普通刀具无故悬浮" - 既违反物理又缺乏逻辑

**MAS工作流考虑**：
- 脚本作家将使用你的叙事指导来创建场景参考
- 视觉艺术家将解释你的视觉指导来生成一致的图像
- 动作导演将遵循你的动作理念来制作动态序列
- 每个智能体应该能够在你的创意框架内自主工作

记住：你的创意决策使专业人员能够有效协作，同时保持统一的创意愿景。所有描述必须符合物理常识和真实世界的逻辑。

重要：只返回一个完整、有效的JSON对象。确保所有字符串都用引号正确关闭，所有大括号都平衡。不要在JSON之前或之后包含任何文本。JSON必须完整且可解析。
"""
    
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
        """Map string scene type to enum"""
        mapping = {
            "intro": SceneType.INTRO,
            "main_content": SceneType.MAIN_CONTENT,
            "transition": SceneType.TRANSITION,
            "outro": SceneType.OUTRO,
            "background": SceneType.BACKGROUND
        }
        return mapping.get(scene_type_str.lower(), SceneType.MAIN_CONTENT)
    
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
    
