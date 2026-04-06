"""obs_events

为 ReAct Agent 提供简单的 obs_t 事件构造工具（领域中立）。

obs_t 用于描述“当前这一轮执行了什么、结果如何”的轻量摘要：
- iteration: 当前迭代轮次（0-based）
- steps: 每次工具调用的一条摘要记录
"""
from __future__ import annotations

from typing import Any, Dict, List


def build_obs_events_from_executed_calls(
    executed_calls: List[Dict[str, Any]],
    iteration: int,
) -> Dict[str, Any]:
    """根据 executed_calls 构造领域中立的 obs_t 摘要。

    每个 step 仅保留决策相关的关键字段：
    - tool: 逻辑工具名（不存在供应商细节）
    - action: 工具内部动作名（如果可用）
    - success: 是否成功
    - error_type: 失败类型（如 timeout/business_failure），成功时为 None
    - tags: 挂载领域标签，例如 scene_id/resource_id 等
    """
    steps: List[Dict[str, Any]] = []
    for call in executed_calls or []:
        if not isinstance(call, dict):
            continue
        tool_name = call.get("tool") or ((call.get("function") or {}).get("name"))
        if isinstance(tool_name, dict):
            tool_name = tool_name.get("name")
        action_name = None
        fn = call.get("function") or {}
        if isinstance(fn, dict):
            action_name = fn.get("name")
        success = bool(call.get("success"))
        error_type = call.get("error_type") or (call.get("metadata") or {}).get("error_type")
        tags: Dict[str, Any] = {}
        args = call.get("args") or ((call.get("function") or {}).get("arguments") or {})
        if isinstance(args, dict):
            if args.get("scene_number") is not None:
                tags["scene_id"] = args.get("scene_number")
        step = {
            "tool": str(tool_name) if tool_name is not None else "",
            "action": str(action_name) if action_name is not None else "",
            "success": success,
            "error_type": error_type,
            "tags": tags,
        }
        steps.append(step)

    return {
        "iteration": int(iteration),
        "steps": steps,
    }


__all__ = ["build_obs_events_from_executed_calls"]

