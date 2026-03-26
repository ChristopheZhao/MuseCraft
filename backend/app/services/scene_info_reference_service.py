"""
Persist scene-info payloads as local JSON references for media agents/tools.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from ..core.config import settings
from ..models import AgentType


class SceneInfoReferencePersistenceError(RuntimeError):
    """Raised when scene-info reference persistence cannot produce a usable ref."""


def persist_scene_info_ref(
    *,
    workflow_id: str,
    agent_type: AgentType,
    payload: Dict[str, Any],
) -> str:
    """Persist scene info payload as JSON and return a repo-relative ref path."""
    normalized_workflow_id = str(workflow_id or "").strip()
    if not normalized_workflow_id:
        raise SceneInfoReferencePersistenceError(
            "Scene info persistence requires workflow_id"
        )
    if not isinstance(payload, dict) or not payload:
        raise SceneInfoReferencePersistenceError(
            "Scene info persistence requires non-empty payload"
        )

    try:
        base_dir = Path(settings.TEMP_PATH) / "context"
        base_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{agent_type.value}_{normalized_workflow_id}.json"
        ref_path = (base_dir / filename).resolve()
        with open(ref_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False)
    except Exception as exc:
        raise SceneInfoReferencePersistenceError(
            "Scene info persistence failed: "
            f"workflow_id={normalized_workflow_id} agent_type={agent_type.value} detail={exc}"
        ) from exc

    backend_root = Path(__file__).resolve().parents[2]
    try:
        return str(ref_path.relative_to(backend_root))
    except ValueError:
        return str(ref_path)
