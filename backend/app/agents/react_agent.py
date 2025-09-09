"""
ReAct Agent - 提供规划-行动-观察循环能力的基类
"""
import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Callable
from sqlalchemy.orm import Session

from .base import BaseAgent, AgentError
from ..models import Task, AgentExecution, AgentType
from .utils.react_helpers import merge_react_state_into_working_state
# LLM 服务通过依赖注入提供（BaseAgent._llms）


class ReActAgent(BaseAgent, ABC):
    """
    ReAct模式Agent基类
    提供 OBSERVE → THINK → PLAN → ACT → REFLECT 循环能力
    
    适用于需要动态调整策略、处理复杂依赖关系的Agent
    """
    
    def __init__(
        self, 
        agent_type: AgentType,
        agent_name: str,
        max_iterations: int = 3,
        **kwargs
    ):
        super().__init__(
            agent_type=agent_type,
            agent_name=agent_name,
            **kwargs
        )
        self.max_iterations = max_iterations
        self.iteration_context = {}
        self.logger.info(f"🔄 {agent_name} initialized as ReAct Agent (max_iterations={max_iterations})")
    
    async def _execute_impl(
        self, 
        task: Task,
        input_data: Dict[str, Any],
        execution: AgentExecution,
        db: Session
    ) -> Dict[str, Any]:
        """
        ReAct循环的标准实现
        
        OBSERVE → THINK → PLAN → ACT → REFLECT → (循环)
        """
        
        # 初始化ReAct上下文
        self.iteration_context = {
            "task_id": str(task.task_id),
            "workflow_state_id": input_data.get("workflow_state_id"),
            "iteration_history": [],
            "cumulative_results": {},
            "decision_log": []
        }
        
        self.logger.info(f"🔄 Starting ReAct loop for {self.agent_name} (max_iterations={self.max_iterations})")
        
        for iteration in range(self.max_iterations):
            iteration_start_progress = 10 + (iteration * 80 // self.max_iterations)
            await self._update_progress(
                execution, 
                iteration_start_progress, 
                f"ReAct iteration {iteration + 1}/{self.max_iterations}",
                db
            )
            
            self.logger.info(f"🔄 ReAct Iteration {iteration + 1}/{self.max_iterations}")
            
            try:
                # OBSERVE
                self.logger.debug(f"👁️ OBSERVE: Analyzing current state...")
                current_state = await self._observe_current_state(
                    input_data, self.iteration_context, iteration
                )
                # 统一归一化仅用于日志观测，不驱动控制流
                try:
                    norm_info = self._normalize_observation(current_state)
                    if norm_info:
                        npending = norm_info.get('normalized_pending')
                        spending = norm_info.get('summary_pending')
                        if npending is not None and spending is not None and npending != spending:
                            self.logger.info(
                                f"OBS_STATE_DIAG: summary.pending={spending} normalized_pending={npending} (log-only)"
                            )
                except Exception:
                    pass
                # 通用观测摘要（不改变行为）：仅输出编号/计数，避免耦合领域
                try:
                    if isinstance(current_state, dict):
                        pending_ids = []
                        if isinstance(current_state.get('pending_scenes'), list):
                            for it in current_state.get('pending_scenes'):
                                if isinstance(it, dict) and 'scene_number' in it:
                                    pending_ids.append(it.get('scene_number'))
                        completed_cnt = int(current_state.get('completed_count', 0) or 0)
                        failed_cnt = int(current_state.get('failed_count', 0) or 0)
                        # 优先使用归一化后的 pending
                        try:
                            pending_cnt = int(current_state.get('summary', {}).get('pending'))
                        except Exception:
                            pending_cnt = int(current_state.get('pending_count', len(pending_ids)) or len(pending_ids))
                        self.logger.info(
                            f"OBS_STATE: pending={pending_cnt} completed={completed_cnt} failed={failed_cnt}"
                            + (f" pending_ids={sorted(pending_ids)[:10]}" if pending_ids else "")
                        )
                except Exception:
                    pass
                
                # 迭代0：Plan-only（tools=[]），仅产出结构化回执，不执行任何工具
                if iteration == 0:
                    # 进入首轮计划（plan-only）诊断标记
                    try:
                        self.logger.info("PLAN_ONLY_START: tools_override=[]")
                    except Exception:
                        pass
                    try:
                        # 允许子类自定义首轮“计划专用”消息（用于总体规划/播种），否则使用通用观察模板
                        if hasattr(self, '_build_plan_only_messages') and callable(getattr(self, '_build_plan_only_messages')):
                            messages = await self._build_plan_only_messages(input_data, current_state)
                        else:
                            facts = self.build_observation_facts(input_data)
                            _ = self.get_observation_schema()
                            messages = self.build_observation_messages(facts)
                    except Exception as _e:
                        self.logger.warning(f"Plan-only round build messages failed: {_e}, falling back to empty messages")
                        messages = []
                    plan_round = await self.run_fc_round(
                        messages=messages,
                        context_description="initial planning (plan-only)",
                        temperature=0.2,
                        tools_override=[]
                    )
                    contract = plan_round.get("contract") or {}
                    if contract:
                        try:
                            self._apply_react_contract(contract)
                        except Exception:
                            pass
                    # 允许子类在首轮后处理计划产物（例如：播种 agent_overall_plan），仅影响本Agent内部工作状态
                    try:
                        if hasattr(self, '_on_plan_only_completed') and callable(getattr(self, '_on_plan_only_completed')):
                            await self._on_plan_only_completed(plan_round, input_data, current_state)
                    except Exception as hook_err:
                        self.logger.debug(f"Plan-only post-hook failed (ignored): {hook_err}")
                    # 仅诊断：打印 PLAN_DIAG（finish_reason/max_tokens层级/usage/长度），不改变行为
                    try:
                        fc = plan_round.get('fc_plan') if isinstance(plan_round, dict) else None
                        lr = (fc or {}).get('llm_response') if isinstance(fc, dict) else None
                        finish = (lr or {}).get('finish_reason')
                        usage = (lr or {}).get('usage') or {}
                        content = (lr or {}).get('content')
                        reasoning = (lr or {}).get('reasoning_content')
                        c_len = len(content or '') if isinstance(content, str) else 0
                        r_len = len(reasoning or '') if isinstance(reasoning, str) else 0
                        # 估算 max_tokens 档位与上限
                        try:
                            tier = 'thinking' if getattr(self, 'default_thinking_mode', 'standard') == 'thinking' else 'standard'
                            limit = getattr(self, 'max_tokens_thinking', None) if tier == 'thinking' else getattr(self, 'max_tokens_standard', None)
                        except Exception:
                            tier, limit = 'standard', None
                        # usage 摘要
                        try:
                            pu = int(usage.get('prompt_tokens')) if isinstance(usage, dict) else None
                        except Exception:
                            pu = None
                        try:
                            cu = int(usage.get('completion_tokens')) if isinstance(usage, dict) else None
                        except Exception:
                            cu = None
                        try:
                            tu = int(usage.get('total_tokens')) if isinstance(usage, dict) else None
                        except Exception:
                            tu = None
                        usage_str = f"{{p:{pu},c:{cu},t:{tu}}}" if (pu or cu or tu) else "{}"
                        self.logger.info(
                            f"PLAN_DIAG: finish_reason={finish} tier={tier} limit={limit} usage={usage_str} content_len={c_len} reasoning_len={r_len}"
                        )
                        # 预览（安全截断）：优先 content，其次 reasoning
                        try:
                            if isinstance(content, str) and content.strip():
                                pv = content.strip().replace('\n', ' ')
                                if len(pv) > 160:
                                    pv = pv[:160] + '...'
                                self.logger.info(f"PLAN_DIAG content_preview=\"{pv}\"")
                            elif isinstance(reasoning, str) and reasoning.strip():
                                rv = reasoning.strip().replace('\n', ' ')
                                if len(rv) > 160:
                                    rv = rv[:160] + '...'
                                self.logger.info(f"PLAN_DIAG reasoning_preview=\"{rv}\"")
                        except Exception:
                            pass
                    except Exception:
                        pass
                    # 显式打印总体规划与初始计划状态（若有）
                    try:
                        approach = plan_round.get('approach')
                        if approach == 'text_response':
                            meta = plan_round.get('meta') or {}
                            pv = meta.get('content_preview') or ''
                            clen = meta.get('content_len') or 0
                            clip = (pv[:160] + '...') if isinstance(pv, str) and len(pv) > 160 else pv
                            self.logger.info(f"🧭 PLAN_INIT: text preview=\"{clip}\" len={clen}")
                        elif approach == 'function_call_plan':
                            self.logger.info("🧭 PLAN_INIT: function_call_plan established")
                        # 合同中的计划增量摘要
                        pd = contract.get('plan_delta') if isinstance(contract, dict) else None
                        if isinstance(pd, dict) and pd:
                            ver = pd.get('version')
                            digest = pd.get('digest')
                            steps = pd.get('active_steps')
                            if isinstance(digest, str) and len(digest) > 120:
                                digest = digest[:120] + '...'
                            self.logger.info(
                                f"🧭 PLAN_STATE: version={ver} active_steps={(steps[:5] if isinstance(steps, list) else steps)} digest={digest}"
                            )
                    except Exception:
                        pass
                    # 退出首轮计划（plan-only）诊断标记
                    try:
                        self.logger.info("PLAN_ONLY_END")
                    except Exception:
                        pass
                    # 记录本次“规划回合”并进入下一轮（若合同声明完成则可直接结束）
                    reflection = {
                        "success": True,
                        "task_complete": bool(contract.get("task_complete", False)),
                        "should_stop": bool(contract.get("should_stop", False)),
                        "context_updates": dict(contract.get("context_updates", {}) or {}),
                        "reflection_summary": (contract.get("notes") or "initial planning")
                    }
                    iteration_record = {
                        "iteration": iteration + 1,
                        "observation": self._summarize_observation(current_state),
                        "plan": "Plan-only established",
                        "action_result": {"plan_only": True, "contract": contract},
                        "action_result_summary": "Plan-only",
                        "reflection": reflection,
                    }
                    self.iteration_context["iteration_history"].append(iteration_record)
                    if reflection.get("task_complete", False):
                        self.logger.info(f"✅ Completed at plan-only round via contract decision")
                        final_result = await self._finalize_success_results(
                            {"contract": contract}, self.iteration_context
                        )
                        await self._update_progress(execution, 95, "ReAct loop completed", db)
                        return final_result
                    # 继续下一轮
                    continue

                # THINK & PLAN（常规回合）
                self.logger.debug(f"🧠 THINK & PLAN: Developing action strategy...")
                action_plan = await self._think_and_plan(
                    current_state, task, execution, iteration
                )
                
                # ACT
                self.logger.debug(f"⚡ ACT: Executing planned actions...")
                action_result = await self._execute_action(
                    action_plan, input_data, execution, db, iteration
                )
                
                # REFLECT（子类反思 + 合同回执融合）
                self.logger.debug(f"🤔 REFLECT: Evaluating results...")
                reflection = await self._reflect_on_results(
                    action_result, current_state, task, iteration
                )
                # 若行动结果包含 LLM 回执（最小契约），以其为主融合裁决
                try:
                    contract = None
                    if isinstance(action_result, dict):
                        contract = action_result.get("llm_react_contract") or action_result.get("contract")
                    if contract:
                        reflection = self._overlay_contract_on_reflection(reflection, contract)
                        self._apply_react_contract(contract)
                except Exception:
                    pass
                
                # 记录本次迭代
                # 保留原始结果用于后续汇总，同时记录精简摘要便于日志与审计
                iteration_record = {
                    "iteration": iteration + 1,
                    "observation": self._summarize_observation(current_state),
                    "plan": self._summarize_plan(action_plan),
                    "action_result": action_result,                 # 原始结果
                    "action_result_summary": self._summarize_action_result(action_result),
                    "reflection": reflection
                }
                self.iteration_context["iteration_history"].append(iteration_record)

                # 可选：每轮结束回写轻量记忆（默认关闭，符合内存解耦）
                try:
                    await self._on_iteration_end(iteration_record, task, iteration + 1)
                except Exception as hook_err:
                    self.logger.debug(f"ReAct迭代回写钩子失败（忽略）：{hook_err}")
                
                # 更新累积上下文（通用）
                updates = reflection.get("context_updates", {}) or {}
                self.iteration_context["cumulative_results"].update(updates)
                # 同步一份标准化的 react_state，便于各子Agent在 OBSERVE 阶段直接读取
                try:
                    rs = dict(self.iteration_context.get("react_state", {}))
                    rs.update(updates)
                    self.iteration_context["react_state"] = rs
                except Exception:
                    self.iteration_context["react_state"] = updates

                # 迭代摘要日志（仅观测，不改变行为）
                try:
                    rm = dict(self.iteration_context.get('react_metrics', {}))
                    # 若本轮有显式 executed_calls，以其为准修正 executed/act_calls，避免与 ACT_DIAG 口径不一致
                    try:
                        ar = action_result if isinstance(action_result, dict) else {}
                        ec = ar.get('executed_calls') or []
                        if isinstance(ec, list):
                            rm['total'] = len(ec)
                            rm['act_total'] = len(ec)
                    except Exception:
                        pass
                    planned = int(rm.get('planned_calls', 0))
                    executed = int(rm.get('total', 0))
                    ok = int(rm.get('success', 0))
                    fail = int(rm.get('fail', 0))
                    plan_calls = int(rm.get('plan_total', 0))
                    act_calls = int(rm.get('act_total', 0))
                    act_ok = int(rm.get('act_success', 0))
                    artifacts = int(rm.get('artifacts', 0))
                    next_stage = self.iteration_context.get('fc_stage', 'auto')
                    self.logger.info(
                        f"ITER_SUMMARY iter={iteration + 1} planned={planned} executed={executed} ok={ok} fail={fail} "
                        f"plan_calls={plan_calls} act_calls={act_calls} act_ok={act_ok} artifacts={artifacts} next_stage={next_stage}"
                    )
                except Exception:
                    pass

                # 移除默认的重复调用阶段收敛，避免在事实未稳定时干预 ReAct 自主迭代
                # 若未来需要，可通过策略/环境开关在编排层启用
                
                # 检查是否完成任务（以 LLM 回执/子类反思裁决为准，不再做本地守卫）
                if reflection.get("task_complete", False):
                    self.logger.info(f"✅ ReAct loop completed successfully after {iteration + 1} iterations")
                    
                    final_result = await self._finalize_success_results(
                        action_result, self.iteration_context
                    )
                    
                    await self._update_progress(execution, 95, "ReAct loop completed", db)
                    return final_result
                
                # 检查是否需要提前退出
                if reflection.get("should_stop", False):
                    self.logger.warning(f"⚠️ ReAct loop stopped early at iteration {iteration + 1}: {reflection.get('stop_reason', 'Unknown')}")
                    break
                    
            except Exception as e:
                self.logger.error(f"❌ ReAct iteration {iteration + 1} failed: {e}")
                
                # 记录失败的迭代
                self.iteration_context["iteration_history"].append({
                    "iteration": iteration + 1,
                    "error": str(e),
                    "failed": True
                })
                
                # 检查是否应该继续迭代还是提前退出
                should_continue = await self._handle_iteration_error(e, iteration, task)
                if not should_continue:
                    break
        
        # 达到最大迭代次数或提前退出
        self.logger.warning(f"⚠️ ReAct loop ended after {len(self.iteration_context['iteration_history'])} iterations")
        
        final_result = await self._finalize_incomplete_results(self.iteration_context, task)
        await self._update_progress(execution, 90, "ReAct loop ended", db)
        
        return final_result

    # === 归一化与完成守卫（通用，无供应商/工具分支）===
    def _normalize_observation(self, obs: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(obs, dict):
            return {}
        scenes = obs.get('scenes') or []
        try:
            normalized_pending = 0
            for it in scenes:
                if not isinstance(it, dict):
                    continue
                st = (it.get('status') or '').strip().lower()
                if st in ("ready", "pending"):
                    normalized_pending += 1
            summary_pending = None
            try:
                summary_pending = int((obs.get('summary') or {}).get('pending'))
            except Exception:
                summary_pending = None
            return {
                'normalized_pending': normalized_pending,
                'summary_pending': summary_pending
            }
        except Exception:
            return {}

    def _completion_guard(self, obs: Dict[str, Any]) -> (bool, str):
        """保持兼容的占位方法：不再用于控制流，仅供日志观测。"""
        try:
            norm = self._normalize_observation(obs)
            npending = int(norm.get('normalized_pending', 0) or 0)
            return (npending == 0), f"pending_left={npending}"
        except Exception as e:
            return False, f"guard_disabled:{e}"

    # （总体规划相关的兼容占位已移除；计划维护交由 LLM 最小契约与领域子类处理）
    
    @abstractmethod
    async def _observe_current_state(
        self, 
        input_data: Dict[str, Any], 
        context: Dict[str, Any], 
        iteration: int
    ) -> Dict[str, Any]:
        """
        观察当前状态
        
        Args:
            input_data: 原始输入数据
            context: ReAct迭代上下文
            iteration: 当前迭代次数
            
        Returns:
            当前状态的观察结果
        """
        pass
    
    @abstractmethod
    async def _think_and_plan(
        self, 
        current_state: Dict[str, Any], 
        task: Task, 
        execution: AgentExecution,
        iteration: int
    ) -> Dict[str, Any]:
        """
        思考和规划下一步行动
        
        Args:
            current_state: 当前观察到的状态
            task: 任务对象
            execution: 执行记录
            iteration: 当前迭代次数
            
        Returns:
            行动计划
        """
        pass
    
    @abstractmethod
    async def _execute_action(
        self, 
        action_plan: Dict[str, Any], 
        input_data: Dict[str, Any], 
        execution: AgentExecution,
        db: Session,
        iteration: int
    ) -> Dict[str, Any]:
        """
        执行计划的行动
        
        Args:
            action_plan: 行动计划
            input_data: 原始输入数据
            execution: 执行记录
            db: 数据库会话
            iteration: 当前迭代次数
            
        Returns:
            行动执行结果
        """
        pass
    
    @abstractmethod
    async def _reflect_on_results(
        self, 
        action_result: Dict[str, Any], 
        current_state: Dict[str, Any], 
        task: Task,
        iteration: int
    ) -> Dict[str, Any]:
        """
        反思行动结果
        
        Args:
            action_result: 行动执行结果
            current_state: 当前状态
            task: 任务对象
            iteration: 当前迭代次数
            
        Returns:
            反思结果，必须包含：
            - task_complete: bool, 是否任务完成
            - should_stop: bool, 是否提前停止
            - context_updates: dict, 上下文更新
            - stop_reason: str, 停止原因（如果should_stop=True）
        """
        pass
    
    async def _finalize_success_results(
        self, 
        final_action_result: Dict[str, Any], 
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        整理成功完成的最终结果
        
        可以被子类重写以定制结果格式
        """
        return {
            **final_action_result,
            "react_metadata": {
                "total_iterations": len(context["iteration_history"]),
                "success": True,
                "completion_type": "task_complete"
            }
        }
    
    async def _finalize_incomplete_results(
        self, 
        context: Dict[str, Any], 
        task: Task
    ) -> Dict[str, Any]:
        """
        整理未完成任务的结果（最大迭代次数或提前退出）
        
        可以被子类重写以提供fallback逻辑
        """
        # 尝试从最后一次成功的行动中提取结果
        last_successful_result = None
        for iteration_record in reversed(context["iteration_history"]):
            if not iteration_record.get("failed", False):
                # 优先使用原始结果，其次回退到摘要
                last_successful_result = iteration_record.get("action_result")
                break
        
        if last_successful_result is not None:
            if isinstance(last_successful_result, dict):
                return {
                    **last_successful_result,
                    "react_metadata": {
                        "total_iterations": len(context["iteration_history"]),
                        "success": False,
                        "completion_type": "incomplete_but_partial_results"
                    }
                }
            else:
                # 容错：历史中保存的是摘要字符串而非映射
                return {
                    "partial_result": last_successful_result,
                    "react_metadata": {
                        "total_iterations": len(context["iteration_history"]),
                        "success": False,
                        "completion_type": "incomplete_summary_only"
                    }
                }
        else:
            # 所有迭代都失败，返回错误结果
            raise AgentError(f"ReAct loop failed completely after {len(context['iteration_history'])} iterations")
    
    async def _handle_iteration_error(
        self, 
        error: Exception, 
        iteration: int, 
        task: Task
    ) -> bool:
        """
        处理迭代中的错误
        
        Returns:
            bool: 是否继续下一次迭代
        """
        # 默认策略：如果不是最后一次迭代，继续尝试
        should_continue = iteration < self.max_iterations - 1
        
        if should_continue:
            self.logger.info(f"🔄 Error in iteration {iteration + 1}, will retry in next iteration")
        else:
            self.logger.error(f"❌ Error in final iteration {iteration + 1}, stopping ReAct loop")
        
        return should_continue
    
    def _summarize_observation(self, current_state: Dict[str, Any]) -> str:
        """总结观察结果用于日志记录"""
        try:
            if isinstance(current_state, dict):
                return f"State: {len(current_state)} observations"
            if isinstance(current_state, list):
                return f"State(list): {len(current_state)} items"
            return "State: recorded"
        except Exception:
            return "State: recorded"
    
    def _summarize_plan(self, action_plan: Dict[str, Any]) -> str:
        """总结行动计划用于日志记录"""
        try:
            if isinstance(action_plan, dict) and action_plan.get("tool_calls"):
                tcs = action_plan.get("tool_calls") or []
                return f"Plan: {len(tcs)} tool calls"
            if isinstance(action_plan, dict) and action_plan.get("action"):
                return f"Plan: action={action_plan.get('action')}"
            if isinstance(action_plan, dict) and action_plan.get("strategy"):
                return f"Plan: {action_plan.get('strategy')}"
            return "Plan: prepared"
        except Exception:
            return "Plan: prepared"
    
    def _summarize_action_result(self, action_result: Dict[str, Any]) -> str:
        """总结行动结果用于日志记录"""
        try:
            # ToolOutput 兼容
            if hasattr(action_result, 'success'):
                ok = getattr(action_result, 'success')
                return f"Result: {'ok' if ok else 'fail'} (ToolOutput)"
            if isinstance(action_result, dict):
                keys = list(action_result.keys())
                return f"Result: dict[{len(keys)}]"
            if isinstance(action_result, list):
                return f"Result: list[{len(action_result)}]"
            if isinstance(action_result, str):
                return f"Result: str[{len(action_result)}]"
            return "Result: recorded"
        except Exception:
            return "Result: recorded"

    # === 可选的每轮回写钩子（默认关闭）===
    async def _on_iteration_end(self, iteration_record: Dict[str, Any], task: Task, iteration: int) -> None:
        """
        每轮迭代结束时的可选回写钩子：写入极简反思笔记。
        - 默认关闭：通过环境变量 REACT_ITERATION_MEMORY_ENABLED 控制。
        - 只写轻量文本与统计信息，避免存储大量原始结果。
        - 不抛异常，确保完全非侵入。
        """
        import os
        enabled = os.getenv("REACT_ITERATION_MEMORY_ENABLED", "false").lower() == "true"
        if not enabled:
            return
        try:
            from ..services.memory_writer import memory_writer
            workflow_id = self.iteration_context.get("task_id") or str(getattr(task, 'task_id', task.id))
            summary = iteration_record.get("reflection", {}).get("reflection_summary") or iteration_record.get("plan")
            output = {
                "react_note": {
                    "agent": self.agent_name,
                    "iteration": iteration,
                    "observation": iteration_record.get("observation"),
                    "plan": iteration_record.get("plan"),
                    "action_result_summary": iteration_record.get("action_result_summary"),
                    "reflection_summary": summary
                }
            }
            # 非关键写入：失败则忽略
            await memory_writer.write(
                task_type=task.task_type,
                workflow_id=workflow_id,
                scene_number=None,
                output=output
            )
        except Exception as e:
            self.logger.debug(f"ReAct迭代回写失败（忽略）：{e}")
    
    # === ReAct专用的辅助方法 ===
    
    def get_iteration_history(self) -> List[Dict[str, Any]]:
        """获取完整的迭代历史"""
        return self.iteration_context.get("iteration_history", [])
    
    def get_current_iteration(self) -> int:
        """获取当前迭代次数"""
        return len(self.iteration_context.get("iteration_history", []))
    
    def get_cumulative_results(self) -> Dict[str, Any]:
        """获取累积结果"""
        return self.iteration_context.get("cumulative_results", {})
    
    # === 通用观察/合并辅助 ===
    def merge_react_state_into(self, working_state: Dict[str, Any]) -> Dict[str, Any]:
        """将迭代上下文中的 react_state 合并到来访的 working_state（领域无关）。"""
        try:
            react_state = dict(self.iteration_context.get("react_state", {}) or {})
        except Exception:
            react_state = {}
        if not react_state:
            return working_state or {}
        return merge_react_state_into_working_state(working_state or {}, react_state)

    def get_generic_observation_facts(self) -> Dict[str, Any]:
        """返回通用可观测事实快照（不含领域特有结构）。"""
        rm = dict(self.iteration_context.get('react_metrics', {}) or {})
        facts = {
            'planned_calls': int(rm.get('planned_calls', 0) or 0),
            'executed_total': int(rm.get('total', 0) or 0),
            'success_total': int(rm.get('success', 0) or 0),
            'fail_total': int(rm.get('fail', 0) or 0),
            'plan_calls': int(rm.get('plan_total', 0) or 0),
            'act_calls': int(rm.get('act_total', 0) or 0),
            'act_success': int(rm.get('act_success', 0) or 0),
            'artifacts': int(rm.get('artifacts', 0) or 0),
            'executed_functions': list(rm.get('executed_functions', []) or [])[:8],
        }
        return facts

    def build_observation_facts(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """聚合中立“观察事实”：场景清单、前置/完成/失败、最近一轮度量与结果快照（不含工具名/参数）。"""
        ws = dict(self.iteration_context.get("working_state", {}) or {})
        ctx = dict(ws.get("context", {}) or {})
        scenes = ctx.get("scenes_to_generate") or []
        try:
            scenes_facts = [
                {
                    "scene_number": s.get("scene_number"),
                    "title": s.get("title"),
                    "duration": s.get("duration"),
                    "depends_on_scene": s.get("depends_on_scene")
                }
                for s in scenes if isinstance(s, dict)
            ]
        except Exception:
            scenes_facts = []
        ap = dict(ws.get("available_prompts", {}) or {})
        completed = ws.get("completed_scenes") or []
        if isinstance(completed, dict):
            completed_list = [{"scene_number": k} for k in completed.keys()]
        else:
            completed_list = [x for x in completed if isinstance(x, dict)]
        failed_list = [x for x in (ws.get("failed_scenes") or []) if isinstance(x, dict)]
        rm = self.get_generic_observation_facts()
        lrr = self.get_last_round_results()
        return {
            "scenes": scenes_facts,
            "available_prompts": {str(k): (v if isinstance(v, str) else str(v)) for k, v in ap.items()},
            "completed_scenes": [x.get("scene_number") for x in completed_list if x.get("scene_number") is not None],
            "failed_scenes": [x.get("scene_number") for x in failed_list if x.get("scene_number") is not None],
            "react_metrics": rm,
            "last_round_preview": [
                {
                    k: v for k, v in r.items()
                    if k in ("scene_number", "success", "stage", "prompt_text", "image_url", "video_url", "file_path")
                }
                for r in (lrr or [])[:6]
            ]
        }

    def get_observation_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "object",
                    "properties": {
                        "total": {"type": "integer"},
                        "ready": {"type": "integer"},
                        "pending": {"type": "integer"},
                        "completed": {"type": "integer"},
                        "failed": {"type": "integer"}
                    },
                    "required": ["total", "ready", "pending", "completed", "failed"]
                },
                "scenes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "scene_number": {"type": ["integer", "string"]},
                            "status": {"type": "string", "enum": ["ready", "pending", "completed", "failed"]},
                            "missing": {"type": "array", "items": {"type": "string"}},
                            "depends_on_scene": {"type": ["integer", "string", "null"]},
                            "rationale": {"type": "string"}
                        },
                        "required": ["scene_number", "status"]
                    }
                },
                "notes": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["summary", "scenes"]
        }

    def build_observation_messages(self, facts: Dict[str, Any]) -> List[Dict[str, Any]]:
        """构造观察阶段消息：优先使用模板（agents/<agent_name>.yaml: templates.observation），否则使用默认文案。"""
        import json as _json
        sys_content = None
        try:
            from ..core.prompt_manager import get_prompt_manager
            pm = get_prompt_manager()
            cfg = f"{self.agent_name}"
            schema = self.get_observation_schema()
            variables = {
                "facts_json": _json.dumps(facts, ensure_ascii=False, indent=2),
                "schema_json": _json.dumps(schema, ensure_ascii=False, indent=2)
            }
            try:
                sys_content = pm.render_template(cfg, "observation", variables=variables, use_cache=True, auto_reload=False)
            except Exception:
                # 尝试强制重载后再次渲染
                try:
                    pm.reload_config(cfg)
                except Exception:
                    pass
                sys_content = pm.render_template(cfg, "observation", variables=variables, use_cache=False, auto_reload=False)
        except Exception as e:
            # 附加可用配置名，便于排查
            try:
                from ..core.prompt_manager import get_prompt_manager
                pm = get_prompt_manager()
                available = pm.list_configs()
                templates = pm.list_templates(cfg)
            except Exception:
                available, templates = [], []
            raise AgentError(f"缺少观察模板或渲染失败: {e}; available_configs={available}; templates_in_cfg={templates}")
        if not isinstance(sys_content, str) or not sys_content.strip():
            raise AgentError("观察模板渲染为空，请提供 prompts/agents/{agent_name}/observation.yaml")
        sys = {"role": "system", "content": sys_content}
        # 注入最小契约JSON回执的要求（键名英文，值可中文；不包含工具/参数信息）
        contract_note = (
            "\n\n请在本轮回复末尾输出一个JSON回执（仅JSON，不要其他文本），用于更新内部状态：\n"
            "- task_complete: boolean\n- should_stop: boolean\n- context_updates: object\n- plan_delta: object（可选）\n- notes: string（可选）\n"
        )
        usr = {"role": "user", "content": ("以下是当前任务的中立事实：\n" + _json.dumps(facts, ensure_ascii=False) + contract_note)}
        return [sys, usr]

    async def llm_structured_observation(self, messages: List[Dict[str, Any]], schema: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """使用注入的 obs_llm + JSON 模式完成结构化观察。"""
        try:
            # 读取建议的 max_tokens（标准档位）
            try:
                from ..core.config import settings as _cfg
                max_tokens = int(getattr(_cfg, 'LLM_MAX_TOKENS_STANDARD', 4096))
            except Exception:
                max_tokens = 2048
            llm = self.get_llm('observe')
            resp = await llm.chat_completion(
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=max_tokens,
                thinking={"type": "disabled"},
            )
            content = resp.get('content') if isinstance(resp, dict) else None
            if not content:
                # 诊断：若 content 为空而 reasoning_content 存在，仅记录长度信息，不消费思维链
                try:
                    rlen = len(resp.get('reasoning_content') or '') if isinstance(resp, dict) else 0
                    self.logger.warning(f"结构化观察返回content为空（reasoning_len={rlen})")
                except Exception:
                    pass
                return None
            # 兼容部分供应商可能返回 ```json 包裹或首尾空行的情况
            text = str(content).strip()
            if text.startswith("```"):
                try:
                    fence = text.split("\n", 1)[0]
                    if fence.startswith("```json"):
                        text = text[len(fence):].strip()
                    if text.endswith("```"):
                        text = text[:-3].strip()
                except Exception:
                    pass
            import json as _json
            data = _json.loads(text)
            return data if isinstance(data, dict) else None
        except Exception as e:
            # 输出关键信息帮助定位（不掩盖错误）
            try:
                pv = (content or '')
                if isinstance(pv, str):
                    pv = pv.strip().replace("\n", " ")[:240]
                self.logger.warning(f"结构化观察失败：{e} | 使用了response_format=json_object | content_preview=\"{pv}\"")
            except Exception:
                self.logger.warning(f"结构化观察失败：{e}")
            return None

    # === 通用FC回合：计划→执行→结果快照 ===
    async def run_fc_round(
        self,
        messages: List[Dict[str, Any]],
        context_description: str = "",
        temperature: float = 0.2,
        tools_override: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """执行一轮通用FC：返回包含基座结果快照的标准字典。"""
        # 在进入FC前，统一注入“进展摘要+短Scratchpad”（仅一次，放在system之后）
        try:
            enriched = self._inject_after_system(messages, self.build_react_context_messages())
        except Exception:
            enriched = list(messages or [])
        fc = await self.llm_function_call(
            messages=enriched,
            context_description=context_description,
            temperature=temperature,
            tools_override=tools_override,
            **kwargs
        )
        executed_calls: List[Dict[str, Any]] = []
        # Warn-only parameter validation (non-intrusive): do not modify tool_calls
        try:
            if fc.get("approach") == "function_call_plan" and fc.get("tool_calls"):
                from .utils.fc_param_guard import get_fc_param_guard
                guard = get_fc_param_guard(self.logger)
                guard.validate(self, fc["tool_calls"])  # diagnostics only
        except Exception:
            pass
        if fc.get("approach") == "function_call_plan" and fc.get("tool_calls"):
            executed_calls = await self.execute_tool_calls(fc["tool_calls"])  # 执行
        # 标准化结果：仅在本轮确实执行了工具调用时读取 last_round_results；
        # 若未执行任何调用，则视为无新结果，避免重复消费上一轮结果导致的重复持久化/准备动作。
        if executed_calls:
            generation_results = list(self.iteration_context.get('last_round_results', []))
        else:
            generation_results = []
        # 解析最小契约 JSON（若有），供调用方合并
        contract = None
        try:
            content = None
            lr = fc.get('llm_response') if isinstance(fc, dict) else None
            if isinstance(lr, dict):
                content = lr.get('content')
            if not content:
                content = fc.get('content') if isinstance(fc, dict) else None
            if isinstance(content, str) and content.strip():
                contract = self._parse_react_contract(content)
                if contract:
                    # 写入最近一次合同，便于后续事实打包或调试
                    self.iteration_context['last_contract'] = contract
        except Exception:
            contract = None
        return {
            "fc_plan": fc,
            "executed_calls": executed_calls,
            "results": generation_results,
            "contract": contract,
        }

    # === 通用注入：进展摘要 + 最近K步短Scratchpad（不暴露工具/参数） ===
    def _inject_after_system(self, base_messages: List[Dict[str, Any]], inject_messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        msgs = list(base_messages or [])
        if not inject_messages:
            return msgs
        # 幂等：若已包含“进度摘要：”开头的 user 消息，则不重复注入
        for m in msgs:
            if isinstance(m, dict) and m.get('role') == 'user' and isinstance(m.get('content'), str):
                if m['content'].strip().startswith('进度摘要：'):
                    return msgs
        # 插入位置：第一条非system之后
        idx = 0
        while idx < len(msgs) and isinstance(msgs[idx], dict) and msgs[idx].get('role') == 'system':
            idx += 1
        return msgs[:idx] + inject_messages + msgs[idx:]

    def build_react_context_messages(self) -> List[Dict[str, Any]]:
        try:
            from ..core.config import settings
            if not bool(getattr(settings, 'REACT_INJECT_SCRATCHPAD', True)):
                return []
            k = int(getattr(settings, 'REACT_SCRATCHPAD_STEPS', 2))
        except Exception:
            k = 2
        out: List[Dict[str, Any]] = []
        ps = self.build_progress_summary()
        if ps:
            out.append({"role": "user", "content": ps})
        sp = self.build_scratchpad(k=k)
        if sp:
            out.append({"role": "user", "content": sp})
        return out

    # === 最小契约解析与合并（不含供应商/工具信息） ===
    def _parse_react_contract(self, content: str) -> Optional[Dict[str, Any]]:
        if not isinstance(content, string_types := (str,)):
            return None
        text = content.strip()
        if not text:
            return None
        # 允许包裹在```json```代码块中
        if text.startswith("```"):
            try:
                fence = text.split("\n", 1)[0]
                if fence.startswith("```json"):
                    text = text[len(fence):].strip()
                if text.endswith("```"):
                    text = text[:-3].strip()
            except Exception:
                pass
        try:
            import json as _json
            data = _json.loads(text)
            if not isinstance(data, dict):
                return None
            out = {}
            # 仅保留允许的键
            for k in ("task_complete", "should_stop", "context_updates", "plan_delta", "notes"):
                if k in data:
                    out[k] = data[k]
            # 规范化布尔
            for b in ("task_complete", "should_stop"):
                if b in out:
                    out[b] = bool(out[b])
            # 结构类型校验
            if "context_updates" in out and not isinstance(out["context_updates"], dict):
                out["context_updates"] = {}
            if "plan_delta" in out and not isinstance(out["plan_delta"], dict):
                out["plan_delta"] = {}
            if not out:
                return None
            return out
        except Exception:
            return None

    def _apply_react_contract(self, contract: Dict[str, Any]) -> None:
        if not isinstance(contract, dict):
            return
        # 合并 context_updates 到 working_state（保持中立，不做领域判断）
        try:
            ws = dict(self.iteration_context.get("working_state", {}) or {})
            cu = dict(contract.get("context_updates", {}) or {})
            if cu:
                # 浅合并：仅覆盖同名键；复杂结构由领域在后续回合细化
                ws.update(cu)
                self.iteration_context["working_state"] = ws
                try:
                    self.logger.info(f"CONTRACT: context_updates keys={list(cu.keys())[:6]}")
                except Exception:
                    pass
        except Exception:
            pass
        # 写入/更新 agent_plan_state（仅保留增量，领域可自行消费）
        try:
            aps = dict(self.iteration_context.get("agent_plan_state", {}) or {})
            pd = dict(contract.get("plan_delta", {}) or {})
            if pd:
                # 记录最近一次 plan_delta 与摘要（不做重排/应用）
                aps["last_plan_delta"] = pd
                if isinstance(pd.get("digest"), str):
                    aps["plan_digest"] = pd.get("digest")
                if isinstance(pd.get("version"), int):
                    aps["version"] = pd.get("version")
                self.iteration_context["agent_plan_state"] = aps
                try:
                    digest = pd.get("digest")
                    active = pd.get("active_steps")
                    self.logger.info(
                        f"CONTRACT: plan_delta version={pd.get('version')} digest={(digest[:80]+'...') if isinstance(digest,str) and len(digest)>80 else digest} "
                        f"active_steps={active[:5] if isinstance(active, list) else active}"
                    )
                    # 显式输出 PLAN 更新，便于检索
                    short_digest = (digest[:120] + '...') if isinstance(digest, str) and len(digest) > 120 else digest
                    self.logger.info(
                        f"🧭 PLAN_UPDATE: version={pd.get('version')} active_steps={active[:5] if isinstance(active, list) else active} digest={short_digest}"
                    )
                except Exception:
                    pass
        except Exception:
            pass

    def _overlay_contract_on_reflection(self, reflection: Dict[str, Any], contract: Dict[str, Any]) -> Dict[str, Any]:
        ref = dict(reflection or {})
        try:
            if isinstance(contract, dict):
                if "task_complete" in contract:
                    ref["task_complete"] = bool(contract.get("task_complete"))
                if "should_stop" in contract:
                    ref["should_stop"] = bool(contract.get("should_stop"))
                cu = contract.get("context_updates")
                if isinstance(cu, dict):
                    merged = dict(ref.get("context_updates", {}) or {})
                    merged.update(cu)
                    ref["context_updates"] = merged
        except Exception:
            pass
        return ref

    def build_progress_summary(self) -> str:
        try:
            ws = dict(self.iteration_context.get("working_state", {}) or {})
            ctx = dict(ws.get("context", {}) or {})
            scenes = ctx.get("scenes_to_generate") or []
            # 完成/失败集合
            completed = ws.get("completed_scenes") or []
            if isinstance(completed, dict):
                comp_ids = {int(k) for k in completed.keys() if str(k).isdigit()}
            else:
                comp_ids = {int(x.get('scene_number')) for x in completed if isinstance(x, dict) and str(x.get('scene_number')).isdigit()}
            failed = ws.get("failed_scenes") or []
            fail_ids = {int(x.get('scene_number')) for x in failed if isinstance(x, dict) and str(x.get('scene_number')).isdigit()}
            all_ids = {int(s.get('scene_number')) for s in scenes if isinstance(s, dict) and str(s.get('scene_number')).isdigit()}
            pending_ids = sorted(list(all_ids - comp_ids - fail_ids))
            # 上轮度量
            rm = dict(self.iteration_context.get('react_metrics', {}) or {})
            calls = int(rm.get('act_total', 0) or 0)
            arts = int(rm.get('artifacts', 0) or 0)
            fails = int(rm.get('fail', 0) or 0)
            lines = [
                "进度摘要：",
                f"- 已完成：{','.join(map(str, sorted(list(comp_ids)))) if comp_ids else '无'}",
                f"- 待办：{','.join(map(str, pending_ids)) if pending_ids else '无'}",
                f"- 上轮：calls={calls}, artifacts={arts}, failures={fails}",
            ]
            return "\n".join(lines)
        except Exception:
            return ""

    def build_scratchpad(self, k: int = 2) -> str:
        try:
            from ..core.config import settings
            max_chars = int(getattr(settings, 'REACT_SCRATCHPAD_MAX_CHARS', 220))
        except Exception:
            max_chars = 220
        try:
            hist = list(self.iteration_context.get('iteration_history', []) or [])
            if not hist:
                return ""
            recent = hist[-k:]
            lines = [f"最近步骤（K={len(recent)}）："]
            for item in recent:
                it = item.get('iteration')
                plan = (item.get('plan') or '').strip()
                ar_sum = (item.get('action_result_summary') or '').strip()
                refl = ''
                refobj = item.get('reflection')
                if isinstance(refobj, dict):
                    refl = (refobj.get('reflection_summary') or '').strip()
                def _clip(s: str) -> str:
                    return (s or '').replace('\n', ' ')[:max_chars]
                line = f"Step {it}: Thought:{_clip(plan)}"
                if ar_sum:
                    line += f" | Action: 已执行（细节省略） | Observation: {_clip(ar_sum)}"
                elif refl:
                    line += f" | Observation: {_clip(refl)}"
                lines.append(line)
            return "\n".join(lines)
        except Exception:
            return ""
    # === 通用观察/合并辅助 ===
    def merge_react_state_into(self, working_state: Dict[str, Any]) -> Dict[str, Any]:
        """将迭代上下文中的 react_state 合并到来访的 working_state（领域无关）。"""
        try:
            react_state = dict(self.iteration_context.get("react_state", {}) or {})
        except Exception:
            react_state = {}
        if not react_state:
            return working_state or {}
        return merge_react_state_into_working_state(working_state or {}, react_state)

    def get_generic_observation_facts(self) -> Dict[str, Any]:
        """返回通用可观测事实快照（不含领域特有结构）。"""
        rm = dict(self.iteration_context.get('react_metrics', {}) or {})
        facts = {
            'planned_calls': int(rm.get('planned_calls', 0) or 0),
            'executed_total': int(rm.get('total', 0) or 0),
            'success_total': int(rm.get('success', 0) or 0),
            'fail_total': int(rm.get('fail', 0) or 0),
            'plan_calls': int(rm.get('plan_total', 0) or 0),
            'act_calls': int(rm.get('act_total', 0) or 0),
            'act_success': int(rm.get('act_success', 0) or 0),
            'artifacts': int(rm.get('artifacts', 0) or 0),
            'executed_functions': list(rm.get('executed_functions', []) or [])[:8],
        }
        return facts
    
    # === 通用结果获取与进展归约（供应商/动作无关） ===
    def get_last_round_results(self) -> List[Dict[str, Any]]:
        """
        读取基座在本轮执行后写入的标准化结果快照列表。
        每条包含：scene_number, success, stage(plan|act), duration_sec,
        prompt_text?, image_url?|video_url?|file_path?
        """
        res = self.iteration_context.get('last_round_results', [])
        return list(res) if isinstance(res, list) else []

    def reduce_progress_from_results(
        self,
        results: List[Dict[str, Any]],
        prev_prompt_keys: Optional[set] = None
    ) -> Dict[str, Any]:
        """
        从通用结果快照中提取“覆盖增量”与关键映射（不识别动作名/供应商）。
        返回：{
          prepared_prompts: {scene_key: prompt_text},
          artifact_scenes: set(scene_key),
          newly_prepared: int,
          newly_completed: int
        }
        """
        prepared_prompts: Dict[str, str] = {}
        artifact_scenes: set = set()
        prev_prompt_keys = prev_prompt_keys or set()
        for r in results or []:
            try:
                if not r.get('success'):
                    continue
                sn = r.get('scene_number')
                key = str(sn) if sn is not None else None
                if key is None:
                    continue
                pt = r.get('prompt_text')
                if isinstance(pt, str) and pt.strip() and key not in prev_prompt_keys:
                    prepared_prompts[key] = pt.strip()
                if r.get('image_url') or r.get('video_url') or r.get('file_path'):
                    artifact_scenes.add(key)
            except Exception:
                continue
        return {
            'prepared_prompts': prepared_prompts,
            'artifact_scenes': artifact_scenes,
            'newly_prepared': len(prepared_prompts),
            'newly_completed': len(artifact_scenes),
        }

    async def reflect_with_reducer(
        self,
        action_result: Dict[str, Any],
        current_state: Dict[str, Any],
        domain_merge_fn: Callable[[Dict[str, Any], Dict[str, Any], List[Dict[str, Any]]], Dict[str, Any]],
        keys_tracker_name: str = "_prev_prompt_keys",
    ) -> Dict[str, Any]:
        """
        通用反思助手：
        - 消费基座快照（或 action_result 中显式 results）
        - 使用通用归约 reduce_progress_from_results 提取增量
        - 调用领域合并函数完成状态写回与完成判断
        - 统一处理 no_progress_rounds 与跟踪键写回

        domain_merge_fn 返回：{
          'context_updates': dict,
          'done': bool,
          'summary': str,
          'tracker_keys': Optional[set]
        }
        """
        # 1) 获取结果与归约
        generation_results = action_result.get("generation_results") or self.get_last_round_results()
        try:
            prev_keys = set((self.iteration_context.get(keys_tracker_name, set()) or set()))
        except Exception:
            prev_keys = set()
        delta = self.reduce_progress_from_results(generation_results, prev_keys)

        # 2) 领域合并
        workflow_state = self.iteration_context.get("working_state") or current_state or {}
        domain_out = domain_merge_fn(workflow_state, delta, generation_results) or {}
        context_updates = dict(domain_out.get('context_updates', {}))
        done = bool(domain_out.get('done', False))
        summary = domain_out.get('summary') or ""
        tracker_keys = domain_out.get('tracker_keys')

        # 3) 统一 no_progress 计数
        try:
            np = int(workflow_state.get("no_progress_rounds", 0) or 0)
        except Exception:
            np = 0
        if (delta.get('newly_completed', 0) + delta.get('newly_prepared', 0)) > 0:
            np = 0
        else:
            np = np + 1
        context_updates["no_progress_rounds"] = np

        # 4) 写回 working_state 与 tracker keys
        try:
            workflow_state.update(context_updates)  # type: ignore
            self.iteration_context["working_state"] = workflow_state
            if isinstance(tracker_keys, set):
                self.iteration_context[keys_tracker_name] = tracker_keys
            else:
                # 若领域未返回明确 tracker_keys，则尝试从 available_prompts 或 delta 推断
                ap = context_updates.get('available_prompts') if isinstance(context_updates, dict) else None
                if isinstance(ap, dict):
                    self.iteration_context[keys_tracker_name] = set(ap.keys())
                else:
                    pp = delta.get('prepared_prompts') or {}
                    self.iteration_context[keys_tracker_name] = set(pp.keys())
        except Exception:
            pass

        # 5) 统一反思返回
        if done:
            return {
                "success": True,
                "task_complete": True,
                "should_stop": True,
                "context_updates": context_updates,
                "reflection_summary": summary or "任务完成"
            }

        return {
            "success": True,
            "task_complete": False,
            "should_stop": False,
            "stop_reason": "",
            "context_updates": context_updates,
            "reflection_summary": summary or (
                f"处理 {len(generation_results)} 个；新增执行 {delta.get('newly_completed',0)}；新增前置 {delta.get('newly_prepared',0)}；"
            ),
        }

    async def log_decision(self, decision: str, reasoning: str = ""):
        """记录重要决策到决策日志"""
        self.iteration_context["decision_log"].append({
            "iteration": self.get_current_iteration() + 1,
            "decision": decision,
            "reasoning": reasoning,
            "timestamp": asyncio.get_event_loop().time()
        })
        self.logger.info(f"📝 Decision logged: {decision}")
