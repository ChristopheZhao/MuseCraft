from __future__ import annotations

"""WorkingMemoryService 全局访问入口（短期记忆服务）"""

from typing import Optional

from typing import Optional, Callable

from .service import WorkingMemoryService
from ..storage.in_memory import ShortTermMemoryStore, InMemoryShortTermStore

_global_service: Optional[WorkingMemoryService] = None


def get_working_memory_service() -> WorkingMemoryService:
    """Return the global WorkingMemoryService singleton."""
    global _global_service
    if _global_service is None:
        _global_service = WorkingMemoryService(store_factory=lambda: InMemoryShortTermStore())
    return _global_service


def set_working_memory_service(
    service: WorkingMemoryService,
) -> None:
    global _global_service
    _global_service = service


def invalidate_working_memory(scope: str, workflow_state_id: Optional[str]) -> None:
    """Invalidate cached WorkingMemory for given scope/workflow."""
    service = get_working_memory_service()
    service.reset(scope, workflow_state_id)


def reset_workflow_working_memory(workflow_state_id: str) -> None:
    """Invalidate all WorkingMemory instances for workflow."""
    service = get_working_memory_service()
    service.reset_workflow(workflow_state_id)


__all__ = [
    "get_working_memory_service",
    "set_working_memory_service",
    "invalidate_working_memory",
    "reset_workflow_working_memory",
]
