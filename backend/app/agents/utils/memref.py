"""MemRef 解析辅助：仅支持 wm.<key> 源，select 过滤可选。"""
from __future__ import annotations

from typing import Any, Dict


def resolve_memref(node: Dict[str, Any], wm: Any) -> Any:
    ref = node.get("$memref") if isinstance(node, dict) else None
    if not isinstance(ref, dict):
        return node
    source = str(ref.get("source") or "")
    selected = ref.get("select")
    if source.startswith("wm.") and wm is not None:
        try:
            key = source.split("wm.", 1)[1]
            val = wm.get(key, {})
            if selected and isinstance(selected, list) and isinstance(val, dict):
                try:
                    return {k: val.get(k) for k in selected if k in val}
                except Exception:
                    return {}
            return val
        except Exception:
            return {}
    return node


def walk_memref(value: Any, wm: Any) -> Any:
    """递归解析 $memref 结构，仅支持 wm.<key> 源。"""
    if isinstance(value, dict) and "$memref" in value:
        return resolve_memref(value, wm)
    if isinstance(value, dict):
        return {k: walk_memref(v, wm) for k, v in value.items()}
    if isinstance(value, list):
        return [walk_memref(v, wm) for v in value]
    return value


__all__ = ["resolve_memref", "walk_memref"]
