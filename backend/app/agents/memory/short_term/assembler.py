from __future__ import annotations

"""WorkingMemoryAssembler - 从 Shared WM 构建/同步 WorkingMemory（短期记忆）。"""

from typing import Dict, Optional

from .working_memory import WorkingMemory
from .builder import WorkingMemoryBuilder


class WorkingMemoryAssembler:
    """Assembles WorkingMemory from shared WM, with small scoped cache.

    - No business rules; no context trimming; no asset persistence.
    - Reads shared WM and uses WorkingMemoryBuilder to build/sync.
    """

    def __init__(
        self,
        journal_max_events: int = 5,
    ):
        self._builder = WorkingMemoryBuilder(journal_max_events)
        # cache key: (task_id, agent_name)
        self._cache: Dict[tuple[str, str], WorkingMemory] = {}

    def get_or_create(
        self,
        task_id: str,
        scope: str,
        *,
        shared_view: Optional[WorkingMemory] = None,
        owner_agent: Optional[str] = None,
        context: Optional[Dict] = None,
    ) -> WorkingMemory:
        key = (str(task_id), str(scope))
        wm = self._cache.get(key)
        if wm is None:
            wm = self._builder.build(
                task_id,
                scope,
                shared_view,
                owner_agent=owner_agent,
                context=context,
            )
            self._cache[key] = wm
        elif shared_view is not None:
            self._builder.sync(wm, shared_view, owner_agent=owner_agent)
        return wm

    def invalidate(self, task_id: str, scope: str) -> None:
        key = (str(task_id), str(scope))
        self._cache.pop(key, None)


__all__ = ["WorkingMemoryAssembler"]
