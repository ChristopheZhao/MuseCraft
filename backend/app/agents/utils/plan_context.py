from __future__ import annotations

from typing import Any, Dict, Optional
from copy import deepcopy


def _normalize_task_assignment(task_ctx: Dict[str, Any]) -> Dict[str, Any]:
    assignment: Dict[str, Any] = {}
    if not isinstance(task_ctx, dict):
        return assignment
    agent = str(task_ctx.get("agent") or "").strip()
    if agent:
        assignment["agent"] = agent
    if task_ctx.get("run") is not None:
        assignment["run"] = bool(task_ctx.get("run"))
    mission = str(task_ctx.get("mission") or "").strip()
    if mission:
        assignment["mission"] = mission
    deliverable = str(task_ctx.get("deliverable") or "").strip()
    if deliverable:
        assignment["deliverable"] = deliverable
    constraints = task_ctx.get("constraints")
    if isinstance(constraints, list):
        assignment["constraints"] = [
            str(item).strip() for item in constraints if str(item or "").strip()
        ]
    runtime_hints = task_ctx.get("runtime_hints")
    if isinstance(runtime_hints, dict) and runtime_hints:
        assignment["runtime_hints"] = deepcopy(runtime_hints)
    order = task_ctx.get("order")
    if order is not None:
        assignment["order"] = order
    return assignment


def build_plan_context(
    *,
    input_data: Dict[str, Any],
    iteration_context: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """统一构造 PLAN 输入上下文（task/static/iteration 分区）。"""
    ctx: Dict[str, Any] = {}
    try:
        if isinstance(input_data, dict):
            task_ctx = input_data.get("task") or {}
            if isinstance(task_ctx, dict) and task_ctx:
                # 使用深拷贝避免下游修改输入
                ctx["task"] = deepcopy(task_ctx)
                task_assignment = _normalize_task_assignment(task_ctx)
                if task_assignment:
                    ctx["task_assignment"] = task_assignment
            static_ctx = input_data.get("static_context") or {}
            if isinstance(static_ctx, dict) and static_ctx:
                ctx["static_context"] = deepcopy(static_ctx)
            execution_contract = input_data.get("execution_contract") or {}
            if isinstance(execution_contract, dict) and execution_contract:
                ctx["execution_contract"] = deepcopy(execution_contract)
    except Exception:
        pass
    if isinstance(iteration_context, dict):
        ctx["iteration_context"] = deepcopy(iteration_context)
    return ctx


__all__ = ["build_plan_context"]
