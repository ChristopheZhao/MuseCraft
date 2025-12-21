"""
上下文管理器占位：后续为 Agent 统一提供从 WM + 状态视图读取上下文的能力。

设计约束（实施时遵守）：
- 上下文构建由独立的 context manager 完成，显式从 Agent WM 读取所需事实/产物/OBS 记录和状态视图。
- 不做裁剪/决策，裁剪/窗口策略由上层配置（默认不裁剪）。
- 共享产物事实仍由 Shared/MAS WM 提供（例如 `scene_outputs.*`）；Agent WM 只保存迭代过程记录。

当前实现（迭代上下文 iteration_context）：
- 仅从 Agent WM 读取：`facts`、`obs_records`；
- 不注入派生统计视图（如 `agent_iteration_view`）；LLM 直接基于 `obs_records` 推理，派生视图仅用于日志/接口返回。
- 不注入 MASStateView（仅用于 orchestrator/UI 展示，避免双轨统计进入 LLM 输入）。

参数说明：
- max_turn：仅用于截断 `obs_records` 的长度；
- max_token_budget：占位，暂未实现基于 token 的裁剪策略；
- state_view：占位（兼容旧调用），当前不消费。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .memory_helpers import get_agent_working_memory

if TYPE_CHECKING:
    from ..memory.short_term.service import WorkingMemoryService


def build_agent_context(
    workflow_id: str,
    agent_name: str,
    *,
    service: "WorkingMemoryService",
    state_view: Optional[Dict[str, Any]] = None,
    max_turn: Optional[int] = None,
    max_token_budget: Optional[int] = None,  # 占位，暂未实现基于 token 的裁剪
) -> Dict[str, Any]:
    """从 Agent WM 构建上下文，可选按 max_turn 截断 obs_records。

    说明：
    - 该方法只从“Agent WM”构建迭代上下文（iteration_context），不注入 MAS 级状态视图。
      MASStateView 仅用于 orchestrator/UI 展示，不进入 ReAct 规划输入，避免双轨统计。
    """
    ctx: Dict[str, Any] = {}
    if not workflow_id or not agent_name:
        return ctx
    wm = get_agent_working_memory(str(workflow_id), agent_name, service=service)

    # 基础 facts
    try:
        facts = wm.get("facts", {})
        if isinstance(facts, dict):
            ctx["facts"] = dict(facts)
    except Exception:
        pass

    # OBS 记录（若有）
    try:
        obs_records = wm.get("obs_records", [])
        if isinstance(obs_records, list) and obs_records:
            # 迭代轨迹（trajectory）是 ReAct 规划所需的事实来源；
            # 这里不做“精挑字段/删结果”的消费侧裁剪，只保证 JSONable 并可选做窗口截断。
            try:
                from .json_utils import to_jsonable
            except Exception:
                to_jsonable = None  # type: ignore

            normalized: List[Dict[str, Any]] = []
            for rec in obs_records:
                if not isinstance(rec, dict):
                    continue
                normalized.append(to_jsonable(rec) if callable(to_jsonable) else rec)
            if max_turn and max_turn > 0:
                ctx["obs_records"] = normalized[-int(max_turn):]
            else:
                ctx["obs_records"] = normalized
    except Exception:
        pass

    return ctx


__all__ = ["build_agent_context"]
