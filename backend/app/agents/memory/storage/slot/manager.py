"""Base classes for slot-backed memory managers."""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from typing import Any, Dict, Optional, Iterable

from ...interfaces import SlotStorageBackend, WorkflowMemoryBackend
from .registry import SlotRegistry
from .schema import SlotSchema, SlotScope


class SlotAccessError(RuntimeError):
    """Raised when an agent violates slot access rules."""


class SlotValidationError(ValueError):
    """Raised when slot validation fails."""


class ACLManager:
    """Simple ACL manager mapping slot_id -> {agent -> set(perms)}."""

    def __init__(self) -> None:
        self._acl = defaultdict(lambda: defaultdict(set))
        self._lock = threading.RLock()

    def grant(self, slot_id: str, agent: str, permissions: Optional[list] = None) -> None:
        perms = permissions or ["read", "write"]
        with self._lock:
            self._acl[slot_id][agent].update(perms)

    def check(self, slot_id: str, agent: Optional[str], permission: str) -> bool:
        if agent is None:
            return True
        with self._lock:
            agent_perms = self._acl.get(slot_id, {}).get(agent)
            wildcard_perms = self._acl.get(slot_id, {}).get("*")
        if not agent_perms and not wildcard_perms:
            return True
        if agent_perms and permission in agent_perms:
            return True
        if wildcard_perms and permission in wildcard_perms:
            return True
        return False


class MemoryAuditLogger:
    """Lightweight audit logger."""

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self._logger = logger or logging.getLogger("memory.audit")

    def record(self, *, workflow_id: str, slot_id: str, op: str, agent: Optional[str], size: int) -> None:
        try:
            self._logger.info(
                "MEMORY_SLOT_%s workflow=%s slot=%s agent=%s size=%s",
                op.upper(),
                workflow_id,
                slot_id,
                agent or "",
                size,
            )
        except Exception:
            pass


class BaseSlotStore(SlotStorageBackend):
    """Thread-safe slot store shared by concrete managers."""

    def __init__(
        self,
        registry: SlotRegistry,
        *,
        acl: Optional[ACLManager] = None,
        audit: Optional[MemoryAuditLogger] = None,
    ) -> None:
        self._registry = registry
        self._acl = acl or ACLManager()
        self._audit = audit or MemoryAuditLogger()
        self._lock = threading.RLock()
        # workflow_id -> slot_id -> value or (value, ts)
        self._store: Dict[str, Dict[str, Any]] = defaultdict(dict)
        self._logger = logging.getLogger(self.__class__.__name__)

    def _get_schema(self, slot_id: str) -> SlotSchema:
        try:
            return self._registry.get(slot_id)
        except Exception as exc:
            raise SlotValidationError(str(exc)) from exc

    def _check_acl(self, slot_id: str, agent: Optional[str], permission: str) -> None:
        if not self._acl.check(slot_id, agent, permission):
            raise SlotAccessError(f"Agent {agent} lacks {permission} permission for slot {slot_id}")

    def set_slot(self, workflow_id: str, slot_id: str, value: Any, *, agent: Optional[str] = None) -> None:
        schema = self._get_schema(slot_id)
        self._check_acl(slot_id, agent, "write")
        schema.validate_value(value)
        with self._lock:
            previous = self._store[workflow_id].get(slot_id)
            to_store = value
            if schema.reducer and previous is not None:
                try:
                    to_store = schema.reducer(previous, value)
                except Exception as exc:
                    raise SlotValidationError(
                        f"Reducer failed for slot {slot_id}: {exc}"
                    ) from exc
            self._store[workflow_id][slot_id] = to_store
        size = len(str(value))
        self._audit.record(workflow_id=workflow_id, slot_id=slot_id, op="write", agent=agent, size=size)

    def get_slot(self, workflow_id: str, slot_id: str, *, agent: Optional[str] = None) -> Any:
        schema = self._get_schema(slot_id)
        self._check_acl(slot_id, agent, "read")
        with self._lock:
            value = self._store[workflow_id].get(slot_id)
            if value is None and schema.default_factory:
                value = schema.default_factory()
                self._store[workflow_id][slot_id] = value
        size = len(str(value)) if value is not None else 0
        self._audit.record(workflow_id=workflow_id, slot_id=slot_id, op="read", agent=agent, size=size)
        return value

    def delete_slot(self, workflow_id: str, slot_id: str) -> None:
        with self._lock:
            self._store[workflow_id].pop(slot_id, None)

    def clear_workflow(self, workflow_id: str) -> None:
        with self._lock:
            self._store.pop(workflow_id, None)

    def has_slot(self, slot_id: str) -> bool:
        try:
            self._get_schema(slot_id)
            return True
        except SlotValidationError:
            return False


class SharedMemoryManager(BaseSlotStore):
    """Manager for workflow scoped slots."""

    def __init__(self, registry: SlotRegistry, **kwargs: Any) -> None:
        super().__init__(registry, **kwargs)


class SlotWorkflowBackend(WorkflowMemoryBackend):
    """Workflow-level adapter that exposes slot storage via generic interface."""

    def __init__(
        self,
        registry: SlotRegistry,
        *,
        acl: Optional[ACLManager] = None,
        audit: Optional[MemoryAuditLogger] = None,
    ) -> None:
        self._store = SharedMemoryManager(registry, acl=acl, audit=audit)
        self._registry = registry

    def set(self, workflow_id: str, key: str, value: Any, *, agent: Optional[str] = None) -> None:
        self._store.set_slot(workflow_id, key, value, agent=agent)

    def get(self, workflow_id: str, key: str, *, agent: Optional[str] = None) -> Any:
        return self._store.get_slot(workflow_id, key, agent=agent)

    def delete(self, workflow_id: str, key: str) -> None:
        self._store.delete_slot(workflow_id, key)

    def clear(self, workflow_id: str) -> None:
        self._store.clear_workflow(workflow_id)

    def list_keys(self) -> Iterable[str]:
        return [schema.slot_id for schema in self._registry.list()]


class IterationMemoryManager(BaseSlotStore):
    """[Deprecated] 迭代槽位管理器。

    旧版通过 SlotScope.AGENT/ITERATION 管理“迭代记忆”的短期状态。
    在新的记忆架构下，短期记忆统一由 WorkingMemory 管理，本类仅保留
    为了兼容老的配置/导入，不再实际管理任何 slot。
    """

    def __init__(self, registry: SlotRegistry, **kwargs: Any) -> None:  # pragma: no cover - legacy
        super().__init__(registry, **kwargs)
        self._logger.warning("IterationMemoryManager is deprecated and no longer manages any slots.")

    def set_slot(self, workflow_id: str, slot_id: str, value: Any, *, agent: Optional[str] = None) -> None:  # pragma: no cover
        raise SlotValidationError(
            f"Slot {slot_id} is no longer managed by IterationMemoryManager; use WorkingMemory instead."
        )

    def get_slot(self, workflow_id: str, slot_id: str, *, agent: Optional[str] = None) -> Any:  # pragma: no cover
        raise SlotValidationError(
            f"Slot {slot_id} is no longer managed by IterationMemoryManager; use WorkingMemory instead."
        )
