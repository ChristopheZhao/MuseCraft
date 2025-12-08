"""Centralized creation of memory subsystem dependencies."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from ..long_term.manager import LongTermMemoryManager
from ..long_term.stores import BaseMemoryStore, DictMemoryStore, SQLiteMemoryStore
from ..services.coordinator import MemoryCoordinator
from ..storage.backend_factory import create_workflow_backend

_LOGGER = logging.getLogger("memory.management")


@dataclass
class MemoryManagement:
    """Bundle of memory subsystem components ready for injection."""

    memory_coordinator: MemoryCoordinator
    long_term_manager: LongTermMemoryManager


_DEFAULT_MANAGEMENT: Optional[MemoryManagement] = None


def build_memory_management(
    *,
    storage_backend: Optional[str] = None,
    stores: Optional[Dict[str, BaseMemoryStore]] = None,
    backend_options: Optional[Dict[str, Any]] = None,
    memory_config: Optional[Dict[str, Any]] = None,
) -> MemoryManagement:
    """Create a new set of memory subsystem components."""

    backend_name = (storage_backend or os.getenv("MEMORY_STORAGE_BACKEND") or "dict").lower()
    backend_kwargs = dict(backend_options or {})
    try:
        workflow_backend = create_workflow_backend(kind=backend_name, **backend_kwargs)
    except ValueError as exc:
        _LOGGER.warning("Memory backend '%s' unavailable (%s); falling back to dict backend", backend_name, exc)
        workflow_backend = create_workflow_backend(kind="dict", **backend_kwargs)
    coordinator = MemoryCoordinator(backend=workflow_backend)

    store_backend_name = (os.getenv("MEMORY_BACKEND", "sqlite")).lower()
    store_map: Dict[str, BaseMemoryStore] = dict(stores or {})
    if "default" not in store_map:
        if store_backend_name == "sqlite" and SQLiteMemoryStore is not None:
            store_map["default"] = SQLiteMemoryStore()
            _LOGGER.info("Using SQLiteMemoryStore as default memory backend")
        else:
            if store_backend_name == "sqlite" and SQLiteMemoryStore is None:
                _LOGGER.warning(
                    "MEMORY_BACKEND=sqlite requested but SQLite backend unavailable; falling back to DictMemoryStore"
                )
            store_map["default"] = DictMemoryStore()

    manager = LongTermMemoryManager(
        stores=store_map,
        config=memory_config or {"enable_consolidation": False, "enable_cleanup": False},
    )

    return MemoryManagement(
        memory_coordinator=coordinator,
        long_term_manager=manager,
    )


def get_default_memory_management() -> MemoryManagement:
    """Return (and lazily build) the default shared memory management bundle."""

    global _DEFAULT_MANAGEMENT
    if _DEFAULT_MANAGEMENT is None:
        _DEFAULT_MANAGEMENT = build_memory_management()
    return _DEFAULT_MANAGEMENT


__all__ = ["MemoryManagement", "build_memory_management", "get_default_memory_management"]
