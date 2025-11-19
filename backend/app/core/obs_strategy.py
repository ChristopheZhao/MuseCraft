from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


_DEFAULT_STRATEGIES = {
    "video_generator": {
        "name": "video_default",
        # build_view controls (interim; will migrate to pure model compaction guidance)
        "ready_limit": 5,
        "dependency_limit": 3,
        "failure_threshold": 2,
        "failure_limit": 3,
        "ready_event_limit": 3,
        "dependency_event_limit": 2,
        "failure_event_limit": 2,
        # Ensure VideoGeneratorAgent invariant: strategy must supply completed_limit
        "completed_limit": 10,
    }
}


def load_obs_strategies(path: Optional[str] = None) -> Dict[str, Any]:
    root = Path(path) if path else Path(__file__).parent.parent / "config" / "obs_strategies.yaml"
    if root.exists():
        try:
            with open(root, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                if isinstance(data, dict) and data:
                    return data
        except Exception:
            pass
    return _DEFAULT_STRATEGIES.copy()


def get_strategy_for_agent(agent_name: str, path: Optional[str] = None) -> Dict[str, Any]:
    data = load_obs_strategies(path)
    return data.get(agent_name) or data.get("video_generator") or {}
