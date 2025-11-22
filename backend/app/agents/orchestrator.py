"""
Orchestrator Agent - Coordinates the entire video generation workflow
基于 Shared Working Memory（共享黑板）作为唯一对外事实源；取消对 WorkflowState 的依赖。
"""
import asyncio
import os
import logging
from typing import Dict, Any, List
from sqlalchemy.orm import Session

from .base import BaseAgent, AgentError
from ..models import Task, AgentExecution, TaskStatus, AgentType
from .services.mas_shared_memory import get_shared_wm
from .adapters.memory_views import build_media_agent_context, build_image_generation_context
from ..services.data_persistence import data_persistence_service, configure_data_persistence
from ..services.memory_provider import build_memory_services, MemoryServices
from .memory.short_term import get_working_memory_service
from .utils.memory_helpers import agent_scope, mas_scope, ensure_mas_memory
from .concept_planner import ConceptPlannerAgent
from .script_writer import ScriptWriterAgent
from .image_generator import ImageGeneratorAgent
from .video_generator import VideoGeneratorAgent
from .audio_generator import AudioGeneratorAgent
from .voice_synthesizer import VoiceSynthesizerAgent
from .video_composer import VideoComposerAgent
from .quality_checker import QualityCheckerAgent
from .tools.tool_registry import get_tool_registry
from ..core.config import settings


class OrchestratorAgent(BaseAgent):
    """
    Orchestrator Agent manages the complete video generation workflow
    by coordinating all specialized agents in the correct order
    """
    
    def __init__(self, memory_services: Optional[MemoryServices] = None):
        import os
        from .utils.llm_policy import LLMPolicyManager
        policy_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'llm_policies.yaml')
        self._llm_policy = LLMPolicyManager(policy_file)
        self._memory_services = memory_services or build_memory_services()
        configure_data_persistence(self._memory_services)
        super().__init__(
            agent_type=AgentType.ORCHESTRATOR,
            agent_name="orchestrator",
            timeout_seconds=getattr(settings, 'ORCHESTRATOR_TIMEOUT_SECONDS', 1800),
            max_retries=1,
            llms=self._llm_policy.build_llms_for_agent('orchestrator'),
            memory_services=self._memory_services,
        )
        
        # Initialize all specialized agents
        self.agents = {
            AgentType.CONCEPT_PLANNER: ConceptPlannerAgent(
                llms=self._llm_policy.build_llms_for_agent('concept_planner'),
                memory_services=self._memory_services,
            ),
            AgentType.SCRIPT_WRITER: ScriptWriterAgent(
                llms=self._llm_policy.build_llms_for_agent('script_writer'),
                memory_services=self._memory_services,
            ),
            AgentType.VOICE_SYNTHESIZER: VoiceSynthesizerAgent(
                llms=self._llm_policy.build_llms_for_agent('voice_synthesizer'),
                memory_services=self._memory_services,
            ),
            AgentType.IMAGE_GENERATOR: ImageGeneratorAgent(
                llms=self._llm_policy.build_llms_for_agent('image_generator'),
                memory_services=self._memory_services,
            ),
            AgentType.VIDEO_GENERATOR: VideoGeneratorAgent(
                llms=self._llm_policy.build_llms_for_agent('video_generator'),
                memory_services=self._memory_services,
            ),
            AgentType.AUDIO_GENERATOR: AudioGeneratorAgent(
                llms=self._llm_policy.build_llms_for_agent('audio_generator'),
                memory_services=self._memory_services,
            ),
            AgentType.VIDEO_COMPOSER: VideoComposerAgent(
                llms=self._llm_policy.build_llms_for_agent('video_composer'),
                memory_services=self._memory_services,
            ),
            AgentType.QUALITY_CHECKER: QualityCheckerAgent(
                llms=self._llm_policy.build_llms_for_agent('quality_checker'),
                memory_services=self._memory_services,
            ),
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
            AgentType.VOICE_SYNTHESIZER,
            AgentType.VIDEO_COMPOSER,  # 视频合成：拼接场景视频 + 后续语音混流
            AgentType.AUDIO_GENERATOR,  # 音频生成：基于完整视频生成匹配音乐
            AgentType.QUALITY_CHECKER
        ]

    def reset_repeat_counters(self) -> None:
        """Clear per-step repeat counters so retries start fresh."""
        self._step_repeat_counts = {}

    def _load_workflow_overview(self, workflow_id: str) -> Dict[str, Any]:
        try:
            value = self.fetch_memory_slot(
                workflow_id,
                "project.workflow_overview",
                default={},
                agent=self.agent_name,
            )
        except Exception as exc:
            raise AgentError(f"Failed to read workflow_overview from shared memory: {exc}") from exc
        if not isinstance(value, dict):
            return {}
        return dict(value)

    def _store_workflow_overview(self, workflow_id: str, payload: Dict[str, Any]) -> None:
        try:
            self.store_memory_slot(
                workflow_id,
                "project.workflow_overview",
                payload,
                agent=self.agent_name,
            )
        except Exception as exc:
            raise AgentError(f"Failed to write workflow_overview to shared memory: {exc}") from exc

    def _update_workflow_overview(self, workflow_id: str, updates: Dict[str, Any], *, raise_error: bool = True) -> None:
        try:
            current = self._load_workflow_overview(workflow_id)
            current.update(updates)
            self._store_workflow_overview(workflow_id, current)
        except AgentError as exc:
            if raise_error:
                raise
            self.logger.warning("Workflow overview update skipped: %s", exc)

    async def _execute_impl(
        self, 
        task: Task, 
        input_data: Dict[str, Any], 
        execution: AgentExecution,
        db: Session
    ) -> Dict[str, Any]:
        """Execute the complete video generation workflow using Shared Working Memory"""
        
        self._current_task = task
        mem_service = get_working_memory_service()
        mem_service.create_or_get(str(task.task_id), mas_scope(str(task.task_id)))
        
        # 使用 Task.task_id 作为本次工作流的 Shared WM 标识
        wf_id = str(task.task_id)
        self.logger.info(f"🚀 开始工作流执行，Workflow ID: {wf_id}")

        # Update task status + 初始化共享黑板概览
        task.status = TaskStatus.IN_PROGRESS
        task.update_progress("Starting workflow", 0)
        try:
            self.store_memory_slot(
                wf_id,
                "project.workflow_overview",
                {
                    "status": "INITIALIZING",
                    "progress": 0,
                    "current_step": "Starting workflow",
                    "step_index": 0,
                    "total_steps": len(self.workflow_order),
                },
                agent=self.agent_name,
            )
        except Exception as wm_err:
            raise AgentError(f"Failed to initialize workflow_overview in shared memory: {wm_err}") from wm_err
        db.commit()
        
        workflow_data = input_data.copy()
        workflow_data.setdefault("resolution", input_data.get("resolution") or settings.DEFAULT_VIDEO_RESOLUTION)
        workflow_data.setdefault("target_resolution", workflow_data.get("resolution"))
        # 将 workflow_state_id 传递给 Agent，Agent 从 Shared WM 读取上下文
        workflow_data["workflow_state_id"] = wf_id
        # Episode/Project 上下文直接留在 workflow_data，由 _prepare_agent_context 注入到各 Agent 输入；
        # Shared WM 作为唯一对外事实源，不再引用本地 WorkflowState 实例。

        workflow_results = {}
        
        total_steps = len(self.workflow_order)
        
        try:
            for step_index, agent_type in enumerate(self.workflow_order):
                agent = self.agents[agent_type]
                try:
                    shared_view = ensure_mas_memory(wf_id)
                    scope = agent_scope(wf_id, agent.agent_name)
                    mem_service.create_or_get(
                        wf_id,
                        scope,
                        owner_agent=agent.agent_name,
                        shared_view=shared_view,
                    )
                except Exception as mem_err:
                    raise AgentError(
                        f"Failed to initialise iteration memory for {agent.agent_name}: {mem_err}"
                    ) from mem_err

                if not self._should_run_agent(agent_type, wf_id):
                    self.logger.info(f"⏭️ Skipping {agent.agent_name} due to workflow conditions")
                    continue
                
                # Update progress
                progress_percentage = int((step_index / total_steps) * 90)  # 为持久化预留10%
                current_step = f"Executing {agent.agent_name}"
                
                await self._update_progress(
                    execution, 
                    progress_percentage, 
                    current_step,
                    db
                )
                
                # Update task progress + 共享黑板概览
                task.update_progress(current_step, progress_percentage)
                try:
                    self._update_workflow_overview(
                        wf_id,
                        {
                            "status": "RUNNING",
                            "progress": progress_percentage,
                            "current_step": current_step,
                            "step_index": step_index + 1,
                            "total_steps": total_steps,
                            "current_agent": agent.agent_name,
                        },
                        raise_error=True,
                    )
                except AgentError as wm_err:
                    raise AgentError(
                        f"Failed to update workflow_overview in shared memory (step {step_index + 1}): {wm_err}"
                    ) from wm_err
                db.commit()
                
                self.logger.info(f"Starting workflow step {step_index + 1}/{total_steps}: {agent.agent_name}")
                
                try:
                    # Prepare agent input with creative context (if available)
                    self.logger.info(f"🧠 DEBUG: Preparing context for {agent_type.value}")
                    agent_input = await self._prepare_agent_context(workflow_data, agent_type, wf_id)
                    
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

                    # Composer re-entry: after AudioAgent, add BGM if in composer mode
                    try:
                        mixing_mode = getattr(settings, 'AUDIO_MIXING_MODE', 'composer')
                    except Exception:
                        mixing_mode = 'composer'
                    if agent_type == AgentType.VIDEO_COMPOSER and mixing_mode == 'composer':
                        try:
                            vm = self.fetch_memory_slot(
                                str(wf_id),
                                "project.voice_assets",
                                default={},
                                agent=self.agent_name,
                            )
                            if vm:
                                self.logger.info("🎤 Scheduling composer to add voice-over tracks")
                                comp_agent = self.agents.get(AgentType.VIDEO_COMPOSER)
                                comp_input = {
                                    "workflow_state_id": wf_id,
                                    "add_voiceover": True
                                }
                                scope = agent_scope(wf_id, comp_agent.agent_name)
                                shared_view = ensure_mas_memory(wf_id)
                                mem_service.create_or_get(
                                    wf_id,
                                    scope,
                                    owner_agent=comp_agent.agent_name,
                                    shared_view=shared_view,
                                )
                                comp_out = await comp_agent.execute(
                                    task=task,
                                    input_data=comp_input,
                                    db=db,
                                    execution_order=step_index + 1
                                )
                                workflow_results[AgentType.VIDEO_COMPOSER.value + "_add_voiceover"] = comp_out
                                workflow_data.update(comp_out)
                        except Exception as e:
                            raise AgentError(f"Composer add_voiceover failed: {e}") from e
                    if agent_type == AgentType.AUDIO_GENERATOR and mixing_mode == 'composer':
                        try:
                            self.logger.info("🎼 Scheduling composer to add background music")
                            comp_agent = self.agents.get(AgentType.VIDEO_COMPOSER)
                            comp_input = {
                                "workflow_state_id": wf_id,
                                "add_bgm": True
                            }
                            scope = agent_scope(wf_id, comp_agent.agent_name)
                            shared_view = ensure_mas_memory(wf_id)
                            mem_service.create_or_get(
                                wf_id,
                                scope,
                                owner_agent=comp_agent.agent_name,
                                shared_view=shared_view,
                            )
                            comp_out = await comp_agent.execute(
                                task=task,
                                input_data=comp_input,
                                db=db,
                                execution_order=step_index + 1
                            )
                            workflow_results[AgentType.VIDEO_COMPOSER.value + "_add_bgm"] = comp_out
                            workflow_data.update(comp_out)
                            base_result = workflow_results.get(AgentType.VIDEO_COMPOSER.value)
                            if isinstance(base_result, dict):
                                merged_result = dict(base_result)
                                merged_result.update(comp_out or {})
                                workflow_results[AgentType.VIDEO_COMPOSER.value] = merged_result
                            else:
                                workflow_results[AgentType.VIDEO_COMPOSER.value] = comp_out
                        except Exception as e:
                            raise AgentError(f"Composer add_bgm failed: {e}") from e

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
                            workflow_id=wf_id
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
                    # 仅写 Shared WM；不再回写 WorkflowState（避免双轨）
                    tracked_kind = None
                    if agent_type == AgentType.IMAGE_GENERATOR:
                        tracked_kind = "image"
                    elif agent_type == AgentType.VIDEO_GENERATOR:
                        tracked_kind = "video"
                    elif agent_type == AgentType.AUDIO_GENERATOR:
                        tracked_kind = "audio"
                    if tracked_kind:
                        shared = ensure_mas_memory(str(wf_id))
                        bucket = shared.get(f"scene_outputs.{tracked_kind}", {}) if shared is not None else {}
                        committed = len(bucket) if isinstance(bucket, dict) else 0
                        self.logger.info(
                            "WM_COMMIT(%s): agent=%s committed=%s",
                            tracked_kind,
                            agent.agent_name,
                            committed,
                        )

                    # Handle memory storage if this agent produced memory data
                    if agent_type == AgentType.CONCEPT_PLANNER:
                        self.logger.info("🧠 DEBUG: About to store creative guidance from ConceptPlanner")
                        await self._store_creative_guidance_from_output(agent_output)
                        
                        # 🔧 同步概念计划到 Shared WM facts（去除 WorkflowState 依赖）
                        if "concept_plan" in agent_output:
                            try:
                                from .utils.memory_helpers import write_shared_fact
                                write_shared_fact(wf_id, "project.concept_plan", agent_output["concept_plan"])
                            except Exception:
                                pass
                    else:
                        self.logger.info(f"🧠 DEBUG: No memory storage needed for {agent_type.value}")
                    
                    self.logger.info(f"Completed workflow step {step_index + 1}/{total_steps}: {agent.agent_name}")

                    # Lightweight WS signals for coarse-grained UI sync
                    try:
                        from .adapters.state.memory_state import build_memory_state
                        from .adapters.state.mas_state import build_mas_state_view
                        shared = ensure_mas_memory(str(wf_id))
                        wm_state = build_memory_state(shared)
                        mas_state = build_mas_state_view(str(wf_id))
                        if agent_type == AgentType.IMAGE_GENERATOR and self._is_image_step_completed(wf_id, agent_output):
                            await self.websocket_manager.broadcast_to_task(
                                str(task.task_id),
                                {
                                    "type": "image_assets_ready",
                                    "task_id": str(task.task_id),
                                    "images_count": int(wm_state.get("outputs", {}).get("image", 0)),
                                    "state": mas_state,
                                }
                            )
                        if agent_type == AgentType.VIDEO_GENERATOR and self._is_video_step_completed(wf_id, agent_output):
                            await self.websocket_manager.broadcast_to_task(
                                str(task.task_id),
                                {
                                    "type": "video_assets_ready",
                                    "task_id": str(task.task_id),
                                    "videos_count": int(wm_state.get("outputs", {}).get("video", 0)),
                                    "state": mas_state,
                                }
                            )
                    except Exception as _ws_sig_err:
                        self.logger.warning(f"WS coarse signal failed: {str(_ws_sig_err)}")
                    
                except Exception as e:
                    error_msg = f"Workflow failed at step {step_index + 1} ({agent.agent_name}): {str(e)}"
                    self.logger.error(error_msg)
                    
                    # Check if we should retry the failed step
                    if await self._should_retry_step(agent_type, e, db):
                        self.logger.info(f"Retrying step {step_index + 1}: {agent.agent_name}")
                        # Retry the step
                        agent_input = await self._prepare_agent_context(workflow_data, agent_type, wf_id)
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
                            try:
                                from .utils.memory_helpers import write_shared_fact
                                write_shared_fact(wf_id, "project.concept_plan", agent_output["concept_plan"])
                                self.logger.info("🎭 重试后 concept_plan 已写入 MAS WM")
                            except Exception:
                                pass
                    else:
                        # Mark task as failed
                        task.status = TaskStatus.FAILED
                        task.add_error(error_msg)
                        db.commit()
                        raise AgentError(error_msg) from e
            
            # Workflow completed successfully
            await self._update_progress(execution, 90, "Workflow completed, persisting data", db)
            try:
                self._update_workflow_overview(
                    wf_id,
                    {
                        "status": "PERSISTING",
                        "progress": 90,
                        "current_step": "Persisting data to database",
                    },
                    raise_error=True,
                )
            except AgentError as wm_err:
                raise AgentError(f"Failed to mark workflow_overview as PERSISTING: {wm_err}") from wm_err
            
            # 使用DataPersistenceService统一持久化数据
            self.logger.info("💾 开始持久化工作流数据到数据库...")
            persistence_result = await data_persistence_service.persist_from_shared_wm(wf_id, db)
            
            if persistence_result["status"] == "success":
                # Update task status
                task.status = TaskStatus.COMPLETED
                task.update_progress("Completed", 100)
                try:
                    ov = self._load_workflow_overview(wf_id)
                    final_url = workflow_results.get("video_composer", {}).get("final_video_url")
                    if bool(getattr(settings, 'ORCHESTRATOR_READS_ARTIFACTS', False)) or bool(getattr(settings, 'ARTIFACTS_SINGLE_WRITE_MODE', False)):
                        try:
                            latest = get_shared_wm().get_latest_artifact(wf_id, kind='video', stage='compose')
                        except Exception as artifact_err:
                            raise AgentError(
                                f"Failed to read latest video artifact from Shared WM: {artifact_err}"
                            ) from artifact_err
                        if isinstance(latest, dict):
                            final_url = latest.get('url') or latest.get('file_path') or final_url
                    ov.update(
                        {
                            "status": "COMPLETED",
                            "progress": 100,
                            "current_step": "Workflow completed",
                            "outputs": {
                                "final_video_url": final_url
                            },
                        }
                    )
                    self._store_workflow_overview(wf_id, ov)
                except AgentError as wm_err:
                    raise AgentError(f"Failed to update workflow_overview on completion: {wm_err}") from wm_err
                
                self.logger.info(f"✅ 工作流和数据持久化完成: {persistence_result}")
            else:
                # 持久化失败，但工作流本身成功了
                task.status = TaskStatus.COMPLETED  # 仍然标记为完成
                task.add_error(f"数据持久化部分失败: {persistence_result.get('error', '')}")
                try:
                    ov = self._load_workflow_overview(wf_id)
                    warn = list(ov.get("warnings") or [])
                    warn.append("数据持久化部分失败，但工作流成功完成")
                    ov["warnings"] = warn[-5:]
                    self._store_workflow_overview(wf_id, ov)
                except AgentError as wm_err:
                    raise AgentError(f"Failed to record persistence warning in shared memory: {wm_err}") from wm_err
                
                self.logger.warning(f"⚠️ 工作流成功但持久化失败: {persistence_result}")
            
            db.commit()
            
            # Send final WebSocket notification
            await self._send_workflow_completion(task, workflow_results)
            
            self.logger.info(f"🎉 工作流完成，任务ID: {task.task_id}")
            
            # 最终输出：按开关改读 artifacts（若可用）
            final_url = workflow_results.get("video_composer", {}).get("final_video_url")
            if bool(getattr(settings, 'ORCHESTRATOR_READS_ARTIFACTS', False)) or bool(getattr(settings, 'ARTIFACTS_SINGLE_WRITE_MODE', False)):
                try:
                    latest = get_shared_wm().get_latest_artifact(wf_id, kind='video', stage='compose')
                except Exception as artifact_err:
                    raise AgentError(f"Failed to fetch latest compose artifact: {artifact_err}") from artifact_err
                if isinstance(latest, dict):
                    final_url = latest.get('url') or latest.get('file_path') or final_url

            return {
                "workflow_status": "completed",
                "total_steps": total_steps,
                "results": workflow_results,
                "final_video_url": final_url,
                "quality_score": workflow_results.get("quality_checker", {}).get("quality_score"),
                "persistence_status": persistence_result["status"],
                "workflow_state_id": wf_id
            }
            
        except Exception as e:
            # Workflow failed
            error_msg = f"Workflow failed: {str(e)}"
            
            # 记录错误到共享黑板概览
            try:
                ov = self._load_workflow_overview(wf_id)
                prog = int(ov.get("progress") or 0)
                ov.update({"status": "FAILED", "progress": prog, "last_error": error_msg})
                self._store_workflow_overview(wf_id, ov)
            except AgentError as wm_err:
                raise AgentError(f"Failed to record workflow failure in shared memory: {wm_err}") from wm_err
            
            # 尝试持久化失败状态（尽力而为）
            try:
                await data_persistence_service.persist_from_shared_wm(wf_id, db)
                self.logger.info("❌ 工作流失败状态已持久化")
            except Exception as persist_error:
                self.logger.error(f"❌❌ 连持久化失败状态都失败了: {str(persist_error)}")
            
            task.status = TaskStatus.FAILED
            task.add_error(error_msg)
            db.commit()
            
            await self._send_workflow_failure(task, error_msg)
            
            raise AgentError(error_msg) from e
        finally:
            try:
                mem_service.cleanup_workflow(wf_id)
            except Exception as cleanup_err:
                self.logger.warning(
                    "Iteration memory cleanup failed for workflow %s: %s",
                    wf_id,
                    cleanup_err,
                )

    async def _decide_next_step_llm(self, current_agent: AgentType, agent_output: Dict[str, Any], workflow_id: str) -> str:
        """Use a lightweight LLM + orchestrator_control tool to decide next step.
        Returns: 'proceed_next' | 'repeat_agent' | 'halt_workflow'
        """
        # Build observation (concise)
        summary = agent_output.get("summary") or {}
        meta = {}
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
            temperature=0.2,
            # 统一使用结构化 JSON 回执，降低长尾解析风险
            response_format={"type": "json_object"}
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
    
    # WorkflowStatus 已移除；概览在共享黑板 facts.workflow_overview 中维护
    
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

    def _is_image_step_completed(self, workflow_id: str, agent_output: Dict[str, Any]) -> bool:
        """Gate condition for image generation step completion."""
        try:
            shared = ensure_mas_memory(str(workflow_id))
            outputs = shared.get("scene_outputs.image", {}) if shared is not None else {}
            if isinstance(outputs, dict) and outputs:
                return True
        except Exception:
            pass
        self.logger.warning("Image step not completed: no scene_outputs.image found in MAS WM")
        return False

    def _is_video_step_completed(self, workflow_id: str, agent_output: Dict[str, Any]) -> bool:
        """Gate condition for video generation step completion."""
        try:
            shared = ensure_mas_memory(str(workflow_id))
            outputs = shared.get("scene_outputs.video", {}) if shared is not None else {}
            if isinstance(outputs, dict) and outputs:
                return True
        except Exception:
            pass
        self.logger.warning("Video step not completed: no scene_outputs.video found in MAS WM")
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
            
            success = await self.memory_service.store_creative_guidance(
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
    
    def _should_run_agent(self, agent_type: AgentType, workflow_state_id: str) -> bool:
        if agent_type == AgentType.VOICE_SYNTHESIZER:
            voice_plan = self.fetch_memory_slot(
                workflow_state_id,
                "project.voice_plan",
                default={}
            ) or {}
            if not voice_plan or not voice_plan.get("enabled"):
                return False
            if str(voice_plan.get("mode", "none")).lower() == "none":
                return False
            scene_guidance = voice_plan.get("scene_guidance") or []
            if scene_guidance:
                return any(bool(g.get("should_narrate", True)) for g in scene_guidance if isinstance(g, dict))
            # 若缺少逐场景指导，则默认尝试执行，由下游Agent自我校验
            return True
        return True

    async def _prepare_agent_context(self, workflow_data: Dict[str, Any], agent_type: AgentType, workflow_id: str) -> Dict[str, Any]:
        """为Agent准备包含创意指导的上下文数据"""
        
        try:
            # 复制基础工作流数据
            agent_input = workflow_data.copy()

            if agent_type in [AgentType.CONCEPT_PLANNER, AgentType.SCRIPT_WRITER]:
                episode_ctx = None
                project_ctx = None
                episode_ctx = workflow_data.get("episode_context")
                project_ctx = workflow_data.get("project_context")

                if episode_ctx:
                    agent_input["episode_context"] = episode_ctx
                    approved_flag = bool(str(episode_ctx.get("approved_script", "")).strip())
                    self.logger.info(
                        "🧠 Episode context injected for %s (approved_script=%s)",
                        agent_type.value,
                        approved_flag,
                    )
                if project_ctx:
                    agent_input["project_context"] = project_ctx
                    try:
                        self.logger.info(
                            "🧠 Project context injected for %s",
                            agent_type.value,
                        )
                    except Exception:
                        pass

            def _merge_media_context(include_roles: bool) -> None:
                context_bundle = build_media_agent_context(
                    workflow_id,
                    include_scripts=True,
                    include_roles=include_roles,
                )
                for key, value in context_bundle.items():
                    if value:
                        agent_input[key] = value

            if agent_type in [AgentType.IMAGE_GENERATOR, AgentType.VIDEO_GENERATOR]:
                _merge_media_context(include_roles=True)
            elif agent_type == AgentType.AUDIO_GENERATOR:
                _merge_media_context(include_roles=False)
            if agent_type == AgentType.IMAGE_GENERATOR:
                image_ctx = build_image_generation_context(workflow_id)
                if image_ctx:
                    agent_input["image_generation_context"] = image_ctx

        if agent_type in [AgentType.IMAGE_GENERATOR, AgentType.VIDEO_GENERATOR, AgentType.AUDIO_GENERATOR]:
            overall_guidance = workflow_data.get("creative_guidance")
            if overall_guidance:
                agent_input["creative_guidance"] = overall_guidance
            scene_guidances = workflow_data.get("scene_guidances")
            if scene_guidances:
                agent_input["scene_guidances"] = scene_guidances

        elif agent_type == AgentType.VOICE_SYNTHESIZER:
            _merge_media_context(include_roles=True)

            return agent_input
            
        except Exception as e:
            self.logger.error(f"❌ Failed to prepare agent context for {agent_type.value}: {e}")
            # 返回原始数据，不阻塞workflow
            return workflow_data
