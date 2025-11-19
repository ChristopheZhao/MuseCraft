"""Workflow facts backend implementations."""
from __future__ import annotations

from typing import Any, Dict, Optional

from ..interfaces import WorkflowFactsBackend
from ..services.coordinator import MemoryCoordinator
from ..short_term.workflow_facts import WorkflowFactStoreError


class SlotFactsBackend(WorkflowFactsBackend):
    """Slot-based implementation of workflow fact storage."""

    def __init__(self, coordinator: MemoryCoordinator, alias_map: Dict[str, str]) -> None:
        if coordinator is None:
            raise WorkflowFactStoreError("Memory coordinator is not initialized")
        self._coordinator = coordinator
        self._alias_map = dict(alias_map or {})

    def _resolve(self, key: str) -> str:
        if not key:
            raise WorkflowFactStoreError("Key must be non-empty")
        if "." in key:
            return key
        slot = self._alias_map.get(key)
        if not slot:
            raise WorkflowFactStoreError(f"Unknown alias '{key}'")
        return slot

    def put(self, workflow_id: str, key: str, value: Any, *, agent: Optional[str] = None) -> None:
        slot = self._resolve(key)
        try:
            self._coordinator.set_memory(str(workflow_id), slot, value, agent=agent)
        except Exception as exc:
            raise WorkflowFactStoreError(str(exc)) from exc

    def get(self, workflow_id: str, key: str, *, default: Any = None, agent: Optional[str] = None) -> Any:
        slot = self._resolve(key)
        try:
            value = self._coordinator.get_memory(str(workflow_id), slot, agent=agent)
        except Exception as exc:
            raise WorkflowFactStoreError(str(exc)) from exc
        return default if value is None else value

    def delete(self, workflow_id: str, key: str) -> None:
        slot = self._resolve(key)
        try:
            self._coordinator.delete_memory(str(workflow_id), slot)
        except Exception as exc:
            raise WorkflowFactStoreError(str(exc)) from exc

    def list_aliases(self) -> Dict[str, str]:
        return dict(self._alias_map)


__all__ = ["SlotFactsBackend"]
