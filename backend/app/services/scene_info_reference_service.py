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


class SceneInfoReferenceResolutionError(RuntimeError):
    """Raised when a scene-info reference cannot be resolved or loaded."""


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


def resolve_scene_info_ref_path(ref: str) -> Path:
    """Resolve a scene-info reference to a readable local JSON path."""
    if not isinstance(ref, str) or not ref.strip():
        raise SceneInfoReferenceResolutionError("scene_info_ref is empty")

    path = ref.strip()
    if path.startswith("file://"):
        path = path[len("file://"):]

    try:
        candidate = Path(path)
    except Exception as exc:
        raise SceneInfoReferenceResolutionError(
            f"scene_info_ref parse failed: {exc}"
        ) from exc

    candidate_paths = []
    if candidate.is_absolute():
        candidate_paths.append(candidate)
    else:
        candidate_paths.append(candidate)
        try:
            backend_root = Path(__file__).resolve().parents[2]
            candidate_paths.append(backend_root / candidate)
        except Exception:
            pass

    for cand in candidate_paths:
        try:
            if cand.exists():
                return cand
        except Exception:
            continue

    raise SceneInfoReferenceResolutionError(f"scene_info_ref not found: {path}")


def load_scene_info_payload(ref: str) -> Dict[str, Any]:
    """Load a scene-info payload from a persisted local reference."""
    resolved_path = resolve_scene_info_ref_path(ref)
    try:
        payload = json.loads(resolved_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SceneInfoReferenceResolutionError(
            f"scene_info_ref load failed: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise SceneInfoReferenceResolutionError(
            "scene_info_ref must be a JSON object"
        )
    return payload
