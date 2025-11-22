"""Helpers for constructing and sharing memory-related services."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..agents.memory.managers import build_memory_management, MemoryManagement
from ..agents.memory.services.coordinator import MemoryCoordinator
from ..agents.memory.services.long_term import SimpleLongTermMemoryService
from ..agents.memory.short_term.registry import set_working_memory_service
from ..agents.memory.short_term.service import WorkingMemoryService
from ..core.config import settings
from .global_memory_service import GlobalMemoryService


@dataclass
class MemoryServices:
    global_service: GlobalMemoryService
    management: MemoryManagement
    coordinator: MemoryCoordinator
    long_term: SimpleLongTermMemoryService


_default_services: Optional[MemoryServices] = None


def build_memory_services() -> MemoryServices:
    management = build_memory_management(
        slots_path=None,
        storage_backend=settings.MEMORY_WORKFLOW_BACKEND,
    )
    global_service = GlobalMemoryService(management)
    coordinator = global_service.memory_coordinator
    long_term = SimpleLongTermMemoryService(global_service.memory_manager)

    services = MemoryServices(
        global_service=global_service,
        management=management,
        coordinator=coordinator,
        long_term=long_term,
    )
    wm_service = WorkingMemoryService()
    set_working_memory_service(wm_service)
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
