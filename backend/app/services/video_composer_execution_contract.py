"""
Helpers for explicit video-composer execution boundaries.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from .agent_execution_contract import require_agent_execution_contract


VALID_COMPOSE_MODES = ("compose", "bgm", "voiceover")


def normalize_video_composer_compose_mode(value: Any) -> str:
    if type(value) is not str or value not in VALID_COMPOSE_MODES:
        raise ValueError(f"unsupported video_composer compose_mode: {value}")
    return value


def build_video_composer_execution_contract(
    *,
    workflow_state_id: str,
    compose_mode: str,
) -> Dict[str, Any]:
    if (
        type(workflow_state_id) is not str
        or not workflow_state_id
        or workflow_state_id != workflow_state_id.strip()
    ):
        raise ValueError("workflow_state_id must be a canonical non-empty string")
    normalized_mode = normalize_video_composer_compose_mode(compose_mode)
    return {
        "contract_version": "v1",
        "agent": "video_composer",
        "operation": normalized_mode,
        "workflow_state_id": workflow_state_id,
    }


def get_video_composer_compose_mode(execution_contract: Optional[Dict[str, Any]]) -> str:
    if not isinstance(execution_contract, dict):
        raise ValueError("video_composer execution_contract is required")
    constraints = execution_contract.get("constraints")
    if isinstance(constraints, dict) and constraints.get("compose_mode") is not None:
        raise ValueError("duplicate compose intent source is not supported")
    if constraints is not None:
        raise ValueError("video_composer execution_contract constraints are not supported")
    compose_mode = execution_contract.get("operation")
    if type(compose_mode) is not str or compose_mode not in VALID_COMPOSE_MODES:
        raise ValueError("video_composer execution_contract compose_mode operation is required")
    return compose_mode


def get_video_composer_execution_contract(
    payload: Optional[Dict[str, Any]],
    *,
    workflow_state_id: str = "",
) -> Dict[str, Any]:
    if isinstance(payload, dict):
        if _contains_legacy_compose_inputs(payload):
            raise ValueError(
                "legacy video_composer inputs are no longer supported; provide execution_contract without legacy compose flags"
            )
    contract = require_agent_execution_contract(
        payload,
        expected_agent="video_composer",
        expected_workflow_state_id=workflow_state_id,
        allowed_fields={
            "contract_version",
            "agent",
            "operation",
            "workflow_state_id",
        },
    )
    get_video_composer_compose_mode(contract)
    return contract


def _contains_legacy_compose_inputs(payload: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(payload, dict):
        return False
    if payload.get("add_bgm") is not None:
        return True
    if payload.get("add_voiceover") is not None:
        return True
    if payload.get("compose_requested") is not None:
        return True

    static_ctx = payload.get("static_context")
    static_ctx = static_ctx if isinstance(static_ctx, dict) else {}
    requests = static_ctx.get("requests")
    requests = requests if isinstance(requests, dict) else {}
    for key in ("compose_requested", "voiceover_requested", "bgm_requested"):
        if requests.get(key) is not None:
            return True
    return False
