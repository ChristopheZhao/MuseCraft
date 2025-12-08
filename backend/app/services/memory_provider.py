"""Helpers for constructing and sharing memory-related services."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING, Any, Callable

from ..core.config import settings

if TYPE_CHECKING:
    from ..agents.memory.managers import MemoryManagement
    from ..agents.memory.services.coordinator import MemoryCoordinator
    from ..agents.memory.services.long_term import SimpleLongTermMemoryService
    from ..agents.memory.short_term.service import WorkingMemoryService
    from ..agents.memory.storage.in_memory import ShortTermMemoryStore
    from .global_memory_service import GlobalMemoryService


@dataclass
class MemoryServices:
    global_service: GlobalMemoryService
    long_term: "SimpleLongTermMemoryService"
    short_term: "WorkingMemoryService"


_default_services: Optional[MemoryServices] = None


def build_memory_services(
    *,
    short_term_store_factory: Optional[Callable[[], "ShortTermMemoryStore"]] = None,
) -> MemoryServices:
    # Lazy imports to avoid circular deps during module import
    from ..agents.memory.managers import build_memory_management
    from ..agents.memory.services.long_term import SimpleLongTermMemoryService
    from ..agents.memory.short_term.service import WorkingMemoryService
    from ..agents.memory.storage.in_memory import create_short_term_store
    from .global_memory_service import GlobalMemoryService

    management = build_memory_management(
        storage_backend=settings.MEMORY_WORKFLOW_BACKEND,
    )
    long_term = SimpleLongTermMemoryService(management.memory_manager)
    global_service = GlobalMemoryService(management, long_term_service=long_term)

    factory = short_term_store_factory or (lambda: create_short_term_store(kind="memory"))
    wm_service = WorkingMemoryService(store_factory=factory)

    services = MemoryServices(
        global_service=global_service,
        long_term=long_term,
        short_term=wm_service,
    )
    # Note: set_working_memory_service removed - use injected short_term instead
    return services


__all__ = [
    "MemoryServices",
    "build_memory_services",
]
