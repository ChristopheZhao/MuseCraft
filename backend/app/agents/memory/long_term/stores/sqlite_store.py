"""
SQLiteMemoryStore - Persistent memory store using SQLite.

Implements BaseMemoryStore with a single-table schema. This is a minimal,
production-friendly baseline (no external services). For larger scale or
advanced retrieval, you can switch to Mem0/other backends without changing
agent code.
"""
from __future__ import annotations

import os
import json
import sqlite3
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from .base import (
    BaseMemoryStore, MemoryItem, MemoryQuery, MemoryType, MemoryImportance,
    MemoryStorageError
)


_logger = logging.getLogger("sqlite_memory_store")


class SQLiteMemoryStore(BaseMemoryStore):
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        default_path = os.getenv(
            "MEMORY_SQLITE_PATH",
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
                         "storage", "memory.sqlite")
        )
        self.db_path = self.config.get("db_path", default_path)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.conn: Optional[sqlite3.Connection] = None
        super().__init__(config)

    def _initialize(self):
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA synchronous=NORMAL;")
        self._create_table()
        _logger.info(f"SQLiteMemoryStore initialized at {self.db_path}")

    def _create_table(self):
        sql = """
        CREATE TABLE IF NOT EXISTS memories (
            id TEXT PRIMARY KEY,
            content TEXT,
            memory_type TEXT,
            importance INTEGER,
            tags TEXT,
            metadata TEXT,
            created_at TEXT,
            last_accessed TEXT,
            expires_at TEXT,
            access_count INTEGER,
            agent_id TEXT,
            task_id TEXT,
            session_id TEXT,
            related_items TEXT,
            parent_id TEXT,
            children_ids TEXT,
            content_hash TEXT
        );
        """
        self.conn.execute(sql)
        self.conn.commit()

    async def store(self, memory_item: MemoryItem) -> bool:
        try:
            sql = """
            INSERT INTO memories (
                id, content, memory_type, importance, tags, metadata,
                created_at, last_accessed, expires_at, access_count,
                agent_id, task_id, session_id, related_items, parent_id,
                children_ids, content_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            self.conn.execute(sql, (
                memory_item.id,
                json.dumps(memory_item.content, ensure_ascii=False, default=str),
                memory_item.memory_type.value,
                memory_item.importance.value,
                json.dumps(memory_item.tags, ensure_ascii=False),
                json.dumps(memory_item.metadata, ensure_ascii=False, default=str),
                memory_item.created_at.isoformat(),
                memory_item.last_accessed.isoformat(),
                memory_item.expires_at.isoformat() if memory_item.expires_at else None,
                memory_item.access_count,
                memory_item.agent_id,
                memory_item.task_id,
                memory_item.session_id,
                json.dumps(memory_item.related_items, ensure_ascii=False),
                memory_item.parent_id,
                json.dumps(memory_item.children_ids, ensure_ascii=False),
                memory_item.content_hash,
            ))
            self.conn.commit()
            return True
        except Exception as e:
            _logger.error(f"SQLite store failed: {e}")
            raise MemoryStorageError(str(e))

    async def retrieve(self, memory_id: str) -> Optional[MemoryItem]:
        row = self.conn.execute("SELECT * FROM memories WHERE id=?", (memory_id,)).fetchone()
        return self._row_to_item(row) if row else None

    async def search(self, query: MemoryQuery) -> List[MemoryItem]:
        # Base filtering in SQL, fine-grained filtering in Python
        clauses = []
        params: List[Any] = []

        if query.agent_id:
            clauses.append("agent_id = ?")
            params.append(query.agent_id)
        if query.task_id:
            clauses.append("task_id = ?")
            params.append(query.task_id)
        if query.session_id:
            clauses.append("session_id = ?")
            params.append(query.session_id)
        if query.importance_min:
            clauses.append("importance >= ?")
            params.append(query.importance_min.value)
        if query.memory_types:
            # Handle in Python after fetch to keep it simple (types small)
            pass

        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"SELECT * FROM memories{where}"
        rows = self.conn.execute(sql, tuple(params)).fetchall()
        items = [it for it in (self._row_to_item(r) for r in rows) if it]

        # Python-side filters
        if query.memory_types:
            allowed = set(t.value for t in query.memory_types)
            items = [it for it in items if it.memory_type.value in allowed]

        if query.tags:
            qtags = set(query.tags)
            items = [it for it in items if it.tags and qtags.intersection(set(it.tags))]

        if query.time_range:
            start, end = query.time_range
            items = [it for it in items if start <= it.created_at <= end]

        if query.content:
            needle = query.content.lower()
            def has_text(it: MemoryItem) -> bool:
                try:
                    txt = json.dumps(it.content, ensure_ascii=False, default=str).lower()
                except Exception:
                    txt = str(it.content).lower()
                return needle in txt
            items = [it for it in items if has_text(it)]

        # Sort: simple relevance heuristic → access_count, last_accessed
        items.sort(key=lambda m: (m.access_count, m.last_accessed), reverse=True)

        if query.limit:
            items = items[: query.limit]
        return items

    async def update(self, memory_item: MemoryItem) -> bool:
        if not self.conn:
            return False
        sql = """
        UPDATE memories SET
            content=?, memory_type=?, importance=?, tags=?, metadata=?,
            created_at=?, last_accessed=?, expires_at=?, access_count=?,
            agent_id=?, task_id=?, session_id=?, related_items=?, parent_id=?,
            children_ids=?, content_hash=?
        WHERE id=?
        """
        cur = self.conn.execute(sql, (
            json.dumps(memory_item.content, ensure_ascii=False, default=str),
            memory_item.memory_type.value,
            memory_item.importance.value,
            json.dumps(memory_item.tags, ensure_ascii=False),
            json.dumps(memory_item.metadata, ensure_ascii=False, default=str),
            memory_item.created_at.isoformat(),
            memory_item.last_accessed.isoformat(),
            memory_item.expires_at.isoformat() if memory_item.expires_at else None,
            memory_item.access_count,
            memory_item.agent_id,
            memory_item.task_id,
            memory_item.session_id,
            json.dumps(memory_item.related_items, ensure_ascii=False),
            memory_item.parent_id,
            json.dumps(memory_item.children_ids, ensure_ascii=False),
            memory_item.content_hash,
            memory_item.id,
        ))
        self.conn.commit()
        return cur.rowcount > 0

    async def delete(self, memory_id: str) -> bool:
        cur = self.conn.execute("DELETE FROM memories WHERE id=?", (memory_id,))
        self.conn.commit()
        return cur.rowcount > 0

    async def cleanup_expired(self) -> int:
        now = datetime.now().isoformat()
        cur = self.conn.execute("DELETE FROM memories WHERE expires_at IS NOT NULL AND expires_at < ?", (now,))
        self.conn.commit()
        return cur.rowcount

    async def get_stats(self) -> Dict[str, Any]:
        rows = self.conn.execute("SELECT memory_type, importance, COUNT(*) FROM memories GROUP BY memory_type, importance").fetchall()
        type_counts: Dict[str, int] = {}
        importance_counts: Dict[str, int] = {}
        total = 0
        for r in rows:
            mtype, importance, count = r[0], int(r[1]), int(r[2])
            total += count
            type_counts[mtype] = type_counts.get(mtype, 0) + count
            # Map back to enum name
            try:
                imp_name = MemoryImportance(importance).name
            except Exception:
                imp_name = str(importance)
            importance_counts[imp_name] = importance_counts.get(imp_name, 0) + count

        return {
            "total_memories": total,
            "type_distribution": type_counts,
            "importance_distribution": importance_counts,
            "store_type": "sqlite",
            "is_persistent": True,
            "db_path": self.db_path,
        }

    def _row_to_item(self, row: sqlite3.Row) -> Optional[MemoryItem]:
        try:
            # PRAGMA table_info returns rows: (cid, name, type, notnull, dflt_value, pk)
            # We need the column 'name' at index 1
            col = [d[1] for d in self.conn.execute("PRAGMA table_info(memories)").fetchall()]
        except Exception:
            col = [
                "id","content","memory_type","importance","tags","metadata",
                "created_at","last_accessed","expires_at","access_count","agent_id",
                "task_id","session_id","related_items","parent_id","children_ids","content_hash"
            ]
        # Fallback positional mapping
        data = dict(zip(col, row)) if isinstance(row, (list, tuple)) else row
        try:
            item = MemoryItem(
                id=data["id"],
                content=json.loads(data["content"]) if data["content"] else None,
                memory_type=MemoryType(data["memory_type"]),
                importance=MemoryImportance(int(data["importance"])) if data["importance"] is not None else MemoryImportance.MEDIUM,
                tags=json.loads(data["tags"]) if data["tags"] else [],
                metadata=json.loads(data["metadata"]) if data["metadata"] else {},
                created_at=datetime.fromisoformat(data["created_at"]) if data["created_at"] else datetime.now(),
                last_accessed=datetime.fromisoformat(data["last_accessed"]) if data["last_accessed"] else datetime.now(),
                expires_at=datetime.fromisoformat(data["expires_at"]) if data["expires_at"] else None,
                access_count=int(data["access_count"]) if data["access_count"] is not None else 0,
                agent_id=data.get("agent_id"),
                task_id=data.get("task_id"),
                session_id=data.get("session_id"),
                related_items=json.loads(data["related_items"]) if data.get("related_items") else [],
                parent_id=data.get("parent_id"),
                children_ids=json.loads(data["children_ids"]) if data.get("children_ids") else [],
                content_hash=data.get("content_hash"),
            )
            return item
        except Exception as e:
            _logger.warning(f"Row to item failed: {e}")
            return None
