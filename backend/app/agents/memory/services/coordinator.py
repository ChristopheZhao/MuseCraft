"""Workflow-level memory coordinator abstraction."""
from __future__ import annotations

from typing import Iterable, Optional, Any

from ..interfaces import WorkflowMemoryBackend


class MemoryCoordinator:
    """Facade to perform workflow-scoped read/write using a generic backend."""

    def __init__(
        self,
        backend: WorkflowMemoryBackend,
        *,
        iteration_manager: Optional[Any] = None,
    ) -> None:
        self._backend = backend
        self._iteration_manager = iteration_manager

    def set_memory(self, workflow_id: str, key: str, value: Any, *, agent: Optional[str] = None) -> None:
        self._backend.set(workflow_id, key, value, agent=agent)

    def get_memory(self, workflow_id: str, key: str, *, agent: Optional[str] = None) -> Any:
        return self._backend.get(workflow_id, key, agent=agent)

    def delete_memory(self, workflow_id: str, key: str) -> None:
        self._backend.delete(workflow_id, key)

    def clear_workflow(self, workflow_id: str) -> None:
        self._backend.clear(workflow_id)

    def list_keys(self) -> Iterable[str]:
        return self._backend.list_keys()


__all__ = ["MemoryCoordinator"]
