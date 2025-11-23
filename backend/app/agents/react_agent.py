"""
ReAct Agent - 提供规划-行动-观察循环能力的基类
"""
import asyncio
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable, Set
from sqlalchemy.orm import Session

from .base import BaseAgent, AgentError
from ..models import Task, AgentExecution, AgentType
from .utils.obs_builder import derive_action_facts
from .memory.context.view_builder import build_react_context_view
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
        self.logger.info(f"🔄 {agent_name} initialized with iterative loop (max_iterations={max_iterations})")
        # Agent 内不保存跨回合状态
    
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

        # 初始化：清理工作记忆引用缓存（WorkingMemory 由 Orchestrator 统一创建）。
        self.reset_iteration_memory_cache()
        # 无缓存执行摘要：上一轮信息全部从 WM 推导
        
        self.logger.info(f"🔄 Starting iterative loop for {self.agent_name} (max_iterations={self.max_iterations})")
        
        # 不跨轮保存状态；每轮上下文显式从 WM / 状态视图读取
        pending_action_facts: Optional[Dict[str, Any]] = None
        last_action_result: Optional[Dict[str, Any]] = None
        for iteration in range(self.max_iterations):
            iteration_start_progress = 10 + (iteration * 80 // self.max_iterations)
            await self._update_progress(
                execution,
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
                        state_view=None,
                        max_turn=None,
                        max_token_budget=None,
                    )
                except Exception:
                    current_iter_context = {}
                pending_action_facts = None

                # THINK & PLAN
                self.logger.debug(f"🧠 THINK & PLAN: Developing action strategy...")
                action_plan = await self._think_and_plan(
                    current_iter_context, task, execution, iteration
                )
                
                # ACT
                self.logger.debug(f"⚡ ACT: Executing planned actions...")
                action_result = await self._execute_action(
                    action_plan, input_data, execution, db, iteration
                )
                action_facts = self._derive_action_facts_payload(action_plan, action_result)
                try:
                    from .utils.wm_obs import append_obs_to_wm

                    obs_record: Dict[str, Any] = {
                        "iteration": iteration,
                        "action_plan": action_plan,
                        "action_result": action_result,
                        "observation": current_iter_context,
                    }
                    append_obs_to_wm(
                        workflow_id=str(input_data.get("workflow_state_id") or self.workflow_state_id or ""),
                        agent_name=self.agent_name,
                        obs_record=obs_record,
                    )
                except Exception:
                    pass
                pending_action_facts = action_facts
                if isinstance(action_result, dict):
                    last_action_result = action_result
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
                # 1) 优先使用 action_result['contract']（若存在并符合键约束）
                # 2) 否则尝试从 action_result['fc_plan'] 或 action_result['plan_llm'] 中解析 content JSON
                try:
                    from .utils.tool_contracts import parse_plan_contract, overlay_contract_on_reflection
                    contract = None
                    if isinstance(action_result, dict):
                        cand = action_result.get('contract')
                        if isinstance(cand, dict):
                            contract = cand
                        if contract is None:
                            plan_obj = action_result.get('fc_plan') or action_result.get('plan_llm')
                            parsed = parse_plan_contract(plan_obj)
                            if isinstance(parsed, dict) and parsed:
                                contract = parsed
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
                    planned_calls = 0
                    if isinstance(action_plan, dict) and isinstance(action_plan.get('tool_calls'), list):
                        planned_calls = len(action_plan.get('tool_calls'))
                    self.logger.info(
                        "ITER_SUMMARY iter=%d planned=%d executed=%d ok=%d",
                        iteration + 1,
                        planned_calls,
                        executed,
                        ok,
                    )
                except Exception:
                    pass

                # 移除默认的重复调用阶段收敛，避免在事实未稳定时干预迭代自主循环
                # 若未来需要，可通过策略/环境开关在编排层启用
                
                # 检查是否完成任务（以 PLAN 合同或领域规约裁决为准）
                if reflection.get("task_complete", False):
                    self.logger.info(f"✅ Iterative loop completed successfully after {iteration + 1} iterations")
                    
                    final_result = await self._finalize_success_results(
                        action_result, {"total_iterations": iteration + 1}
                    )
                    
                    await self._update_progress(execution, 95, "completed", db)
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
            "last_action_result": last_action_result,
        }, task)
        await self._update_progress(execution, 90, "processing", db)
        
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

    @abstractmethod
    async def _observe_current_state(
        self, 
        input_data: Dict[str, Any], 
        base_observation: Dict[str, Any], 
        iteration: int
    ) -> Dict[str, Any]:
        """
        基于 WorkingMemory facts 构建领域增强后的观察结果

        Args:
            input_data: 原始输入数据
            base_observation: 已包含 WM 事实与 act 摘要的基础观察
            iteration: 当前迭代次数

        Returns:
            当前状态的观察结果
        """
        pass

    async def _observe(
        self,
        input_data: Dict[str, Any],
        iteration: int,
        action_facts: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        默认的 OBSERVE 流程：先执行 ACT→OBSERVE 归并，再构造观察视图。
        子类如需扩展，可重写本方法或其中的 `_prepare_observation`。
        """
        await self._prepare_observation(
            action_result=None,
            input_data=input_data,
            iteration=iteration,
        )
        try:
            wm = self.wm
        except AgentError:
            wm = None

        act_log = None
        if isinstance(action_facts, dict):
            act_log = action_facts.get("act_log")

        observation = build_react_context_view(
            wm,
            iteration=iteration,
            act_log=act_log,
        )
        observation = await self._observe_current_state(
            input_data,
            observation,
            iteration,
        )
        observation = await self.maybe_augment_observation(observation)
        return observation
    
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
        if not isinstance(action_result, dict):
            return
        # 无操作：OBS 构建仅依赖 WM 事实 + 执行摘要

    # === THINK / PLAN PHASE ==============================================
    
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
    
    # === ACT PHASE ========================================================

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
    
    # === REFLECT PHASE ====================================================

    @abstractmethod
    async def _reflect_on_results(
        self, 
        action_result: Dict[str, Any], 
        current_state: Dict[str, Any], 
        task: Task,
        iteration: int
    ) -> Dict[str, Any]:
        """
        反思行动结果（领域规约，不做进度统计与合同裁决）
        
        Args:
            action_result: 行动执行结果
            current_state: 当前状态
            task: 任务对象
            iteration: 当前迭代次数
            
        Returns:
            反思结果（仅规约）：
            - task_complete: bool（可选，若领域已判定完成）
            - completed_reason: str（可选，诊断用途）
            - 其它领域需要的非状态信息
        """
        pass
    
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
        # 优先返回最后一次行动的结果（若存在）
        last_action_result = context.get("last_action_result")
        if isinstance(last_action_result, dict):
            return dict(last_action_result)
        # 无部分结果可返回，抛出明确错误
        total_iters = int(context.get("total_iterations") or 0)
        raise AgentError(f"Iterative loop ended without results after {total_iters} iterations")
    
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
    
    # === PLAN 消息构造（通用）：系统模板 + 观察 JSON ===
    def build_plan_messages(self, observation: Dict[str, Any]) -> List[Dict[str, Any]]:
        """构造 THINK/PLAN 阶段消息。

        要求：
        - 必须加载到 agents/<agent>.system 模板；缺失时抛 AgentError（遵循 Fail-Fast 与可审计）。
        - 可选加载 agents/<agent>.plan 模板（若存在则拼接在 system 之后）。
        - user 消息为事实 JSON（不包含工具名/参数名）。
        """
        import json as _json
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
                    variables={},
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
        # 观察 JSON
        try:
            # 过滤可能的衍生键，保持 PLAN 仅基于“事实”输入
            obs_for_plan = {}
            if isinstance(observation, dict):
                obs_for_plan = {k: v for k, v in observation.items() if k not in ("aug", "aug_meta")}
            obs_json = _json.dumps(obs_for_plan or {}, ensure_ascii=False)
        except Exception:
            obs_json = str(observation or {})
        return [
            {"role": "system", "content": sys_text},
            {"role": "user", "content": obs_json},
        ]

    def get_observation_schema(self) -> Dict[str, Any]:
        """默认观测 Schema（通用、领域无关）：
        - 仅描述客观事实字段；不包含模型决策/统计/提示性信息
        - 领域专用字段（如 image_url）应在子类重写时添加
        """
        scene_schema = {
            "type": "object",
            "properties": {
                "scene_number": {
                    "oneOf": [
                        {"type": "integer"},
                        {"type": "string", "pattern": "^[0-9]+$"},
                    ]
                },
                "depends_on_scene": {"type": ["integer", "string", "null"]},
                "visual_description": {"type": "string"},
                "narrative_description": {"type": "string"},
                "duration": {"type": ["number", "string"]},
            },
            "required": ["scene_number"],
            "additionalProperties": True,
        }
        array_of_int_or_str = {
            "type": "array",
            "items": {
                "oneOf": [
                    {"type": "integer"},
                    {"type": "string", "pattern": "^[0-9]+$"},
                ]
            },
        }
        return {
            "type": "object",
            "properties": {
                "scenes": {"type": "array", "items": scene_schema},
                "completed_scene_numbers": array_of_int_or_str,
                "failed_scene_numbers": array_of_int_or_str,
            },
            "required": ["scenes"],
            "additionalProperties": True,
        }


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
        planned_calls = []
        if isinstance(action_plan, dict):
            planned_calls = list(action_plan.get("tool_calls") or [])
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
            planned_calls=planned_calls,
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
