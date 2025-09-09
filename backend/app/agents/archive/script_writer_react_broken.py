"""
Script Writer Agent - ReAct模式批量脚本生成
重构为批量处理ReAct模式，移除循环硬编码
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
    Script Writer Agent - 批量脚本生成ReAct模式
    专注于场景脚本、叙事结构和连续性分析
    """
    
    def __init__(self):
        super().__init__(
            agent_type=AgentType.SCRIPT_WRITER,
            agent_name="script_writer",
            timeout_seconds=600,
            max_retries=2,
            tools=[
                "scene_continuity_analysis_tool",
                "script_generation_tool",
                "narrative_structure_generation_tool"
            ]
        )
        
    async def execute(
        self,
        task: Task,
        input_data: Dict[str, Any],
        db: Session,
        execution_order: int = 0
    ) -> Dict[str, Any]:
        """ReAct模式执行批量脚本生成"""
        try:
            from ..core.config import settings
            
            # 动态超时基于场景数量
            scene_count = self._estimate_scene_count(input_data)
            if scene_count > 0:
                dynamic_timeout = min(600, scene_count * 45)
                self.timeout_seconds = dynamic_timeout
            
            # 调用父类ReAct执行
            return await super().execute(task, input_data, db, execution_order)
            
        except Exception as e:
            self.logger.error(f"ScriptWriter execution failed: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "workflow_state_updated": False,
                "fallback_applied": True,
                "results": []
            }

    async def _observe_current_state(self, input_data: Dict[str, Any], iteration_context: Dict[str, Any], iteration: int) -> Dict[str, Any]:
        """观察当前脚本生成状态"""
        # 从input_data获取workflow_state
        workflow_state_id = input_data.get("workflow_state_id")
        from ..core.workflow_state import workflow_manager
        workflow_state = workflow_manager.get_workflow(workflow_state_id) if workflow_state_id else None
        
        if not workflow_state:
            return {"error": "No workflow state available", "pending_scenes": [], "completed_scenes": []}
            
        scenes = getattr(workflow_state, 'scenes', [])
        concept_plan = getattr(workflow_state, 'concept_plan', {})
        
        # 分析哪些场景需要脚本生成
        pending_scenes = []
        completed_scenes = []
        
        for scene in scenes:
            if not scene.script_text or len(scene.script_text.strip()) < 50:
                pending_scenes.append({
                    "scene_number": scene.scene_number,
                    "title": scene.title,
                    "duration": scene.duration,
                    "narrative_description": scene.narrative_description,
                    "status": "需要脚本生成"
                })
            else:
                completed_scenes.append({
                    "scene_number": scene.scene_number,
                    "title": scene.title,
                    "script_length": len(scene.script_text),
                    "status": "已完成"
                })
        
        return {
            "total_scenes": len(scenes),
            "pending_scenes": pending_scenes,
            "completed_scenes": completed_scenes,
            "concept_overview": concept_plan.get('overview', ''),
            "style_guidance": concept_plan.get('style_guidance', {}),
            "narrative_arc": concept_plan.get('narrative_arc', {})
        }

    async def _think_and_plan(self, observation: Dict[str, Any], task, execution, iteration: int) -> Dict[str, Any]:
        """分析并制定批量脚本生成策略"""
        pending_scenes = observation.get("pending_scenes", [])
        concept_overview = observation.get("concept_overview", "")
        
        if not pending_scenes:
            return {
                "strategy": "all_completed",
                "reasoning": "所有场景脚本已生成完成",
                "action_needed": False
            }
        
        # 分析批量处理策略
        context_messages = [
            {
                "role": "system", 
                "content": f"""你是专业的脚本策划师。分析{len(pending_scenes)}个场景的批量脚本生成策略。

**核心任务**: 制定高效的批量脚本生成执行计划
**场景概览**: {concept_overview}
**待处理场景**: {json.dumps(pending_scenes, ensure_ascii=False, indent=2)}

请分析:
1. 批量处理策略 (一次性生成 vs 分批处理)
2. 场景间的连续性要求
3. 叙事结构统一性
4. 工具调用优化方案"""
            },
            {
                "role": "user",
                "content": "基于场景分析，制定最优的批量脚本生成策略"
            }
        ]
        
        # LLM推理批量处理策略
        result = await self.llm_function_call(
            messages=context_messages,
            context_description=f"批量脚本生成策略规划 - {len(pending_scenes)}个场景",
            temperature=0.2
        )
        
        return {
            "strategy": "batch_script_generation",
            "reasoning": result.get("content", "批量处理可提升效率和连续性"),
            "batch_size": min(len(pending_scenes), 6),  # 最多6个场景一批
            "action_needed": True,
            "pending_count": len(pending_scenes)
        }

    async def _execute_action(self, plan: Dict[str, Any], task, execution, iteration: int) -> Dict[str, Any]:
        """执行批量脚本生成"""
        if not plan.get("action_needed", False):
            return {
                "success": True,
                "message": "无需执行脚本生成",
                "scenes_generated": 0
            }
        
        # 从task获取workflow_state
        workflow_state_id = getattr(task, 'workflow_state_id', None) 
        from ..core.workflow_state import workflow_manager
        workflow_state = workflow_manager.get_workflow(workflow_state_id) if workflow_state_id else None
        
        if not workflow_state:
            return {"success": False, "error": "No workflow state", "scenes_generated": 0}
            
        scenes = getattr(workflow_state, 'scenes', [])
        concept_plan = getattr(workflow_state, 'concept_plan', {})
        
        # 批量生成脚本
        return await self._batch_generate_scripts(scenes, concept_plan, workflow_state)

    async def _batch_generate_scripts(
        self, 
        scenes: List[SceneData], 
        concept_plan: Dict[str, Any],
        workflow_state: WorkflowState
    ) -> Dict[str, Any]:
        """批量生成场景脚本"""
        
        # 筛选需要脚本的场景
        scenes_needing_scripts = [
            scene for scene in scenes 
            if not scene.script_text or len(scene.script_text.strip()) < 50
        ]
        
        if not scenes_needing_scripts:
            return {
                "success": True,
                "message": "所有场景脚本已完成",
                "scenes_generated": 0
            }
        
        try:
            # Function Call: 批量脚本生成
            script_results = await self.use_tool(
                "script_generation_tool",
                "batch_generate_scripts",
                {
                    "scenes": [
                        {
                            "scene_number": scene.scene_number,
                            "title": scene.title,
                            "duration": scene.duration,
                            "narrative_description": scene.narrative_description
                        } for scene in scenes_needing_scripts
                    ],
                    "concept_plan": concept_plan,
                    "style_guidance": concept_plan.get('style_guidance', {}),
                    "generation_mode": "batch_optimized"
                }
            )
            
            # 并行连续性分析
            continuity_analysis = await self.use_tool(
                "scene_continuity_analysis_tool",
                "analyze_narrative_flow",
                {
                    "scenes_data": [
                        {
                            "scene_number": scene.scene_number,
                            "title": scene.title,
                            "script_preview": script_results.get("scripts", {}).get(str(scene.scene_number), {}).get("script_text", "")[:300]
                        } for scene in scenes_needing_scripts
                    ],
                    "concept_overview": concept_plan.get('overview', ''),
                    "analysis_focus": "narrative_consistency"
                }
            )
            
            # 更新workflow_state
            generated_count = 0
            if script_results.get("success") and script_results.get("scripts"):
                for scene in scenes_needing_scripts:
                    scene_script_data = script_results["scripts"].get(str(scene.scene_number))
                    if scene_script_data:
                        workflow_state.update_scene(
                            scene.scene_number,
                            script_text=scene_script_data.get("script_text", ""),
                            voice_over_text=scene_script_data.get("script_text", ""),
                            narrative_description=scene_script_data.get("narrative_description", scene.narrative_description),
                            background_music_style=scene_script_data.get("background_music_style", ""),
                            sound_effects=scene_script_data.get("sound_effects", []),
                            scene_design_elements=scene_script_data.get("scene_design_elements", {}),
                            narrative_structure=scene_script_data.get("narrative_structure", {}),
                            audio_design=scene_script_data.get("audio_design", {}),
                            pacing_and_timing=scene_script_data.get("pacing_and_timing", {})
                        )
                        generated_count += 1
            
            return {
                "success": True,
                "message": f"批量生成{generated_count}个场景脚本",
                "scenes_generated": generated_count,
                "script_results": script_results,
                "continuity_analysis": continuity_analysis,
                "total_scenes": len(scenes_needing_scripts)
            }
            
        except Exception as e:
            self.logger.error(f"批量脚本生成失败: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "scenes_generated": 0
            }

    async def _reflect_on_results(self, action_result: Dict[str, Any], task, execution, iteration: int) -> Dict[str, Any]:
        """反思脚本生成结果，决定是否继续迭代"""
        
        if not action_result.get("success", False):
            return {
                "continue_iteration": False,
                "reasoning": f"执行失败: {action_result.get('error', 'Unknown error')}",
                "workflow_complete": False
            }
        
        # 从task获取workflow_state 
        workflow_state_id = getattr(task, 'workflow_state_id', None)
        from ..core.workflow_state import workflow_manager
        workflow_state = workflow_manager.get_workflow(workflow_state_id) if workflow_state_id else None
        
        if not workflow_state:
            return {"continue_iteration": False, "reasoning": "No workflow state", "workflow_complete": False}
            
        scenes = getattr(workflow_state, 'scenes', [])
        
        # 检查完成度
        total_scenes = len(scenes)
        completed_scripts = sum(
            1 for scene in scenes 
            if scene.script_text and len(scene.script_text.strip()) >= 50
        )
        
        completion_rate = completed_scripts / total_scenes if total_scenes > 0 else 0
        
        if completion_rate >= 0.95:  # 95%以上完成
            return {
                "continue_iteration": False,
                "reasoning": f"脚本生成完成率{completion_rate:.1%}，已达到要求",
                "workflow_complete": True,
                "final_stats": {
                    "total_scenes": total_scenes,
                    "completed_scripts": completed_scripts,
                    "completion_rate": completion_rate
                }
            }
        else:
            # 检查是否有明显错误需要重新处理
            failed_scenes = [
                scene.scene_number for scene in scenes
                if not scene.script_text or len(scene.script_text.strip()) < 50
            ]
            
            return {
                "continue_iteration": True,
                "reasoning": f"还有{len(failed_scenes)}个场景脚本待完成",
                "workflow_complete": False,
                "remaining_scenes": failed_scenes
            }

    def _estimate_scene_count(self, input_data: Dict[str, Any]) -> int:
        """估算场景数量用于动态超时"""
        try:
            workflow_state_id = input_data.get("workflow_state_id")
            if workflow_state_id:
                from ..core.workflow_state import workflow_manager
                ws = workflow_manager.get_workflow(workflow_state_id)
                if ws and getattr(ws, 'scenes', None):
                    return len(ws.scenes)
            return 6  # 默认估算
        except:
            return 6

    # 向后兼容性方法
    async def _think_and_plan_action(self, workflow_state: WorkflowState) -> Dict[str, Any]:
        """兼容BaseAgent接口"""
        observation = await self._observe_current_state(workflow_state)
        return await self._think_and_plan(observation)
"""
DEPRECATION NOTICE (archived)
Broken experimental module archived. Do not import in production.
"""
import warnings as _warnings
raise ImportError(
    "Archived legacy module 'script_writer_react_broken'. Do not import in production."
)
