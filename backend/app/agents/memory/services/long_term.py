"""Simple long-term memory service accessible to agents/tools."""
from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from ..interfaces import LongTermMemoryService
from ..long_term.stores import MemoryImportance, MemoryItem, MemoryType


class SimpleLongTermMemoryService(LongTermMemoryService):
    """Wrapper around MemoryManager providing uniform store/retrieve APIs."""

    def __init__(self, memory_manager) -> None:
        self._manager = memory_manager

    # --- High-level fact APIs (existing interface) ------------------------
    async def store_fact(
        self,
        workflow_id: str,
        payload: Dict[str, Any],
        *,
        tags: Optional[Iterable[str]] = None,
        memory_type: MemoryType = MemoryType.WORKING,
        importance: MemoryImportance = MemoryImportance.MEDIUM,
        agent_id: str = "memory_service",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        return await self._manager.store_memory(
            content=payload,
            memory_type=memory_type,
            importance=importance,
            tags=list(tags or []),
            agent_id=agent_id,
            task_id=workflow_id,
            metadata=metadata or {},
        )

    async def retrieve_facts(
        self,
        workflow_id: str,
        *,
        tags: Optional[Iterable[str]] = None,
        limit: int = 10,
        memory_type: Optional[MemoryType] = None,
    ) -> list[Dict[str, Any]]:
        memories = await self._manager.retrieve_memories(
            tags=list(tags or []),
            memory_type=memory_type,
            task_id=workflow_id,
            limit=limit,
        )
        return [m.content for m in memories if isinstance(m, MemoryItem)]

    # --- Extended accessors for agent/tool use (hide underlying manager) ---
    async def store_memory(
        self,
        *,
        content: Dict[str, Any],
        memory_type: MemoryType,
        importance: MemoryImportance,
        tags: Iterable[str],
        agent_id: str,
        task_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        return await self._manager.store_memory(
            content=content,
            memory_type=memory_type,
            importance=importance,
            tags=list(tags or []),
            agent_id=agent_id,
            task_id=task_id,
            metadata=metadata or {},
        )

    async def retrieve_memories(
        self,
        *,
        tags: Optional[Iterable[str]] = None,
        memory_type: Optional[MemoryType] = None,
        task_id: Optional[str] = None,
        limit: int = 10,
    ) -> list[MemoryItem]:
        return await self._manager.retrieve_memories(
            tags=list(tags or []),
            memory_type=memory_type,
            task_id=task_id,
            limit=limit,
        )

    async def search_memories(
        self,
        *,
        query: Optional[str] = None,
        tags: Optional[Iterable[str]] = None,
        agent_id: Optional[str] = None,
        limit: int = 10,
        task_id: Optional[str] = None,
    ) -> list[MemoryItem]:
        return await self._manager.search_memories(
            query=query,
            tags=list(tags or []),
            agent_id=agent_id,
            limit=limit,
            task_id=task_id,
        )

    async def get_memory_stats(self) -> Dict[str, Any]:
        return await self._manager.get_memory_stats()


__all__ = ["SimpleLongTermMemoryService"]
