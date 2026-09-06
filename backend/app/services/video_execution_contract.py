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
    if (
        type(workflow_state_id) is not str
        or not workflow_state_id
        or workflow_state_id != workflow_state_id.strip()
    ):
        raise ValueError("workflow_state_id must be a canonical non-empty string")
    if generate_audio is not None and type(generate_audio) is not bool:
        raise ValueError("generate_audio must be boolean when provided")
    contract: Dict[str, Any] = {
        "contract_version": "v1",
        "agent": "video_generator",
        "operation": "generate_scene_video",
        "workflow_state_id": workflow_state_id,
    }
    if type(generate_audio) is bool:
        contract["constraints"] = {"generate_audio": generate_audio}
    return contract


def get_video_generation_execution_contract(
    payload: Optional[Dict[str, Any]],
    *,
    workflow_state_id: str = "",
) -> Dict[str, Any]:
    contract = require_agent_execution_contract(
        payload,
        expected_agent="video_generator",
        expected_workflow_state_id=workflow_state_id,
        allowed_fields={
            "contract_version",
            "agent",
            "operation",
            "workflow_state_id",
            "constraints",
        },
    )
    if contract.get("operation") != "generate_scene_video":
        raise ValueError("video_generator execution_contract.operation is invalid")
    constraints = contract.get("constraints")
    constraints = constraints if isinstance(constraints, dict) else {}
    if "generate_audio" in constraints and type(constraints.get("generate_audio")) is not bool:
        raise ValueError(
            "video_generator execution_contract.constraints.generate_audio must be boolean"
        )
    return contract
