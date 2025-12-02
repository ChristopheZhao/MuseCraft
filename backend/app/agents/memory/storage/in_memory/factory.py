"""Factory for short-term memory stores (pluggable backends)."""
from __future__ import annotations

from typing import Any

from .base import ShortTermMemoryStore
from .in_memory import InMemoryShortTermStore


def create_short_term_store(kind: str = "memory", **_: Any) -> ShortTermMemoryStore:
    normalized = (kind or "memory").lower()
    if normalized in {"memory", "in_memory", "default"}:
        return InMemoryShortTermStore()
    raise ValueError(f"Unsupported short-term store backend: {kind}")


__all__ = ["create_short_term_store", "ShortTermMemoryStore", "InMemoryShortTermStore"]
