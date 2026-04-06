"""Abstract service interfaces for short/long-term memory."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Iterable, Optional


class ShortTermMemoryService(ABC):
    @abstractmethod
    def create_or_get(
        self,
        workflow_state_id: str,
        scope: str,
        *,
        owner_agent: Optional[str] = None,
        shared_view: Optional[Any] = None,
    ) -> Any:
        ...

    @abstractmethod
    def write(self, workflow_state_id: str, scope: str, apply_patch) -> None:
        ...


class LongTermMemoryService(ABC):
    @abstractmethod
    async def store_fact(self, workflow_id: str, payload: Dict[str, Any], *, tags: Optional[Iterable[str]] = None) -> str:
        ...

    @abstractmethod
    async def retrieve_facts(self, workflow_id: str, *, tags: Optional[Iterable[str]] = None, limit: int = 10) -> list[Dict[str, Any]]:
        ...

    # Extended agent/tool-facing APIs
    @abstractmethod
    async def store_memory(
        self,
        *,
        content: Dict[str, Any],
        memory_type,
        importance,
        tags: Iterable[str],
        agent_id: str,
        task_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        ...

    @abstractmethod
    async def retrieve_memories(
        self,
        *,
        tags: Optional[Iterable[str]] = None,
        memory_type=None,
        task_id: Optional[str] = None,
        limit: int = 10,
    ):
        ...

    @abstractmethod
    async def search_memories(
        self,
        *,
        query: Optional[str] = None,
        tags: Optional[Iterable[str]] = None,
        agent_id: Optional[str] = None,
        limit: int = 10,
        task_id: Optional[str] = None,
    ):
        ...

    @abstractmethod
    async def get_memory_stats(self) -> Dict[str, Any]:
        ...
