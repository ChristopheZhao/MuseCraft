"""
Utilities for building neutral observation payloads for ReAct agents.

These helpers construct the canonical `obs` structure mandated by stage 3.6:
facts pulled from WorkingMemory + the current round's action digest.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

from ..memory.short_term.working_memory import WorkingMemory


def _coerce_int_list(values: Iterable[Any]) -> List[int]:
    out: List[int] = []
    for value in values or []:
        try:
            out.append(int(value))
        except Exception:
            continue
    return sorted(set(out))


def _sanitize_action_log(actions: Optional[Sequence[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    if not actions:
        return []
    sanitized: List[Dict[str, Any]] = []
    whitelist = {
        "tool",
        "action",
        "scene_number",
        "success",
        "has_artifact",
        "text_present",
        "payload_keys",
        "error_type",
        "error",
        "duration_sec",
        "tokens_used",
    }
    for item in actions:
        if not isinstance(item, dict):
            continue
        record = {}
        for key in whitelist:
            if key in item:
                record[key] = item[key]
        sanitized.append(record)
    return sanitized


def _collect_affected_scenes(
    candidates: Sequence[Dict[str, Any]],
) -> List[int]:
    affected: List[int] = []
    for item in candidates or []:
        if not isinstance(item, dict):
            continue
        sn = item.get("scene_number")
        try:
            if sn is None:
                continue
            affected.append(int(sn))
        except Exception:
            continue
    return sorted(set(affected))


def build_observation_from_wm(
    wm: Optional[WorkingMemory],
    *,
    iteration: int,
    act_log: Optional[Sequence[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Construct the canonical observation structure for a ReAct round.

    Args:
        wm: WorkingMemory instance (required for facts; gracefully handles None).
        iteration: Current iteration index (0-based).
        act_log: Optional list of per-call action records (already fact-only).
    """
    observation: Dict[str, Any] = {"iteration": int(iteration)}

    if wm is not None:
        facts = wm.build_fact_observation()
        scenes = facts.get("scenes") if isinstance(facts, dict) else None
        observation["scenes"] = scenes if isinstance(scenes, list) else []
        observation["completed_scene_numbers"] = _coerce_int_list(
            facts.get("completed_scene_numbers", [])
            if isinstance(facts, dict)
            else []
        )
        observation["failed_scene_numbers"] = _coerce_int_list(
            facts.get("failed_scene_numbers", [])
            if isinstance(facts, dict)
            else []
        )
    else:
        observation["scenes"] = []
        observation["completed_scene_numbers"] = []
        observation["failed_scene_numbers"] = []
        observation["prepared_assets_refs"] = []

    if act_log:
        observation["act_log"] = _sanitize_action_log(act_log)

    return observation


def compute_obs_digest(obs: Dict[str, Any]) -> Dict[str, Any]:
    """Compute a neutral observation digest for logging/diagnostics.

    Returns:
    - scenes_count: number of scene entries (if present)
    - payload_chars: serialized char length (approx)
    - keys_present: list of interesting keys present
    """
    if not isinstance(obs, dict):
        return {}
    try:
        scenes = obs.get("scenes") or []
        scenes_count = len(scenes) if isinstance(scenes, list) else 0
    except Exception:
        scenes_count = 0
    try:
        import json as _json
        payload_chars = len(_json.dumps(obs, ensure_ascii=False))
    except Exception:
        try:
            payload_chars = len(str(obs))
        except Exception:
            payload_chars = 0
    keys_present: List[str] = []
    try:
        for k in ("scenes", "completed_scene_numbers", "failed_scene_numbers", "exec_outcomes", "aug_meta", "aug"):
            if k in obs:
                keys_present.append(k)
    except Exception:
        keys_present = []
    return {
        "scenes_count": scenes_count,
        "payload_chars": payload_chars,
        "keys_present": keys_present,
    }


def derive_action_facts(
    *,
    tool_calls_requested: Optional[Sequence[Any]] = None,
    executed_calls: Optional[Sequence[Any]] = None,
    round_metrics: Optional[Dict[str, Any]] = None,
    actions: Optional[Sequence[Dict[str, Any]]] = None,
    duration_ms: Optional[Union[int, float]] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any], List[Dict[str, Any]]]:
    """
    Derive act_summary/react_metrics/act_log tuples from raw execution data.

    Returns:
        (act_summary, react_metrics, act_log)
    """
    requested_count = len(tool_calls_requested or [])
    executed_count = len(executed_calls or [])
    metrics = {k: (int(v) if isinstance(v, (int, float)) else v) for k, v in (round_metrics or {}).items()}
    success = int(metrics.get("success", 0) or 0)
    fail = int(metrics.get("fail", 0) or 0)
    act_log = _sanitize_action_log(actions)
    act_summary = {
        "tool_calls_requested": requested_count,
        "executed_calls": executed_count or int(metrics.get("total", executed_count)),
        "success": success,
        "fail": fail,
        "affected_scenes": _collect_affected_scenes(act_log),
        "duration_ms": int(duration_ms) if isinstance(duration_ms, (int, float)) else None,
    }
    return act_summary, metrics, act_log
