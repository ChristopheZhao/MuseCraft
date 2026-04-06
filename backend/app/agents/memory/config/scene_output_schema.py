"""Loader for scene_outputs schema definitions."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml

_SCENE_SCHEMA_CACHE: Dict[str, Dict[str, Any]] | None = None


def _load_scene_output_schemas() -> Dict[str, Dict[str, Any]]:
    global _SCENE_SCHEMA_CACHE
    if _SCENE_SCHEMA_CACHE is not None:
        return _SCENE_SCHEMA_CACHE
    base = Path(__file__).resolve().parent
    path = base / "scene_outputs.yaml"
    if not path.exists():
        _SCENE_SCHEMA_CACHE = {}
        return _SCENE_SCHEMA_CACHE
    with path.open("r", encoding="utf-8") as fh:
        payload = yaml.safe_load(fh) or {}
    data = payload.get("scene_outputs")
    if not isinstance(data, dict):
        data = {}
    _SCENE_SCHEMA_CACHE = {str(k): (v or {}) for k, v in data.items()}
    return _SCENE_SCHEMA_CACHE


def load_scene_output_schema(kind: str) -> Dict[str, Any]:
    schemas = _load_scene_output_schemas()
    return schemas.get(str(kind), {})


__all__ = ["load_scene_output_schema"]
