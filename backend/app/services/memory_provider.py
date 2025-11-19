"""Helpers for constructing and sharing memory-related services."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..agents.memory.managers import build_memory_management, MemoryManagement
from ..agents.memory.services.coordinator import MemoryCoordinator
from ..agents.memory.short_term.workflow_facts import WorkflowFactStore, load_fact_aliases
from ..agents.memory.services.long_term import SimpleLongTermMemoryService
from ..agents.services.mas_shared_memory import configure_shared_wm
from ..agents.memory.short_term.assembler import WorkingMemoryAssembler
from ..agents.memory.short_term.service import WorkingMemoryService
from ..agents.memory.short_term.registry import set_working_memory_service
from ..agents.memory.storage.backend_factory import create_workflow_facts_backend
from ..core.config import settings
from .global_memory_service import GlobalMemoryService


@dataclass
class MemoryServices:
    global_service: GlobalMemoryService
    management: MemoryManagement
    coordinator: MemoryCoordinator
    long_term: SimpleLongTermMemoryService
    fact_store: WorkflowFactStore


_default_services: Optional[MemoryServices] = None


def build_memory_services() -> MemoryServices:
    slots_path = Path(settings.MEMORY_SLOTS_PATH)
    management = build_memory_management(
        slots_path=slots_path,
        storage_backend=settings.MEMORY_WORKFLOW_BACKEND,
    )
    global_service = GlobalMemoryService(management)
    coordinator = global_service.memory_coordinator
    long_term = SimpleLongTermMemoryService(global_service.memory_manager)
    alias_map = load_fact_aliases(settings.MEMORY_FACT_ALIASES_PATH)
    fact_backend = create_workflow_facts_backend(
        kind=settings.MEMORY_FACTS_BACKEND,
        coordinator=coordinator,
        alias_map=alias_map,
    )
    fact_store = WorkflowFactStore(fact_backend)
    services = MemoryServices(
        global_service=global_service,
        management=management,
        coordinator=coordinator,
        long_term=long_term,
        fact_store=fact_store,
    )
    wm_service = WorkingMemoryService()
    set_working_memory_service(wm_service)
    configure_shared_wm(services.fact_store, wm_service)
    return services


def get_memory_services() -> MemoryServices:
    global _default_services
    if _default_services is None:
        _default_services = build_memory_services()
    return _default_services


def set_memory_services(services: MemoryServices) -> None:
    global _default_services
    _default_services = services


__all__ = [
    "MemoryServices",
    "build_memory_services",
    "get_memory_services",
    "set_memory_services",
]
