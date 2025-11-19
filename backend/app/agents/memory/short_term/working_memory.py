"""Short-term Working Memory container (domain-neutral)."""
from __future__ import annotations

import logging
from collections import deque
from time import time as _now
from typing import Any, Deque, Dict, List, Optional

logger = logging.getLogger(__name__)


class WorkingMemory:
    """Generic per-workflow/per-agent scratch pad storing facts and events."""

    def __init__(
        self,
        *,
        workflow_state_id: str,
        scope: str,
        goal_text: str,
        journal_max_events: int = 5,
    ) -> None:
        self.workflow_state_id = workflow_state_id
        self.scope = scope
        self.goal_text = goal_text
        self.journal_max_events = int(journal_max_events)
        self.facts: Dict[str, Any] = {}
        self.event_streams: Dict[str, Deque[Dict[str, Any]]] = {}
        self.notes: List[str] = []
        self.iteration_artifacts: Deque[Dict[str, Any]] = deque(maxlen=32)
        self.facts_slots: Dict[str, Dict[int, Any]] = {}
        self.workflow_facts: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Generic data helpers
    # ------------------------------------------------------------------
    def put(self, key: str, value: Any) -> None:
        """Store arbitrary data payload referenced by a string key."""
        self.facts[str(key)] = value

    def get(self, key: str, default: Any = None) -> Any:
        """Return stored payload for key or default when absent."""
        return self.facts.get(str(key), default)

    def delete(self, key: str) -> None:
        """Remove payload associated with key when it exists."""
        self.facts.pop(str(key), None)

    def list_keys(self) -> List[str]:
        """Return a snapshot list of current data keys."""
        return list(self.facts.keys())

    # Backwards-compatible aliases (to be removed once callers migrate)
    def set_fact(self, key: str, value: Any) -> None:
        self.put(key, value)

    def get_fact(self, key: str, default: Any = None) -> Any:
        return self.get(key, default)

    def clear_fact(self, key: str) -> None:
        self.delete(key)

    # ------------------------------------------------------------------
    # Event helpers
    # ------------------------------------------------------------------
    def _new_event_queue(self) -> Deque[Dict[str, Any]]:
        return deque(maxlen=self.journal_max_events)

    def _normalize_stream_id(self, stream_id: Any) -> str:
        if isinstance(stream_id, (tuple, list)):
            return ":".join(str(part) for part in stream_id)
        return str(stream_id)

    def record_event(
        self,
        stream_id: Any,
        *,
        action: str,
        success: bool,
        error_type: Optional[str] = None,
        dur_sec: Optional[float] = None,
        ts: Optional[float] = None,
        tags: Optional[Dict[str, Any]] = None,
    ) -> None:
        stream_key = self._normalize_stream_id(stream_id)
        dq = self.event_streams.setdefault(stream_key, self._new_event_queue())
        event: Dict[str, Any] = {
            "action": action,
            "success": bool(success),
            "ts": float(ts if ts is not None else _now()),
        }
        if error_type:
            event["error_type"] = str(error_type)
        if dur_sec is not None:
            try:
                event["dur_sec"] = float(dur_sec)
            except Exception:
                pass
        if tags:
            event["tags"] = dict(tags)
        if dq:
            last = dq[-1]
            if (
                isinstance(last, dict)
                and last.get("action") == event.get("action")
                and bool(last.get("success")) == event["success"]
                and last.get("error_type") == event.get("error_type")
            ):
                last["count"] = int(last.get("count", 1)) + 1
                last["ts"] = event["ts"]
                if "dur_sec" in event:
                    last["dur_sec"] = event["dur_sec"]
                merged_tags = dict(last.get("tags") or {})
                merged_tags.update(event.get("tags") or {})
                if merged_tags:
                    last["tags"] = merged_tags
                return
        dq.append(event)

    def get_recent_step_summaries(self, k: Optional[int] = None) -> List[Dict[str, Any]]:
        limit = int(k) if k is not None else _default_recent_steps_k()
        events: List[Dict[str, Any]] = []
        for stream, dq in (self.event_streams or {}).items():
            for event in dq or []:
                if not isinstance(event, dict):
                    continue
                row = {
                    "stream": stream,
                    "action": event.get("action"),
                    "success": bool(event.get("success")),
                    "error_type": event.get("error_type"),
                    "dur_sec": event.get("dur_sec"),
                    "ts": event.get("ts"),
                }
                tags = event.get("tags")
                if isinstance(tags, dict):
                    for key in ("scene_number", "scene_id", "entity_id", "domain"):
                        if key in tags:
                            row[key] = tags[key]
                events.append(row)
        if not events:
            return []

        def ts_key(entry: Dict[str, Any]) -> float:
            try:
                return float(entry.get("ts", 0.0))
            except Exception:
                return 0.0

        events.sort(key=ts_key, reverse=True)
        return events[: max(1, limit)]

    # ------------------------------------------------------------------
    # Iteration artifacts / slots / notes
    # ------------------------------------------------------------------
    def add_iteration_artifact(
        self,
        *,
        kind: str,
        scene_number: Optional[int] = None,
        file_path: str = "",
        url: str = "",
        duration: Optional[float] = None,
        prompt_text: str = "",
        stage: Optional[str] = None,
        ts: Optional[float] = None,
    ) -> None:
        record: Dict[str, Any] = {
            "ts": float(ts if ts is not None else _now()),
            "kind": kind,
            "scene_number": scene_number,
            "file_path": file_path or "",
            "url": url or "",
            "prompt_text": prompt_text or "",
        }
        if duration is not None:
            try:
                record["duration_sec"] = float(duration)
            except Exception:
                pass
        if stage:
            record["stage"] = stage
        self.iteration_artifacts.append(record)

    def latest_iteration_artifacts(
        self,
        *,
        kind: Optional[str] = None,
        scene_number: Optional[int] = None,
        limit: int = 1,
    ) -> List[Dict[str, Any]]:
        entries = list(self.iteration_artifacts or [])
        if not entries:
            return []
        samples: List[Dict[str, Any]] = []
        max_items = max(1, int(limit))
        for record in reversed(entries):
            if not isinstance(record, dict):
                continue
            if kind and record.get("kind") != kind:
                continue
            if scene_number is not None and record.get("scene_number") != scene_number:
                continue
            samples.append(record)
            if len(samples) >= max_items:
                break
        return samples

    def set_slot_value(self, slot: str, scene_number: Optional[int], payload: Any) -> None:
        if payload is None or scene_number is None:
            return
        bucket = self.facts_slots.setdefault(str(slot), {})
        bucket[int(scene_number)] = payload

    def get_slot_value(self, slot: str, scene_number: int) -> Optional[Any]:
        bucket = self.facts_slots.get(str(slot)) or {}
        return bucket.get(int(scene_number))

    def append_note(self, note: str) -> None:
        if note:
            self.notes.append(str(note))


def _default_recent_steps_k() -> int:
    try:
        from app.core.config import settings as _cfg  # type: ignore

        return int(getattr(_cfg, "REACT_WM_RECENT_STEPS_K", 3))
    except Exception:
        return 3


__all__ = ["WorkingMemory"]
