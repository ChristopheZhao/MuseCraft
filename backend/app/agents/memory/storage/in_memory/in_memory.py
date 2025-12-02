"""Default in-memory implementation of ShortTermMemoryStore."""
from __future__ import annotations

from collections import defaultdict, deque
from typing import Any, Deque, Dict

from .base import ShortTermMemoryStore


class InMemoryShortTermStore(ShortTermMemoryStore):
    """Default in-memory store backed by dict/deque."""

    def __init__(self) -> None:
        self._facts: Dict[str, Any] = {}
        self._event_streams: Dict[str, Deque[Dict[str, Any]]] = defaultdict(deque)

    def put(self, key: str, value: Any) -> None:
        self._facts[str(key)] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self._facts.get(str(key), default)

    def delete(self, key: str) -> None:
        self._facts.pop(str(key), None)

    def list_keys(self) -> list[str]:
        return list(self._facts.keys())

    def new_event_queue(self, maxlen: int) -> Deque[Dict[str, Any]]:
        return deque(maxlen=maxlen)

    def clear(self) -> None:
        self._facts.clear()
        self._event_streams.clear()

    def event_streams(self) -> Dict[str, Deque[Dict[str, Any]]]:
        return self._event_streams
