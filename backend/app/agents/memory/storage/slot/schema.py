"""Slot schema definitions for the new memory system."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional, List


ReducerCallable = Callable[[Any, Any], Any]
ValidatorCallable = Callable[[Any], bool]


class SlotScope(Enum):
    """Scope of a slot within the memory system."""

    WORKFLOW = "workflow"   # Shared across all agents in a workflow
    AGENT = "agent"         # Private to an agent across the workflow lifespan
    ITERATION = "iteration" # Ephemeral for a single agent iteration


@dataclass
class SlotSchema:
    """Metadata that defines how a slot behaves."""

    slot_id: str
    display_name: str
    scope: SlotScope
    value_type: type
    schema_version: str = "1.0.0"
    required: bool = False
    reducer: Optional[ReducerCallable] = None
    validator: Optional[ValidatorCallable] = None
    description: str = ""
    default_factory: Optional[Callable[[], Any]] = None
    max_size: Optional[int] = None
    ttl_seconds: Optional[int] = None
    allow_empty: bool = False
    metadata: dict = field(default_factory=dict)
    read_agents: List[str] = field(default_factory=list)
    write_agents: List[str] = field(default_factory=list)

    def validate_value(self, value: Any) -> None:
        """Ensure the provided value conforms to the schema."""
        if value is None:
            raise ValueError(f"Slot {self.slot_id} does not accept None")
        if not isinstance(value, self.value_type):
            raise TypeError(
                f"Slot {self.slot_id} expects {self.value_type.__name__}, "
                f"got {type(value).__name__}"
            )
        if not self.allow_empty:
            if isinstance(value, (dict, list, tuple, set)) and not value:
                raise ValueError(f"Slot {self.slot_id} rejects empty payloads")
        if self.validator and not self.validator(value):
            raise ValueError(f"Slot {self.slot_id} validator rejected the value")


class Reducers:
    """Built-in reducer helpers."""

    @staticmethod
    def replace(old: Any, new: Any) -> Any:
        return new

    @staticmethod
    def merge_dict(old: Any, new: Any) -> Any:
        if not isinstance(new, dict):
            raise TypeError("merge_dict reducer requires dict payloads")
        base = dict(old or {})
        base.update(new)
        return base

    @staticmethod
    def append(old: Any, new: Any) -> Any:
        if isinstance(new, list):
            incoming = new
        else:
            incoming = [new]
        if not isinstance(old, list):
            return list(incoming)
        return list(old) + incoming

    @staticmethod
    def sum_numeric(old: Any, new: Any) -> Any:
        return (old or 0) + (new or 0)


__all__ = ["SlotScope", "SlotSchema", "Reducers"]

