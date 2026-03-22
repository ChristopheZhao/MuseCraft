"""
Helpers for explicit video-composer execution boundaries.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


VALID_COMPOSE_MODES = ("compose", "bgm", "voiceover")


def normalize_video_composer_compose_mode(value: Any) -> str:
    lowered = str(value or "").strip().lower()
    if lowered in {"background_music", "bgm_mix"}:
        lowered = "bgm"
    elif lowered in {"voice", "voice_mix", "voiceover_mix"}:
        lowered = "voiceover"
    elif lowered in {"compose_video", "compose_story"}:
        lowered = "compose"
    if lowered not in VALID_COMPOSE_MODES:
        raise ValueError(f"unsupported video_composer compose_mode: {value}")
    return lowered


def build_video_composer_execution_contract(
    *,
    workflow_state_id: str,
    compose_mode: str = "compose",
) -> Dict[str, Any]:
    normalized_mode = normalize_video_composer_compose_mode(compose_mode)
    operation_by_mode = {
        "compose": "compose_final_video",
        "bgm": "mix_background_music",
        "voiceover": "mix_voiceover",
    }
    return {
        "contract_version": "v1",
        "agent": "video_composer",
        "operation": operation_by_mode[normalized_mode],
        "scope": {
            "scope_type": "workflow",
            "scope_ref": str(workflow_state_id or ""),
        },
        "inputs": {
            "facts": {},
            "artifacts": [],
        },
        "constraints": {
            "compose_mode": normalized_mode,
        },
        "storage": {
            "workflow_state_id": str(workflow_state_id or ""),
        },
    }


def get_video_composer_compose_mode(execution_contract: Optional[Dict[str, Any]]) -> str:
    constraints = execution_contract.get("constraints") if isinstance(execution_contract, dict) else {}
    if not isinstance(constraints, dict):
        constraints = {}
    return normalize_video_composer_compose_mode(constraints.get("compose_mode") or "compose")


def get_video_composer_execution_contract(
    payload: Optional[Dict[str, Any]],
    *,
    workflow_state_id: str = "",
) -> Dict[str, Any]:
    if isinstance(payload, dict):
        contract = payload.get("execution_contract")
        if isinstance(contract, dict):
            return dict(contract)
        if _contains_legacy_compose_inputs(payload):
            raise ValueError(
                "legacy video_composer inputs are no longer supported; provide execution_contract instead"
            )
    return build_video_composer_execution_contract(
        workflow_state_id=str(workflow_state_id or ""),
    )


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
