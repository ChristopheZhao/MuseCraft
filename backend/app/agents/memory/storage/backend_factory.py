"""Lightweight workflow backend factory (slot system retired)."""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable

from ..interfaces.storage import WorkflowMemoryBackend


class DictWorkflowBackend(WorkflowMemoryBackend):
    """Simple in-memory workflow backend used after slot retirement."""

    def __init__(self) -> None:
        self._store: Dict[str, Dict[str, Any]] = defaultdict(dict)

    def set(self, workflow_id: str, key: str, value: Any, *, agent: str | None = None) -> None:
        self._store[str(workflow_id)][str(key)] = value

    def get(self, workflow_id: str, key: str, *, agent: str | None = None) -> Any:
        return self._store.get(str(workflow_id), {}).get(str(key))

    def delete(self, workflow_id: str, key: str) -> None:
        self._store.get(str(workflow_id), {}).pop(str(key), None)

    def clear(self, workflow_id: str) -> None:
        self._store.pop(str(workflow_id), None)

    def list_keys(self) -> Iterable[str]:
        # Return union of keys across workflows for compatibility
        keys: set[str] = set()
        for bucket in self._store.values():
            keys.update(bucket.keys())
        return sorted(keys)


def create_workflow_backend(kind: str = "dict", **_: Any) -> WorkflowMemoryBackend:
    """Factory for workflow-level backend; slot backend is retired, default to dict."""
    normalized = (kind or "dict").lower()
    if normalized in {"dict", "memory", "slot", "default"}:
        return DictWorkflowBackend()
    raise ValueError(f"Unsupported workflow backend: {kind}")


__all__ = ["create_workflow_backend", "DictWorkflowBackend"]
