"""
Script Writer Agent - 简化版批量脚本生成
移除复杂的ReAct接口，直接实现批量处理
"""
import json
from typing import Dict, Any, List
from sqlalchemy.orm import Session

from .base import BaseAgent, AgentError
from ..models import Task, AgentExecution, AgentType, Scene
from ..core.workflow_state import WorkflowState, SceneData


class ScriptWriterAgent(BaseAgent):
    """
    Script Writer Agent - 简化版批量脚本生成
    专注于场景脚本、叙事结构和连续性分析，但使用BaseAgent接口
    """
    
    def __init__(self, llms=None):
        super().__init__(
            agent_type=AgentType.SCRIPT_WRITER,
            agent_name="script_writer",
            timeout_seconds=600,
            max_retries=2,
            tools=[
                "scene_continuity_analysis_tool",
                "script_generation_tool", 
                "narrative_structure_generation_tool"
            ],
            llms=llms
        )
        
    async def _execute_impl(
        self,
        task: Task,
        input_data: Dict[str, Any],
        execution: AgentExecution,
        db: Session
    ) -> Dict[str, Any]:
        """批量脚本生成 - 实现在 _execute_impl，使用 BaseAgent.execute 统一包装"""
        try:
            from ..core.config import settings

            # 动态超时：基于.env配置的基数、每场景增量和最大值
            scene_count = self._estimate_scene_count(input_data)
            base = getattr(settings, 'SCRIPT_WRITER_TIMEOUT_BASE', 180)
            per_scene = getattr(settings, 'SCRIPT_WRITER_TIMEOUT_PER_SCENE', 30)
            max_timeout = getattr(settings, 'SCRIPT_WRITER_TIMEOUT_MAX', 900)
            if scene_count > 0:
                dynamic_timeout = min(max_timeout, base + scene_count * per_scene)
                self.timeout_seconds = int(dynamic_timeout)

            # 获取workflow_state
            workflow_state_id = input_data.get("workflow_state_id")
            from ..core.workflow_state import workflow_manager
            workflow_state = workflow_manager.get_workflow(workflow_state_id) if workflow_state_id else None

            if not workflow_state:
                return {
                    "success": False,
                    "error": "No workflow state available",
                    "workflow_state_updated": False,
                    "results": []
                }

            # 获取场景和概念规划
            scenes = getattr(workflow_state, 'scenes', [])
            concept_plan = getattr(workflow_state, 'concept_plan', {})

            if not scenes:
                return {
                    "success": False,
                    "error": "No scenes available for script generation",
                    "workflow_state_updated": False,
                    "results": []
                }

            # 批量生成脚本
            return await self._batch_generate_scripts(scenes, concept_plan, workflow_state, task)

        except Exception as e:
            self.logger.error(f"ScriptWriter execution failed: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "workflow_state_updated": False,
                "fallback_applied": True,
                "results": []
            }

    async def _batch_generate_scripts(
        self, 
        scenes: List[SceneData], 
        concept_plan: Dict[str, Any],
        workflow_state: WorkflowState,
        task: Task
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
                "scenes_generated": 0,
                "workflow_state_updated": False
            }
        
        try:
            self.logger.info(f"开始批量生成{len(scenes_needing_scripts)}个场景脚本")
            
            # 准备批量生成参数
            batch_scenes = [
                {
                    "scene_number": scene.scene_number,
                    "title": scene.title,
                    "duration": scene.duration,
                    "narrative_description": scene.narrative_description
                } for scene in scenes_needing_scripts
            ]
            
            # 逐场景生成脚本（使用 script_generation 工具的 generate_scene_script 动作）
            scripts_map: Dict[str, Any] = {}
            intelligent_style = concept_plan.get('intelligent_style_design', {})
            for scene in scenes_needing_scripts:
                try:
                    tool_params = {
                        "scene_data": {
                            "scene_number": scene.scene_number,
                            "visual_description": scene.visual_description,
                            "narrative_description": scene.narrative_description,
                            "duration": scene.duration,
                        },
                        "intelligent_style_design": intelligent_style,
                        "context": {
                            "previous_scene": "",
                            "narrative_arc": concept_plan.get('genre_and_theme', {}).get('theme', '')
                        }
                    }
                    one = await self.use_tool(
                        "script_generation",
                        "generate_scene_script",
                        tool_params
                    )
                    payload = getattr(one, 'result', one)
                    if isinstance(payload, dict):
                        # 归一化结果
                        scripts_map[str(scene.scene_number)] = {
                            "script_text": payload.get("script_text", payload.get("content", "")),
                            "narrative_description": payload.get("narrative_description", scene.narrative_description),
                            "background_music_style": payload.get("background_music_style", ""),
                            "sound_effects": payload.get("sound_effects", [])
                        }
                except Exception as se:
                    self.logger.warning(f"场景 {scene.scene_number} 脚本生成失败: {se}")
            script_results = {"success": True, "scripts": scripts_map}
            
            # 连续性分析（可选），调用统一的 analyze_all_scenes_continuity
            try:
                cont_params = {
                    "scenes": [
                        {
                            "scene_number": s["scene_number"],
                            "title": s.get("title", ""),
                            "description": s.get("narrative_description", "") or "",
                            "script_text": scripts_map.get(str(s["scene_number"])) and scripts_map[str(s["scene_number"])].get("script_text", "") or "",
                            "narrative_description": s.get("narrative_description", "") or "",
                            "mood_and_atmosphere": ""
                        } for s in batch_scenes
                    ],
                    "overall_narrative": concept_plan.get('overview', ''),
                    "narrative_flow": concept_plan.get('genre_and_theme', {}).get('theme', ''),
                    "main_message": ":".join(concept_plan.get('key_messages', [])) if concept_plan.get('key_messages') else ""
                }
                cont_res = await self.use_tool(
                    "scene_continuity_analysis_tool",
                    "analyze_all_scenes_continuity",
                    cont_params
                )
                continuity_analysis = getattr(cont_res, 'result', cont_res)
            except Exception as e:
                self.logger.warning(f"连续性分析失败，继续脚本生成: {e}")
                continuity_analysis = {"warning": "连续性分析失败"}

            # 更新workflow_state
            generated_count = 0
            # 标准化回合结果：供编排器统计 success/failed
            generation_results: List[Dict[str, Any]] = []
            if script_results and script_results.get("success") and script_results.get("scripts"):
                for scene in scenes_needing_scripts:
                    scene_script_data = script_results["scripts"].get(str(scene.scene_number))
                    if scene_script_data:
                        workflow_state.update_scene(
                            scene.scene_number,
                            script_text=scene_script_data.get("script_text", ""),
                            voice_over_text=scene_script_data.get("script_text", ""),
                            narrative_description=scene_script_data.get("narrative_description", scene.narrative_description),
                            background_music_style=scene_script_data.get("background_music_style", ""),
                            sound_effects=scene_script_data.get("sound_effects", [])
                        )
                        generated_count += 1
                        generation_results.append({
                            "scene_number": scene.scene_number,
                            "success": True,
                            "prompt_text": scene_script_data.get("script_text", "")[:120] or "script_generated",
                        })
                    else:
                        generation_results.append({
                            "scene_number": scene.scene_number,
                            "success": False,
                            "error": "script_generation_failed_or_empty"
                        })
            else:
                # 工具层未返回结构化脚本映射时，按尝试的场景全部视为失败
                for scene in scenes_needing_scripts:
                    generation_results.append({
                        "scene_number": scene.scene_number,
                        "success": False,
                        "error": "no_scripts_map"
                    })

            # 将连续性分析结果写回到 WorkflowState.scenes（用于 Image/Video 连续性处理）
            try:
                decisions = (continuity_analysis or {}).get("continuity_decisions", {}) if isinstance(continuity_analysis, dict) else {}
                if decisions:
                    # 遍历所有场景，依据决策落地字段
                    for sc in getattr(workflow_state, 'scenes', []) or []:
                        sn = getattr(sc, 'scene_number', None)
                        if not sn:
                            continue
                        key = str(sn)
                        d = decisions.get(key)
                        if not isinstance(d, dict):
                            # 对缺失决策的场景，保持现状，不强行覆盖
                            continue
                        strategy = d.get("strategy", "new")
                        reason = d.get("reason", "")
                        try:
                            confidence = float(d.get("confidence", 0.8))
                        except Exception:
                            confidence = 0.8

                        if strategy == "continue_from_previous" and sn > 1:
                            depends = sn - 1
                            workflow_state.update_scene(
                                sn,
                                depends_on_scene=depends,
                                requires_continuity_from=depends,
                                continuity_reason=reason,
                                continuity_confidence=confidence,
                                image_generation_strategy="continue_from_previous",
                            )
                        else:
                            # 标记为独立生成；清理依赖
                            workflow_state.update_scene(
                                sn,
                                depends_on_scene=None,
                                requires_continuity_from=None,
                                continuity_reason=reason,
                                continuity_confidence=confidence,
                                image_generation_strategy="new",
                            )
                    self.logger.info("✅ 连续性决策已写回 WorkflowState.scenes")
            except Exception as ce:
                self.logger.warning(f"连续性结果写回失败：{ce}")

            self.logger.info(f"批量脚本生成完成: {generated_count}/{len(scenes_needing_scripts)}")
            
            return {
                "success": True,
                "message": f"批量生成{generated_count}个场景脚本",
                "scenes_generated": generated_count,
                "script_results": script_results,
                "continuity_analysis": continuity_analysis,
                "generation_results": generation_results,
                "workflow_state_updated": generated_count > 0,
                "total_scenes": len(scenes_needing_scripts)
            }
            
        except Exception as e:
            self.logger.error(f"批量脚本生成失败: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "scenes_generated": 0,
                "workflow_state_updated": False
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
