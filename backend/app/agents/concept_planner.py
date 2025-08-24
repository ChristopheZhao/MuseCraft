"""
Function Call版本的ConceptPlannerAgent - 完全使用LLM智能决策
"""
import json
import asyncio
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from .base import BaseAgent, AgentError
from ..models import Task, AgentExecution, AgentType, Scene, SceneType
from ..core.workflow_state import workflow_manager, SceneData


class ConceptPlannerAgent(BaseAgent):
    """
    Function Call版本的ConceptPlannerAgent
    使用LLM Function Call进行所有决策：场景规划、内容分析、创意优化
    """
    
    def __init__(self):
        super().__init__(
            agent_type=AgentType.CONCEPT_PLANNER,
            agent_name="concept_planner",
            timeout_seconds=120,
            max_retries=2
            # 不指定tools，使用Agent工具分配系统自动分配
        )
    
    async def _execute_impl(
        self, 
        task: Task, 
        input_data: Dict[str, Any], 
        execution: AgentExecution,
        db: Session
    ) -> Dict[str, Any]:
        """使用LLM Function Call进行概念规划"""
        
        # 验证输入 - MAS智能风格决策适配
        self._validate_input(input_data, ["user_prompt", "duration", "workflow_state_id"])
        
        user_prompt = input_data["user_prompt"]
        style_preference = input_data.get("style_preference")
        duration = input_data.get("duration", 30)
        aspect_ratio = input_data.get("aspect_ratio", "16:9")
        workflow_state_id = input_data["workflow_state_id"]
        
        # 获取 WorkflowState
        workflow_state = workflow_manager.get_workflow(workflow_state_id)
        if not workflow_state:
            raise AgentError(f"WorkflowState {workflow_state_id} not found")
        
        await self._update_progress(execution, 10, "Starting LLM-driven concept planning", db)
        
        # 🧠 使用ConceptGenerationTool进行智能风格决策和概念规划
        try:
            # 使用智能风格决策工具
            concept_params = {
                "user_prompt": user_prompt,
                "duration": duration,
                "aspect_ratio": aspect_ratio
            }
            if style_preference:
                concept_params["style_preference"] = style_preference
                
            planning_result = await self.use_tool(
                "concept_generation_tool",
                "generate_concept", 
                concept_params
            )
            
            await self._update_progress(execution, 60, "Processing planning results", db)
            
            # 处理ConceptGenerationTool的智能风格决策结果
            if hasattr(planning_result, 'result') and isinstance(planning_result.result, dict):
                concept_data = planning_result.result
            elif isinstance(planning_result, dict):
                concept_data = planning_result
            else:
                concept_data = {}
            
            # 提取智能风格设计
            intelligent_style_design = concept_data.get("intelligent_style_design", {})
            
            # 更新WorkflowState中的智能风格设计
            workflow_state.intelligent_style_design = intelligent_style_design
            
            await self._update_progress(execution, 80, "Creating scene data", db)
            
            # 从ConceptGenerationTool结果创建场景数据
            scenes = self._create_scene_data_from_tool_result(concept_data, workflow_state_id)
            
            await self._update_progress(execution, 95, "Finalizing concept plan", db)
            
            # 构建输出结果 - 包含智能风格设计
            result = {
                "concept_plan": concept_data,  # 🔧 修复：传递完整的概念数据字典
                "scenes": scenes,
                "total_scenes": len(scenes),
                "intelligent_style_design": intelligent_style_design,  # 新增智能风格设计
                "duration": duration,
                "aspect_ratio": aspect_ratio,
                "llm_driven": True,  # 标记这是LLM驱动的结果
                "planning_approach": "concept_generation_tool"
            }
            
            self.logger.info(f"🎭 LLM概念规划完成: {len(scenes)}个场景, 方法={result['planning_approach']}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"ConceptGenerationTool失败: {e}")
            self.logger.info("🔄 启用fallback概念规划...")
            
            # Fallback: 创建基本的概念规划和场景数据
            fallback_result = self._create_fallback_concept_plan(
                user_prompt, style_preference, duration, aspect_ratio, workflow_state_id
            )
            
            self.logger.info(f"🎭 Fallback概念规划完成: {len(fallback_result['scenes'])}个场景")
            return fallback_result
    
    async def _llm_guided_concept_planning(
        self, 
        user_prompt: str, 
        video_style: str, 
        duration: int,
        aspect_ratio: str
    ) -> Dict[str, Any]:
        """使用LLM Function Call进行概念规划"""
        
        # 构建给LLM的消息
        messages = [
            {
                "role": "user",
                "content": f"""请为以下视频需求制定完整的概念规划：

用户需求：{user_prompt}
视频风格：{video_style}
总时长：{duration}秒
画面比例：{aspect_ratio}

请分析内容并智能决定：
1. 最佳的场景数量和分配
2. 每个场景的内容重点和视觉描述
3. 整体的创意方向和叙事结构

请使用你的工具来完成这个任务。"""
            }
        ]
        
        # 使用LLM Function Call让AI选择合适的工具和参数
        fc_result = await self.llm_function_call(
            messages=messages,
            context_description="你需要进行视频概念规划，包括场景分析、内容规划和创意优化"
        )
        
        if not fc_result.get("success"):
            raise AgentError(f"LLM Function Call failed: {fc_result.get('error')}")
        
        return fc_result
    
    def _process_planning_results(self, planning_result: Dict[str, Any]) -> Dict[str, Any]:
        """处理LLM规划结果，提取概念规划信息"""
        
        # 从Function Call结果中提取规划信息
        tool_results = planning_result.get("tool_results", [])
        
        concept_plan = {
            "title": "LLM Generated Concept",
            "description": "Intelligent concept planning by LLM",
            "scenes": [],
            "video_style": "professional",
            "approach": "llm_function_call"
        }
        
        # 处理智能场景规划结果
        for result in tool_results:
            if result.get("tool") and "intelligent_scene_planning" in result.get("tool", ""):
                if result.get("result") and hasattr(result["result"], "result"):
                    planning_data = result["result"].result
                    if planning_data.get("success") and planning_data.get("scene_plan"):
                        scene_plan = planning_data["scene_plan"]
                        if "scenes" in scene_plan:
                            concept_plan["scenes"] = scene_plan["scenes"]
                        elif "scene_plan" in scene_plan and "scenes" in scene_plan["scene_plan"]:
                            concept_plan["scenes"] = scene_plan["scene_plan"]["scenes"]
                        
                        concept_plan["approach"] = planning_data.get("approach", "llm_function_call")
                        self.logger.info(f"🧠 智能场景规划: {len(concept_plan['scenes'])}个场景")
        
        # 如果没有场景，创建默认场景
        if not concept_plan["scenes"]:
            concept_plan["scenes"] = [
                {
                    "scene_number": 1,
                    "duration": 30,
                    "content_focus": "Complete video content",
                    "visual_description": "Full video visualization",
                    "narrative_description": "Complete narrative"
                }
            ]
            concept_plan["approach"] = "fallback"
            self.logger.warning("🎭 使用fallback场景规划")
        
        return concept_plan
    
    def _create_scene_data(self, concept_plan: Dict[str, Any], workflow_state_id: str) -> List[Dict[str, Any]]:
        """根据概念规划创建场景数据"""
        
        scenes = []
        for i, scene_info in enumerate(concept_plan.get("scenes", [])):
            scene_data = {
                "scene_number": i + 1,
                "duration": scene_info.get("duration", 5),
                "script_text": scene_info.get("content_focus", ""),
                "visual_description": scene_info.get("visual_description", ""),
                "narrative_description": scene_info.get("narrative_description", ""),
                "scene_type": SceneType.MAIN_CONTENT.value,
                "workflow_state_id": workflow_state_id
            }
            scenes.append(scene_data)
            
            # 创建SceneData对象并存储到workflow_state
            scene_data_obj = SceneData(
                scene_number=scene_data["scene_number"],
                duration=scene_data["duration"],
                script_text=scene_data["script_text"],
                visual_description=scene_data["visual_description"],
                narrative_description=scene_data["narrative_description"]
            )
            
            workflow_state = workflow_manager.get_workflow(workflow_state_id)
            if workflow_state:
                workflow_state.add_scene(scene_data_obj)
                self.logger.info(f"📝 Created scene {scene_data['scene_number']}: {scene_data['script_text'][:50]}...")
        
        return scenes
    
    def _create_fallback_concept_plan(
        self, 
        user_prompt: str, 
        style_preference: str, 
        duration: int, 
        aspect_ratio: str, 
        workflow_state_id: str
    ) -> Dict[str, Any]:
        """当ConceptGenerationTool失败时的fallback概念规划"""
        
        self.logger.info("🎭 使用fallback概念规划...")
        
        # 基于时长智能决定场景数量
        if duration <= 15:
            scene_count = 1
        elif duration <= 30:
            scene_count = 2
        elif duration <= 60:
            scene_count = 3
        else:
            scene_count = min(4, duration // 20)  # 最多4个场景
        
        scene_duration = duration // scene_count
        remaining_duration = duration % scene_count
        
        # 创建基本场景数据
        scenes = []
        for i in range(scene_count):
            # 最后一个场景包含剩余时间
            current_duration = scene_duration + (remaining_duration if i == scene_count - 1 else 0)
            
            scene_data = {
                "scene_number": i + 1,
                "duration": current_duration,
                "script_text": f"Scene {i + 1}: {user_prompt}",
                "visual_description": f"Visual content for scene {i + 1}",
                "narrative_description": f"Narrative for scene {i + 1}",
                "scene_type": "main_content",
                "workflow_state_id": workflow_state_id
            }
            scenes.append(scene_data)
            
            # 创建SceneData对象并存储到workflow_state
            from ..core.workflow_state import SceneData
            scene_data_obj = SceneData(
                scene_number=scene_data["scene_number"],
                duration=scene_data["duration"],
                script_text=scene_data["script_text"],
                visual_description=scene_data["visual_description"],
                narrative_description=scene_data["narrative_description"]
            )
            
            workflow_state = workflow_manager.get_workflow(workflow_state_id)
            if workflow_state:
                workflow_state.add_scene(scene_data_obj)
                self.logger.info(f"📝 Created fallback scene {scene_data['scene_number']}: {current_duration}s")
        
        # 创建fallback智能风格设计
        fallback_style_design = {
            "style_name": "balanced_professional",
            "visual_approach": "mixed_media",
            "narrative_style": "documentary_style",
            "production_taste": "clean_minimal",
            "emotional_tone": "professional_authoritative",
            "style_reasoning": "Fallback style based on content analysis without LLM assistance"
        }
        
        # 构建fallback结果
        result = {
            "concept_plan": {
                "overview": f"Fallback concept plan for: {user_prompt}",
                "scenes": [],
                "intelligent_style_design": fallback_style_design,
                "success": True
            },  # 🔧 修复：返回字典而不是字符串
            "scenes": scenes,
            "total_scenes": len(scenes),
            "intelligent_style_design": fallback_style_design,
            "duration": duration,
            "aspect_ratio": aspect_ratio,
            "llm_driven": False,  # 标记这不是LLM驱动的结果
            "planning_approach": "fallback"
        }
        
        return result
    
    def _create_scene_data_from_tool_result(self, concept_data: Dict[str, Any], workflow_state_id: str) -> List[Dict[str, Any]]:
        """从ConceptGenerationTool结果创建场景数据"""
        
        scenes = []
        scene_list = concept_data.get("scenes", [])
        
        for i, scene_info in enumerate(scene_list):
            scene_data = {
                "scene_number": i + 1,
                "duration": scene_info.get("duration", 5),
                "script_text": scene_info.get("description", ""),
                "visual_description": scene_info.get("visual_description", ""),
                "narrative_description": scene_info.get("description", ""),
                "scene_type": "main_content",
                "workflow_state_id": workflow_state_id
            }
            scenes.append(scene_data)
            
            # 创建SceneData对象并存储到workflow_state
            from ..core.workflow_state import SceneData
            scene_data_obj = SceneData(
                scene_number=scene_data["scene_number"],
                duration=scene_data["duration"],
                script_text=scene_data["script_text"],
                visual_description=scene_data["visual_description"],
                narrative_description=scene_data["narrative_description"]
            )
            
            workflow_state = workflow_manager.get_workflow(workflow_state_id)
            if workflow_state:
                workflow_state.add_scene(scene_data_obj)
                self.logger.info(f"📝 Created scene {scene_data['scene_number']}: {scene_data['script_text'][:50]}...")
        
        return scenes
    
    def _create_fallback_concept_plan(
        self, 
        user_prompt: str, 
        style_preference: str, 
        duration: int, 
        aspect_ratio: str, 
        workflow_state_id: str
    ) -> Dict[str, Any]:
        """当ConceptGenerationTool失败时的fallback概念规划"""
        
        self.logger.info("🎭 使用fallback概念规划...")
        
        # 基于时长智能决定场景数量
        if duration <= 15:
            scene_count = 1
        elif duration <= 30:
            scene_count = 2
        elif duration <= 60:
            scene_count = 3
        else:
            scene_count = min(4, duration // 20)  # 最多4个场景
        
        scene_duration = duration // scene_count
        remaining_duration = duration % scene_count
        
        # 创建基本场景数据
        scenes = []
        for i in range(scene_count):
            # 最后一个场景包含剩余时间
            current_duration = scene_duration + (remaining_duration if i == scene_count - 1 else 0)
            
            scene_data = {
                "scene_number": i + 1,
                "duration": current_duration,
                "script_text": f"Scene {i + 1}: {user_prompt}",
                "visual_description": f"Visual content for scene {i + 1}",
                "narrative_description": f"Narrative for scene {i + 1}",
                "scene_type": "main_content",
                "workflow_state_id": workflow_state_id
            }
            scenes.append(scene_data)
            
            # 创建SceneData对象并存储到workflow_state
            from ..core.workflow_state import SceneData
            scene_data_obj = SceneData(
                scene_number=scene_data["scene_number"],
                duration=scene_data["duration"],
                script_text=scene_data["script_text"],
                visual_description=scene_data["visual_description"],
                narrative_description=scene_data["narrative_description"]
            )
            
            workflow_state = workflow_manager.get_workflow(workflow_state_id)
            if workflow_state:
                workflow_state.add_scene(scene_data_obj)
                self.logger.info(f"📝 Created fallback scene {scene_data['scene_number']}: {current_duration}s")
        
        # 创建fallback智能风格设计
        fallback_style_design = {
            "style_name": "balanced_professional",
            "visual_approach": "mixed_media",
            "narrative_style": "documentary_style",
            "production_taste": "clean_minimal",
            "emotional_tone": "professional_authoritative",
            "style_reasoning": "Fallback style based on content analysis without LLM assistance"
        }
        
        # 构建fallback结果
        result = {
            "concept_plan": {
                "overview": f"Fallback concept plan for: {user_prompt}",
                "scenes": [],
                "intelligent_style_design": fallback_style_design,
                "success": True
            },  # 🔧 修复：返回字典而不是字符串
            "scenes": scenes,
            "total_scenes": len(scenes),
            "intelligent_style_design": fallback_style_design,
            "duration": duration,
            "aspect_ratio": aspect_ratio,
            "llm_driven": False,  # 标记这不是LLM驱动的结果
            "planning_approach": "fallback"
        }
        
        return result