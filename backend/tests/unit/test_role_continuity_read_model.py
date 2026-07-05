from app.services.role_continuity_read_model import (
    build_role_continuity_read_model_from_quality,
    build_role_continuity_read_model_from_results,
)


def test_role_continuity_read_model_projects_unverified_contract_ready_state():
    quality_result = {
        "requires_human_review": True,
        "content_quality": {
            "role_continuity_score": None,
            "contract_readiness": {
                "status": "ready",
                "score": 100,
                "same_carrier_verified": True,
            },
            "visual_evidence_verified": False,
            "role_continuity_diagnostics": {
                "status": "not_evaluated",
                "score_cap_when_unverified": 89,
                "fallback_reason": "role_continuity_visual_evidence_missing",
                "contract_carrier": {"scene_info_ref": "internal/full/payload.json"},
                "contract_diagnostics": [{"code": "same_identity_carrier_verified"}],
                "display_summary": {
                    "characters": [
                        {
                            "canonical_id": "mother",
                            "display_name": "Mother",
                            "stable_anchor_count": 4,
                            "allowed_variant_count": 2,
                            "reference_asset_count": 0,
                        }
                    ],
                    "character_count": 1,
                    "scene_lock_count": 6,
                    "locked_scene_numbers": [1, 2, 3, 4, 5, 6],
                    "missing_lock_scenes": [],
                    "empty_cast_scenes": [],
                },
            },
        },
        "quality_assessment": {
            "approval_status": "conditional",
            "requires_human_review": True,
            "quality_score_cap_applied": 89,
            "fallback_reason": "role_continuity_visual_evidence_missing",
        },
    }

    projection = build_role_continuity_read_model_from_quality(quality_result)

    assert projection["status"] == "not_evaluated"
    assert projection["review_status"] == "unverified"
    assert projection["role_continuity_score"] is None
    assert projection["score_cap"] == 89
    assert projection["requires_human_review"] is True
    assert projection["unverified_reason"] == "role_continuity_visual_evidence_missing"
    assert projection["contract_readiness"] == {
        "status": "ready",
        "score": 100,
        "same_carrier_verified": True,
    }
    assert projection["display_summary"]["characters"][0]["display_name"] == "Mother"
    assert "contract_carrier" not in projection
    assert "contract_diagnostics" not in projection


def test_role_continuity_read_model_extracts_quality_checker_result():
    projection = build_role_continuity_read_model_from_results(
        {
            "quality_checker": {
                "content_quality": {
                    "role_continuity_score": 40,
                    "identity_drift_findings": [{"scene_number": 3, "message": "drift"}],
                    "visual_evidence_verified": True,
                    "role_continuity_diagnostics": {
                        "status": "failed",
                        "score_cap_when_failed": 79,
                    },
                    "contract_readiness": {
                        "status": "ready",
                        "score": 100,
                        "same_carrier_verified": True,
                    },
                },
                "quality_assessment": {
                    "approval_status": "conditional",
                    "requires_human_review": True,
                },
            }
        }
    )

    assert projection["review_status"] == "failed"
    assert projection["role_continuity_score"] == 40
    assert projection["score_cap"] == 79
    assert projection["visual_evidence_verified"] is True
    assert projection["identity_drift_findings"] == [{"scene_number": 3, "message": "drift"}]


def test_role_continuity_read_model_marks_missing_quality_result():
    projection = build_role_continuity_read_model_from_results({"video_generator": {"ok": True}})

    assert projection["status"] == "not_available"
    assert projection["review_status"] == "not_available"
    assert projection["fallback_reason"] == "quality_checker_result_missing"
    assert projection["requires_human_review"] is True
