"""
Role-continuity visual observation contract.

This module normalizes explicit visual evidence before the quality checker
consumes it. It does not infer visual continuity from prompt text or provider
status.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


ROLE_CONTINUITY_OBSERVATION_CONTRACT_VERSION = "v1"


def _as_list(value: Any) -> List[Any]:
    return list(value) if isinstance(value, list) else []


def _coerce_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def _clamp_score(value: Any) -> Optional[int]:
    score = _coerce_int(value)
    if score is None:
        return None
    return max(0, min(100, score))


def _normalize_status(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"pass", "passed", "verified", "ok", "deliverable"}:
        return "passed"
    if raw in {"fail", "failed", "drift", "identity_drift"}:
        return "failed"
    if raw in {"inconclusive", "uncertain", "needs_review", "needs_human_review"}:
        return "needs_human_review"
    if raw in {"not_evaluated", "unverified", "missing", "not_available"}:
        return "not_evaluated"
    return "not_available"


def _normalize_findings(value: Any) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    for item in _as_list(value):
        if isinstance(item, dict):
            finding = dict(item)
        else:
            text = str(item or "").strip()
            if not text:
                continue
            finding = {"message": text}
        if finding:
            findings.append(finding)
    return findings[:20]


def _normalize_evidence_refs(value: Any) -> List[Dict[str, Any]]:
    refs: List[Dict[str, Any]] = []
    for item in _as_list(value):
        if isinstance(item, dict):
            ref = dict(item)
        else:
            uri = str(item or "").strip()
            if not uri:
                continue
            ref = {"uri": uri}
        if ref:
            refs.append(ref)
    return refs[:20]


def normalize_role_continuity_observation(value: Any) -> Dict[str, Any]:
    """Normalize explicit visual role-continuity evidence."""
    if not isinstance(value, dict) or not value:
        return {
            "contract_version": ROLE_CONTINUITY_OBSERVATION_CONTRACT_VERSION,
            "status": "not_available",
            "visual_evidence_verified": False,
            "score": None,
            "identity_drift_findings": [],
            "evidence_refs": [],
            "checked_scene_numbers": [],
            "source": "",
            "reviewer": "",
            "fallback_reason": "role_continuity_observation_missing",
        }

    status = _normalize_status(value.get("status") or value.get("review_status"))
    findings = _normalize_findings(
        value.get("identity_drift_findings")
        or value.get("findings")
        or value.get("drift_findings")
    )
    if findings and status != "failed":
        status = "failed"

    explicit_visual = value.get("visual_evidence_verified")
    visual_evidence_verified = (
        bool(explicit_visual)
        if explicit_visual is not None
        else status in {"passed", "failed"}
    )

    checked_scene_numbers = [
        scene_number
        for scene_number in (_coerce_int(item) for item in _as_list(value.get("checked_scene_numbers")))
        if scene_number is not None
    ]

    fallback_reason = str(value.get("fallback_reason") or "").strip()
    if status in {"not_available", "not_evaluated", "needs_human_review"} and not fallback_reason:
        fallback_reason = "role_continuity_observation_unverified"

    return {
        "contract_version": ROLE_CONTINUITY_OBSERVATION_CONTRACT_VERSION,
        "status": status,
        "visual_evidence_verified": visual_evidence_verified,
        "score": _clamp_score(value.get("score") or value.get("role_continuity_score")),
        "identity_drift_findings": findings,
        "evidence_refs": _normalize_evidence_refs(value.get("evidence_refs") or value.get("references")),
        "checked_scene_numbers": checked_scene_numbers[:50],
        "source": str(value.get("source") or "").strip(),
        "reviewer": str(value.get("reviewer") or value.get("actor_id") or "").strip(),
        "fallback_reason": fallback_reason,
    }


__all__ = [
    "ROLE_CONTINUITY_OBSERVATION_CONTRACT_VERSION",
    "normalize_role_continuity_observation",
]
