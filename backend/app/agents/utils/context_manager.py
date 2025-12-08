"""
上下文管理器占位：后续为 Agent 统一提供从 WM + 状态视图读取上下文的能力。

设计约束（实施时遵守）：
- 上下文构建由独立的 context manager 完成，显式从 Agent WM 读取所需事实/产物/OBS 记录和状态视图。
- 不做裁剪/决策，裁剪/窗口策略由上层配置（默认不裁剪）。
- 仅作用于 Agent WM；共享产物仍由 MAS WM 提供。

当前实现：读取 Agent WM 的 facts、scene_outputs.*、obs_records，以及可选的状态视图，默认不裁剪；提供 max_turn/max_token_budget 参数占位，当前仅支持截断 obs_records 长度。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .memory_helpers import get_agent_working_memory
from ..adapters.state.mas_state import build_mas_state_view

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

    state_view 不传时仅返回 WM 数据，不自动构建 MAS 状态视图。
    """
    ctx: Dict[str, Any] = {}
    if not workflow_id or not agent_name:
        return ctx
    wm = get_agent_working_memory(str(workflow_id), agent_name, service=service)

    # 基础 facts
    try:
        facts = wm.get("facts", {}) if hasattr(wm, "facts") else {}
        if isinstance(facts, dict):
            ctx["facts"] = dict(facts)
    except Exception:
        pass

    # 产物：按 scene_outputs.* 聚合
    try:
        outputs_bucket = {}
        facts_all = wm.get("facts", {}) if hasattr(wm, "facts") else {}
        if isinstance(facts_all, dict):
            for key, val in facts_all.items():
                if isinstance(key, str) and key.startswith("scene_outputs."):
                    outputs_bucket[key] = val
        if outputs_bucket:
            ctx["scene_outputs"] = outputs_bucket
    except Exception:
        pass

    # OBS 记录（若有）
    try:
        obs_records = wm.get("obs_records", [])
        if isinstance(obs_records, list) and obs_records:
            if max_turn and max_turn > 0:
                ctx["obs_records"] = list(obs_records)[-int(max_turn):]
            else:
                ctx["obs_records"] = list(obs_records)
    except Exception:
        pass

    if state_view and isinstance(state_view, dict):
        ctx["state_view"] = state_view
    elif workflow_id:
        try:
            ctx["state_view"] = build_mas_state_view(workflow_id, service=service)
        except Exception as e:
            raise f"构建 MAS 状态视图失败: {e}"
    return ctx


__all__ = ["build_agent_context"]
