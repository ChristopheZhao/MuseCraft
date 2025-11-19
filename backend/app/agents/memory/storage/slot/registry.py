"""Slot registry and configuration loader."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import yaml

from ...interfaces import SlotSchemaProvider
from .schema import SlotSchema, SlotScope, Reducers


class SlotDefinitionError(RuntimeError):
    """Raised when slot definitions are invalid or missing."""


class SlotRegistry:
    """Registry of slot schemas (thread-safe lookups)."""

    def __init__(self) -> None:
        self._slots: Dict[str, SlotSchema] = {}
        self._lock = threading.RLock()

    def register(self, schema: SlotSchema) -> None:
        with self._lock:
            if schema.slot_id in self._slots:
                raise SlotDefinitionError(f"Slot {schema.slot_id} already registered")
            self._slots[schema.slot_id] = schema

    def get(self, slot_id: str) -> SlotSchema:
        with self._lock:
            if slot_id not in self._slots:
                raise SlotDefinitionError(f"Slot {slot_id} not registered")
            return self._slots[slot_id]

    def list(self) -> Iterable[SlotSchema]:
        with self._lock:
            return list(self._slots.values())

    def list_by_scope(self, scope: SlotScope) -> List[SlotSchema]:
        with self._lock:
            return [schema for schema in self._slots.values() if schema.scope == scope]

    @classmethod
    def from_config(cls, path: Path) -> "SlotRegistry":
        if not path.exists():
            raise SlotDefinitionError(f"Slot config not found: {path}")
        with path.open("r", encoding="utf-8") as fh:
            payload = yaml.safe_load(fh) or {}
        slots_def = payload.get("slots")
        if not isinstance(slots_def, list):
            raise SlotDefinitionError("Slot config must contain a list under 'slots'")

        registry = cls()
        for entry in slots_def:
            if not isinstance(entry, dict):
                raise SlotDefinitionError(f"Invalid slot entry: {entry}")
            slot_id = entry.get("slot_id")
            scope_raw = entry.get("scope")
            value_type_raw = entry.get("value_type")
            if not slot_id or not scope_raw or not value_type_raw:
                raise SlotDefinitionError(f"Slot definition missing required fields: {entry}")

            try:
                scope = SlotScope(scope_raw)
            except ValueError as exc:
                raise SlotDefinitionError(f"Invalid slot scope for {slot_id}: {scope_raw}") from exc

            value_type = _resolve_type(value_type_raw)

            reducer_name = entry.get("reducer")
            reducer = _resolve_reducer(reducer_name) if reducer_name else None

            access = entry.get("access") or {}
            read_agents = list(access.get("read", [])) if isinstance(access, dict) else []
            write_agents = list(access.get("write", [])) if isinstance(access, dict) else []

            schema = SlotSchema(
                slot_id=slot_id,
                display_name=entry.get("display_name", slot_id),
                scope=scope,
                value_type=value_type,
                schema_version=str(entry.get("schema_version", "1.0.0")),
                required=bool(entry.get("required", False)),
                reducer=reducer,
                description=entry.get("description", ""),
                allow_empty=bool(entry.get("allow_empty", False)),
                max_size=entry.get("max_size"),
                ttl_seconds=entry.get("ttl_seconds"),
                metadata=entry.get("metadata") or {},
                read_agents=read_agents,
                write_agents=write_agents,
            )
            registry.register(schema)
        return registry


class SlotRegistryProvider(SlotSchemaProvider):
    """Adapter that exposes SlotRegistry through the abstract provider interface."""

    def __init__(self, registry: SlotRegistry) -> None:
        self._registry = registry

    def get_schema(self, slot_id: str) -> SlotSchema:
        return self._registry.get(slot_id)

    def list_schemas(self) -> Iterable[SlotSchema]:
        return self._registry.list()


def _resolve_type(name: str) -> type:
    mapping = {
        "dict": dict,
        "list": list,
        "set": set,
        "tuple": tuple,
        "str": str,
        "int": int,
        "float": float,
        "bool": bool,
    }
    if name not in mapping:
        raise SlotDefinitionError(f"Unsupported value_type: {name}")
    return mapping[name]


def _resolve_reducer(name: Optional[str]) -> Optional[callable]:
    if not name:
        return None
    table = {
        "replace": Reducers.replace,
        "merge_dict": Reducers.merge_dict,
        "append": Reducers.append,
        "sum_numeric": Reducers.sum_numeric,
    }
    if name not in table:
        raise SlotDefinitionError(f"Unknown reducer: {name}")
    return table[name]


__all__ = [
    "SlotRegistry",
    "SlotDefinitionError",
    "SlotRegistryProvider",
]
