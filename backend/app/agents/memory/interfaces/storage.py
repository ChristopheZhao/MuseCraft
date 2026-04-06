"""Abstract storage interfaces for memory backends."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Iterable, Optional, Protocol


class SlotSchemaProtocol(Protocol):
    slot_id: str
    scope: Any


class SlotSchemaProvider(ABC):
    """Provides slot schema metadata without exposing concrete storage types."""

    @abstractmethod
    def get_schema(self, slot_id: str) -> SlotSchemaProtocol:
        ...

    @abstractmethod
    def list_schemas(self) -> Iterable[SlotSchemaProtocol]:
        ...


class SlotStorageBackend(ABC):
    """Abstract interface for slot-aware backends (schema+ACL)."""

    @abstractmethod
    def set_slot(self, workflow_id: str, slot_id: str, value: Any, *, agent: str | None = None) -> None:
        ...

    @abstractmethod
    def get_slot(self, workflow_id: str, slot_id: str, *, agent: str | None = None) -> Any:
        ...

    @abstractmethod
    def delete_slot(self, workflow_id: str, slot_id: str) -> None:
        ...

    @abstractmethod
    def clear_workflow(self, workflow_id: str) -> None:
        ...


class WorkflowMemoryBackend(ABC):
    """Generic workflow-scoped key/value backend."""

    @abstractmethod
    def set(self, workflow_id: str, key: str, value: Any, *, agent: Optional[str] = None) -> None:
        ...

    @abstractmethod
    def get(self, workflow_id: str, key: str, *, agent: Optional[str] = None) -> Any:
        ...

    @abstractmethod
    def delete(self, workflow_id: str, key: str) -> None:
        ...

    @abstractmethod
    def clear(self, workflow_id: str) -> None:
        ...

    @abstractmethod
    def list_keys(self) -> Iterable[str]:
        ...


class WorkflowFactsBackend(ABC):
    """Backend interface for workflow-level fact storage."""

    @abstractmethod
    def put(self, workflow_id: str, key: str, value: Any, *, agent: Optional[str] = None) -> None:
        ...

    @abstractmethod
    def get(self, workflow_id: str, key: str, *, default: Any = None, agent: Optional[str] = None) -> Any:
        ...

    @abstractmethod
    def delete(self, workflow_id: str, key: str) -> None:
        ...

    @abstractmethod
    def list_aliases(self) -> Dict[str, str]:
        ...
