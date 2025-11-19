"""Compatibility layer for legacy imports.

This stub re-exports the new base store definitions so that older modules
still referencing ``app.agents.memory.long_term.stores.base_memory`` keep
working during the ongoing refactor.
"""
from __future__ import annotations

from .base import (  # noqa: F401
    BaseMemoryRetriever,
    BaseMemoryStore,
    MemoryError,
    MemoryImportance,
    MemoryItem,
    MemoryQuery,
    MemoryRetrievalError,
    MemoryStorageError,
    MemoryType,
)

__all__ = [
    "BaseMemoryStore",
    "BaseMemoryRetriever",
    "MemoryItem",
    "MemoryQuery",
    "MemoryType",
    "MemoryImportance",
    "MemoryError",
    "MemoryStorageError",
    "MemoryRetrievalError",
]
