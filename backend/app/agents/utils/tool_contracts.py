"""
Tool output contract utilities.

Contracts let tools describe how their structured outputs should be written back
into an agent's working memory slots without adding tool-specific conditionals
inside agents.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Union


@dataclass
class ContractSlotWrite:
    """Concrete instruction for writing tool output into a WM slot."""

    slot: str
    scene_number: Optional[int]
    value: Any
    spec: Dict[str, Any]
    source_path: str


def _tokenize_path(path: str) -> List[Union[str, int]]:
    """Split dot/bracket notation into traversal tokens."""
    segments: List[Union[str, int]] = []
    cursor = path or ""
    for part in cursor.split("."):
        remainder = part
        while remainder:
            bracket_idx = remainder.find("[")
            if bracket_idx == -1:
                segments.append(remainder)
                remainder = ""
                continue
            # prefix before '['
            prefix = remainder[:bracket_idx]
            if prefix:
                segments.append(prefix)
            # extract index between [ ]
            after_bracket = remainder[bracket_idx + 1 :]
            closing = after_bracket.find("]")
            if closing == -1:
                # treat the rest as a single token
                segments.append(after_bracket)
                remainder = ""
                continue
            index_token = after_bracket[:closing]
            if index_token.isdigit():
                segments.append(int(index_token))
            else:
                segments.append(index_token)
            remainder = after_bracket[closing + 1 :]
    return [tok for tok in segments if tok != ""]


def _deep_get(payload: Any, path: str) -> Any:
    if not isinstance(path, str) or not path:
        return None
    node = payload
    for token in _tokenize_path(path):
        if isinstance(token, int):
            if isinstance(node, (list, tuple)) and 0 <= token < len(node):
                node = node[token]
            else:
                return None
        else:
            if isinstance(node, dict):
                node = node.get(token)
            else:
                return None
    return node


def _coerce_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        if isinstance(value, int):
            return value
        as_int = int(str(value))
        return as_int
    except Exception:
        return None


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, set)):
        return len(value) == 0
    if isinstance(value, dict):
        return len(value) == 0
    return False


def _sanitize_value(value: Any, spec: Optional[Dict[str, Any]]) -> Any:
    if spec is None:
        return value
    if isinstance(value, str):
        max_text = spec.get("max_text")
        if isinstance(max_text, int) and max_text > 0 and len(value) > max_text:
            return value[:max_text]
        return value
    if isinstance(value, list):
        max_items = spec.get("max_items")
        items = value
        if isinstance(max_items, int) and max_items >= 0:
            items = items[:max_items]
        item_spec = spec.get("items")
        sanitized = [
            _sanitize_value(item, item_spec) if item_spec else item
            for item in items
        ]
        return [item for item in sanitized if not _is_empty(item)]
    if isinstance(value, dict):
        allowed = spec.get("allowed_keys")
        keys: Iterable[str] = value.keys()
        if isinstance(allowed, (list, tuple)) and allowed:
            keys = [k for k in keys if k in allowed]
        max_dict_items = spec.get("max_dict_items")
        if isinstance(max_dict_items, int) and max_dict_items >= 0:
            keys = list(keys)[:max_dict_items]
        fields_spec = spec.get("fields") or {}
        default_field_spec = spec.get("default_field_spec")
        result: Dict[str, Any] = {}
        for key in keys:
            child_value = value.get(key)
            child_spec = fields_spec.get(key, default_field_spec) if isinstance(fields_spec, dict) else default_field_spec
            sanitized_child = (
                _sanitize_value(child_value, child_spec) if child_spec else child_value
            )
            if _is_empty(sanitized_child):
                continue
            result[key] = sanitized_child
        return result
    return value


def _iter_slot_specs(memory_slots: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(memory_slots, dict):
        for slot_name, spec in memory_slots.items():
            if not isinstance(spec, dict):
                continue
            slot_spec = dict(spec)
            slot_spec.setdefault("slot", slot_name)
            yield slot_spec
    elif isinstance(memory_slots, (list, tuple)):
        for entry in memory_slots:
            if isinstance(entry, dict):
                yield entry


def extract_contract_slot_writes(
    payload: Any,
    contract: Dict[str, Any],
    *,
    default_scene: Optional[Any] = None,
) -> List[ContractSlotWrite]:
    """
    Translate a tool output contract into concrete WM slot writes.

    Args:
        payload: Tool result payload (dict expected).
        contract: Tool-defined contract dict.
        default_scene: Fallback scene number (e.g., from tool args).
    """
    if not isinstance(payload, dict):
        return []
    if not isinstance(contract, dict):
        return []
    memory_slots = contract.get("memory_slots") or contract.get("slots")
    slot_specs = list(_iter_slot_specs(memory_slots))
    if not slot_specs:
        return []

    base_scene_path = contract.get("scene_path", "scene_number")
    writes: List[ContractSlotWrite] = []
    for raw_spec in slot_specs:
        if not raw_spec.get("enabled", True):
            continue
        slot_name = raw_spec.get("slot")
        path = raw_spec.get("path")
        if not slot_name or not isinstance(slot_name, str):
            continue
        if not path or not isinstance(path, str):
            continue
        scene_path = raw_spec.get("scene_path", base_scene_path)
        scene_value = _deep_get(payload, scene_path) if scene_path else None
        scene_number = _coerce_int(scene_value)
        if scene_number is None:
            scene_number = _coerce_int(default_scene)
        if scene_number is None and not raw_spec.get("allow_null_scene"):
            continue
        raw_value = _deep_get(payload, path)
        if raw_value is None:
            continue
        sanitized = _sanitize_value(raw_value, raw_spec.get("value_spec"))
        if _is_empty(sanitized) and not raw_spec.get("allow_empty"):
            continue
        writes.append(
            ContractSlotWrite(
                slot=slot_name,
                scene_number=scene_number,
                value=sanitized,
                spec=raw_spec,
                source_path=path,
            )
        )
    return writes


def plan_contract_conflicts_with_actions(
    contract: Dict[str, Any],
    planned_calls: Optional[List[Any]],
) -> bool:
    """Return True when a plan simultaneously claims completion and schedules ACT."""
    if not isinstance(contract, dict):
        return False
    if contract.get("task_complete") is not True:
        return False
    return bool(planned_calls)


__all__ = [
    "ContractSlotWrite",
    "extract_contract_slot_writes",
    "plan_contract_conflicts_with_actions",
]


def overlay_contract_on_reflection(reflection: Dict[str, Any], contract: Dict[str, Any], ignore_complete: bool = False) -> Dict[str, Any]:
    """Overlay minimal contract fields into reflection result.

    - task_complete: bool
    - completed_reason: str (diagnostic)
    ignore_complete=True to ignore task_complete when executed_calls exist.
    """
    ref = dict(reflection or {})
    try:
        if not isinstance(contract, dict):
            return ref
        if not ignore_complete and ("task_complete" in contract):
            ref["task_complete"] = bool(contract.get("task_complete"))
        if isinstance(contract.get("completed_reason"), str):
            ref["completed_reason"] = contract.get("completed_reason")
    except Exception:
        pass
    return ref
