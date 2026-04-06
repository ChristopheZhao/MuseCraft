"""Slot-based storage backend implementation."""

from .schema import SlotSchema, SlotScope
from .registry import SlotRegistry, SlotDefinitionError, SlotRegistryProvider

__all__ = [
    "SlotSchema",
    "SlotScope",
    "SlotDefinitionError",
    "SlotRegistry",
    "SlotRegistryProvider",
]
