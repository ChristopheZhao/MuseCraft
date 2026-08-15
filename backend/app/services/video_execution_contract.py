"""
Helpers for explicit video-generation execution contracts.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from .agent_execution_contract import require_agent_execution_contract


def build_video_generation_execution_contract(
    *,
    workflow_state_id: str,
    generate_audio: Optional[bool] = None,
) -> Dict[str, Any]:
    contract: Dict[str, Any] = {
        "contract_version": "v1",
        "agent": "video_generator",
        "operation": "generate_scene_video",
        "scope": {
            "scope_type": "workflow",
            "scope_ref": str(workflow_state_id or ""),
        },
        "inputs": {
            "facts": {},
            "artifacts": [],
        },
        "constraints": {},
        "storage": {
            "workflow_state_id": str(workflow_state_id or ""),
        },
    }
    if isinstance(generate_audio, bool):
        contract["constraints"]["generate_audio"] = bool(generate_audio)
    return contract


def get_video_generation_execution_contract(
    payload: Optional[Dict[str, Any]],
    *,
    workflow_state_id: str = "",
) -> Dict[str, Any]:
    del workflow_state_id
    return require_agent_execution_contract(
        payload,
        expected_agent="video_generator",
    )
