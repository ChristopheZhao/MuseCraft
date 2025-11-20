from __future__ import annotations

"""应用层的 WorkingMemory 使用辅助函数。

这里定义 scope 命名约定以及 MAS / Agent 级记忆的初始化逻辑，确保这些业务决策
不会下沉到 memory 基础设施中。
"""

from typing import Optional

from app.agents.memory.short_term import WorkingMemory, get_working_memory_service
from app.agents.memory.short_term.service import MemoryNotInitializedError
from typing import Any

MAS_SCOPE_PREFIX = "mas"
AGENT_SCOPE_PREFIX = "agent"


def agent_scope(workflow_id: str, agent_name: str) -> str:
    return f"{AGENT_SCOPE_PREFIX}:{workflow_id}:{agent_name}"


def mas_scope(workflow_id: str) -> str:
    return f"{MAS_SCOPE_PREFIX}:{workflow_id}"


def ensure_mas_memory(workflow_id: str) -> WorkingMemory:
    """确保 MAS 级 WorkingMemory 存在并返回引用。"""
    service = get_working_memory_service()
    scope = mas_scope(workflow_id)
    try:
        return service.get(workflow_id, scope)
    except MemoryNotInitializedError:
        return service.create_or_get(workflow_id, scope)


def ensure_agent_memory(workflow_id: str, agent_name: str, *, shared_view: Optional[WorkingMemory] = None) -> WorkingMemory:
    """确保某个 Agent 的 WorkingMemory 已初始化，必要时同步 MAS 视图。"""
    service = get_working_memory_service()
    scope = agent_scope(workflow_id, agent_name)
    try:
        return service.get(workflow_id, scope)
    except MemoryNotInitializedError:
        shared = shared_view or ensure_mas_memory(workflow_id)
        return service.create_or_get(workflow_id, scope, owner_agent=agent_name, shared_view=shared)


def write_shared_fact(workflow_id: str, key: str, value: Any) -> None:
    """Write a fact into MAS WorkingMemory under facts.<key>."""
    wm = ensure_mas_memory(workflow_id)
    wm.put(key, value)


def read_shared_fact(workflow_id: str, key: str, default: Any = None) -> Any:
    """Read a fact from MAS WorkingMemory, with default fallback."""
    wm = ensure_mas_memory(workflow_id)
    return wm.get(key, default)


__all__ = ["agent_scope", "mas_scope", "ensure_mas_memory", "ensure_agent_memory", "write_shared_fact", "read_shared_fact"]
