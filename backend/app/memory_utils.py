"""Memory helper utilities decoupled from agents."""
from __future__ import annotations

from typing import Any, Dict, Optional

from .services.memory_provider import get_memory_services, MemoryServices


def _resolve_memory_services(memory_services: Optional[MemoryServices]) -> MemoryServices:
    return memory_services or get_memory_services()


def fetch_slot(
    workflow_id: str,
    slot_id: str,
    *,
    memory_services: Optional[MemoryServices] = None,
) -> Optional[Dict[str, Any]]:
    """Read a workflow-scoped slot via the MemoryCoordinator."""
    services = _resolve_memory_services(memory_services)
    coordinator = services.coordinator
    if coordinator is None:
        return None
    try:
        return coordinator.get_memory(workflow_id, slot_id)
    except Exception:
        return None


def fetch_shared_fact(
    workflow_id: str,
    key: str,
    *,
    memory_services: Optional[MemoryServices] = None,
) -> Optional[Any]:
    """Deprecated: fact_store removed in favor of WorkingMemory facts."""
    return None


def fetch_shared_state(workflow_id: str):
    """Deprecated: SharedWM removed; use MAS WorkingMemory facts instead."""
    return None
