"""
Orchestrator Agent - Coordinates the entire video generation workflow
现在使用WorkflowState内存管理，避免数据库中断问题
"""
import asyncio
import logging
from typing import Dict, Any, List
from sqlalchemy.orm import Session

from .base import BaseAgent, AgentError
from ..models import Task, AgentExecution, TaskStatus, AgentType
from ..core.workflow_state import WorkflowState, WorkflowStatus, workflow_manager
from ..services.data_persistence import data_persistence_service
from ..services.global_memory_service import global_memory_service
from .concept_planner import ConceptPlannerAgent
from .script_writer import ScriptWriterAgent
from .image_generator import ImageGeneratorAgent
from .video_generator import VideoGeneratorAgent
from .audio_generator import AudioGeneratorAgent
from .video_composer import VideoComposerAgent
from .quality_checker import QualityCheckerAgent


class OrchestratorAgent(BaseAgent):
    """
    Orchestrator Agent manages the complete video generation workflow
    by coordinating all specialized agents in the correct order
    """
    
    def __init__(self):
        super().__init__(
            agent_type=AgentType.ORCHESTRATOR,
            agent_name="orchestrator",
            timeout_seconds=1800,  # 30 minutes total workflow timeout
            max_retries=1
        )
        
        # Initialize all specialized agents
        self.agents = {
            AgentType.CONCEPT_PLANNER: ConceptPlannerAgent(),
            AgentType.SCRIPT_WRITER: ScriptWriterAgent(),
            AgentType.IMAGE_GENERATOR: ImageGeneratorAgent(),
            AgentType.VIDEO_GENERATOR: VideoGeneratorAgent(),
            AgentType.AUDIO_GENERATOR: AudioGeneratorAgent(),
            AgentType.VIDEO_COMPOSER: VideoComposerAgent(),
            AgentType.QUALITY_CHECKER: QualityCheckerAgent()
        }
        
        # Define workflow execution order
        self.workflow_order = [
            AgentType.CONCEPT_PLANNER,
            AgentType.SCRIPT_WRITER,
            AgentType.IMAGE_GENERATOR,
            AgentType.VIDEO_GENERATOR,
            AgentType.VIDEO_COMPOSER,  # 视频合成：拼接场景视频
            AgentType.AUDIO_GENERATOR,  # 音频生成：基于完整视频生成匹配音乐
            AgentType.QUALITY_CHECKER
        ]
    
    async def _execute_impl(
        self, 
        task: Task, 
        input_data: Dict[str, Any], 
        execution: AgentExecution,
        db: Session
    ) -> Dict[str, Any]:
        """Execute the complete video generation workflow using WorkflowState"""
        
        self._current_task = task
        
        # 创建WorkflowState对象
        workflow_state = workflow_manager.create_workflow(
            user_prompt=input_data.get("user_prompt", ""),
            video_style=input_data.get("video_style", "professional"),
            duration=input_data.get("duration", 30),
            aspect_ratio=input_data.get("aspect_ratio", "16:9")
        )
        
        self.logger.info(f"🚀 开始工作流执行，WorkflowState ID: {workflow_state.task_id}")
        
        # Update task status
        task.status = TaskStatus.IN_PROGRESS
        task.update_progress("Starting workflow", 0)
        workflow_state.set_status(WorkflowStatus.INITIALIZING, "Starting workflow", 0)
        db.commit()
        
        workflow_data = input_data.copy()
        # 不能直接传递 WorkflowState 对象，因为它不能JSON序列化
        # 将 workflow_state_id 传递给 Agent，Agent内部通过 workflow_manager 获取状态
        workflow_data["workflow_state_id"] = workflow_state.task_id
        workflow_results = {}
        
        total_steps = len(self.workflow_order)
        
        try:
            for step_index, agent_type in enumerate(self.workflow_order):
                agent = self.agents[agent_type]
                
                # Update progress
                progress_percentage = int((step_index / total_steps) * 90)  # 为持久化预留10%
                current_step = f"Executing {agent.agent_name}"
                
                await self._update_progress(
                    execution, 
                    progress_percentage, 
                    current_step,
                    db
                )
                
                # Update task and workflow state progress
                task.update_progress(current_step, progress_percentage)
                workflow_state.set_status(
                    self._get_workflow_status_for_agent(agent_type),
                    current_step,
                    progress_percentage
                )
                db.commit()
                
                self.logger.info(f"Starting workflow step {step_index + 1}/{total_steps}: {agent.agent_name}")
                
                try:
                    # Prepare agent input with creative context (if available)
                    self.logger.info(f"🧠 DEBUG: Preparing context for {agent_type.value}")
                    agent_input = await self._prepare_agent_context(workflow_data, agent_type, workflow_state.task_id)
                    
                    # Debug: Check if context contains creative guidance
                    if agent_type in [AgentType.IMAGE_GENERATOR, AgentType.VIDEO_GENERATOR]:
                        has_creative_guidance = "creative_guidance" in agent_input
                        scene_guidances_count = len(agent_input.get("scene_guidances", {}))
                        self.logger.info(f"🧠 DEBUG: {agent_type.value} context - creative_guidance: {has_creative_guidance}, scene_guidances: {scene_guidances_count}")
                    
                    # Execute the agent (now purely stateless)
                    agent_output = await agent.execute(
                        task=task,
                        input_data=agent_input,
                        db=db,
                        execution_order=step_index + 1
                    )
                    
                    # Store results and prepare input for next agent
                    workflow_results[agent_type.value] = agent_output
                    workflow_data.update(agent_output)
                    
                    # Handle memory storage if this agent produced memory data
                    if agent_type == AgentType.CONCEPT_PLANNER:
                        self.logger.info("🧠 DEBUG: About to store creative guidance from ConceptPlanner")
                        await self._store_creative_guidance_from_output(agent_output)
                    else:
                        self.logger.info(f"🧠 DEBUG: No memory storage needed for {agent_type.value}")
                    
                    self.logger.info(f"Completed workflow step {step_index + 1}/{total_steps}: {agent.agent_name}")
                    
                except Exception as e:
                    error_msg = f"Workflow failed at step {step_index + 1} ({agent.agent_name}): {str(e)}"
                    self.logger.error(error_msg)
                    
                    # Check if we should retry the failed step
                    if await self._should_retry_step(agent_type, e, db):
                        self.logger.info(f"Retrying step {step_index + 1}: {agent.agent_name}")
                        # Retry the step
                        agent_input = await self._prepare_agent_context(workflow_data, agent_type, workflow_state.task_id)
                        agent_output = await agent.execute(
                            task=task,
                            input_data=agent_input,
                            db=db,
                            execution_order=step_index + 1
                        )
                        workflow_results[agent_type.value] = agent_output
                        workflow_data.update(agent_output)
                    else:
                        # Mark task as failed
                        task.status = TaskStatus.FAILED
                        task.add_error(error_msg)
                        db.commit()
                        raise AgentError(error_msg) from e
            
            # Workflow completed successfully
            await self._update_progress(execution, 90, "Workflow completed, persisting data", db)
            workflow_state.set_status(WorkflowStatus.PERSISTING_DATA, "Persisting data to database", 90)
            
            # 使用DataPersistenceService统一持久化数据
            self.logger.info("💾 开始持久化工作流数据到数据库...")
            persistence_result = await data_persistence_service.persist_workflow_results(workflow_state, db)
            
            if persistence_result["status"] == "success":
                # Update task status
                task.status = TaskStatus.COMPLETED
                task.update_progress("Completed", 100)
                workflow_state.set_status(WorkflowStatus.COMPLETED, "Workflow completed", 100)
                
                self.logger.info(f"✅ 工作流和数据持久化完成: {persistence_result}")
            else:
                # 持久化失败，但工作流本身成功了
                task.status = TaskStatus.COMPLETED  # 仍然标记为完成
                task.add_error(f"数据持久化部分失败: {persistence_result.get('error', '')}")
                workflow_state.add_warning("数据持久化部分失败，但工作流成功完成")
                
                self.logger.warning(f"⚠️ 工作流成功但持久化失败: {persistence_result}")
            
            db.commit()
            
            # Send final WebSocket notification
            await self._send_workflow_completion(task, workflow_results)
            
            self.logger.info(f"🎉 工作流完成，任务ID: {task.task_id}")
            
            return {
                "workflow_status": "completed",
                "total_steps": total_steps,
                "results": workflow_results,
                "final_video_url": workflow_results.get("video_composer", {}).get("final_video_url"),
                "quality_score": workflow_results.get("quality_checker", {}).get("quality_score"),
                "persistence_status": persistence_result["status"],
                "workflow_state_id": workflow_state.task_id
            }
            
        except Exception as e:
            # Workflow failed
            error_msg = f"Workflow failed: {str(e)}"
            
            # 记录错误到WorkflowState
            workflow_state.add_error(error_msg)
            workflow_state.set_status(WorkflowStatus.FAILED, error_msg, workflow_state.progress_percentage)
            
            # 尝试持久化失败状态（尽力而为）
            try:
                await data_persistence_service.persist_workflow_results(workflow_state, db)
                self.logger.info("❌ 工作流失败状态已持久化")
            except Exception as persist_error:
                self.logger.error(f"❌❌ 连持久化失败状态都失败了: {str(persist_error)}")
            
            task.status = TaskStatus.FAILED
            task.add_error(error_msg)
            db.commit()
            
            await self._send_workflow_failure(task, error_msg)
            
            raise AgentError(error_msg) from e
    
    def _get_workflow_status_for_agent(self, agent_type: AgentType) -> WorkflowStatus:
        """根据Agent类型获取对应的WorkflowStatus"""
        status_mapping = {
            AgentType.CONCEPT_PLANNER: WorkflowStatus.CONCEPT_PLANNING,
            AgentType.SCRIPT_WRITER: WorkflowStatus.SCRIPT_WRITING,
            AgentType.IMAGE_GENERATOR: WorkflowStatus.IMAGE_GENERATING,
            AgentType.VIDEO_GENERATOR: WorkflowStatus.VIDEO_GENERATING,
            AgentType.VIDEO_COMPOSER: WorkflowStatus.VIDEO_COMPOSING,
            AgentType.QUALITY_CHECKER: WorkflowStatus.QUALITY_CHECKING
        }
        return status_mapping.get(agent_type, WorkflowStatus.INITIALIZING)
    
    async def _should_retry_step(
        self, 
        agent_type: AgentType, 
        error: Exception, 
        db: Session
    ) -> bool:
        """Determine if a failed workflow step should be retried"""
        
        # Get the latest execution for this agent type
        latest_execution = db.query(AgentExecution).filter(
            AgentExecution.task_id == self._current_task.id,
            AgentExecution.agent_type == agent_type
        ).order_by(AgentExecution.created_at.desc()).first()
        
        if not latest_execution or not latest_execution.can_retry:
            return False
        
        # Define retry logic based on error type and agent type
        retry_conditions = {
            AgentType.IMAGE_GENERATOR: ["timeout", "api_rate_limit", "temporary_service_error"],
            AgentType.VIDEO_GENERATOR: ["timeout", "api_rate_limit", "temporary_service_error"],
            AgentType.VIDEO_COMPOSER: ["processing_error", "temporary_file_error"],
        }
        
        error_type = type(error).__name__.lower()
        
        if agent_type in retry_conditions:
            return any(condition in error_type for condition in retry_conditions[agent_type])
        
        # Default: retry on timeout and temporary errors
        return "timeout" in error_type or "temporary" in error_type
    
    async def _send_workflow_completion(self, task: Task, results: Dict[str, Any]):
        """Send workflow completion notification via WebSocket"""
        try:
            message = {
                "type": "workflow_completed",
                "task_id": str(task.task_id),
                "status": "completed",
                "results": results,
                "timestamp": int(asyncio.get_event_loop().time())
            }
            
            await self.websocket_manager.broadcast_to_task(
                str(task.task_id),
                message
            )
        except Exception as e:
            self.logger.warning(f"Failed to send workflow completion notification: {e}")
    
    async def _send_workflow_failure(self, task: Task, error_message: str):
        """Send workflow failure notification via WebSocket"""
        try:
            message = {
                "type": "workflow_failed",
                "task_id": str(task.task_id),
                "status": "failed", 
                "error": error_message,
                "timestamp": int(asyncio.get_event_loop().time())
            }
            
            await self.websocket_manager.broadcast_to_task(
                str(task.task_id),
                message
            )
        except Exception as e:
            self.logger.warning(f"Failed to send workflow failure notification: {e}")
    
    def get_workflow_status(self, task: Task, db: Session) -> Dict[str, Any]:
        """Get current workflow status and progress"""
        
        executions = db.query(AgentExecution).filter(
            AgentExecution.task_id == task.id
        ).order_by(AgentExecution.execution_order).all()
        
        workflow_status = {
            "task_id": str(task.task_id),
            "overall_status": task.status.value,
            "overall_progress": task.progress_percentage,
            "current_step": task.current_step,
            "total_steps": len(self.workflow_order),
            "completed_steps": len([e for e in executions if e.is_completed]),
            "failed_steps": len([e for e in executions if e.is_failed]),
            "steps": []
        }
        
        for agent_type in self.workflow_order:
            execution = next(
                (e for e in executions if e.agent_type == agent_type), 
                None
            )
            
            step_info = {
                "agent_type": agent_type.value,
                "status": execution.status.value if execution else "pending",
                "progress": execution.progress_percentage if execution else 0,
                "duration": execution.duration if execution else None,
                "error": execution.error_message if execution and execution.is_failed else None
            }
            
            workflow_status["steps"].append(step_info)
        
        return workflow_status
    
    async def _store_creative_guidance_from_output(self, agent_output: Dict[str, Any]):
        """从ConceptPlanner输出中存储创意指导到全局记忆"""
        
        try:
            memory_data = agent_output.get("memory_for_storage")
            if not memory_data:
                self.logger.warning("No memory data found in ConceptPlanner output")
                return
            
            success = await global_memory_service.store_creative_guidance(
                workflow_id=memory_data["workflow_id"],
                concept_plan=memory_data["concept_plan"],
                agent_name=memory_data["agent_name"]
            )
            
            if success:
                self.logger.info(f"✅ Orchestrator stored creative guidance for workflow {memory_data['workflow_id']}")
            else:
                self.logger.error(f"❌ Failed to store creative guidance for workflow {memory_data['workflow_id']}")
                
        except Exception as e:
            self.logger.error(f"❌ Orchestrator failed to handle memory storage: {e}")
    
    async def _prepare_agent_context(self, workflow_data: Dict[str, Any], agent_type: AgentType, workflow_id: str) -> Dict[str, Any]:
        """为Agent准备包含创意指导的上下文数据"""
        
        try:
            # 复制基础工作流数据
            agent_input = workflow_data.copy()
            
            # 如果是需要创意指导的Agent，从记忆服务获取并添加到上下文
            if agent_type in [AgentType.IMAGE_GENERATOR, AgentType.VIDEO_GENERATOR]:
                
                # 获取整体创意指导
                overall_guidance = await global_memory_service.retrieve_creative_guidance(
                    workflow_id=workflow_id,
                    agent_name=f"orchestrator_for_{agent_type.value}"
                )
                
                if overall_guidance.get("has_guidance"):
                    agent_input["creative_guidance"] = overall_guidance.get("overall_guidance", {})
                    
                    # 为所有场景准备指导数据
                    scene_guidances = {}
                    concept_plan = workflow_data.get("concept_plan", {})
                    scenes = concept_plan.get("scenes", [])
                    
                    for scene in scenes:
                        scene_number = scene.get("scene_number")
                        if scene_number:
                            scene_guidance = await global_memory_service.retrieve_creative_guidance(
                                workflow_id=workflow_id,
                                scene_number=scene_number,
                                agent_name=f"orchestrator_for_{agent_type.value}"
                            )
                            
                            if scene_guidance.get("has_guidance"):
                                scene_guidances[f"scene_{scene_number}"] = scene_guidance.get("scene_guidance", {})
                    
                    agent_input["scene_guidances"] = scene_guidances
                    
                    self.logger.info(f"🧠 Orchestrator prepared creative context for {agent_type.value} with {len(scene_guidances)} scene guidances")
                else:
                    self.logger.warning(f"⚠️ No creative guidance available for {agent_type.value}")
            
            return agent_input
            
        except Exception as e:
            self.logger.error(f"❌ Failed to prepare agent context for {agent_type.value}: {e}")
            # 返回原始数据，不阻塞workflow
            return workflow_data