from __future__ import annotations

"""Context editor - normalizes raw observation views for downstream agents."""

from typing import Any, Dict, Iterable, List, Optional, Tuple


def edit_context(
    raw_view: Optional[Dict[str, Any]],
    strategy: Optional[Dict[str, Any]] = None,
    model_name: Optional[str] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Normalize raw observation dict to a predictable schema.

    This is a lightweight sanitiser that:
        - Enforces list of scenes with integer scene_number
        - Converts completed/failed IDs to integer lists
        - Drops legacy fields (summary/ready/etc.)
    """
    if not isinstance(raw_view, dict):
        raw_view = {}

    normalized: Dict[str, Any] = {
        "scenes": _sanitize_scenes(raw_view.get("scenes")),
        "completed_scene_numbers": _coerce_int_list(raw_view.get("completed_scene_numbers")),
        "failed_scene_numbers": _coerce_int_list(raw_view.get("failed_scene_numbers")),
        "notes": _sanitize_notes(raw_view.get("notes")),
    }
    if "act_log" in raw_view and isinstance(raw_view["act_log"], list):
        normalized["act_log"] = list(raw_view["act_log"])
    if "recent_events" in raw_view and isinstance(raw_view["recent_events"], list):
        normalized["recent_events"] = list(raw_view["recent_events"])
    if "facts" in raw_view and isinstance(raw_view["facts"], dict):
        normalized["facts"] = dict(raw_view["facts"])
    if "workflow_facts" in raw_view and isinstance(raw_view["workflow_facts"], dict):
        normalized["workflow_facts"] = dict(raw_view["workflow_facts"])

    receipt = {
        "strategy": (strategy or {}).get("name") if isinstance(strategy, dict) else strategy,
        "model_name": model_name,
        "compacted": False,
        "original_tokens": None,
        "input_budget_tokens": None,
    }
    return normalized, receipt


def _sanitize_scenes(entries: Any) -> List[Dict[str, Any]]:
    if not isinstance(entries, Iterable):
        return []
    sanitized: List[Dict[str, Any]] = []
    for item in entries or []:
        if not isinstance(item, dict):
            continue
        sn = _coerce_int(item.get("scene_number"))
        if sn is None:
            continue
        record = dict(item)
        record["scene_number"] = sn
        sanitized.append(record)
    sanitized.sort(key=lambda entry: entry["scene_number"])
    return sanitized


def _sanitize_notes(notes: Any) -> List[str]:
    if not isinstance(notes, Iterable):
        return []
    values: List[str] = []
    for note in notes:
        if note is None:
            continue
        values.append(str(note))
    return values


def _coerce_int_list(values: Any) -> List[int]:
    if values is None:
        return []
    result: List[int] = []
    if isinstance(values, dict):
        values = list(values)
    if not isinstance(values, Iterable):
        values = [values]
    for value in values:
        sn = _coerce_int(value)
        if sn is None:
            continue
        result.append(sn)
    # Ensure deterministic ordering
    result = sorted(set(result))
    return result


def _coerce_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        try:
            return int(value)
        except Exception:
            return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.isdigit() or (text.startswith("-") and text[1:].isdigit()):
            try:
                return int(text)
            except Exception:
                return None
    return None


__all__ = ["edit_context"]
