"""
Persist scene-info payloads as local JSON references for media agents/tools.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from ..core.config import settings
from ..models import AgentType


def persist_scene_info_ref(
    *,
    workflow_id: str,
    agent_type: AgentType,
    payload: Dict[str, Any],
) -> Optional[str]:
    """Persist scene info payload as JSON and return a repo-relative ref path."""
    if not payload or not workflow_id:
        return None

    try:
        base_dir = Path(settings.TEMP_PATH) / "context"
        base_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{agent_type.value}_{workflow_id}.json"
        ref_path = (base_dir / filename).resolve()
        with open(ref_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False)
        try:
            backend_root = Path(__file__).resolve().parents[2]
            return str(ref_path.relative_to(backend_root))
        except Exception:
            return str(ref_path)
    except Exception:
        return None
