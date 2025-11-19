"""Factories for workflow-level memory backends."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from ..interfaces import WorkflowFactsBackend, WorkflowMemoryBackend
from ..services.coordinator import MemoryCoordinator

_LOGGER = logging.getLogger("memory.storage.backend")
_DEFAULT_SLOTS_PATH = Path(__file__).resolve().parent.parent / "config" / "memory_slots.yaml"


def _create_slot_backend(*, slots_path: Optional[Path], **kwargs: Any) -> WorkflowMemoryBackend:
    """Return the slot-based backend wired with ACL/audit policies."""

    from .slot.manager import ACLManager, MemoryAuditLogger, SlotWorkflowBackend
    from .slot.registry import SlotRegistry

    slots_file = Path(slots_path or _DEFAULT_SLOTS_PATH)
    registry = SlotRegistry.from_config(slots_file)
    acl = kwargs.get("acl") or ACLManager()
    audit_logger = kwargs.get("audit") or MemoryAuditLogger(logging.getLogger("memory.audit"))

    for schema in registry.list():
        for agent in schema.read_agents:
            acl.grant(schema.slot_id, agent, ["read"])
        for agent in schema.write_agents:
            acl.grant(schema.slot_id, agent, ["write"])

    _LOGGER.info("Using slot-based workflow backend (slots=%s)", slots_file)
    return SlotWorkflowBackend(registry, acl=acl, audit=audit_logger)


def create_workflow_backend(
    *,
    kind: str = "slot",
    slots_path: Optional[Path] = None,
    **kwargs: Any,
) -> WorkflowMemoryBackend:
    """Create a workflow memory backend based on the configured kind."""

    backend_kind = (kind or "slot").lower()
    if backend_kind == "slot":
        return _create_slot_backend(slots_path=slots_path, **kwargs)
    raise ValueError(f"Unsupported workflow memory backend '{backend_kind}'")


def create_workflow_facts_backend(
    *,
    kind: str = "slot",
    coordinator: MemoryCoordinator,
    alias_map: Dict[str, str],
    **kwargs: Any,
) -> WorkflowFactsBackend:
    """Create a workflow facts backend based on the configured kind."""

    backend_kind = (kind or "slot").lower()
    if backend_kind == "slot":
        from .facts_backend import SlotFactsBackend

        return SlotFactsBackend(coordinator, alias_map)
    raise ValueError(f"Unsupported workflow facts backend '{backend_kind}'")


__all__ = ["create_workflow_backend", "create_workflow_facts_backend"]
