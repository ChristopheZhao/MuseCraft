"""
Helpers for the explicit script-review execution contract.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional


SCRIPT_REVIEW_RUNTIME_KEY = "script_review"


def build_script_review_contract(
    *,
    action: str,
    gate_id: Optional[int] = None,
    decision_id: Optional[int] = None,
    feedback_text: Optional[str] = None,
    structured_constraints: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    normalized_action = str(action or "").strip().lower()
    target_agents = ["script_writer"]
    if normalized_action == "replan":
        target_agents = ["concept_planner", "script_writer"]
    return {
        "contract_version": "v1",
        "stage": "script",
        "action": normalized_action,
        "gate_id": gate_id,
        "decision_id": decision_id,
        "feedback_text": feedback_text or "",
        "structured_constraints": structured_constraints or {},
        "target_agents": target_agents,
    }


def get_script_review_contract(payload: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return None
    runtime_contracts = payload.get("runtime_contracts")
    if not isinstance(runtime_contracts, dict):
        return None
    contract = runtime_contracts.get(SCRIPT_REVIEW_RUNTIME_KEY)
    return dict(contract) if isinstance(contract, dict) else None


def set_script_review_contract(
    payload: Optional[Dict[str, Any]],
    contract: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    merged = dict(payload or {})
    runtime_contracts = dict(merged.get("runtime_contracts") or {})
    if contract:
        runtime_contracts[SCRIPT_REVIEW_RUNTIME_KEY] = dict(contract)
    else:
        runtime_contracts.pop(SCRIPT_REVIEW_RUNTIME_KEY, None)
    if runtime_contracts:
        merged["runtime_contracts"] = runtime_contracts
    else:
        merged.pop("runtime_contracts", None)
    return merged


def format_script_review_guidance(contract: Optional[Dict[str, Any]]) -> str:
    if not isinstance(contract, dict):
        return ""

    action = str(contract.get("action") or "").strip().lower()
    feedback_text = str(contract.get("feedback_text") or "").strip()
    constraints = contract.get("structured_constraints")

    parts = []
    if action == "revise":
        parts.append("本轮为脚本修订，请保留整体故事方向，仅根据反馈调整脚本表述、节奏或分场细节。")
    elif action == "replan":
        parts.append("本轮为脚本重规划，请根据反馈重做概念/脚本规划，不要沿用已被否决的脚本结构。")

    if feedback_text:
        parts.append(f"人工反馈：{feedback_text}")

    if isinstance(constraints, dict) and constraints:
        try:
            constraints_text = json.dumps(constraints, ensure_ascii=False, indent=2)
        except Exception:
            constraints_text = str(constraints)
        parts.append(f"必须遵守的结构化约束：\n{constraints_text}")

    return "\n".join(parts).strip()


def build_script_preview_text(
    scene_scripts: Optional[Dict[str, Any]],
    *,
    script_output: Optional[Dict[str, Any]] = None,
) -> str:
    preview_segments = []
    if isinstance(scene_scripts, dict):
        for scene_no in sorted(
            scene_scripts.keys(),
            key=lambda value: int(str(value)) if str(value).isdigit() else 999,
        ):
            item = scene_scripts.get(scene_no)
            if not isinstance(item, dict):
                continue
            script_text = str(item.get("script_text") or "").strip()
            if not script_text:
                continue
            preview_segments.append(f"Scene {scene_no}: {script_text}")

    if not preview_segments and isinstance(script_output, dict):
        script_results = script_output.get("script_results")
        scripts = script_results.get("scripts") if isinstance(script_results, dict) else {}
        if isinstance(scripts, dict):
            for scene_no in sorted(
                scripts.keys(),
                key=lambda value: int(str(value)) if str(value).isdigit() else 999,
            ):
                item = scripts.get(scene_no)
                if not isinstance(item, dict):
                    continue
                script_text = str(item.get("script_text") or "").strip()
                if not script_text:
                    continue
                preview_segments.append(f"Scene {scene_no}: {script_text}")

    return "\n\n".join(preview_segments).strip()[:4000]
