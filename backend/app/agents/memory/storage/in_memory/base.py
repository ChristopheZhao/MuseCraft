"""Short-term memory store interface (backends implement this)."""
from __future__ import annotations

from typing import Any, Deque, Dict


class ShortTermMemoryStore:
    """Abstract store API for WorkingMemory backends."""

    def put(self, key: str, value: Any) -> None:
        raise NotImplementedError

    def get(self, key: str, default: Any = None) -> Any:
        raise NotImplementedError

    def delete(self, key: str) -> None:
        raise NotImplementedError

    def list_keys(self) -> list[str]:
        raise NotImplementedError

    def new_event_queue(self, maxlen: int) -> Deque[Dict[str, Any]]:
        raise NotImplementedError

    def clear(self) -> None:
        raise NotImplementedError
