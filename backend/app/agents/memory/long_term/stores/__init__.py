"""长期记忆存储后端（stores）。

统一暴露 MemoryStore 抽象与具体实现（dict/sqlite）。
"""
from __future__ import annotations

from .base import (
    MemoryItem,
    MemoryQuery,
    MemoryType,
    MemoryImportance,
    BaseMemoryStore,
    BaseMemoryRetriever,
    MemoryError,
    MemoryStorageError,
    MemoryRetrievalError,
)
from .dict_store import DictMemoryStore
try:
    from .sqlite_store import SQLiteMemoryStore  # type: ignore
except Exception:  # pragma: no cover - optional backend
    SQLiteMemoryStore = None  # type: ignore

__all__ = [
    "MemoryItem",
    "MemoryQuery",
    "MemoryType",
    "MemoryImportance",
    "BaseMemoryStore",
    "BaseMemoryRetriever",
    "MemoryError",
    "MemoryStorageError",
    "MemoryRetrievalError",
    "DictMemoryStore",
    "SQLiteMemoryStore",
]
