"""
ReAct Agent - 提供“基于记忆的迭代规划”能力的基类
"""
import asyncio
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable, Set
from sqlalchemy.orm import Session

from .base import BaseAgent, AgentError
from ..models import Task, AgentType
from .utils.obs_builder import derive_action_facts
# LLM 服务通过依赖注入提供（BaseAgent._llms）


class ReActAgent(BaseAgent, ABC):
    """
    ReAct模式Agent基类

    说明（避免术语误解）：
    - 本实现的每一轮迭代在进入 PLAN 之前，会先从 WorkingMemory 读取上一轮写入的观察记录与产物索引，
      组装为 iteration_context（等价于“观察输入”）。
    - 因此单轮时序可理解为：PLAN → ACT → OBSERVE（写回WM）→（可选）REFLECT；
      下一轮再基于 WM 推导出的 iteration_context 继续规划。
    
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
        self.logger.info(f"🔄 {agent_name} initialized with iterative loop (max_iterations={max_iterations})")
        # Agent 内不保存跨回合状态
    
    async def _execute_impl(
        self,
        task: Task,
        input_data: Dict[str, Any],
        db: Session = None,
    ) -> Dict[str, Any]:
        """
        ReAct循环的标准实现（基于 WM 的迭代闭环）
        
        单轮时序：
        1) 从 WM 构建 iteration_context（承载上一轮 OBSERVE 的结果）
        2) THINK/PLAN（一次 FC 产出 tool_calls 或输出合同 JSON）
        3) ACT（仅执行 tool_calls）
        4) OBSERVE（将本轮结果写入 WM）
        5) REFLECT（可选领域反思 + 合同融合，决定是否退出）
        """

        # 初始化：清理工作记忆引用缓存（WorkingMemory 由 Orchestrator 统一创建）。
        self.reset_iteration_memory_cache()
        # 无缓存执行摘要：上一轮信息全部从 WM 推导
        
        self.logger.info(f"🔄 Starting iterative loop for {self.agent_name} (max_iterations={self.max_iterations})")
        
        # 不跨轮保存状态；每轮上下文显式从 WM / 状态视图读取
        pending_action_facts: Optional[Dict[str, Any]] = None
        no_tool_calls_streak = 0
        for iteration in range(self.max_iterations):
            iteration_start_progress = 10 + (iteration * 80 // self.max_iterations)
            await self._update_progress(
                iteration_start_progress,
                "processing",
                db
            )

            self.logger.info(f"🔄 Iteration {iteration + 1}/{self.max_iterations}")
            
            try:
                # 上下文由 context manager 基于 Agent WM/状态视图构建
                try:
                    from .utils.context_manager import build_agent_context
                    current_iter_context = build_agent_context(
                        workflow_id=str(input_data.get("workflow_state_id") or self.workflow_state_id or ""),
                        agent_name=self.agent_name,
                        service=self.short_term_service,
                        state_view=None,
                        max_turn=None,
                        max_token_budget=None,
                    )
                except Exception as ctx_err:
                    try:
                        self.logger.warning(
                            "build_agent_context failed for agent=%s err=%s",
                            self.agent_name,
                            ctx_err,
                            exc_info=True,
                        )
                    except Exception:
                        pass
                    current_iter_context = {}
                pending_action_facts = None

                # THINK & PLAN
                self.logger.debug(f"🧠 THINK & PLAN: Developing action strategy...")
                # 合并任务指令 + 静态上下文（由 orchestrator 注入）与迭代上下文，作为本轮 PLAN 输入
                plan_context: Dict[str, Any] = self._build_plan_context(
                    input_data=input_data,
                    iteration_context=current_iter_context,
                )
                # NOTE: 临时调试“PLAN_CONTEXT 落盘到 /tmp”已移除（避免隐性 I/O 与数据泄露风险）。

                action_plan = await self._think_and_plan(plan_context, task, iteration)

                # 空转保护（单一职责）：
                # - 本轮无 tool_calls 时，对 PLAN 文本做一次“退出合同规整”（response_format=json_object，且不携带 tools），
                #   以获得可解析的 task_complete / completed_reason / plan_summary，避免仅凭自然语言 content 猜测。
                # - 连续多轮无 tool_calls 且合同仍判定未完成：以 blocked 早停并告警，避免浪费预算空转到 max_iterations。
                def _tool_calls_requested(plan: Any) -> List[Any]:
                    if isinstance(plan, dict):
                        calls = plan.get("tool_calls") or []
                        return list(calls) if isinstance(calls, list) else []
                    return []

                tool_calls_requested = _tool_calls_requested(action_plan)
                raw_plan_text = self._extract_plan_contract_source_text(action_plan)
                plan_contract: Dict[str, Any] = {}
                if isinstance(action_plan, dict) and isinstance(action_plan.get("plan_contract"), dict):
                    plan_contract = dict(action_plan.get("plan_contract") or {})

                if tool_calls_requested:
                    if not plan_contract and raw_plan_text:
                        self.logger.info(
                            "PLAN_CONTRACT_NORMALIZE agent=%s iter=%d (tool_calls present)",
                            self.agent_name,
                            iteration + 1,
                        )
                        plan_contract = await self._normalize_plan_contract_from_text(raw_plan_text)
                    if isinstance(action_plan, dict) and plan_contract:
                        action_plan["plan_contract"] = plan_contract
                    try:
                        from .utils.tool_contracts import plan_contract_conflicts_with_actions

                        conflict = plan_contract_conflicts_with_actions(plan_contract, tool_calls_requested)
                    except Exception:
                        conflict = False
                    if conflict:
                        completed_reason = plan_contract.get("completed_reason")
                        completed_reason_str = (
                            completed_reason.strip() if isinstance(completed_reason, str) else ""
                        )
                        plan_summary = plan_contract.get("plan_summary")
                        plan_summary_str = (
                            plan_summary.strip() if isinstance(plan_summary, str) else ""
                        )
                        self.logger.error(
                            "PLAN_CONTRACT_CONFLICT agent=%s iter=%d tool_calls_requested=%d completed_reason=%s",
                            self.agent_name,
                            iteration + 1,
                            len(tool_calls_requested),
                            completed_reason_str or None,
                        )
                        try:
                            from .utils.wm_obs import append_obs_to_wm

                            wf_id = str(input_data.get("workflow_state_id") or self.workflow_state_id or "")
                            append_obs_to_wm(
                                workflow_id=wf_id,
                                agent_name=self.agent_name,
                                obs_record={
                                    "iteration": iteration,
                                    "event": {
                                        "type": "loop_end",
                                        "reason": "plan_contract_conflict",
                                        "subtask_state": "error",
                                        "completed_reason": completed_reason_str or None,
                                        "plan_summary": plan_summary_str or None,
                                        "tool_calls_requested": len(tool_calls_requested),
                                    },
                                },
                                service=self.short_term_service,
                            )
                        except Exception:
                            pass
                        final_result = await self._finalize_incomplete_results(
                            {
                                "total_iterations": iteration + 1,
                                "workflow_state_id": input_data.get("workflow_state_id") or self.workflow_state_id,
                                "subtask_state": "error",
                                "loop_end_reason": "plan_contract_conflict",
                                "completed_reason": completed_reason_str or "plan_contract_conflict",
                                "plan_summary": plan_summary_str or None,
                            },
                            task,
                        )
                        await self._update_progress(90, "processing", db)
                        return final_result
                    no_tool_calls_streak = 0
                else:
                    # 无 tool_calls：将 PLAN 的自然语言回执规整为最小退出合同（不做二次规划决策）。
                    if not plan_contract:
                        if not raw_plan_text.strip():
                            # 风险1修复（轻量）：PLAN 空输出属于模型/供应商异常，不应误判为业务 blocked；
                            # 且需要落一条终止事实到 Agent WM 便于审计。
                            self.logger.warning(
                                "PLAN_EMPTY_OUTPUT agent=%s iter=%d; ending loop early",
                                self.agent_name,
                                iteration + 1,
                            )
                            terminal_result = {
                                "success": False,
                                "subtask_state": "error",
                                "loop_end_reason": "plan_output_empty",
                                "completed_reason": "plan_output_empty",
                                "plan_summary": "PLAN 输出为空，无法规整退出合同",
                            }
                            try:
                                from .utils.wm_obs import append_obs_to_wm

                                wf_id = str(input_data.get("workflow_state_id") or self.workflow_state_id or "")
                                append_obs_to_wm(
                                    workflow_id=wf_id,
                                    agent_name=self.agent_name,
                                    obs_record={
                                        "iteration": iteration,
                                        "event": {
                                            "type": "loop_end",
                                            "reason": "plan_output_empty",
                                            "subtask_state": "error",
                                            "completed_reason": terminal_result.get("completed_reason"),
                                            "plan_summary": terminal_result.get("plan_summary"),
                                        },
                                    },
                                    service=self.short_term_service,
                                )
                            except Exception as obs_err:
                                self.logger.warning(
                                    "EARLY_STOP_OBS_WRITE_FAILED agent=%s iter=%d err=%s",
                                    self.agent_name,
                                    iteration + 1,
                                    obs_err,
                                    exc_info=True,
                                )
                            # fail-fast：以明确错误结果结束本次执行（不进入 ACT/REFLECT）
                            final_result = await self._finalize_incomplete_results(
                                {
                                    "total_iterations": iteration + 1,
                                    "workflow_state_id": input_data.get("workflow_state_id") or self.workflow_state_id,
                                    "subtask_state": "error",
                                    "loop_end_reason": "plan_output_empty",
                                    "completed_reason": terminal_result.get("completed_reason"),
                                    "plan_summary": terminal_result.get("plan_summary"),
                                },
                                task,
                            )
                            await self._update_progress(90, "processing", db)
                            return final_result

                        self.logger.info(
                            "PLAN_CONTRACT_NORMALIZE agent=%s iter=%d (no tool_calls, no inline contract)",
                            self.agent_name,
                            iteration + 1,
                        )
                        plan_contract = await self._normalize_plan_contract_from_text(raw_plan_text)

                    if isinstance(action_plan, dict) and plan_contract:
                        action_plan["plan_contract"] = plan_contract

                    task_complete = bool(plan_contract.get("task_complete") is True)
                    # 关键可观测性：记录规整后的合同关键信息，便于定位“为何无 tool_calls / 为何未退出”
                    plan_summary = plan_contract.get("plan_summary")
                    plan_summary_str = plan_summary.strip() if isinstance(plan_summary, str) else ""
                    plan_summary_preview = (
                        (plan_summary_str[:240] + "...(truncated)")
                        if len(plan_summary_str) > 240
                        else plan_summary_str
                    )
                    completed_reason = plan_contract.get("completed_reason")
                    completed_reason_str = completed_reason.strip() if isinstance(completed_reason, str) else ""
                    self.logger.info(
                        "PLAN_CONTRACT agent=%s iter=%d tool_calls_requested=%d task_complete=%s completed_reason=%s plan_summary_preview=%s",
                        self.agent_name,
                        iteration + 1,
                        len(tool_calls_requested),
                        task_complete,
                        completed_reason_str or None,
                        plan_summary_preview or None,
                    )
                    if task_complete:
                        completion_gate = self._accept_completion_request(
                            stage="plan_contract",
                            input_data=input_data,
                            plan_context=plan_context,
                            iteration_context=current_iter_context,
                            iteration=iteration,
                            plan_contract=plan_contract,
                        )
                        gate_accepted = bool(completion_gate.get("accepted", True))
                        if not gate_accepted:
                            task_complete = False
                            self._record_completion_gate_rejection(
                                input_data=input_data,
                                iteration=iteration,
                                stage="plan_contract",
                                details=completion_gate,
                            )
                            self.logger.warning(
                                "COMPLETION_GATE_REJECTED agent=%s iter=%d stage=plan_contract reason=%s",
                                self.agent_name,
                                iteration + 1,
                                completion_gate.get("reason"),
                            )
                            if isinstance(action_plan, dict) and isinstance(action_plan.get("plan_contract"), dict):
                                action_plan["plan_contract"] = dict(action_plan["plan_contract"])
                                action_plan["plan_contract"]["task_complete"] = False
                            plan_contract = dict(plan_contract or {})
                            plan_contract["task_complete"] = False
                            plan_contract.setdefault(
                                "completed_reason",
                                str(completion_gate.get("reason") or "completion_gate_rejected"),
                            )
                    if task_complete:
                        # 关键语义：当 PLAN 判定“无需再行动且任务完成”时，本轮不应进入 ACT（否则会产生 noop 结果覆盖上一轮产物）。
                        no_tool_calls_streak = 0
                        # 写入一次终止事实到 Agent WM（便于审计/追溯），但不写入 PLAN 原文回执
                        try:
                            from .utils.wm_obs import append_obs_to_wm

                            wf_id = str(input_data.get("workflow_state_id") or self.workflow_state_id or "")
                            append_obs_to_wm(
                                workflow_id=wf_id,
                                agent_name=self.agent_name,
                                obs_record={
                                    "iteration": iteration,
                                    "event": {
                                        "type": "loop_end",
                                        "reason": "plan_contract_task_complete",
                                        "subtask_state": "complete",
                                        "completed_reason": completed_reason_str or None,
                                        "plan_summary": plan_summary_str or None,
                                    },
                                },
                                service=self.short_term_service,
                            )
                        except Exception:
                            pass

                        # 重要：本分支是“计划回合（无工具调用）”；交付物应由 MAS SoT 承担，
                        # 不应在基类内依赖“上一轮 action_result”做隐式拼接。
                        final_action_result: Dict[str, Any] = {
                            "success": True,
                            "subtask_state": "complete",
                            "loop_end_reason": "plan_contract_task_complete",
                        }
                        if completed_reason_str:
                            final_action_result["completed_reason"] = completed_reason_str
                        if plan_summary_str:
                            final_action_result["plan_summary"] = plan_summary_str

                        self.logger.info(
                            "✅ Iterative loop completed successfully after %d iterations (plan_contract)",
                            iteration + 1,
                        )
                        final_result = await self._finalize_success_results(
                            final_action_result,
                            {
                                "total_iterations": iteration + 1,
                                "workflow_state_id": input_data.get("workflow_state_id") or self.workflow_state_id,
                            },
                        )
                        await self._update_progress(95, "completed", db)
                        return final_result
                    else:
                        no_tool_calls_streak += 1
                        if no_tool_calls_streak >= 2:
                            try:
                                self.logger.warning(
                                    "PLAN_NO_TOOL_CALLS_STREAK agent=%s iter=%d streak=%d; ending loop early to avoid empty-loop",
                                    self.agent_name,
                                    iteration + 1,
                                    no_tool_calls_streak,
                                )
                            except Exception:
                                pass
                            # 以“阻塞/未完成但无法推进”收尾（不抛错，避免误把“计划回合”当异常）
                            terminal_result = {
                                "success": False,
                                "subtask_state": "blocked",
                                "loop_end_reason": "no_tool_calls_streak",
                                "completed_reason": plan_contract.get("completed_reason") if isinstance(plan_contract, dict) else None,
                                "plan_summary": plan_contract.get("plan_summary") if isinstance(plan_contract, dict) else None,
                            }
                            # 风险1补齐：早停前写入一次终止事实到 Agent WM（避免审计缺口）
                            try:
                                from .utils.wm_obs import append_obs_to_wm

                                wf_id = str(input_data.get("workflow_state_id") or self.workflow_state_id or "")
                                append_obs_to_wm(
                                    workflow_id=wf_id,
                                    agent_name=self.agent_name,
                                    obs_record={
                                        "iteration": iteration,
                                        "event": {
                                            "type": "loop_end",
                                            "reason": "no_tool_calls_streak",
                                            "subtask_state": "blocked",
                                            "completed_reason": terminal_result.get("completed_reason"),
                                            "plan_summary": terminal_result.get("plan_summary"),
                                        },
                                    },
                                    service=self.short_term_service,
                                )
                            except Exception as obs_err:
                                self.logger.warning(
                                    "EARLY_STOP_OBS_WRITE_FAILED agent=%s iter=%d err=%s",
                                    self.agent_name,
                                    iteration + 1,
                                    obs_err,
                                    exc_info=True,
                                )
                            final_result = await self._finalize_incomplete_results(
                                {
                                    "total_iterations": iteration + 1,
                                    "workflow_state_id": input_data.get("workflow_state_id") or self.workflow_state_id,
                                    "subtask_state": "blocked",
                                    "loop_end_reason": "no_tool_calls_streak",
                                    "completed_reason": terminal_result.get("completed_reason"),
                                    "plan_summary": terminal_result.get("plan_summary"),
                                },
                                task,
                            )
                            await self._update_progress(90, "processing", db)
                            return final_result
                        # 本轮无可执行动作且未完成：直接进入下一轮重新规划
                        continue
                
                # ACT
                self.logger.debug(f"⚡ ACT: Executing planned actions...")
                action_result = await self._execute_action(
                    action_plan, input_data, db, iteration
                )
                action_facts = self._derive_action_facts_payload(action_plan, action_result)
                try:
                    from .utils.wm_obs import append_obs_to_wm

                    obs_record = await self._observe(
                        input_data=input_data,
                        iteration=iteration,
                        action_result=action_result if isinstance(action_result, dict) else None,
                    )
                    append_obs_to_wm(
                        workflow_id=str(input_data.get("workflow_state_id") or self.workflow_state_id or ""),
                        agent_name=self.agent_name,
                        obs_record=obs_record,
                        service=self.short_term_service,
                    )
                except Exception:
                    pass
                pending_action_facts = action_facts
                await self._log_react_iteration_event(
                    iteration=iteration,
                    observation=current_iter_context,
                    action_plan=action_plan,
                    action_result=action_result,
                    action_facts=action_facts,
                )
                # 行动结果用于日志与领域反思；跨轮所需信息从 WM 推导

                # REFLECT（子类规约 + 合同回执融合）
                self.logger.debug(f"🤔 REFLECT: Evaluating results...")
                reflection = await self._reflect_on_results(
                    action_result, current_iter_context, task, iteration
                )
                # 与 PLAN 响应的合同回执融合：
                # - 不将 PLAN 回执写入 WM；仅在本轮内从 action_plan['plan_llm'] 解析并融合到 reflection，用于退出判断。
                try:
                    from .utils.tool_contracts import overlay_contract_on_reflection
                    contract = None
                    if isinstance(action_plan, dict) and isinstance(action_plan.get("plan_contract"), dict):
                        contract = action_plan.get("plan_contract")
                    if isinstance(contract, dict) and contract:
                        has_actions = False
                        try:
                            ec = action_result.get('executed_calls') if isinstance(action_result, dict) else None
                            has_actions = bool(ec) and isinstance(ec, list) and len(ec) > 0
                        except Exception:
                            has_actions = False
                        reflection = overlay_contract_on_reflection(reflection, contract, ignore_complete=has_actions)
                except Exception:
                    pass
                
                # 仅日志（不累积状态）：保留执行结果与计划摘要打印，避免维护重复的“迭代记录”结构
                try:
                    from .utils.react_logging import (
                        summarize_observation,
                        summarize_plan,
                        summarize_action_result,
                    )
                    self.logger.info(
                        "ITER_LOG iter=%d obs=%s plan=%s result=%s refl=%s",
                        iteration + 1,
                        summarize_observation(current_iter_context),
                        summarize_plan(action_plan),
                        summarize_action_result(action_result),
                        reflection.get("reflection_summary") if isinstance(reflection, dict) else "",
                    )
                except Exception:
                    pass

                # 迭代摘要日志（仅观测，不改变行为）—简化为按执行结果统计
                try:
                    executed_calls = action_result.get('executed_calls') if isinstance(action_result, dict) else None
                    executed = len(executed_calls or []) if isinstance(executed_calls, list) else 0
                    # 成功统计以统一语义：按 executed_calls[i]['success'] 判断
                    ok = 0
                    if isinstance(executed_calls, list):
                        ok = sum(1 for call in executed_calls if isinstance(call, dict) and bool(call.get('success')))
                    tool_calls_requested_count = 0
                    if isinstance(action_plan, dict) and isinstance(action_plan.get('tool_calls'), list):
                        tool_calls_requested_count = len(action_plan.get('tool_calls'))
                    self.logger.info(
                        "ITER_SUMMARY iter=%d requested=%d executed=%d ok=%d",
                        iteration + 1,
                        tool_calls_requested_count,
                        executed,
                        ok,
                    )
                except Exception:
                    pass

                # 移除默认的重复调用阶段收敛，避免在事实未稳定时干预迭代自主循环
                # 若未来需要，可通过策略/环境开关在编排层启用
                
                # 检查是否完成任务（以 PLAN 合同或领域规约裁决为准）
                if reflection.get("task_complete", False):
                    completion_gate = self._accept_completion_request(
                        stage="reflection",
                        input_data=input_data,
                        plan_context=plan_context,
                        iteration_context=current_iter_context,
                        iteration=iteration,
                        plan_contract=plan_contract,
                        reflection=reflection,
                        action_result=action_result,
                    )
                    gate_accepted = bool(completion_gate.get("accepted", True))
                    if not gate_accepted:
                        reflection = dict(reflection or {})
                        reflection["task_complete"] = False
                        self._record_completion_gate_rejection(
                            input_data=input_data,
                            iteration=iteration,
                            stage="reflection",
                            details=completion_gate,
                        )
                        self.logger.warning(
                            "COMPLETION_GATE_REJECTED agent=%s iter=%d stage=reflection reason=%s",
                            self.agent_name,
                            iteration + 1,
                            completion_gate.get("reason"),
                        )
                        continue
                    self.logger.info(f"✅ Iterative loop completed successfully after {iteration + 1} iterations")
                    
                    final_result = await self._finalize_success_results(
                        action_result, {"total_iterations": iteration + 1}
                    )
                    
                    await self._update_progress(95, "completed", db)
                    return final_result
                    
            except Exception as e:
                self.logger.error(f"❌ Iteration {iteration + 1} failed: {e}")
                
                # 仅日志：失败迭代
                try:
                    self.logger.error("ITER_ERROR iter=%d error=%s", iteration + 1, str(e))
                except Exception:
                    pass
                
                # 检查是否应该继续迭代还是提前退出
                should_continue = await self._handle_iteration_error(e, iteration, task)
                if not should_continue:
                    break
        
        # 达到最大迭代次数或提前退出
        self.logger.warning(f"⚠️ Iterative loop ended after {iteration + 1} iterations")
        
        final_result = await self._finalize_incomplete_results({
                "total_iterations": iteration + 1,
                "workflow_state_id": input_data.get("workflow_state_id") or self.workflow_state_id,
                "subtask_state": "max_iter_reached",
                "loop_end_reason": "max_iterations",
        }, task)
        await self._update_progress(90, "processing", db)
        
        return final_result

    # === OBSERVE PHASE ====================================================
    # 仅关注事实构建与可选的结构化压缩。

    # OBS 不承载“准备功能”提示，不暴露 prepared_* 引导字段

    # （已废弃）不再提供从 WM 构造状态视图的基类便捷方法；
    # 子类应直接使用 _observe 构建的 base_observation（其中已包含 WM 事实）。

    # 观察压缩策略判断与执行均委托至 utils/obs_strategy

    async def maybe_augment_observation(self, observation: Dict[str, Any]) -> Dict[str, Any]:
        """委托策略层执行可选的观察压缩（默认关闭）。"""
        try:
            from .utils.obs_strategy import maybe_compress_observation
            from ..core.config import settings as _cfg
            enabled = bool(getattr(_cfg, 'REACT_OBS_AUGMENT_ENABLED', False))
            scene_threshold = int(getattr(_cfg, 'REACT_OBS_SCENE_THRESHOLD', 8))
            size_threshold = int(getattr(_cfg, 'REACT_OBS_SIZE_THRESHOLD', 2000))
        except Exception:
            if isinstance(observation, dict):
                observation["aug_meta"] = {"used": False, "reason": "config_error"}
            return observation
        try:
            return await maybe_compress_observation(
                prompt_manager=self.prompt_manager,
                agent_name=self.agent_name,
                observation=observation,
                llm_structured_observation=self.llm_structured_observation,
                enabled=enabled,
                scene_threshold=scene_threshold,
                size_threshold=size_threshold,
            )
        except Exception as exc:
            if isinstance(observation, dict):
                observation["aug_meta"] = {"used": False, "reason": f"error:{exc.__class__.__name__}"}
            return observation


    async def _observe(
        self,
        input_data: Dict[str, Any],
        iteration: int,
        action_result: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """生成当轮 obs_record（不含 plan/context），默认不精简，仅对 action_result 做预算限制。"""
        await self._prepare_observation(
            action_result=action_result,
            input_data=input_data,
            iteration=iteration,
        )
        record: Dict[str, Any] = {"iteration": iteration}
        if action_result is not None:
            record["action_result"] = self._truncate_action_result(action_result)
        return record
    
    async def _prepare_observation(
        self,
        action_result: Optional[Dict[str, Any]],
        input_data: Dict[str, Any],
        iteration: int,
    ) -> None:
        """
        扩展点：在 ACT→OBSERVE 之间进行必要的领域写回或整理。

        默认实现不做任何处理（不消费合同、不写入状态、不统计进度）。
        子类如需写回领域事实，可在此方法中完成，仍需遵守“无状态 Agent”与“事实写入 WM/Shared WM”的原则。
        """
        return

    def _truncate_action_result(self, action_result: Dict[str, Any], max_token_budget: int = 3000) -> Any:
        """对 action_result 做简单预算限制，超限时做通用截断（不丢整条结果）。"""
        # 设计约束：OBS/WM 仅记录可复现的“执行事实”，不写入 PLAN 文本回执，避免上下文污染与双轨不一致。
        try:
            if isinstance(action_result, dict):
                action_result = dict(action_result)
                for k in ("plan_llm", "fc_plan", "contract"):
                    action_result.pop(k, None)
        except Exception:
            pass
        try:
            from .utils.json_utils import estimate_tokens, shrink_jsonable, to_jsonable
        except Exception:
            return action_result
        try:
            jsonable = to_jsonable(action_result)
            approx_tokens = estimate_tokens(jsonable)
            if max_token_budget and approx_tokens > max_token_budget:
                truncated = shrink_jsonable(
                    jsonable,
                    max_string_chars=600,
                    max_list_items=60,
                    max_dict_items=80,
                    max_depth=7,
                )
                approx_tokens2 = estimate_tokens(truncated)
                if approx_tokens2 > max_token_budget:
                    truncated = shrink_jsonable(
                        truncated,
                        max_string_chars=220,
                        max_list_items=20,
                        max_dict_items=40,
                        max_depth=5,
                    )
                    approx_tokens2 = estimate_tokens(truncated)
                if isinstance(truncated, dict):
                    meta = dict(truncated.get("action_result_meta") or {})
                    meta.update(
                        {
                            "truncated": True,
                            "reason": "over_token_budget",
                            "original_tokens": int(approx_tokens),
                            "budget": int(max_token_budget),
                            "tokens_after": int(approx_tokens2),
                        }
                    )
                    truncated["action_result_meta"] = meta
                return truncated
            return jsonable
        except Exception:
            return action_result

    # === THINK / PLAN PHASE ==============================================
    
    @abstractmethod
    async def _think_and_plan(
        self, 
        current_state: Dict[str, Any], 
        task: Task, 
        iteration: int
    ) -> Dict[str, Any]:
        """
        思考和规划下一步行动
        
        Args:
            current_state: 当前观察到的状态
            task: 任务对象
            iteration: 当前迭代次数
            
        Returns:
            行动计划
        """
        pass
    
    # === ACT PHASE ========================================================

    @abstractmethod
    async def _execute_action(
        self, 
        action_plan: Dict[str, Any], 
        input_data: Dict[str, Any], 
        db: Session,
        iteration: int
    ) -> Dict[str, Any]:
        """
        执行计划的行动
        
        Args:
            action_plan: 行动计划
            input_data: 原始输入数据
            db: 数据库会话
            iteration: 当前迭代次数
            
        Returns:
            行动执行结果
        """
        pass
    
    # === REFLECT PHASE ====================================================

    async def _reflect_on_results(
        self, 
        action_result: Dict[str, Any], 
        current_state: Dict[str, Any], 
        task: Task,
        iteration: int
    ) -> Dict[str, Any]:
        """Optional REFLECT hook.

        Notes:
        - This framework's completion decision is primarily driven by PLAN contracts.
          REFLECT is kept as an optional hook for lightweight per-iteration receipts
          (e.g. a short summary or progress snapshot emission).
        - Return value must be a dict; `overlay_contract_on_reflection(...)` may inject
          `task_complete` / `completed_reason` into this dict.
        """
        summary = ""
        try:
            action_performed = action_result.get("action_performed") if isinstance(action_result, dict) else None
            if isinstance(action_performed, str) and action_performed:
                summary = action_performed
        except Exception:
            summary = ""
        return {"success": True, "reflection_summary": summary}
    
    # === FINALIZATION / ERROR HANDLING ===================================

    async def _finalize_success_results(
        self, 
        final_action_result: Dict[str, Any], 
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        整理成功完成的最终结果
        
        可以被子类重写以定制结果格式
        """
        return dict(final_action_result or {})
    
    async def _finalize_incomplete_results(
        self, 
        context: Dict[str, Any], 
        task: Task
    ) -> Dict[str, Any]:
        """
        整理未完成任务的结果（最大迭代次数或提前退出）
        
        可以被子类重写以提供fallback逻辑
        """
        # 注意：MAS 架构下的交付 SoT 在 Shared/MAS WM；ReAct 基类不再通过“上一轮 action_result 缓存”兜底交付。
        # 这里仅返回明确的未完成回执，供 orchestrator 做门控/重试决策；子类可覆写并从 MAS 聚合部分产物。
        total_iters = int(context.get("total_iterations") or 0)
        subtask_state = context.get("subtask_state") or "max_iter_reached"
        loop_end_reason = context.get("loop_end_reason") or "max_iterations"
        completed_reason = context.get("completed_reason")
        plan_summary = context.get("plan_summary")
        result: Dict[str, Any] = {
            "success": False,
            "subtask_state": str(subtask_state),
            "loop_end_reason": str(loop_end_reason),
            "total_iterations": total_iters,
        }
        if completed_reason:
            result["completed_reason"] = completed_reason
        if plan_summary:
            result["plan_summary"] = plan_summary
        wf_id = context.get("workflow_state_id") or self.workflow_state_id
        if wf_id:
            result["workflow_state_id"] = wf_id
        return result
    
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
            self.logger.error(f"❌ Error in final iteration {iteration + 1}, stopping iterative loop")

        return should_continue

    def _record_completion_gate_rejection(
        self,
        *,
        input_data: Dict[str, Any],
        iteration: int,
        stage: str,
        details: Optional[Dict[str, Any]],
    ) -> None:
        try:
            from .utils.wm_obs import append_obs_to_wm

            append_obs_to_wm(
                workflow_id=str(input_data.get("workflow_state_id") or self.workflow_state_id or ""),
                agent_name=self.agent_name,
                obs_record={
                    "iteration": iteration,
                    "event": {
                        "type": "completion_gate_rejected",
                        "stage": stage,
                        "reason": (details or {}).get("reason"),
                        "details": dict(details or {}),
                    },
                },
                service=self.short_term_service,
            )
        except Exception:
            pass

    # === PLAN 上下文构造（分区：task/static/iteration） ===
    def _build_plan_context(
        self,
        input_data: Dict[str, Any],
        iteration_context: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """构造 PLAN 输入上下文，分区而非平铺。"""
        from .utils.plan_context import build_plan_context

        return build_plan_context(
            input_data=input_data,
            iteration_context=iteration_context,
            workflow_state_id=str(input_data.get("workflow_state_id") or self.workflow_state_id or ""),
            service=self.short_term_service,
            progress_kind=self._get_plan_progress_kind(),
            include_execution_contract=self._include_execution_contract_in_plan_context(),
        )

    def _get_plan_progress_kind(self) -> Optional[str]:
        return None

    def _include_execution_contract_in_plan_context(self) -> bool:
        return True

    def _accept_completion_request(
        self,
        *,
        stage: str,
        input_data: Dict[str, Any],
        plan_context: Dict[str, Any],
        iteration_context: Optional[Dict[str, Any]],
        iteration: int,
        plan_contract: Optional[Dict[str, Any]] = None,
        reflection: Optional[Dict[str, Any]] = None,
        action_result: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return {"accepted": True}
    
    # === PLAN 消息构造（通用）：系统模板 + 观察 JSON ===
    def build_plan_messages(self, plan_context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """构造 THINK/PLAN 阶段消息。

        要求：
        - 必须加载到 agents/<agent>.system 模板；缺失时抛 AgentError（遵循 Fail-Fast 与可审计）。
        - 可选加载 agents/<agent>.plan 模板（若存在则拼接在 system 之后）。
        - user 消息为事实 JSON（不包含工具名/参数名）。
        """
        import json as _json
        # PLAN 输入事实 JSON：同时作为 user content 与 plan 模板变量（facts_json）
        try:
            from .utils.json_utils import to_jsonable

            facts_payload = to_jsonable(plan_context or {})
            facts_json = _json.dumps(facts_payload, ensure_ascii=False)
        except Exception as exc:
            try:
                self.logger.warning(
                    "PLAN_CONTEXT_SERIALIZE_FAILED agent=%s err=%s",
                    self.agent_name,
                    exc,
                    exc_info=True,
                )
            except Exception:
                pass
            try:
                facts_json = str(plan_context or {})
            except Exception:
                facts_json = "{}"
        template_vars = {"facts_json": facts_json, "plan_context_json": facts_json}
        # 渲染系统模板
        sys_text: str = ""
        cfg_name = str(self.agent_name)
        try:
            sys_rendered = self.prompt_manager.render_template(
                cfg_name,
                "system",
                variables={},
                use_cache=True,
                auto_reload=False,
            )
            sys_text = sys_rendered.strip() if isinstance(sys_rendered, str) else ""
        except Exception as e:
            # 直接失败：系统提示词是必需项
            raise AgentError(f"PLAN system prompt load failed for agent={self.agent_name} cfg={cfg_name}: {e}")
        if not sys_text:
            # 直接失败：系统提示词不得为空
            raise AgentError(f"PLAN system prompt is empty for agent={self.agent_name} cfg={cfg_name}")
        plan_text: str = ""
        if sys_text:
            try:
                plan_rendered = self.prompt_manager.render_template(
                    cfg_name,
                    "plan",
                    variables=template_vars,
                    use_cache=True,
                    auto_reload=False,
                )
                plan_text = plan_rendered.strip() if isinstance(plan_rendered, str) else ""
                if plan_text:
                    self.logger.info(
                        f"PLAN_GUIDE_TEMPLATE agent={self.agent_name} cfg={cfg_name} len={len(plan_text)}"
                    )
            except Exception:
                plan_text = ""
        if plan_text:
            combined = f"{sys_text.strip()}\n\n{plan_text.strip()}"
            sys_text = combined.strip()
        if sys_text:
            try:
                # 打印模板来源文件，便于定位加载路径
                cfg_obj = self.prompt_manager.get_config(cfg_name)
                src = getattr(cfg_obj, 'source_path', None) if cfg_obj else None
                self.logger.info(f"PLAN_SYS_TEMPLATE agent={self.agent_name} cfg={cfg_name} len={len(sys_text)} src={src}")
            except Exception:
                pass
        # 上下文 JSON（不做过滤/改造）
        return [
            {"role": "system", "content": sys_text},
            {"role": "user", "content": facts_json},
        ]

    def _extract_plan_contract_source_text(self, action_plan: Any) -> str:
        if not isinstance(action_plan, dict):
            return ""
        plan_llm = action_plan.get("plan_llm")
        if isinstance(plan_llm, dict):
            content = plan_llm.get("content")
            if isinstance(content, str) and content.strip():
                return content
        content = action_plan.get("content")
        if isinstance(content, str) and content.strip():
            return content
        return ""

    async def _normalize_plan_contract_from_text(self, raw_plan_text: str) -> Dict[str, Any]:
        """将 PLAN 的自然语言输出规整为最小退出合同 JSON。

        重要约束：
        - 仅做“抽取/规整”，不做二次规划与决策；
        - 输入仅为 raw_plan_text（不再注入 plan_context），避免二次推理偏移。
        """
        raw = (raw_plan_text or "").strip()
        if not raw:
            return {}

        try:
            sys_text = self.prompt_manager.render_template(
                "react_plan_contract",
                "system",
                variables={},
                use_cache=True,
                auto_reload=False,
            ).strip()
            user_text = self.prompt_manager.render_template(
                "react_plan_contract",
                "user",
                variables={"raw_plan_text": raw},
                use_cache=True,
                auto_reload=False,
            ).strip()
        except Exception as e:
            raise AgentError(f"react_plan_contract prompt render failed: {e}") from e

        llm = self.get_llm("plan")
        try:
            resp = await llm.chat_completion(
                messages=[
                    {"role": "system", "content": sys_text},
                    {"role": "user", "content": user_text},
                ],
                response_format={"type": "json_object"},
                temperature=0.0,
                max_tokens=512,
                thinking={"type": "disabled"},
            )
        except Exception as e:
            raise AgentError(f"react_plan_contract LLM call failed: {e}") from e

        content = resp.get("content") if isinstance(resp, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise AgentError("react_plan_contract returned empty content")

        from .utils.json_utils import safe_json_loads  # type: ignore

        try:
            data = safe_json_loads(
                content,
                logger=self.logger,
                context="react_plan_contract",
                allow_fallback=False,
                allow_syntax_repair=True,
            )
        except Exception as e:
            raise AgentError(f"react_plan_contract JSON parse failed: {e}") from e

        if not isinstance(data, dict):
            raise AgentError("react_plan_contract output is not a JSON object")
        if "task_complete" not in data or not isinstance(data.get("task_complete"), bool):
            raise AgentError("react_plan_contract missing task_complete:boolean")
        if "completed_reason" in data and data.get("completed_reason") is not None and not isinstance(data.get("completed_reason"), str):
            raise AgentError("react_plan_contract completed_reason must be string|null")
        if "plan_summary" not in data or not isinstance(data.get("plan_summary"), str):
            raise AgentError("react_plan_contract missing plan_summary:string")
        return data


    async def llm_structured_observation(self, messages: List[Dict[str, Any]], schema: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """调用 LLM 生成结构化观察，并委托统一校验工具做解析与 schema 校验。

        默认严格模式（可通过 settings.REACT_OBS_SCHEMA_STRICT 关闭）：
        - 缺少必须字段或类型不符 → 抛 AgentError，避免静默传播以保障可审计。
        - 存在 jsonschema 时进行严格校验；否则执行最小校验（例如必须存在 scenes 数组）。
        """
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
            strict = True
            try:
                from ..core.config import settings as _cfg
                strict = bool(getattr(_cfg, 'REACT_OBS_SCHEMA_STRICT', True))
            except Exception:
                strict = True
            from .utils.obs_validator import parse_and_validate_structured
            data = parse_and_validate_structured(
                content=str(content),
                schema=schema,
                strict=strict,
                logger=self.logger,
                context="structured_observation",
                require_scenes_if_declared=True,
            )
            return data
        except Exception as e:
            # 输出关键信息帮助定位（不掩盖错误）
            try:
                pv = (content or '')
                if isinstance(pv, str):
                    pv = pv.strip().replace("\n", " ")[:240]
                self.logger.warning(f"结构化观察失败：{e} | 使用了response_format=json_object | content_preview=\"{pv}\"")
            except Exception:
                self.logger.warning(f"结构化观察失败：{e}")
            # 严格模式下抛错，非严格模式返回 None（调用方可据此降级）
            try:
                from ..core.config import settings as _cfg
                strict = bool(getattr(_cfg, 'REACT_OBS_SCHEMA_STRICT', True))
            except Exception:
                strict = True
            if strict:
                raise
            return None

    # === 通用FC回合：仅返回 LLM 规划结果，不执行 ===
    async def run_fc_round(
        self,
        messages: List[Dict[str, Any]],
        context_description: str = "",
        temperature: float = 0.2,
        tools_override: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """执行一轮 FC 规划：只返回计划，不执行工具。"""
        # 在进入 FC 前，按需注入额外中立上下文（默认不注入，放在 system 之后）
        try:
            from .utils.fc_messages import inject_after_system
            enriched = inject_after_system(messages, self.build_react_context_messages())
        except Exception:
            enriched = list(messages or [])
        try:
            total_len = sum(
                len(msg.get("content", ""))
                for msg in enriched
                if isinstance(msg, dict) and isinstance(msg.get("content"), str)
            )
            self.logger.info(
                "FC_PROMPT_TOTAL[%s]: total_chars=%d",
                context_description or "",
                total_len,
            )
        except Exception:
            pass
        fc = await self.llm_function_call(
            messages=enriched,
            context_description=context_description,
            temperature=temperature,
            tools_override=tools_override,
            **kwargs
        )
        # 解析最小契约 JSON（若有），供 REFLECT 阶段提取 task_complete/completed_reason
        # 不再解析合同：仅返回规划输出（由上层决定是否消费 llm_response）
        return {
            "fc_plan": fc,
        }


    def _derive_action_facts_payload(
        self,
        action_plan: Dict[str, Any],
        action_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """从 ACT 输出派生中立的执行日志，供 OBS 和审计使用。"""
        executed_calls = []
        if isinstance(action_result, dict):
            executed_calls = list(action_result.get("executed_calls") or [])
        tool_calls_requested = []
        if isinstance(action_plan, dict):
            tool_calls_requested = list(action_plan.get("tool_calls") or [])
        round_metrics = {}
        if isinstance(action_result, dict):
            round_metrics = action_result.get("react_metrics") or {}
        actions = []
        if isinstance(action_result, dict):
            actions = list(action_result.get("act_log") or [])
        duration_ms = None
        if isinstance(action_result, dict):
            duration_ms = action_result.get("duration_ms")
        _, react_metrics, act_log = derive_action_facts(
            tool_calls_requested=tool_calls_requested,
            executed_calls=executed_calls,
            round_metrics=round_metrics,
            actions=actions,
            duration_ms=duration_ms,
        )
        if react_metrics:
            try:
                self.logger.info("REACT_METRICS %s", json.dumps(react_metrics, ensure_ascii=False))
            except Exception:
                pass
        return {
            "act_log": act_log,
        }

    # === 可选注入扩展点（默认禁用）：在 PLAN 消息中注入额外中立上下文 ===

    def build_react_context_messages(self) -> List[Dict[str, Any]]:
        """默认不向 PLAN 消息注入任何派生摘要，避免干预模型决策。

        若未来需要，可通过配置在子类中安全开启，并确保仅注入中立事实。
        """
        return []

    async def _log_react_iteration_event(
        self,
        *,
        iteration: int,
        observation: Dict[str, Any],
        action_plan: Dict[str, Any],
        action_result: Dict[str, Any],
        action_facts: Optional[Dict[str, Any]],
    ) -> None:
        if not self._episodic_logging_enabled():
            return
        wf_id = self.workflow_state_id
        if not wf_id:
            return
        try:
            from .memory.long_term.episodic import log_react_iteration
        except Exception:
            return
        act_log = None
        if isinstance(action_result, dict):
            act_log = action_result.get("act_log")
        if not act_log and isinstance(action_facts, dict):
            act_log = action_facts.get("act_log")
        react_metrics = None
        if isinstance(action_result, dict):
            react_metrics = action_result.get("react_metrics")
        try:
            await log_react_iteration(
                workflow_id=str(wf_id),
                agent_name=self.agent_name,
                iteration=iteration,
                observation=self._sanitize_for_log(observation),
                action_plan=self._sanitize_for_log(action_plan),
                action_result=self._sanitize_for_log(action_result),
                act_log=self._sanitize_for_log(act_log or []),
                react_metrics=self._sanitize_for_log(react_metrics or {}),
            )
        except Exception:
            self.logger.debug("episodic log skipped (wf=%s iter=%s)", wf_id, iteration, exc_info=True)

    def _episodic_logging_enabled(self) -> bool:
        try:
            from ..core.config import settings as _cfg

            return bool(getattr(_cfg, "REACT_EPISODIC_LOG_ENABLED", False))
        except Exception:
            return False

    def _sanitize_for_log(self, payload: Any) -> Any:
        try:
            return json.loads(json.dumps(payload, ensure_ascii=False, default=str))
        except Exception:
            try:
                return json.loads(json.dumps(str(payload), ensure_ascii=False))
            except Exception:
                return str(payload)

    # === 最小契约解析与合并（不含供应商/工具信息） ===
    # 旧合同解析/应用逻辑已移除：停止裁决交由领域 REFLECT 与 WM 事实判定

    # 合同解析/叠加工具函数已下沉至 utils.tool_contracts

    # 已移除：build_progress_summary / build_scratchpad
    # === 通用结果获取与进展归约（移除：不在 Agent 内维护快照） ===

    # reflect_with_reducer 与增量辅助已移除：
    # - REFLECT 仅做领域规约（覆盖式写回），不追踪“上一轮 keys”与新增统计。
    # - 统计/监控交由日志与外部监控层处理，避免在 Agent 内引入状态。

    async def log_decision(self, decision: str, reasoning: str = ""):
        """记录重要决策到决策日志"""
        self.logger.info(f"📝 Decision: {decision}")
