"""
Image Generator ReAct Agent - 基于ReAct模式的智能图像生成Agent
"""
import asyncio
import json
from typing import Dict, Any, List
from sqlalchemy.orm import Session

from .react_agent import ReActAgent, AgentError
from .tools.base_tool import ToolError
from ..models import Task, AgentExecution, AgentType
from ..core.config import settings


class ImageGeneratorAgent(ReActAgent):
    """
    Image Generator ReAct Agent - 纯粹的图像生成执行器
    
    单一职责：根据ScriptWriter的连续性决策执行图像生成
    
    职责边界：
    - ✅ 执行图像生成（提示词优化 + 工具调用）
    - ❌ 不做场景连续性分析（由ScriptWriter负责）
    
    ReAct循环：
    1. OBSERVE: 观察当前场景状态和进度
    2. THINK: 读取ScriptWriter的连续性决策
    3. PLAN: 制定执行计划（生成 vs 跳过）
    4. ACT: 执行图像生成或复用
    5. REFLECT: 验证执行结果和完成度
    """
    
    def __init__(self):
        super().__init__(
            agent_type=AgentType.IMAGE_GENERATOR,
            agent_name="image_generator",
            max_iterations=settings.IMAGE_GENERATOR_MAX_ITERATIONS,
            timeout_seconds=600
        )
    
    async def _plan_execution(
        self, 
        task: Task, 
        input_data: Dict[str, Any], 
        execution: AgentExecution,
        workflow_state: Dict[str, Any],
        db: Session
    ) -> Dict[str, Any]:
        """ReAct规划：分析图像生成任务并制定执行计划"""
        
        # 验证输入
        self._validate_input(input_data, ["concept_plan", "workflow_state_id"])
        
        concept_plan = input_data["concept_plan"]
        workflow_state_id = input_data["workflow_state_id"]
        
        # 获取场景数据
        from ..core.workflow_state import workflow_manager
        workflow_state_obj = workflow_manager.get_workflow(workflow_state_id)
        scenes_data = workflow_state_obj.scenes if workflow_state_obj else []
        
        # 构建ReAct规划上下文
        planning_context = {
            "task_type": "image_generation",
            "total_scenes": len(scenes_data),
            "concept_plan": concept_plan,
            "workflow_state_id": workflow_state_id,
            "scenes_overview": [
                {
                    "scene_number": s.scene_number,
                    "title": getattr(s, 'title', ''),
                    "visual_description": getattr(s, 'visual_description', ''),
                    "duration": getattr(s, 'duration', 0)
                } for s in scenes_data[:3]  # 显示前3个场景概览
            ],
            "intelligent_style": concept_plan.get("intelligent_style_design", {})
        }
        
        # 生成ReAct规划
        plan = f"""分析{len(scenes_data)}个场景的图像生成需求：
1. 遍历每个场景，分析连续性需求
2. 对需要生成新图像的场景，创建优化提示词
3. 调用图像生成工具生成图像
4. 验证生成结果质量和一致性
5. 更新场景状态到工作流记忆

当前状态：开始图像生成任务
目标：为所有需要的场景生成高质量图像"""
        
        return {
            "plan": plan,
            "context": planning_context,
            "next_action": "analyze_scene_continuity",
            "scene_index": 0,
            "completed_scenes": [],
            "pending_scenes": list(range(len(scenes_data)))
        }
    
    async def _observe_current_state(self, workflow_state: Dict[str, Any]) -> Dict[str, Any]:
        """OBSERVE: 观察当前场景状态和图像生成进展"""
        
        context = workflow_state.get("context", {})
        scene_index = workflow_state.get("scene_index", 0)
        completed_scenes = workflow_state.get("completed_scenes", [])
        pending_scenes = workflow_state.get("pending_scenes", [])
        
        # 获取当前场景数据
        from ..core.workflow_state import workflow_manager
        workflow_state_obj = workflow_manager.get_workflow(context["workflow_state_id"])
        scenes_data = workflow_state_obj.scenes if workflow_state_obj else []
        
        current_scene = scenes_data[scene_index] if scene_index < len(scenes_data) else None
        
        # 构建观察结果
        observation = {
            "current_scene_index": scene_index,
            "total_scenes": len(scenes_data),
            "completed_count": len(completed_scenes),
            "pending_count": len(pending_scenes),
            "current_scene": {
                "scene_number": current_scene.scene_number if current_scene else None,
                "title": getattr(current_scene, 'title', '') if current_scene else '',
                "visual_description": getattr(current_scene, 'visual_description', '') if current_scene else '',
                "has_existing_image": bool(getattr(current_scene, 'first_frame_url', '')) if current_scene else False
            } if current_scene else None,
            "workflow_progress": f"{len(completed_scenes)}/{len(scenes_data)} scenes completed"
        }
        
        self.logger.info(f"🔍 OBSERVE: 场景 {scene_index + 1}/{len(scenes_data)}, 已完成 {len(completed_scenes)} 个")
        
        return observation
    
    async def _think_and_reason(
        self, 
        observation: Dict[str, Any], 
        workflow_state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """THINK: 读取ScriptWriter的连续性决策，执行相应的图像生成策略"""
        
        context = workflow_state.get("context", {})
        current_scene = observation.get("current_scene")
        
        if not current_scene or current_scene["scene_number"] is None:
            return {"reasoning": "所有场景已处理完成", "decision": "complete"}
        
        # 获取当前场景的完整数据（包含ScriptWriter设置的连续性策略）
        from ..core.workflow_state import workflow_manager
        workflow_state_obj = workflow_manager.get_workflow(context["workflow_state_id"])
        scenes_data = workflow_state_obj.scenes if workflow_state_obj else []
        scene_index = workflow_state.get("scene_index", 0)
        scene_obj = scenes_data[scene_index] if scene_index < len(scenes_data) else None
        
        if not scene_obj:
            return {"reasoning": "场景数据不存在", "decision": "complete"}
        
        # 读取ScriptWriter设置的连续性策略
        image_strategy = getattr(scene_obj, 'image_generation_strategy', 'new')
        depends_on_scene = getattr(scene_obj, 'depends_on_scene', None)
        continuity_reason = getattr(scene_obj, 'continuity_reason', '')
        
        # 根据ScriptWriter的决策执行相应策略
        if image_strategy == 'new':
            decision_data = {
                "need_generation": True,
                "reasoning": f"ScriptWriter决策：需要生成新图像 - {continuity_reason}",
                "next_action": "generate_image"
            }
        else:
            decision_data = {
                "need_generation": False, 
                "reasoning": f"ScriptWriter决策：复用场景{depends_on_scene}的图像 - {continuity_reason}",
                "next_action": "skip_scene",
                "reuse_from_scene": depends_on_scene
            }
        
        self.logger.info(f"🧠 THINK: 场景 {current_scene['scene_number']} - {decision_data['reasoning']}")
        
        return decision_data
    
    async def _plan_next_action(
        self, 
        reasoning: Dict[str, Any], 
        workflow_state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """PLAN: 基于推理结果制定具体的执行计划"""
        
        context = workflow_state.get("context", {})
        scene_index = workflow_state.get("scene_index", 0)
        
        # 获取当前场景
        from ..core.workflow_state import workflow_manager
        workflow_state_obj = workflow_manager.get_workflow(context["workflow_state_id"])
        scenes_data = workflow_state_obj.scenes if workflow_state_obj else []
        current_scene = scenes_data[scene_index] if scene_index < len(scenes_data) else None
        
        if not current_scene:
            return {
                "action": "complete_task",
                "parameters": {},
                "next_scene_index": scene_index
            }
        
        # 根据推理结果制定行动计划
        if reasoning.get("need_generation", False):
            # 需要生成图像 - 制定生成计划
            action_plan = {
                "action": "generate_scene_image",
                "parameters": {
                    "scene_data": {
                        "scene_number": current_scene.scene_number,
                        "title": getattr(current_scene, 'title', ''),
                        "visual_description": getattr(current_scene, 'visual_description', ''),
                        "duration": getattr(current_scene, 'duration', 0)
                    },
                    "style_guidance": context.get("intelligent_style", {}),
                    "concept_plan": context.get("concept_plan", {})
                },
                "next_scene_index": scene_index
            }
            
            self.logger.info(f"📋 PLAN: 为场景 {current_scene.scene_number} 生成图像")
        else:
            # 跳过图像生成 - 标记为复用
            action_plan = {
                "action": "skip_scene_generation", 
                "parameters": {
                    "scene_number": current_scene.scene_number,
                    "reason": reasoning.get("reasoning", "按ScriptWriter决策跳过生成")
                },
                "next_scene_index": scene_index + 1
            }
            
            self.logger.info(f"📋 PLAN: 跳过场景 {current_scene.scene_number} 图像生成")
        
        return action_plan
    
    async def _execute_action(
        self, 
        action_plan: Dict[str, Any], 
        workflow_state: Dict[str, Any],
        db: Session
    ) -> Dict[str, Any]:
        """ACT: 执行具体的图像生成或跳过行动"""
        
        action = action_plan["action"]
        parameters = action_plan["parameters"]
        
        if action == "generate_scene_image":
            return await self._execute_image_generation(parameters, workflow_state)
        
        elif action == "skip_scene_generation":
            return await self._execute_scene_skip(parameters)
        
        elif action == "complete_task":
            return await self._execute_task_completion(workflow_state)
        
        else:
            raise AgentError(f"Unknown action: {action}")
    
    async def _execute_image_generation(
        self, 
        parameters: Dict[str, Any], 
        workflow_state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """执行图像生成：分两步 - 先生成提示词，再调用生成工具"""
        
        scene_data = parameters["scene_data"]
        style_guidance = parameters["style_guidance"]
        
        # Step 1: 使用LLM生成优化的图像提示词
        prompt_messages = [
            {
                "role": "system", 
                "content": """你是专业的图像提示词优化专家。根据场景描述和风格指导生成最优的图像生成提示词。

要求：
1. 提示词应该详细、具象，包含视觉细节
2. 融合智能风格设计指导
3. 适合AI图像生成模型理解
4. 直接在content中返回提示词文本，不使用tool_calls"""
            },
            {
                "role": "user",
                "content": f"""场景信息：
标题：{scene_data['title']}
视觉描述：{scene_data['visual_description']}

风格指导：{style_guidance}

请生成针对此场景的最优图像提示词。"""
            }
        ]
        
        # 生成提示词
        prompt_result = await self.llm_function_call(
            messages=prompt_messages,
            context_description="生成优化的图像提示词",
            temperature=0.7
        )
        
        optimized_prompt = prompt_result.get("content", "").strip()
        
        self.logger.info(f"🎨 生成场景 {scene_data['scene_number']} 提示词: {optimized_prompt[:100]}...")
        
        # Step 2: 调用图像生成工具
        try:
            image_result = await self.use_tool(
                tool_name="image_generation",
                action="generate_image", 
                parameters={
                    "prompt": optimized_prompt,
                    "style": style_guidance.get("表现形式", "realistic"),
                    "quality": "standard",
                    "size": "1024x1024"
                }
            )
            
            tool_result = image_result.result if hasattr(image_result, 'result') else image_result
            
            # 存储图像到文件系统
            if tool_result.get("image_url"):
                storage_result = await self.use_tool(
                    tool_name="file_storage_tool",
                    action="upload_from_url",
                    parameters={
                        "url": tool_result["image_url"],
                        "destination_key": f"images/scene_{scene_data['scene_number']}_image.jpg",
                        "metadata": {
                            "scene_number": scene_data['scene_number'],
                            "source": "react_image_generation"
                        }
                    }
                )
                
                file_result = storage_result.result if hasattr(storage_result, 'result') else storage_result
                
                execution_result = {
                    "success": True,
                    "scene_number": scene_data['scene_number'],
                    "image_url": tool_result["image_url"],
                    "image_path": file_result.get("file_path", ""),
                    "optimized_prompt": optimized_prompt,
                    "generation_params": tool_result.get("parameters", {}),
                    "action_performed": "generated_new_image"
                }
            else:
                raise ToolError("图像生成工具未返回图像URL")
                
        except Exception as e:
            self.logger.error(f"❌ 场景 {scene_data['scene_number']} 图像生成失败: {str(e)}")
            execution_result = {
                "success": False,
                "scene_number": scene_data['scene_number'],
                "error": str(e),
                "action_performed": "generation_failed"
            }
        
        return execution_result
    
    async def _execute_scene_skip(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """执行场景跳过：记录跳过原因"""
        
        scene_number = parameters["scene_number"]
        reason = parameters["reason"]
        
        self.logger.info(f"⏭️ 跳过场景 {scene_number} 图像生成: {reason}")
        
        return {
            "success": True,
            "scene_number": scene_number,
            "action_performed": "skipped_generation",
            "reason": reason
        }
    
    async def _execute_task_completion(self, workflow_state: Dict[str, Any]) -> Dict[str, Any]:
        """执行任务完成：汇总结果"""
        
        completed_scenes = workflow_state.get("completed_scenes", [])
        
        self.logger.info(f"✅ 图像生成任务完成，处理了 {len(completed_scenes)} 个场景")
        
        return {
            "success": True,
            "action_performed": "task_completed",
            "total_scenes_processed": len(completed_scenes),
            "completed_scenes": completed_scenes
        }
    
    async def _reflect_on_results(
        self, 
        action_result: Dict[str, Any], 
        workflow_state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """REFLECT: 反思执行结果并决定是否继续迭代"""
        
        action_performed = action_result.get("action_performed", "")
        success = action_result.get("success", False)
        
        # 更新工作流状态
        scene_index = workflow_state.get("scene_index", 0)
        completed_scenes = workflow_state.get("completed_scenes", [])
        pending_scenes = workflow_state.get("pending_scenes", [])
        next_scene_index = action_result.get("next_scene_index", scene_index + 1)
        
        if success and action_performed in ["generated_new_image", "skipped_generation"]:
            # 场景处理成功
            scene_number = action_result.get("scene_number")
            completed_scenes.append({
                "scene_number": scene_number,
                "action": action_performed,
                "result": action_result
            })
            
            # 从待处理列表移除
            if scene_index in pending_scenes:
                pending_scenes.remove(scene_index)
        
        # 判断是否完成所有场景
        context = workflow_state.get("context", {})
        total_scenes = context.get("total_scenes", 0)
        workflow_complete = next_scene_index >= total_scenes
        
        reflection = {
            "success": success,
            "workflow_complete": workflow_complete,
            "updated_state": {
                "scene_index": next_scene_index,
                "completed_scenes": completed_scenes,
                "pending_scenes": pending_scenes
            },
            "continue_iteration": not workflow_complete,
            "reflection_summary": f"场景处理: {action_performed}, 成功: {success}, 进度: {len(completed_scenes)}/{total_scenes}"
        }
        
        if workflow_complete:
            self.logger.info(f"🎯 REFLECT: 任务完成 - 处理了 {len(completed_scenes)}/{total_scenes} 个场景")
        else:
            self.logger.info(f"🎯 REFLECT: 继续下一场景 {next_scene_index + 1}/{total_scenes}")
        
        return reflection
    
    # ReActAgent兼容性方法
    async def _think_and_plan(
        self, 
        current_state: Dict[str, Any], 
        task: Task, 
        execution: AgentExecution,
        iteration: int
    ) -> Dict[str, Any]:
        """ReActAgent要求的统一思考和规划方法（兼容性实现）"""
        
        # 合并新架构的think和plan步骤
        reasoning = await self._think_and_reason(current_state, current_state)
        action_plan = await self._plan_next_action(reasoning, current_state)
        
        return action_plan
"""
DEPRECATION NOTICE (archived)
Legacy experimental module archived. Do not import in production.
"""
import warnings as _warnings
raise ImportError(
    "Archived legacy module 'image_generator_old_react'. Do not import in production."
)
