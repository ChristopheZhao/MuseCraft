"""
Orchestrator Agent - Coordinates the entire video generation workflow
现在使用WorkflowState内存管理，避免数据库中断问题
"""
import asyncio
import os
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
from .tools.tool_registry import get_tool_registry
from ..core.config import settings


class OrchestratorAgent(BaseAgent):
    """
    Orchestrator Agent manages the complete video generation workflow
    by coordinating all specialized agents in the correct order
    """
    
    def __init__(self):
        import os
        from .utils.llm_policy import LLMPolicyManager
        policy_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'llm_policies.yaml')
        self._llm_policy = LLMPolicyManager(policy_file)
        super().__init__(
            agent_type=AgentType.ORCHESTRATOR,
            agent_name="orchestrator",
            timeout_seconds=getattr(settings, 'ORCHESTRATOR_TIMEOUT_SECONDS', 1800),
            max_retries=1,
            llms=self._llm_policy.build_llms_for_agent('orchestrator')
        )
        
        # Initialize all specialized agents
        self.agents = {
            AgentType.CONCEPT_PLANNER: ConceptPlannerAgent(llms=self._llm_policy.build_llms_for_agent('concept_planner')),
            AgentType.SCRIPT_WRITER: ScriptWriterAgent(llms=self._llm_policy.build_llms_for_agent('script_writer')),
            AgentType.IMAGE_GENERATOR: ImageGeneratorAgent(llms=self._llm_policy.build_llms_for_agent('image_generator')),
            AgentType.VIDEO_GENERATOR: VideoGeneratorAgent(llms=self._llm_policy.build_llms_for_agent('video_generator')),
            AgentType.AUDIO_GENERATOR: AudioGeneratorAgent(llms=self._llm_policy.build_llms_for_agent('audio_generator')),
            AgentType.VIDEO_COMPOSER: VideoComposerAgent(llms=self._llm_policy.build_llms_for_agent('video_composer')),
            AgentType.QUALITY_CHECKER: QualityCheckerAgent(llms=self._llm_policy.build_llms_for_agent('quality_checker'))
        }

        # Per-step repeat counters for policy decisions
        self._step_repeat_counts: Dict[AgentType, int] = {}

        # 打印每个Agent的LLM注入摘要，便于排查：role -> provider/model
        try:
            for atype, agent in self.agents.items():
                roles = {}
                llms = getattr(agent, "_llms", {}) or {}
                for role, handle in llms.items():
                    try:
                        provider = getattr(handle._service, 'get_provider_name', lambda: 'unknown')()
                        model = getattr(handle, '_model', None) or 'default'
                        roles[role] = f"{provider}/{model}"
                    except Exception:
                        roles[role] = "unknown"
                self.logger.info(f"LLM injected for {atype.value}: {roles}")
        except Exception:
            pass
        
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
        
        # 创建WorkflowState对象 - MAS智能风格决策
        workflow_state = workflow_manager.create_workflow(
            user_prompt=input_data.get("user_prompt", ""),
            style_preference=input_data.get("style_preference"),
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

                    # Orchestrator policy-first decision; LLM provides optional advice
                    try:
                        # Policy decision based on subtask_state + repeat budget
                        policy_decision = None
                        st = (agent_output.get("subtask_state") or "").strip().lower() if isinstance(agent_output, dict) else ""
                        summary = agent_output.get("summary") if isinstance(agent_output, dict) else {}
                        pending_cnt = 0
                        try:
                            pending_cnt = int(summary.get("pending") or 0) if isinstance(summary, dict) else 0
                        except Exception:
                            pending_cnt = 0
                        max_repeat = getattr(settings, 'ORCHESTRATOR_MAX_REPEAT_PER_STEP', 1)
                        cnt = self._step_repeat_counts.get(agent_type, 0)
                        if st == "complete":
                            policy_decision = "proceed_next"
                        elif st in ("partial", "blocked"):
                            policy_decision = "repeat_agent" if (cnt < max_repeat and pending_cnt > 0) else "proceed_next"
                        elif st == "max_iter_reached":
                            policy_decision = "proceed_next"
                        elif st == "error":
                            policy_decision = "repeat_agent" if (cnt < max_repeat) else "halt_workflow"

                        # If not determinable from policy, ask LLM; otherwise prefer policy
                        decision = policy_decision or await self._decide_next_step_llm(
                            current_agent=agent_type,
                            agent_output=agent_output,
                            workflow_state=workflow_state
                        )
                        if decision == "repeat_agent":
                            self.logger.info(f"🔁 Orchestrator LLM decided to repeat {agent.agent_name}")
                            # Repeat with limit
                            if cnt < max_repeat:
                                self._step_repeat_counts[agent_type] = cnt + 1
                                agent_output = await agent.execute(
                                    task=task,
                                    input_data=agent_input,
                                    db=db,
                                    execution_order=step_index + 1
                                )
                                workflow_results[agent_type.value] = agent_output
                                workflow_data.update(agent_output)
                            else:
                                self.logger.warning(f"⚠️ Repeat limit reached for {agent.agent_name} (max={max_repeat}); proceeding to next step")
                        elif decision == "halt_workflow":
                            raise AgentError("Workflow halted by orchestrator LLM decision")
                        else:
                            self.logger.info(f"➡️ Orchestrator LLM decided to proceed to next step")
                    except Exception as ce:
                        # If LLM decision fails, proceed sequentially
                        self.logger.warning(f"⚠️ Orchestrator decision failed: {ce}. Proceeding sequentially.")
                    
                    # Handoff final results to WF (only when agent reports completion via final_* fields)
                    try:
                        finals = agent_output.get("final_completed_scenes") if isinstance(agent_output, dict) else None
                        if finals and isinstance(finals, list):
                            wf_id = workflow_state.task_id
                            wf = workflow_manager.get_workflow(wf_id)
                            committed = 0
                            for rec in finals:
                                if not isinstance(rec, dict):
                                    continue
                                sn = rec.get("scene_number")
                                if sn is None:
                                    continue
                                # 支持图像或视频两类产物
                                iu = rec.get("image_url") or ""
                                ip = rec.get("image_path") or ""
                                vu = rec.get("video_url") or ""
                                vp = rec.get("video_path") or ""
                                pt = rec.get("prompt_text") or ""
                                try:
                                    if iu or ip:
                                        wf.update_scene(int(sn), image_url=iu, image_path=ip, image_prompt=pt)
                                        committed += 1
                                    if vu or vp:
                                        wf.update_scene(int(sn), video_url=vu, video_path=vp, video_prompt=pt)
                                        committed += 1
                                except Exception:
                                    continue
                            self.logger.info(f"WF_COMMIT: agent={agent.agent_name} scenes={len(finals)} committed={committed}")
                    except Exception as _wf_err:
                        self.logger.warning(f"WF_COMMIT_WARN: {str(_wf_err)}")

                    # Handle memory storage if this agent produced memory data
                    if agent_type == AgentType.CONCEPT_PLANNER:
                        self.logger.info("🧠 DEBUG: About to store creative guidance from ConceptPlanner")
                        await self._store_creative_guidance_from_output(agent_output)
                        
                        # 🔧 修复：设置concept_plan到workflow_state
                        if "concept_plan" in agent_output:
                            workflow_state.concept_plan = agent_output["concept_plan"]
                            self.logger.info("🎭 设置concept_plan到workflow_state")
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
                        
                        # 🔧 修复：在重试成功后也设置concept_plan
                        if agent_type == AgentType.CONCEPT_PLANNER and "concept_plan" in agent_output:
                            workflow_state.concept_plan = agent_output["concept_plan"]
                            self.logger.info("🎭 重试后设置concept_plan到workflow_state")
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

    async def _decide_next_step_llm(self, current_agent: AgentType, agent_output: Dict[str, Any], workflow_state: WorkflowState) -> str:
        """Use a lightweight LLM + orchestrator_control tool to decide next step.
        Returns: 'proceed_next' | 'repeat_agent' | 'halt_workflow'
        """
        # Build observation (concise)
        summary = agent_output.get("summary") or {}
        meta = agent_output.get("react_metadata") or {}
        gen_results = agent_output.get("generation_results") or []
        success_count = sum(1 for r in gen_results if isinstance(r, dict) and r.get("success"))
        fail_count = sum(1 for r in gen_results if isinstance(r, dict) and not r.get("success"))

        # 使用模板生成系统指令（保持中立，不暴露工具/参数名）
        # 使用统一提示体系：优先读取 YAML 中 orchestrator 的系统指令；如不可用则回退到简短中立文案
        # Render decision prompts from templates
        pm = self.prompt_manager
        try:
            agent_sys = self.get_system_instructions() or {}
            pr = agent_sys.get("primary_role") or "工作流编排器"
        except Exception:
            pr = "工作流编排器"
        sys_content = pm.render_template(
            "agents/orchestrator",
            "decision_system",
            variables={"primary_role": pr},
            use_cache=True,
            auto_reload=False,
        )
        import json as _json
        user_content = pm.render_template(
            "agents/orchestrator",
            "decision_user",
            variables={
                "agent_name": current_agent.value,
                "meta_json": _json.dumps(meta, ensure_ascii=False),
                "summary_json": _json.dumps(summary, ensure_ascii=False),
                "success_count": success_count,
                "fail_count": fail_count,
            },
            use_cache=True,
            auto_reload=False,
        )
        sys_msg = {"role": "system", "content": sys_content}
        user_msg = {"role": "user", "content": user_content}

        # Use a light model for orchestration
        model_name = getattr(settings, 'ORCHESTRATOR_DECISION_MODEL', 'glm-4.5-air')
        result = await self.llm_function_call(
            messages=[sys_msg, user_msg],
            context_description="Workflow step decision",
            model=model_name,
            temperature=0.2
        )

        if result.get("approach") == "function_call_plan" and result.get("tool_calls"):
            exec_res = await self.execute_tool_calls(result["tool_calls"])  # 执行控制动作
            for call in exec_res:
                tool_name = call.get("tool") or ""
                if tool_name == "orchestrator_control_repeat_agent" and call.get("success"):
                    return "repeat_agent"
                if tool_name == "orchestrator_control_halt_workflow" and call.get("success"):
                    return "halt_workflow"
                if tool_name == "orchestrator_control_proceed_next" and call.get("success"):
                    return "proceed_next"
        # 无工具可用：尝试解析严格 JSON 文本决策
        if result.get("approach") == "text_response":
            try:
                content = (result.get("content") or "").strip()
                import json as _json
                data = _json.loads(content) if content else {}
                decision = str(data.get("decision") or "").strip()
                rationale = str(data.get("rationale") or "").strip()
                subtask_state = str(data.get("subtask_state") or "").strip()
                loop_end_reason = str(data.get("loop_end_reason") or "").strip()
                # 记录一次可观测诊断，但不影响决策落地
                try:
                    self.logger.info(
                        f"ORCH_DECISION_JSON: decision={decision} state={subtask_state} reason={loop_end_reason} rationale={rationale[:120]}"
                    )
                except Exception:
                    pass
                if decision in ("repeat_agent", "proceed_next", "halt_workflow"):
                    return decision
            except Exception:
                # 解析失败走默认
                pass
        # Default fallback: proceed
        return "proceed_next"
    
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

    def _is_image_step_completed(self, agent_output: Dict[str, Any]) -> bool:
        """Gate condition for image generation step completion."""
        meta = agent_output.get("react_metadata") or {}
        if isinstance(meta, dict) and meta.get("completion_type") == "task_complete":
            return True
        summary = agent_output.get("summary") or {}
        if isinstance(summary, dict) and int(summary.get("generated_successfully", 0)) > 0:
            return True
        results = agent_output.get("generation_results") or []
        if isinstance(results, list) and any(bool(r.get("success")) for r in results if isinstance(r, dict)):
            return True
        self.logger.warning("Image step not completed: no task_complete and no successful results")
        return False

    def _is_video_step_completed(self, agent_output: Dict[str, Any]) -> bool:
        """Gate condition for video generation step completion."""
        meta = agent_output.get("react_metadata") or {}
        if isinstance(meta, dict) and meta.get("completion_type") == "task_complete":
            return True
        summary = agent_output.get("summary") or {}
        if isinstance(summary, dict) and int(summary.get("generated_successfully", 0)) > 0:
            return True
        results = agent_output.get("generation_results") or []
        if isinstance(results, list) and any(bool(r.get("success")) for r in results if isinstance(r, dict)):
            return True
        self.logger.warning("Video step not completed: no task_complete and no successful results")
        return False
    
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
