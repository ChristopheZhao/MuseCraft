"""
Image Generator ReAct Agent - 正确的批量处理迭代逻辑
"""
import json
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from .react_agent import ReActAgent, AgentError
from .utils.progress_snapshot import emit_progress_snapshot
from .utils.artifacts import (
    normalize_executed_calls_to_artifacts,
    persist_scene_outputs,
    finalize_scene_outputs,
)
from .utils.memory_helpers import get_mas_working_memory
from ..models import Task, AgentType
from ..core.config import settings
from .adapters.memory_views import build_image_generation_context
from .adapters.state.scene_iteration import SceneIterationStateBuilder


class ImageGeneratorAgent(ReActAgent):
    """
    Image Generator ReAct Agent - 场景驱动的图像生成

    ReAct 流程由 LLM 主导：
    1. OBSERVE: 汇总 WorkingMemory 中的场景事实；
    2. PLAN: 基于观察生成一次 FC 调用，决定本轮是否执行工具或直接收尾；
    3. ACT: 执行 FC 返回的工具调用（若有），写回产物；
    4. REFLECT: 合并执行结果，判断是否继续迭代。
    """
    
    def __init__(self, llms=None, memory_services=None):
        super().__init__(
            agent_type=AgentType.IMAGE_GENERATOR,
            agent_name="image_generator",
            max_iterations=settings.IMAGE_GENERATOR_MAX_ITERATIONS,
            timeout_seconds=600,
            llms=llms,
            memory_services=memory_services,
        )
        self._scene_state_builder = SceneIterationStateBuilder()
    # 覆盖基类的上下文注入：本 Agent 交给通用 FC 逻辑处理上下文提示
    def build_react_context_messages(self) -> List[Dict[str, Any]]:
        return []


    async def maybe_augment_observation(self, observation: Dict[str, Any]) -> Dict[str, Any]:
        """ImageAgent 使用最小观察视图，不做额外压缩或总结。"""
        if isinstance(observation, dict):
            observation["aug_meta"] = {"used": False, "reason": "disabled"}
        return observation
    
    async def _execute_action(
        self, 
        action_plan: Dict[str, Any], 
        input_data: Dict[str, Any],
        db: Session,
        iteration: int
    ) -> Dict[str, Any]:
        """ACT: 执行批量图像生成"""
        
        action_label = action_plan.get("action") or "noop"
        plan_llm = action_plan.get("plan_llm")
        tool_calls = list(action_plan.get("tool_calls") or [])
        if action_label == "noop" or not tool_calls:
            summary = {
                "action": action_label,
                "plan_llm": plan_llm,
                "reason": action_plan.get("reason") or ("no_tool_calls" if action_label == "noop" else "empty_plan"),
                "executed_calls": 0,
                "success": 0,
            }
            self.logger.info("🚀 ACT: no tool calls to execute: %s", summary)
            return {
                "action_performed": action_label,
                "executed_calls": [],
                "act_log": [],
                "react_metrics": {},
                "plan_llm": plan_llm,
                "success": True,
                "subtask_state": "complete",
                "processed": 0,
            }

        self.logger.info("🚀 ACT: execute %d planned calls", len(tool_calls))
        exec_out = await self.execute_tool_calls(tool_calls, collect_facts=True)
        executed_calls: List[Dict[str, Any]] = list(exec_out.get("executed_calls") or [])
        act_log = exec_out.get("act_log") or []
        react_metrics = exec_out.get("react_metrics") or {}
        planned_functions = [
            ((call or {}).get("function") or {}).get("name")
            for call in tool_calls
            if isinstance((call or {}).get("function"), dict)
        ]
        planned_total = len(tool_calls)

        results = await self._persist_executed_results(executed_calls or [])
        if results:
            try:
                self.logger.info("ImageAgent generated %d results", len(results))
            except Exception:
                pass

        exec_scenes = [c.get("args", {}).get("scene_number") for c in executed_calls if isinstance(c, dict)]
        parsed_scenes = [r.get("scene_number") for r in results if isinstance(r, dict)]
        successes = sum(1 for call in executed_calls if call.get("success"))
        executed_tools: List[str] = []
        for call in executed_calls:
            fn = call.get("tool")
            if isinstance(fn, str) and fn:
                executed_tools.append(fn)

        self.logger.info(
            "ACT_DIAG(image): planned_total=%d executed=%d success=%d exec_scenes=%s parsed_scenes=%s tools=%s",
            planned_total,
            len(executed_calls),
            successes,
            exec_scenes,
            parsed_scenes,
            sorted(set(executed_tools)),
        )
        summary_payload = {
            "action": action_label,
            "plan_llm": plan_llm,
            "planned_calls": planned_total,
            "planned_functions": [fn for fn in planned_functions if fn],
            "executed_calls": len(executed_calls),
            "success": successes,
            "scenes": parsed_scenes,
            "tools": sorted(set(executed_tools)),
        }
        # 仅日志纪录，不再保留跨轮摘要
        try:
            cleaned = json.loads(json.dumps(summary_payload, ensure_ascii=False, default=str))
            self.logger.info("ACT_SUMMARY %s", json.dumps(cleaned, ensure_ascii=False))
        except Exception:
            pass
        # 构造本轮 obs 事件摘要，暂挂在结果中供后续情景记忆/调试使用
        try:
            from .utils.obs_events import build_obs_events_from_executed_calls
            obs_event = build_obs_events_from_executed_calls(executed_calls, iteration)
        except Exception:
            obs_event = None
        batch_scene_ids = {int(sn) for sn in exec_scenes if isinstance(sn, int)}
        # 不用“产物清单”覆盖反思输入：返回 executed_calls，反思将回退读取 Base 写入的 last_round_results
        return {
            "action_performed": action_label,
            "batch_size": len(batch_scene_ids),
            "executed_calls": executed_calls,
            "act_log": act_log,
            "react_metrics": react_metrics,
            "plan_llm": plan_llm,
            "obs_event": obs_event,
        }
    
    @staticmethod
    def _coerce_int_list(values: Any) -> List[int]:
        if not values:
            return []
        result: List[int] = []
        candidates = values if isinstance(values, list) else list(values)
        for item in candidates:
            try:
                result.append(int(item))
            except Exception:
                continue
        return sorted(set(result))

    @staticmethod
    def _coerce_int(value: Any) -> Optional[int]:
        if value is None:
            return None
        try:
            return int(value)
        except Exception:
            return None

    async def _persist_executed_results(self, executed_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        wf_id = str(self.workflow_state_id or "")
        shared_wm = get_mas_working_memory(wf_id) if wf_id else None
        return await persist_scene_outputs(
            executed_calls=executed_calls,
            kind="image",
            agent_memory=None,
            shared_memory=shared_wm,
            include_prompt=True,
        )

    async def _finalize_success_results(self, final_action_result: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """打包最终产出：从 Shared WM 聚合（单一事实源），构造 orchestrator 所需结构。
        返回字段：final_completed_scenes / final_failed_scenes
        """
        wf_id = context.get("workflow_state_id") or self.workflow_state_id
        finals, finals_failed = finalize_scene_outputs(
            kind="image",
            workflow_id=str(wf_id) if wf_id else None,
            agent_memory=self.wm,
        )

        return {
            **(final_action_result or {}),
            "final_completed_scenes": finals,
            "final_failed_scenes": finals_failed,
        }
    
    @emit_progress_snapshot
    async def _reflect_on_results(
        self, 
        action_result: Dict[str, Any], 
        current_state: Dict[str, Any],
        task: Task,
        iteration: int
    ) -> Dict[str, Any]:
        """REFLECT：领域规约（覆盖式写回），不判断增量/进度。

        - 直接将本轮结果中的 prepared_prompts 写入 Shared WM 对应槽（覆盖式）。
        - 返回轻量摘要，不计算“新增/剩余”。
        """
        action_performed = action_result.get("action_performed", "")
        if action_performed == "task_completed":
            return {
                "success": True,
                "task_complete": True,
                "completed_reason": "所有图像生成任务已完成",
            }

        # 规约：从 executed_calls 规范化提取带 prompt_text 的结果
        executed_calls = action_result.get("executed_calls") or []
        generation_results = normalize_executed_calls_to_artifacts(
            executed_calls, kind="image", include_prompt=True
        )

        summary = f"处理 {len(generation_results or [])} 个场景"
        return {
            "success": True,
            "task_complete": False,
            "reflection_summary": summary,
        }

    # ReActAgent兼容性方法
    async def _think_and_plan(
        self,
        current_state: Dict[str, Any],
        task: Task,
        iteration: int
    ) -> Dict[str, Any]:
        """PLAN：直接通过 FC 产出 tool_calls，ACT 仅执行。"""
        observation = current_state or {}
        messages = self.build_plan_messages(observation)
        fc_plan = await self.llm_function_call(
            messages=messages,
            context_description="image_generation_plan_fc",
            temperature=0.2,
        )
        planned_calls = list(fc_plan.get("tool_calls") or []) if isinstance(fc_plan, dict) else []
        plan_llm = fc_plan.get("llm_response") if isinstance(fc_plan, dict) else None

        if not planned_calls:
            self.logger.info("PLAN decision: no_calls_planned")
            return {
                "action": "noop",
                "plan_llm": plan_llm,
                "reason": "no_calls_planned",
            }

        self.logger.info("PLAN decision: execute_planned_calls count=%d", len(planned_calls))
        return {
            "action": "execute_planned_calls",
            "tool_calls": planned_calls,
            "plan_llm": plan_llm,
        }
