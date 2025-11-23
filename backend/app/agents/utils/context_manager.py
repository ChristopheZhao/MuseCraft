"""
上下文管理器占位：后续为 Agent 统一提供从 WM + 状态视图读取上下文的能力。

设计约束（实施时遵守）：
- 上下文构建由独立的 context manager 完成，显式从 Agent WM 读取所需事实/产物/OBS 记录和状态视图。
- 不做裁剪/决策，裁剪/窗口策略由上层配置（默认不裁剪）。
- 仅作用于 Agent WM；共享产物仍由 MAS WM 提供。

当前为占位实现，待迭代循环重构时补充具体读取逻辑。
"""
from __future__ import annotations

from typing import Any, Dict, Optional


def build_agent_context(
    workflow_id: str,
    agent_name: str,
    *,
    state_view: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """占位：返回基础上下文骨架，后续填充 WM 读取逻辑。"""
    ctx: Dict[str, Any] = {}
    if state_view and isinstance(state_view, dict):
        ctx["state_view"] = state_view
    return ctx


__all__ = ["build_agent_context"]
