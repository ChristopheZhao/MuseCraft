from app.services.role_continuity_observation_contract import (
    normalize_role_continuity_observation,
)


def test_role_continuity_observation_normalizes_passed_visual_evidence():
    observation = normalize_role_continuity_observation(
        {
            "status": "verified",
            "role_continuity_score": 92,
            "source": "manual_contact_sheet_review",
            "reviewer": "qa",
            "checked_scene_numbers": ["1", "2"],
            "evidence_refs": ["/tmp/contact_sheet.jpg"],
        }
    )

    assert observation["status"] == "passed"
    assert observation["visual_evidence_verified"] is True
    assert observation["score"] == 92
    assert observation["checked_scene_numbers"] == [1, 2]
    assert observation["evidence_refs"] == [{"uri": "/tmp/contact_sheet.jpg"}]
    assert observation["source"] == "manual_contact_sheet_review"


def test_role_continuity_observation_promotes_findings_to_failed():
    observation = normalize_role_continuity_observation(
        {
            "status": "needs_review",
            "score": 61,
            "findings": ["scene 3 daughter identity drift"],
        }
    )

    assert observation["status"] == "failed"
    assert observation["visual_evidence_verified"] is True
    assert observation["score"] == 61
    assert observation["identity_drift_findings"] == [
        {"message": "scene 3 daughter identity drift"}
    ]
