from __future__ import annotations

from typing import Any, Dict, Optional
from copy import deepcopy


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
            static_ctx = input_data.get("static_context") or {}
            if isinstance(static_ctx, dict) and static_ctx:
                ctx["static_context"] = deepcopy(static_ctx)
    except Exception:
        pass
    if isinstance(iteration_context, dict):
        ctx["iteration_context"] = deepcopy(iteration_context)
    return ctx


__all__ = ["build_plan_context"]
