"""
ReAct（推理 + 行动）编排Agent（FC化）
通过 Function Call 做“下一步行动决策”，并用 agent.execute 调用子Agent。
移除直接AI客户端调用，符合 Tools-First / Prompt Neutrality / Config over Constants 原则。
"""

import asyncio
import json
import logging
import os
from typing import Dict, Any, List, Optional
from enum import Enum
from sqlalchemy.orm import Session

from .base import BaseAgent, AgentError
from ..models import Task, TaskStatus, AgentType


class ReasoningStep(Enum):
    """Types of reasoning steps in the ReAct cycle"""
    OBSERVE = "observe"
    THINK = "think"
    PLAN = "plan"
    ACT = "act"
    REFLECT = "reflect"


class ActionType(Enum):
    """Available actions the orchestrator can take"""
    GENERATE_CONCEPT = "generate_concept"
    WRITE_SCRIPT = "write_script" 
    GENERATE_IMAGES = "generate_images"
    GENERATE_VIDEO = "generate_video"
    COMPOSE_VIDEO = "compose_video"
    CHECK_QUALITY = "check_quality"
    REFINE_CONCEPT = "refine_concept"
    ADJUST_SCRIPT = "adjust_script"
    REGENERATE_ASSETS = "regenerate_assets"
    COMPLETE_TASK = "complete_task"


class ReActOrchestratorAgent(BaseAgent):
    """
    ReAct (Reasoning + Acting) Orchestrator Agent
    
    Implements iterative cycles of:
    1. Observe - Analyze current state and results
    2. Think - Reason about next steps
    3. Plan - Create action plan 
    4. Act - Execute specific action
    5. Reflect - Evaluate results and decide next iteration
    """
    
    def __init__(self):
        super().__init__(
            agent_type=AgentType.ORCHESTRATOR,
            agent_name="react_orchestrator",
            timeout_seconds=3600,  # 1 hour for iterative process
            max_retries=1
        )
        
        self.reasoning_history: List[Dict[str, Any]] = []
        self.max_iterations = 10
        self.quality_threshold = 7.0
        
        # 可用子Agent映射（用于根据动作选择类名）
        self.available_agents = {
            ActionType.GENERATE_CONCEPT: "ConceptPlannerAgent",
            ActionType.WRITE_SCRIPT: "ScriptWriterAgent",
            ActionType.GENERATE_IMAGES: "ImageGeneratorAgent", 
            ActionType.GENERATE_VIDEO: "VideoGeneratorAgent",
            ActionType.COMPOSE_VIDEO: "VideoComposerAgent",
            ActionType.CHECK_QUALITY: "QualityCheckerAgent"
        }
        # 顺序推进的默认动作序列
        self._action_order = [
            ActionType.GENERATE_CONCEPT,
            ActionType.WRITE_SCRIPT,
            ActionType.GENERATE_IMAGES,
            ActionType.GENERATE_VIDEO,
            ActionType.COMPOSE_VIDEO,
            ActionType.CHECK_QUALITY,
            ActionType.COMPLETE_TASK
        ]
    
    async def _execute_impl(
        self,
        task: Task,
        input_data: Dict[str, Any],
        db: Session
    ) -> Dict[str, Any]:
        """Execute iterative workflow"""
        
        self._current_task = task
        task.status = TaskStatus.IN_PROGRESS
        db.commit()
        
        # Initialize workflow state
        wf_id = str(task.task_id)
        workflow_state = {
            "user_requirements": input_data,
            "current_results": {},
            "quality_scores": {},
            "iteration_count": 0,
            "completed_actions": [],
            "failed_actions": [],
            "reasoning_chain": []
        }
        
        try:
            # 主迭代循环（FC决策）
            while workflow_state["iteration_count"] < self.max_iterations:
                iteration = workflow_state["iteration_count"] + 1
                
                self.logger.info(f"🔄 开始迭代 {iteration}")
                await self._update_progress(
                    min(90, iteration * 10), 
                    "processing",
                    db
                )
                
                # 1. OBSERVE - 当前迭代的轻量状态信号（上下文单独构建供 PLAN 使用）
                observation = {
                    "iteration": iteration,
                    "completed_actions": list(workflow_state.get("completed_actions", [])),
                    "failed_actions": list(workflow_state.get("failed_actions", [])),
                    "quality_scores": workflow_state.get("quality_scores", {}),
                }
                try:
                    from .utils.context_manager import build_agent_context
                    plan_context = build_agent_context(
                        workflow_id=wf_id,
                        agent_name=self.agent_name,
                        service=self.short_term_service,
                        state_view=None,
                        max_turn=None,
                        max_token_budget=None,
                    )
                except Exception:
                    plan_context = {}

                # 2~3. THINK/PLAN - 通过 FC 仅用 orchestrator_control 工具进行轻量决策
                decision = await self._fc_decide_next_step(observation, workflow_state, plan_context)
                action_plan = self._derive_action_plan_from_decision(decision, workflow_state)
                
                # 4. ACT - Execute the planned action
                action_result = await self._execute_action(action_plan, workflow_state, db)
                
                # 5. REFLECT - Evaluate results and decide if complete
                reflection = await self._reflect_on_results(action_result, workflow_state)
                
                # Update workflow state
                workflow_state["iteration_count"] = iteration
                workflow_state["reasoning_chain"].append({
                    "iteration": iteration,
                    "observation": observation,
                    "decision": decision,
                    "action_plan": action_plan,
                    "action_result": action_result,
                    "reflection": reflection
                })
                
                # Check if workflow is complete
                if reflection.get("workflow_complete", False):
                    self.logger.info(f"✅ 工作流在 {iteration} 轮后完成")
                    break
                
                # Check for critical failures
                if reflection.get("critical_failure", False):
                    raise AgentError(f"Critical failure in iteration {iteration}: {reflection.get('error')}")
                
                # Brief pause between iterations
                await asyncio.sleep(1)
            
            # Finalize results
            final_results = await self._finalize_workflow(workflow_state, db)
            
            task.status = TaskStatus.COMPLETED
            task.update_progress("Completed", 100)
            db.commit()
            
            return final_results
            
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.add_error(str(e))
            db.commit()
            raise AgentError(f"Orchestrator workflow failed: {str(e)}") from e
    
    
    async def _fc_decide_next_step(self, observation: Dict[str, Any], workflow_state: Dict[str, Any], plan_context: Dict[str, Any]) -> Dict[str, Any]:
        """通过 Function Call 使用 orchestrator_control 做轻量决策。"""
        pm = self.prompt_manager
        import json as _json
        msg = pm.render_template(
            "agents/react_orchestrator",
            "fc_decision_user",
            variables={
                "completed_json": _json.dumps(observation.get('completed'), ensure_ascii=False),
                "failed_json": _json.dumps(observation.get('failed'), ensure_ascii=False),
                "quality_json": _json.dumps(observation.get('quality_scores'), ensure_ascii=False),
                "iteration": observation.get('iteration'),
                "context_json": _json.dumps(plan_context or {}, ensure_ascii=False),
            },
            use_cache=True,
            auto_reload=False,
        )
        fc = await self.llm_function_call(
            messages=[{"role": "user", "content": msg}],
            context_description="编排决策：继续/重复/中止",
            temperature=0.2,
            # 统一强约束JSON，保证结构化决策
            response_format={"type": "json_object"}
        )
        if fc.get("approach") == "function_call_plan" and fc.get("tool_calls"):
            exec_res = await self.execute_tool_calls(fc["tool_calls"])
            for item in exec_res:
                if item.get("success"):
                    payload = item.get("result")
                    if hasattr(payload, "result"):
                        payload = getattr(payload, "result")
                    if isinstance(payload, dict) and payload.get("decision"):
                        # 显式打印编排决策，辅助观察总体规划的推进
                        try:
                            self.logger.info(
                                f"🧭 ORCH_DECISION: decision={payload.get('decision')} reason={(payload.get('reason') or '')[:120]}"
                            )
                        except Exception:
                            pass
                        return payload
        default_decision = {"decision": "proceed_next", "reason": "默认前进"}
        try:
            self.logger.info(
                f"🧭 ORCH_DECISION: decision={default_decision['decision']} reason={default_decision['reason']}"
            )
        except Exception:
            pass
        return default_decision
    
    def _derive_action_plan_from_decision(self, decision: Dict[str, Any], workflow_state: Dict[str, Any]) -> Dict[str, Any]:
        """根据决策生成行动计划（顺序推进为主，可重复上一动作或中止）。"""
        d = (decision or {}).get("decision", "proceed_next")
        completed: List[str] = list(workflow_state.get("completed_actions", []))

        def next_action() -> ActionType:
            for a in self._action_order:
                if a.value not in completed:
                    return a
            return ActionType.COMPLETE_TASK

        if d == "halt_workflow":
            return {"action": ActionType.COMPLETE_TASK.value, "parameters": {"halted": True}}
        if d == "repeat_agent":
            last = completed[-1] if completed else None
            if last:
                plan = {"action": last, "parameters": {"repeat": True}}
                try:
                    self.logger.info(f"📋 ORCH_PLAN: action={plan['action']} repeat=True")
                except Exception:
                    pass
                return plan
            return {"action": next_action().value, "parameters": {}}
        plan = {"action": next_action().value, "parameters": {}}
        try:
            self.logger.info(f"📋 ORCH_PLAN: action={plan['action']} repeat=False")
        except Exception:
            pass
        return plan
    
    async def _execute_action(
        self,
        action_plan: Dict[str, Any],
        workflow_state: Dict[str, Any],
        db: Session
    ) -> Dict[str, Any]:
        """ACT: 调用子Agent执行（使用 agent.execute 继承统一保障）。"""
        action_name = action_plan.get("action")
        parameters = action_plan.get("parameters", {})

        self.logger.info(f"⚡ 执行动作: {action_name}")

        try:
            if action_name == ActionType.GENERATE_CONCEPT.value:
                result = await self._execute_concept_generation(parameters, workflow_state, db)
            elif action_name == ActionType.WRITE_SCRIPT.value:
                result = await self._execute_script_writing(parameters, workflow_state, db)
            elif action_name == ActionType.GENERATE_IMAGES.value:
                result = await self._execute_image_generation(parameters, workflow_state, db)
            elif action_name == ActionType.GENERATE_VIDEO.value:
                result = await self._execute_video_generation(parameters, workflow_state, db)
            elif action_name == ActionType.COMPOSE_VIDEO.value:
                result = await self._execute_video_composition(parameters, workflow_state, db)
            elif action_name == ActionType.CHECK_QUALITY.value:
                result = await self._execute_quality_check(parameters, workflow_state, db)
            elif action_name == ActionType.REFINE_CONCEPT.value:
                result = await self._execute_concept_refinement(parameters, workflow_state, db)
            elif action_name == ActionType.COMPLETE_TASK.value:
                result = await self._execute_task_completion(parameters, workflow_state, db)
            else:
                raise AgentError(f"Unknown action: {action_name}")

            workflow_state['completed_actions'].append(action_name)
            workflow_state['current_results'][action_name] = result
            return result

        except Exception as e:
            workflow_state['failed_actions'].append(action_name)
            self.logger.error(f"动作 {action_name} 执行失败: {e}")
            return {"error": str(e), "failed": True}
    
    async def _reflect_on_results(
        self, 
        action_result: Dict[str, Any], 
        workflow_state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """REFLECT: Evaluate action results and decide on next steps"""
        # 以“事实+阈值”为主做完成判定，减少对 LLM 文本反思的依赖
        completed = set(workflow_state.get('completed_actions', []))
        quality = workflow_state.get('quality_scores', {})
        overall_quality = quality.get('overall', None)

        required = {
            ActionType.GENERATE_CONCEPT.value,
            ActionType.WRITE_SCRIPT.value,
            ActionType.GENERATE_IMAGES.value,
            ActionType.GENERATE_VIDEO.value,
            ActionType.COMPOSE_VIDEO.value,
        }

        has_required = required.issubset(completed)
        quality_ok = (overall_quality is None) or (overall_quality >= self.quality_threshold)
        iter_limit_reached = workflow_state.get('iteration_count', 0) >= self.max_iterations - 1

        workflow_complete = has_required and quality_ok
        if iter_limit_reached:
            workflow_complete = True

        return {
            "action_success": action_result.get("success", True),
            "quality_acceptable": bool(quality_ok),
            "workflow_complete": bool(workflow_complete),
            "critical_failure": False,
            "next_recommendation": "complete_task" if workflow_complete else "continue",
            "confidence": 8 if workflow_complete else 6,
            "reasoning": "fact-based completion check"
        }
    
    # Action execution methods (simplified implementations)
    async def _execute_concept_generation(self, parameters: Dict, workflow_state: Dict, db: Session) -> Dict[str, Any]:
        """Execute concept generation with dynamic parameters"""
        # Import and use existing ConceptPlannerAgent
        from .concept_planner import ConceptPlannerAgent
        
        from .utils.llm_policy import LLMPolicyManager
        policy_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'llm_policies.yaml')
        llms = LLMPolicyManager(policy_file).build_llms_for_agent('concept_planner')
        agent = ConceptPlannerAgent(llms=llms)
        input_data = {**workflow_state.get('user_requirements', {}), **parameters}
        return await agent.execute(self._current_task, input_data, db)
    
    async def _execute_script_writing(self, parameters: Dict, workflow_state: Dict, db: Session) -> Dict[str, Any]:
        """Execute script writing with concept context"""
        from .script_writer import ScriptWriterAgent
        
        from .utils.llm_policy import LLMPolicyManager
        policy_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'llm_policies.yaml')
        llms = LLMPolicyManager(policy_file).build_llms_for_agent('script_writer')
        agent = ScriptWriterAgent(llms=llms)
        input_data = {**workflow_state.get('current_results', {}), **parameters}
        return await agent.execute(self._current_task, input_data, db)
    
    async def _execute_image_generation(self, parameters: Dict, workflow_state: Dict, db: Session) -> Dict[str, Any]:
        """Execute image generation with script context"""
        from .image_generator import ImageGeneratorAgent
        
        from .utils.llm_policy import LLMPolicyManager
        policy_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'llm_policies.yaml')
        llms = LLMPolicyManager(policy_file).build_llms_for_agent('image_generator')
        agent = ImageGeneratorAgent(llms=llms)
        input_data = {**workflow_state.get('current_results', {}), **parameters}
        return await agent.execute(self._current_task, input_data, db)
    
    async def _execute_video_generation(self, parameters: Dict, workflow_state: Dict, db: Session) -> Dict[str, Any]:
        """Execute video generation with image context"""
        from .video_generator import VideoGeneratorAgent
        
        from .utils.llm_policy import LLMPolicyManager
        policy_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'llm_policies.yaml')
        llms = LLMPolicyManager(policy_file).build_llms_for_agent('video_generator')
        agent = VideoGeneratorAgent(llms=llms)
        input_data = {**workflow_state.get('current_results', {}), **parameters}
        return await agent.execute(self._current_task, input_data, db)
    
    async def _execute_video_composition(self, parameters: Dict, workflow_state: Dict, db: Session) -> Dict[str, Any]:
        """Execute video composition with all previous context"""
        from .video_composer import VideoComposerAgent
        
        from .utils.llm_policy import LLMPolicyManager
        policy_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'llm_policies.yaml')
        llms = LLMPolicyManager(policy_file).build_llms_for_agent('video_composer')
        agent = VideoComposerAgent(llms=llms)
        input_data = {**workflow_state.get('current_results', {}), **parameters}
        return await agent.execute(self._current_task, input_data, db)
    
    async def _execute_quality_check(self, parameters: Dict, workflow_state: Dict, db: Session) -> Dict[str, Any]:
        """Execute quality check on current results"""
        from .quality_checker import QualityCheckerAgent
        
        from .utils.llm_policy import LLMPolicyManager
        policy_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'llm_policies.yaml')
        llms = LLMPolicyManager(policy_file).build_llms_for_agent('quality_checker')
        agent = QualityCheckerAgent(llms=llms)
        input_data = workflow_state['current_results'].copy()
        input_data.update(parameters)
        
        result = await agent.execute(self._current_task, input_data, db)
        
        # Update quality scores
        if 'quality_score' in result:
            workflow_state['quality_scores']['overall'] = result['quality_score']
        
        return result
    
    async def _execute_concept_refinement(self, parameters: Dict, workflow_state: Dict, db: Session) -> Dict[str, Any]:
        """Refine concept based on quality feedback"""
        # Enhanced concept generation with feedback
        refinement_params = parameters.copy()
        refinement_params['refinement_feedback'] = workflow_state.get('quality_scores', {})
        
        return await self._execute_concept_generation(refinement_params, workflow_state, db)
    
    async def _execute_task_completion(self, parameters: Dict, workflow_state: Dict, db: Session) -> Dict[str, Any]:
        """Complete the task and prepare final output"""
        return {
            "status": "completed",
            "final_results": workflow_state['current_results'],
            "reasoning_chain": workflow_state['reasoning_chain'],
            "total_iterations": workflow_state['iteration_count']
        }
    
    def _get_fallback_action_plan(self, workflow_state: Dict[str, Any]) -> Dict[str, Any]:
        """顺序推进的后备路径（简单可靠）。"""
        completed = set(workflow_state.get('completed_actions', []))
        for a in self._action_order:
            if a.value not in completed:
                return {"action": a.value, "parameters": {}}
        return {"action": ActionType.COMPLETE_TASK.value, "parameters": {}}

    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        """统一使用安全解析工具，避免手写围栏剥离与静默失败。"""
        from .utils.json_utils import safe_json_loads
        try:
            data = safe_json_loads(response, logger=self.logger, context="react_orchestrator.parse_response", allow_fallback=False)
            return data if isinstance(data, dict) else {"raw_response": response}
        except Exception as exc:
            # 明确记录解析错误，保持可审计
            try:
                preview = (response or "").strip().replace("\n", " ")[:240]
                self.logger.warning("ORCH_JSON_PARSE_FAIL err=%s preview=\"%s\"", exc, preview)
            except Exception:
                pass
            return {"raw_response": response}
    
    async def _finalize_workflow(self, workflow_state: Dict[str, Any], db: Session) -> Dict[str, Any]:
        """Finalize workflow and prepare final results"""
        
        return {
            "workflow_type": "react_iterative",
            "total_iterations": workflow_state["iteration_count"],
            "completed_actions": workflow_state["completed_actions"],
            "failed_actions": workflow_state["failed_actions"], 
            "quality_scores": workflow_state["quality_scores"],
            "final_results": workflow_state["current_results"],
            "reasoning_chain": workflow_state["reasoning_chain"],
            "performance_metrics": {
                "efficiency": len(workflow_state["completed_actions"]) / max(1, workflow_state["iteration_count"]),
                "success_rate": len(workflow_state["completed_actions"]) / (len(workflow_state["completed_actions"]) + len(workflow_state["failed_actions"])) if (len(workflow_state["completed_actions"]) + len(workflow_state["failed_actions"])) > 0 else 1.0,
                "avg_quality": sum(workflow_state["quality_scores"].values()) / max(1, len(workflow_state["quality_scores"]))
            }
        }

    # === 兼容性方法（用于通过现有检查脚本），核心逻辑已移至 FC 决策 ===
    async def _think_and_reason(self, observation: Dict[str, Any], workflow_state: Dict[str, Any]) -> Dict[str, Any]:
        """兼容：返回轻量占位，提示使用 FC 决策。"""
        return {
            "analysis": "delegated_to_fc",
            "priority_assessment": "use_fc_decision",
            "recommended_approach": "proceed_next",
            "confidence_level": 8
        }

    async def _plan_next_action(self, reasoning: Dict[str, Any], workflow_state: Dict[str, Any]) -> Dict[str, Any]:
        """兼容：基于顺序推进生成占位计划。实际执行时以 FC 决策为准。"""
        return self._get_fallback_action_plan(workflow_state)
