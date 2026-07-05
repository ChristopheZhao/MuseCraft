"""
Compact role-continuity projection for terminal/runtime read models.

This module normalizes quality-checker output at the read-model boundary. It
does not infer runtime state from queue/provider details and does not expose
the full character identity carrier.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


ROLE_CONTINUITY_READ_MODEL_VERSION = "v1"


def _as_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> List[Any]:
    return list(value) if isinstance(value, list) else []


def _first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _coerce_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def _cap_list(values: Any, *, limit: int = 20) -> List[Any]:
    return _as_list(values)[: max(0, int(limit))]


def _extract_quality_result(results: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(results, dict):
        return {}
    quality_result = results.get("quality_checker")
    if isinstance(quality_result, dict):
        return dict(quality_result)
    return {}


def _derive_score_cap(status: str, diagnostics: Dict[str, Any]) -> Optional[int]:
    if status == "failed":
        return _coerce_int(diagnostics.get("score_cap_when_failed"))
    if status in {"not_evaluated", "visual_not_evaluated"}:
        return _coerce_int(diagnostics.get("score_cap_when_unverified"))
    if status in {
        "needs_human_review",
        "missing_contract",
        "carrier_missing",
        "unverifiable",
        "missing_scene_locks",
        "incomplete",
    }:
        return _coerce_int(diagnostics.get("score_cap_when_contract_missing"))
    return None


def _derive_review_status(
    *,
    status: str,
    visual_evidence_verified: bool,
    role_score: Optional[int],
    fallback_reason: str,
    drift_findings: List[Any],
) -> str:
    if not status:
        return "unverified" if fallback_reason else "unknown"
    if status == "not_available":
        return "not_available"
    if status == "not_required":
        return "not_required"
    if status == "failed" or drift_findings:
        return "failed"
    if status in {"not_evaluated", "visual_not_evaluated"}:
        return "unverified"
    if status in {
        "needs_human_review",
        "missing_contract",
        "carrier_missing",
        "unverifiable",
        "missing_scene_locks",
        "incomplete",
    }:
        return "needs_human_review"
    if visual_evidence_verified and role_score is not None:
        return "deliverable"
    if fallback_reason:
        return "needs_human_review"
    return "unverified"


def _build_display_summary(diagnostics: Dict[str, Any]) -> Dict[str, Any]:
    display_summary = _as_dict(diagnostics.get("display_summary"))
    if display_summary:
        characters = _cap_list(display_summary.get("characters"), limit=8)
        return {
            "characters": characters,
            "character_count": _coerce_int(display_summary.get("character_count")) or len(characters),
            "scene_lock_count": _coerce_int(display_summary.get("scene_lock_count")) or 0,
            "locked_scene_numbers": _cap_list(display_summary.get("locked_scene_numbers"), limit=20),
            "missing_lock_scenes": _cap_list(display_summary.get("missing_lock_scenes"), limit=20),
            "empty_cast_scenes": _cap_list(display_summary.get("empty_cast_scenes"), limit=20),
        }

    return {
        "characters": [],
        "character_count": _coerce_int(diagnostics.get("character_count")) or 0,
        "scene_lock_count": _coerce_int(diagnostics.get("scene_lock_count")) or 0,
        "locked_scene_numbers": _cap_list(diagnostics.get("locked_scene_numbers"), limit=20),
        "missing_lock_scenes": _cap_list(diagnostics.get("missing_lock_scenes"), limit=20),
        "empty_cast_scenes": _cap_list(diagnostics.get("empty_cast_scenes"), limit=20),
    }


def build_role_continuity_read_model_from_quality(
    quality_result: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Normalize quality-checker role-continuity output for frontend/runtime reads."""
    if not isinstance(quality_result, dict) or not quality_result:
        return {
            "version": ROLE_CONTINUITY_READ_MODEL_VERSION,
            "status": "not_available",
            "review_status": "not_available",
            "role_continuity_score": None,
            "visual_evidence_verified": False,
            "score_cap": None,
            "fallback_reason": "quality_checker_result_missing",
            "unverified_reason": "quality_checker_result_missing",
            "requires_human_review": True,
            "approval_status": "needs_review",
            "contract_readiness": {
                "status": "unknown",
                "score": None,
                "same_carrier_verified": False,
            },
            "identity_drift_findings": [],
            "display_summary": {
                "characters": [],
                "character_count": 0,
                "scene_lock_count": 0,
                "locked_scene_numbers": [],
                "missing_lock_scenes": [],
                "empty_cast_scenes": [],
            },
        }

    assessment = _as_dict(quality_result.get("quality_assessment"))
    content_quality = _as_dict(quality_result.get("content_quality"))
    diagnostics = _as_dict(
        assessment.get("role_continuity_diagnostics")
        or content_quality.get("role_continuity_diagnostics")
    )
    contract_readiness = _as_dict(
        assessment.get("contract_readiness") or content_quality.get("contract_readiness")
    )

    status = _first_text(diagnostics.get("status"), contract_readiness.get("status"))
    status = status or "unknown"
    role_score = content_quality.get("role_continuity_score")
    if role_score is None:
        role_score = _as_dict(assessment.get("detailed_scores")).get("role_continuity")
    role_score = _coerce_int(role_score)

    visual_evidence_verified = bool(
        assessment.get("visual_evidence_verified")
        if "visual_evidence_verified" in assessment
        else content_quality.get("visual_evidence_verified")
    )
    fallback_reason = _first_text(
        assessment.get("fallback_reason"),
        content_quality.get("fallback_reason"),
        diagnostics.get("fallback_reason"),
    )
    drift_findings = _as_list(
        assessment.get("identity_drift_findings")
        if "identity_drift_findings" in assessment
        else content_quality.get("identity_drift_findings")
    )
    score_cap = _coerce_int(assessment.get("quality_score_cap_applied"))
    if score_cap is None:
        score_cap = _derive_score_cap(status, diagnostics)

    review_status = _derive_review_status(
        status=status,
        visual_evidence_verified=visual_evidence_verified,
        role_score=role_score,
        fallback_reason=fallback_reason,
        drift_findings=drift_findings,
    )
    requires_human_review = bool(
        quality_result.get("requires_human_review")
        or assessment.get("requires_human_review")
        or review_status in {"failed", "needs_human_review", "unverified", "not_available"}
    )
    unverified_reason = ""
    if review_status in {"unverified", "needs_human_review", "not_available"}:
        unverified_reason = fallback_reason or status

    return {
        "version": ROLE_CONTINUITY_READ_MODEL_VERSION,
        "status": status,
        "review_status": review_status,
        "role_continuity_score": role_score,
        "visual_evidence_verified": visual_evidence_verified,
        "score_cap": score_cap,
        "fallback_reason": fallback_reason,
        "unverified_reason": unverified_reason,
        "requires_human_review": requires_human_review,
        "approval_status": _first_text(
            assessment.get("approval_status"),
            quality_result.get("approval_status"),
        ),
        "contract_readiness": {
            "status": contract_readiness.get("status"),
            "score": contract_readiness.get("score"),
            "same_carrier_verified": bool(contract_readiness.get("same_carrier_verified")),
        },
        "identity_drift_findings": drift_findings[:10],
        "display_summary": _build_display_summary(diagnostics),
    }


def build_role_continuity_read_model_from_results(
    results: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Extract quality_checker output from workflow results and normalize it."""
    return build_role_continuity_read_model_from_quality(_extract_quality_result(results))
