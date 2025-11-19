"""Workflow-level fact service for MAS working memory."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Union

import yaml

from ..interfaces import WorkflowFactsBackend

_DEFAULT_ALIASES_PATH = Path(__file__).resolve().parent.parent / "config" / "fact_aliases.yaml"


class WorkflowFactStoreError(RuntimeError):
    pass


class WorkflowFactStore:
    def __init__(self, backend: WorkflowFactsBackend) -> None:
        if backend is None:
            raise WorkflowFactStoreError("Facts backend is not initialized")
        self._backend = backend

    def put(self, workflow_id: str, key: str, value: Any, *, agent: Optional[str] = None) -> None:
        self._backend.put(workflow_id, key, value, agent=agent)

    def get(self, workflow_id: str, key: str, *, default: Any = None, agent: Optional[str] = None) -> Any:
        return self._backend.get(workflow_id, key, default=default, agent=agent)

    def delete(self, workflow_id: str, key: str) -> None:
        self._backend.delete(workflow_id, key)

    def list_aliases(self) -> Dict[str, str]:
        return self._backend.list_aliases()


_aliases_cache: Optional[Dict[str, str]] = None


def load_fact_aliases(path: Optional[Union[str, Path]] = None) -> Dict[str, str]:
    global _aliases_cache
    if _aliases_cache is not None:
        return _aliases_cache
    path_obj = Path(path) if path else _DEFAULT_ALIASES_PATH
    if not path_obj.exists():
        _aliases_cache = {}
        return _aliases_cache
    with path_obj.open("r", encoding="utf-8") as fh:
        payload = yaml.safe_load(fh) or {}
    aliases = payload.get("aliases", {})
    if not isinstance(aliases, dict):
        aliases = {}
    _aliases_cache = {str(k): str(v) for k, v in aliases.items()}
    return _aliases_cache


__all__ = ["WorkflowFactStore", "WorkflowFactStoreError", "load_fact_aliases"]
