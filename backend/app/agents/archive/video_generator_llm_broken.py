"""
Video Generator Agent - LLM驱动的智能视频生成
移除所有硬编码，让LLM通过Function Call自主决策
"""
import asyncio
import json
from typing import Dict, Any, List
from sqlalchemy.orm import Session

from .react_agent import ReActAgent, AgentError
from ..models import Task, AgentExecution, AgentType
from ..core.workflow_state import WorkflowState, SceneData


class VideoGeneratorAgent(ReActAgent):
    """
    Video Generator Agent - 真正的LLM驱动视频生成
    让LLM自主观察、分析、决策和反思，Agent不做任何硬编码规划
    """
    
    def __init__(self):
        super().__init__(
            agent_type=AgentType.VIDEO_GENERATOR,
            agent_name="video_generator",
            timeout_seconds=1800,
            max_retries=3,
            # 使用自动工具分配
            tools=None
        )

    async def _observe_current_state(self, input_data: Dict[str, Any], context: Dict[str, Any], iteration: int) -> Dict[str, Any]:
        """OBSERVE: 让LLM观察场景状态，不做硬编码分析"""
        
        # 获取workflow_state
        workflow_state_id = input_data.get("workflow_state_id")
        from ..core.workflow_state import workflow_manager
        workflow_state = workflow_manager.get_workflow(workflow_state_id) if workflow_state_id else None
        
        if not workflow_state:
            return {"error": "No workflow state available", "scenes": []}
        
        scenes = getattr(workflow_state, 'scenes', [])
        if not scenes:
            return {"error": "No scenes available", "scenes": []}
        
        # 构建场景状态描述，让LLM分析
        scene_states = []
        for scene in scenes:
            scene_state = {
                "scene_number": scene.scene_number,
                "title": scene.title,
                "duration": scene.duration,
                "narrative_description": scene.narrative_description,
                "has_script": bool(scene.script_text),
                "has_image": bool(scene.image_path or scene.image_url),
                "has_video": bool(scene.video_path or scene.video_url),
                "first_frame_available": bool(scene.first_frame_path),
                "visual_description": getattr(scene, 'visual_description', ''),
                "status": "completed" if (scene.video_path or scene.video_url) else "pending"
            }
            scene_states.append(scene_state)
        
        return {
            "total_scenes": len(scenes),
            "scene_states": scene_states,
            "iteration": iteration,
            "context_notes": "分析场景依赖关系、生成状态和优先级，制定智能生成策略"
        }

    async def _think_and_plan(self, current_state: Dict[str, Any], task: Task, execution: AgentExecution, iteration: int) -> Dict[str, Any]:
        """THINK & PLAN: 让LLM分析状态并制定策略，不硬编码规划逻辑"""
        
        if current_state.get("error"):
            return {"action": "error", "reasoning": current_state["error"]}
        
        scene_states = current_state.get("scene_states", [])
        total_scenes = current_state.get("total_scenes", 0)
        
        # 构建LLM分析上下文
        context_messages = [
            {
                "role": "system",
                "content": f"""你是专业的视频生成策划师。分析{total_scenes}个场景的生成状态，制定最优的批量视频生成策略。

**核心能力**:
- 智能分析场景依赖关系和生成优先级
- 根据资源状态制定批量处理策略  
- 选择最适合的工具和参数组合
- 优化生成效率和质量

**场景状态分析**:
{json.dumps(scene_states, ensure_ascii=False, indent=2)}

**你的任务**:
1. 分析哪些场景可以并行生成，哪些需要等待依赖
2. 根据场景复杂度和内容特点选择生成策略
3. 决定使用什么工具和参数来执行
4. 制定具体的执行计划

请基于分析结果制定策略，不要使用预设的固定模式。"""
            },
            {
                "role": "user", 
                "content": f"这是第{iteration}次迭代。请分析当前场景状态，制定智能的批量视频生成策略。"
            }
        ]
        
        # LLM推理和规划
        result = await self.llm_function_call(
            messages=context_messages,
            context_description=f"视频生成策略规划 - 第{iteration}次迭代",
            temperature=0.3
        )
        
        # 解析LLM的决策
        reasoning = result.get("content", "LLM智能策略分析")
        
        # 基于LLM分析确定行动
        pending_scenes = [s for s in scene_states if s["status"] == "pending"]
        
        if not pending_scenes:
            return {
                "action": "complete_generation",
                "reasoning": "所有场景视频已生成完成",
                "scenes_to_process": []
            }
        else:
            return {
                "action": "batch_generate_videos", 
                "reasoning": reasoning,
                "scenes_to_process": pending_scenes[:5],  # 批量处理，但不超过5个
                "total_pending": len(pending_scenes)
            }

    async def _execute_action(self, action_plan: Dict[str, Any], input_data: Dict[str, Any], execution: AgentExecution, db: Session, iteration: int) -> Dict[str, Any]:
        """ACT: 执行LLM规划的行动，通过Function Call调用工具"""
        
        action = action_plan.get("action")
        
        if action == "complete_generation":
            return {
                "success": True,
                "action_performed": "complete_generation",
                "message": "所有视频生成已完成",
                "videos_generated": 0
            }
        
        if action == "batch_generate_videos":
            return await self._execute_llm_driven_generation(action_plan, input_data)
        
        return {
            "success": False,
            "action_performed": "unknown",
            "error": f"未知行动类型: {action}"
        }

    async def _execute_llm_driven_generation(self, action_plan: Dict[str, Any], input_data: Dict[str, Any]) -> Dict[str, Any]:
        """执行LLM驱动的视频生成，让工具自主优化参数"""
        
        scenes_to_process = action_plan.get("scenes_to_process", [])
        if not scenes_to_process:
            return {"success": True, "videos_generated": 0, "message": "无场景需要处理"}
        
        # 获取workflow_state
        workflow_state_id = input_data.get("workflow_state_id")
        from ..core.workflow_state import workflow_manager
        workflow_state = workflow_manager.get_workflow(workflow_state_id) if workflow_state_id else None
        
        try:
            self.logger.info(f"🎬 开始LLM驱动的批量视频生成: {len(scenes_to_process)}个场景")
            
            # 让LLM选择工具和参数，不硬编码
            generation_requests = []
            for scene_info in scenes_to_process:
                generation_requests.append({
                    "scene_number": scene_info["scene_number"],
                    "scene_description": {
                        "title": scene_info["title"],
                        "narrative": scene_info["narrative_description"], 
                        "visual_description": scene_info.get("visual_description", ""),
                        "duration": scene_info["duration"],
                        "has_first_frame": scene_info["first_frame_available"]
                    }
                })
            
            # Function Call: 让工具自主处理参数优化和生成
            generation_result = await self.use_tool(
                "video_generation",
                "batch_generate_videos",
                {
                    "generation_requests": generation_requests,
                    "generation_mode": "llm_optimized",  # 让工具使用LLM优化
                    "workflow_state_id": workflow_state_id,
                    "quality_priority": "balanced"  # 平衡质量和效率
                }
            )
            
            # 更新workflow_state (工具应该已经处理了大部分更新)
            generated_count = 0
            if generation_result and generation_result.get("success"):
                generated_videos = generation_result.get("generated_videos", {})
                
                for scene_info in scenes_to_process:
                    scene_video = generated_videos.get(str(scene_info["scene_number"]))
                    if scene_video and scene_video.get("video_path"):
                        workflow_state.update_scene(
                            scene_info["scene_number"],
                            video_path=scene_video["video_path"],
                            video_url=scene_video.get("video_url", "")
                        )
                        generated_count += 1
            
            return {
                "success": True,
                "action_performed": "batch_generate_videos",
                "videos_generated": generated_count,
                "generation_result": generation_result,
                "total_requested": len(scenes_to_process)
            }
            
        except Exception as e:
            self.logger.error(f"LLM驱动视频生成失败: {str(e)}")
            return {
                "success": False,
                "action_performed": "batch_generate_videos", 
                "error": str(e),
                "videos_generated": 0
            }

    async def _reflect_on_results(self, action_result: Dict[str, Any], current_state: Dict[str, Any], task: Task, iteration: int) -> Dict[str, Any]:
        """REFLECT: 让LLM反思结果，决定是否继续迭代"""
        
        action_performed = action_result.get("action_performed", "")
        
        if action_performed == "complete_generation":
            return {
                "continue_iteration": False,
                "reasoning": "所有视频生成已完成",
                "workflow_complete": True
            }
        
        if not action_result.get("success", False):
            return {
                "continue_iteration": True,
                "reasoning": f"生成失败，需要重试: {action_result.get('error', 'Unknown error')}",
                "workflow_complete": False
            }
        
        videos_generated = action_result.get("videos_generated", 0)
        total_scenes = current_state.get("total_scenes", 0)
        
        # 让LLM分析完成度和下一步策略
        context_messages = [
            {
                "role": "system",
                "content": f"""分析当前视频生成进展，决定是否继续迭代。

**当前状态**:
- 总场景数: {total_scenes}
- 本次生成: {videos_generated}个视频
- 迭代次数: {iteration}

**判断标准**:
1. 如果还有场景需要生成且迭代次数合理，继续迭代
2. 如果生成成功率低，分析原因并调整策略
3. 如果大部分场景完成，可以结束迭代

请基于实际情况做出智能判断。"""
            },
            {
                "role": "user",
                "content": f"本次生成了{videos_generated}个视频。请判断是否需要继续迭代？"
            }
        ]
        
        # LLM反思和决策
        result = await self.llm_function_call(
            messages=context_messages,
            context_description="视频生成进展反思",
            temperature=0.2
        )
        
        reasoning = result.get("content", f"生成{videos_generated}个视频，继续处理剩余场景")
        
        # 基于生成率和迭代次数智能决策
        if videos_generated == 0 and iteration >= 3:
            return {
                "continue_iteration": False,
                "reasoning": "多次迭代无进展，停止生成", 
                "workflow_complete": False
            }
        elif videos_generated > 0:
            return {
                "continue_iteration": True,
                "reasoning": reasoning,
                "workflow_complete": False
            }
        else:
            return {
                "continue_iteration": True if iteration < 5 else False,
                "reasoning": reasoning,
                "workflow_complete": iteration >= 5
            }
"""
DEPRECATION NOTICE (archived)
Broken experimental module archived. Do not import in production.
"""
import warnings as _warnings
raise ImportError(
    "Archived legacy module 'video_generator_llm_broken'. Do not import in production."
)
