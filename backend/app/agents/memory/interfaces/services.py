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
