import asyncio
import json
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agents.adapters.memory_views import build_quality_checker_context
from app.agents.memory.short_term.service import WorkingMemoryService
from app.agents.memory.storage.in_memory import InMemoryShortTermStore
from app.agents.quality_checker import QualityCheckerAgent
from app.agents.utils.memory_helpers import write_shared_fact
from app.core.config import settings
from app.models import AgentType
from app.services.context_assembler import ContextContractAssembler
from app.services.character_identity_contract import normalize_character_identity_contract
from app.services.scene_info_reference_service import persist_scene_info_ref


def _build_service() -> WorkingMemoryService:
    return WorkingMemoryService(store_factory=lambda: InMemoryShortTermStore())


def _load_intro_outro_real_sample() -> tuple[dict, dict]:
    backend_root = Path(__file__).resolve().parents[2]
    published = json.loads(
        (
            backend_root
            / "storage/temp/published_deliverables/"
            / "script_9587c5b5-216c-4bf4-8a37-4c9078b4e900_attempt106_rev0.json"
        ).read_text(encoding="utf-8")
    )
    composer = json.loads(
        (
            backend_root
            / "storage/temp/context/"
            / "video_composer_scene_media_9587c5b5-216c-4bf4-8a37-4c9078b4e900.json"
        ).read_text(encoding="utf-8")
    )
    return published, composer


def test_build_quality_checker_context_normalizes_boundary_from_mas_wm(monkeypatch):
    service = _build_service()
    workflow_id = "wf-quality-boundary"

    monkeypatch.setattr(settings, "FINAL_OUTPUT_ROOT", "/tmp/final_outputs")
    monkeypatch.setattr(
        "app.agents.adapters.memory_views.probe_local_video_metadata_sync",
        lambda path: {
            "duration": 45.2,
            "format": "mp4",
            "file_size": 17030496,
            "file_size_mb": 16.24,
            "resolution": "1920x1080",
        }
        if path == "/tmp/final_outputs/videos/final.mp4"
        else {},
    )

    write_shared_fact(
        workflow_id,
        "project.concept_plan",
        {"overview": "original brief", "scenes": [{"scene_number": 1}]},
        service=service,
    )
    write_shared_fact(
        workflow_id,
        "project.final_video",
        {"url": "/files/outputs/videos/final.mp4"},
        service=service,
    )
    write_shared_fact(
        workflow_id,
        "scene_outputs.video",
        {
            "2": {"scene_number": 2, "duration_sec": 5.0},
            "1": {"scene_number": 1, "duration_sec": 10.0},
        },
        service=service,
    )

    result = build_quality_checker_context(workflow_id, service=service)
    context = result["context"]
    diagnostics = result["diagnostics"]

    assert context["final_video"]["path"] == "/tmp/final_outputs/videos/final.mp4"
    assert context["final_video"]["url"] == "/files/outputs/videos/final.mp4"
    assert context["concept_plan"]["overview"] == "original brief"
    assert context["original_requirements"]["overview"] == "original brief"
    assert context["video_metadata"]["duration"] == 45.2
    assert context["video_metadata"]["format"] == "mp4"
    assert context["composition_timeline"] == [
        {"scene_number": 1, "start": 0.0, "end": 10.0, "duration": 10.0},
        {"scene_number": 2, "start": 10.0, "end": 15.0, "duration": 5.0},
    ]
    assert diagnostics["status"] == "resolved_with_fallbacks"
    assert diagnostics["concept_plan_source"] == "project.concept_plan"
    assert diagnostics["timeline_source"] == "scene_outputs.video"
    assert diagnostics["video_metadata_source"] == "local_probe"


def test_build_quality_checker_context_projects_role_continuity_contract_from_same_carrier(
    tmp_path,
    monkeypatch,
):
    service = _build_service()
    workflow_id = "wf-quality-role-continuity"
    monkeypatch.setattr(settings, "TEMP_PATH", str(tmp_path))

    concept_plan = {
        "content_elements": {
            "characters": [
                {
                    "canonical_id": "mother",
                    "display_name": "妈妈",
                    "visual_identity": ["温柔母亲", "稳定面部轮廓"],
                },
                {
                    "canonical_id": "child",
                    "display_name": "孩子",
                    "visual_identity": ["从幼年到青年", "明亮眼神"],
                },
            ]
        }
    }
    scenes = [
        {
            "scene_number": 1,
            "duration": 5.0,
            "characters_present": ["妈妈", "孩子"],
            "character_descriptions": ["孩子随年龄变化：幼年→少年→青年"],
        },
        {
            "scene_number": 2,
            "duration": 5.0,
            "characters_present": ["妈妈", "孩子"],
        },
    ]

    write_shared_fact(
        workflow_id,
        "project.concept_plan",
        concept_plan,
        service=service,
    )
    write_shared_fact(
        workflow_id,
        "scene_overview",
        {"scenes": scenes},
        service=service,
    )
    scene_info_ref = persist_scene_info_ref(
        workflow_id=workflow_id,
        agent_type=AgentType.VIDEO_GENERATOR,
        payload=normalize_character_identity_contract(
            {
                "concept_plan": concept_plan,
                "scenes_to_generate": scenes,
            }
        ),
    )

    result = build_quality_checker_context(workflow_id, service=service)
    context = result["context"]

    assert context["character_identity_contract_carrier"] == {
        "source": "scene_info_ref",
        "agent_type": AgentType.VIDEO_GENERATOR.value,
        "scene_info_ref": scene_info_ref,
        "same_carrier_verified": True,
        "fallback_reason": "",
    }
    assert context["character_identity_bible"]["source"] == "concept_plan.content_elements.characters"
    assert [item["canonical_id"] for item in context["character_identity_bible"]["characters"]] == [
        "mother",
        "child",
    ]
    assert context["quality_expectations"]["role_continuity"]["required"] is True
    assert context["quality_expectations"]["role_continuity"]["score_field"] == "role_continuity_score"
    assert [lock["scene_number"] for lock in context["scene_character_locks"]] == [1, 2]
    assert [cast["canonical_id"] for cast in context["scene_character_locks"][0]["cast"]] == [
        "mother",
        "child",
    ]
    assert result["diagnostics"]["character_identity_contract_source"] == (
        "concept_plan.content_elements.characters"
    )
    assert result["diagnostics"]["character_identity_contract_carrier"]["same_carrier_verified"] is True


def test_build_quality_checker_context_marks_missing_same_identity_carrier(tmp_path, monkeypatch):
    service = _build_service()
    workflow_id = "wf-quality-role-carrier-missing"
    monkeypatch.setattr(settings, "TEMP_PATH", str(tmp_path))

    write_shared_fact(
        workflow_id,
        "project.concept_plan",
        {
            "content_elements": {
                "characters": [
                    {
                        "canonical_id": "mother",
                        "display_name": "妈妈",
                        "visual_identity": ["温柔母亲"],
                    }
                ]
            }
        },
        service=service,
    )
    write_shared_fact(
        workflow_id,
        "scene_overview",
        {"scenes": [{"scene_number": 1, "characters_present": ["妈妈"], "duration": 5.0}]},
        service=service,
    )

    result = build_quality_checker_context(workflow_id, service=service)
    carrier = result["context"]["character_identity_contract_carrier"]

    assert carrier["source"] == "rebuilt_from_working_memory"
    assert carrier["same_carrier_verified"] is False
    assert carrier["fallback_reason"] == "identity_contract_rebuilt_from_working_memory"
    assert any(
        item.get("code") == "same_identity_carrier_missing"
        for item in result["context"]["character_identity_diagnostics"]
    )


def test_build_quality_checker_context_reports_incomplete_scene_video_outputs(monkeypatch):
    service = _build_service()
    workflow_id = "wf-quality-incomplete-scene-videos"

    monkeypatch.setattr(settings, "FINAL_OUTPUT_ROOT", "/tmp/final_outputs")
    monkeypatch.setattr(
        "app.agents.adapters.memory_views.probe_local_video_metadata_sync",
        lambda _path: {"duration": 10.0, "format": "mp4"},
    )

    write_shared_fact(
        workflow_id,
        "project.final_video",
        {"url": "/files/outputs/videos/final.mp4"},
        service=service,
    )
    write_shared_fact(
        workflow_id,
        "scene_overview",
        {"scenes": [{"scene_number": 1, "duration": 10.0}, {"scene_number": 2, "duration": 10.0}]},
        service=service,
    )
    write_shared_fact(
        workflow_id,
        "scene_outputs.video",
        {"1": {"scene_number": 1, "duration_sec": 10.0}},
        service=service,
    )

    result = build_quality_checker_context(workflow_id, service=service)
    media = result["context"]["media_completeness"]

    assert media["status"] == "incomplete"
    assert media["expected_scene_numbers"] == [1, 2]
    assert media["video_output_scene_numbers"] == [1]
    assert media["missing_scene_numbers"] == [2]
    assert "scene_video_outputs_incomplete" in result["diagnostics"]["fallback_reason"]


def test_build_quality_checker_context_projects_role_continuity_observation(monkeypatch):
    service = _build_service()
    workflow_id = "wf-quality-role-observation"

    monkeypatch.setattr(settings, "FINAL_OUTPUT_ROOT", "/tmp/final_outputs")
    monkeypatch.setattr(
        "app.agents.adapters.memory_views.probe_local_video_metadata_sync",
        lambda _path: {"duration": 10.0, "format": "mp4"},
    )

    write_shared_fact(
        workflow_id,
        "project.final_video",
        {"url": "/files/outputs/videos/final.mp4"},
        service=service,
    )
    write_shared_fact(
        workflow_id,
        "quality.role_continuity_observation",
        {
            "status": "verified",
            "score": 91,
            "source": "manual_contact_sheet_review",
            "checked_scene_numbers": [1],
        },
        service=service,
    )

    result = build_quality_checker_context(workflow_id, service=service)
    observation = result["context"]["role_continuity_observation"]

    assert observation["status"] == "passed"
    assert observation["score"] == 91
    assert observation["source"] == "manual_contact_sheet_review"
    assert result["diagnostics"]["role_continuity_observation_status"] == "passed"


def test_real_sample_scene_type_is_absent_across_quality_checker_inputs():
    service = _build_service()
    workflow_id = "wf-quality-intro-outro-real-sample"
    published, composer = _load_intro_outro_real_sample()

    write_shared_fact(
        workflow_id,
        "project.concept_plan",
        published.get("concept_plan", {}),
        service=service,
    )
    write_shared_fact(
        workflow_id,
        "scene_overview",
        published.get("scene_overview", {}),
        service=service,
    )
    write_shared_fact(
        workflow_id,
        "scene_outputs.video",
        {
            str(scene["scene_number"]): {
                "scene_number": scene["scene_number"],
                "duration_sec": scene.get("duration", 0.0),
            }
            for scene in composer.get("scenes", [])
            if isinstance(scene, dict) and scene.get("scene_number") is not None
        },
        service=service,
    )

    result = build_quality_checker_context(workflow_id, service=service)
    context = result["context"]

    assert [scene.get("scene_type") for scene in context["concept_plan"]["scenes"]] == [
        None,
        None,
        None,
        None,
        None,
    ]
    assert [scene.get("scene_type") for scene in context["scene_overview"]["scenes"]] == [
        None,
        None,
        None,
        None,
        None,
    ]
    assert context["composition_timeline"] == [
        {"scene_number": 1, "start": 0.0, "end": 10.0, "duration": 10.0},
        {"scene_number": 2, "start": 10.0, "end": 20.0, "duration": 10.0},
        {"scene_number": 3, "start": 20.0, "end": 30.0, "duration": 10.0},
        {"scene_number": 4, "start": 30.0, "end": 40.0, "duration": 10.0},
        {"scene_number": 5, "start": 40.0, "end": 45.0, "duration": 5.0},
    ]
    assert all("scene_type" not in entry for entry in context["composition_timeline"])
    assert result["diagnostics"]["timeline_source"] == "scene_overview"


def test_context_assembler_projects_quality_checker_static_context(monkeypatch):
    service = _build_service()
    workflow_id = "wf-quality-assembler"
    assembler = ContextContractAssembler(memory_services=SimpleNamespace(short_term=service))

    monkeypatch.setattr(settings, "FINAL_OUTPUT_ROOT", "/tmp/final_outputs")
    monkeypatch.setattr(
        "app.agents.adapters.memory_views.probe_local_video_metadata_sync",
        lambda _path: {"duration": 12.5, "format": "mp4"},
    )

    write_shared_fact(
        workflow_id,
        "project.final_video",
        {"url": "/files/outputs/videos/final.mp4"},
        service=service,
    )
    write_shared_fact(
        workflow_id,
        "scene_overview",
        {"scenes": [{"scene_number": 1, "duration": 12.5}]},
        service=service,
    )

    boundary = assembler.assemble_agent_context(
        agent_type=AgentType.QUALITY_CHECKER,
        workflow_state_id=workflow_id,
        workflow_data={},
    )

    assert boundary["static_context"]["final_video"]["path"] == "/tmp/final_outputs/videos/final.mp4"
    assert boundary["static_context"]["video_metadata"]["duration"] == 12.5
    assert boundary["_assembler_diagnostics"]["quality_checker_context"]["status"] == "resolved_with_fallbacks"


def test_content_quality_treats_unlabeled_scene_types_as_unverified_not_missing():
    agent = object.__new__(QualityCheckerAgent)
    agent.logger = logging.getLogger("test.quality_checker.scene_types")

    async def _fake_ai_content_analysis(*_args, **_kwargs):
        return {"overall_assessment": "stub"}

    agent._ai_content_analysis = _fake_ai_content_analysis

    concept_plan = {
        "scenes": [
            {"scene_number": 1},
            {"scene_number": 2},
            {"scene_number": 3},
        ]
    }
    unlabeled_timeline = [
        {"scene_number": 1, "start": 0.0, "end": 5.0, "duration": 5.0},
        {"scene_number": 2, "start": 5.0, "end": 10.0, "duration": 5.0},
        {"scene_number": 3, "start": 10.0, "end": 15.0, "duration": 5.0},
    ]
    unlabeled_result = asyncio.run(
        agent._analyze_content_quality(
            concept_plan,
            unlabeled_timeline,
            "",
            {},
            {"duration": 15.0, "format": "mp4"},
        )
    )

    assert "Missing introduction scene" not in unlabeled_result["issues"]
    assert "Missing conclusion scene" not in unlabeled_result["issues"]
    assert unlabeled_result["scene_breakdown"]["scene_type_distribution"] == {}
    assert unlabeled_result["scene_breakdown"]["scene_type_label_status"] == "missing"
    assert unlabeled_result["scene_breakdown"]["unlabeled_scene_count"] == 3
    assert unlabeled_result["scene_type_diagnostics"]["intro_outro_check_applied"] is False
    assert unlabeled_result["scene_type_diagnostics"]["label_status"] == "missing"

    partial_timeline = [
        {"scene_number": 1, "start": 0.0, "end": 5.0, "duration": 5.0},
        {"scene_number": 2, "start": 5.0, "end": 10.0, "duration": 5.0, "scene_type": "main_content"},
        {"scene_number": 3, "start": 10.0, "end": 15.0, "duration": 5.0},
    ]
    partial_result = asyncio.run(
        agent._analyze_content_quality(
            concept_plan,
            partial_timeline,
            "",
            {},
            {"duration": 15.0, "format": "mp4"},
        )
    )

    assert "Missing introduction scene" not in partial_result["issues"]
    assert "Missing conclusion scene" not in partial_result["issues"]
    assert partial_result["scene_breakdown"]["scene_type_distribution"] == {
        "main_content": 1
    }
    assert partial_result["scene_breakdown"]["scene_type_label_status"] == "partial"
    assert partial_result["scene_type_diagnostics"]["intro_outro_check_applied"] is False
    assert partial_result["scene_type_diagnostics"]["unlabeled_scene_count"] == 2

    labeled_timeline = [
        {"scene_number": 1, "start": 0.0, "end": 5.0, "duration": 5.0, "scene_type": "main_content"},
        {"scene_number": 2, "start": 5.0, "end": 10.0, "duration": 5.0, "scene_type": "main_content"},
        {"scene_number": 3, "start": 10.0, "end": 15.0, "duration": 5.0, "scene_type": "main_content"},
    ]
    labeled_result = asyncio.run(
        agent._analyze_content_quality(
            concept_plan,
            labeled_timeline,
            "",
            {},
            {"duration": 15.0, "format": "mp4"},
        )
    )

    assert "Missing introduction scene" in labeled_result["issues"]
    assert "Missing conclusion scene" in labeled_result["issues"]
    assert labeled_result["scene_breakdown"]["scene_type_distribution"] == {
        "main_content": 3,
    }
    assert labeled_result["scene_breakdown"]["scene_type_label_status"] == "complete"
    assert labeled_result["scene_type_diagnostics"]["intro_outro_check_applied"] is True


def test_content_quality_includes_role_continuity_contract_diagnostics():
    agent = object.__new__(QualityCheckerAgent)
    agent.logger = logging.getLogger("test.quality_checker.role_continuity")

    async def _fake_ai_content_analysis(*_args, **_kwargs):
        return {"overall_assessment": "stub"}

    agent._ai_content_analysis = _fake_ai_content_analysis

    result = asyncio.run(
        agent._analyze_content_quality(
            {"scenes": [{"scene_number": 1}, {"scene_number": 2}]},
            [
                {"scene_number": 1, "start": 0.0, "end": 5.0, "duration": 5.0},
                {"scene_number": 2, "start": 5.0, "end": 10.0, "duration": 5.0},
            ],
            "",
            {},
            {"duration": 10.0, "format": "mp4"},
            character_identity_bible={
                "source": "concept_plan.content_elements.characters",
                "characters": [
                    {"canonical_id": "mother", "display_name": "妈妈"},
                    {"canonical_id": "child", "display_name": "孩子"},
                ],
            },
            scene_character_locks=[
                {"scene_number": 1, "cast": [{"canonical_id": "mother"}]},
                {"scene_number": 2, "cast": [{"canonical_id": "mother"}, {"canonical_id": "child"}]},
            ],
            quality_expectations={
                "role_continuity": {
                    "required": True,
                    "score_cap_when_failed": 79,
                    "score_cap_when_contract_missing": 69,
                    "score_cap_when_unverified": 89,
                }
            },
            character_identity_diagnostics=[],
            character_identity_contract_carrier={
                "source": "scene_info_ref",
                "agent_type": AgentType.VIDEO_GENERATOR.value,
                "scene_info_ref": "storage/temp/context/video_generator_wf-quality-role-continuity.json",
                "same_carrier_verified": True,
            },
        )
    )

    assert result["contract_readiness"] == {
        "status": "ready",
        "score": 100,
        "same_carrier_verified": True,
    }
    assert result["role_continuity_score"] is None
    assert result["analysis"]["role_continuity"] is False
    assert result["role_continuity_diagnostics"]["status"] == "not_evaluated"
    assert result["role_continuity_diagnostics"]["visual_evidence_verified"] is False
    assert result["role_continuity_diagnostics"]["display_summary"]["character_count"] == 2
    assert result["role_continuity_diagnostics"]["display_summary"]["locked_scene_numbers"] == [1, 2]
    assert result["fallback_reason"] == "role_continuity_visual_evidence_missing"


def test_content_quality_uses_passed_role_continuity_visual_observation():
    agent = object.__new__(QualityCheckerAgent)
    agent.logger = logging.getLogger("test.quality_checker.role_observation_passed")

    async def _fake_ai_content_analysis(*_args, **_kwargs):
        return {"overall_assessment": "stub"}

    agent._ai_content_analysis = _fake_ai_content_analysis

    result = asyncio.run(
        agent._analyze_content_quality(
            {"scenes": [{"scene_number": 1}]},
            [{"scene_number": 1, "start": 0.0, "end": 5.0, "duration": 5.0}],
            "",
            {},
            {"duration": 5.0, "format": "mp4"},
            character_identity_bible={
                "source": "concept_plan.content_elements.characters",
                "characters": [{"canonical_id": "mother", "display_name": "妈妈"}],
            },
            scene_character_locks=[{"scene_number": 1, "cast": [{"canonical_id": "mother"}]}],
            quality_expectations={"role_continuity": {"required": True}},
            role_continuity_observation={
                "status": "passed",
                "visual_evidence_verified": True,
                "score": 92,
                "source": "manual_contact_sheet_review",
            },
            character_identity_contract_carrier={
                "source": "scene_info_ref",
                "same_carrier_verified": True,
            },
        )
    )

    assert result["analysis"]["role_continuity"] is True
    assert result["role_continuity_score"] == 92
    assert result["visual_evidence_verified"] is True
    assert result["role_continuity_diagnostics"]["status"] == "passed"
    assert result["role_continuity_diagnostics"]["evaluation_scope"] == "visual_observation"


def test_content_quality_uses_failed_role_continuity_visual_observation():
    agent = object.__new__(QualityCheckerAgent)
    agent.logger = logging.getLogger("test.quality_checker.role_observation_failed")

    async def _fake_ai_content_analysis(*_args, **_kwargs):
        return {"overall_assessment": "stub"}

    agent._ai_content_analysis = _fake_ai_content_analysis

    result = asyncio.run(
        agent._analyze_content_quality(
            {"scenes": [{"scene_number": 1}, {"scene_number": 2}]},
            [
                {"scene_number": 1, "start": 0.0, "end": 5.0, "duration": 5.0},
                {"scene_number": 2, "start": 5.0, "end": 10.0, "duration": 5.0},
            ],
            "",
            {},
            {"duration": 10.0, "format": "mp4"},
            character_identity_bible={
                "source": "concept_plan.content_elements.characters",
                "characters": [{"canonical_id": "mother", "display_name": "妈妈"}],
            },
            scene_character_locks=[
                {"scene_number": 1, "cast": [{"canonical_id": "mother"}]},
                {"scene_number": 2, "cast": [{"canonical_id": "mother"}]},
            ],
            quality_expectations={
                "role_continuity": {
                    "required": True,
                    "score_cap_when_failed": 79,
                }
            },
            role_continuity_observation={
                "status": "failed",
                "visual_evidence_verified": True,
                "score": 48,
                "identity_drift_findings": [
                    {"scene_number": 2, "message": "mother identity drift"}
                ],
            },
            character_identity_contract_carrier={
                "source": "scene_info_ref",
                "same_carrier_verified": True,
            },
        )
    )

    assert result["analysis"]["role_continuity"] is False
    assert result["role_continuity_score"] == 48
    assert result["visual_evidence_verified"] is True
    assert result["identity_drift_findings"] == [
        {"scene_number": 2, "message": "mother identity drift"}
    ]
    assert result["role_continuity_diagnostics"]["status"] == "failed"


def test_quality_assessment_caps_excellent_when_role_continuity_contract_missing():
    agent = object.__new__(QualityCheckerAgent)
    agent.logger = logging.getLogger("test.quality_checker.role_gate_missing")

    assessment = asyncio.run(
        agent._generate_quality_assessment(
            technical_quality={"score": 100, "issues": [], "recommendations": []},
            content_quality={
                "score": 100,
                "issues": [],
                "recommendations": [],
                "contract_readiness": {"status": "missing_contract", "score": 0},
                "role_continuity_score": None,
                "identity_drift_findings": [],
                "role_continuity_diagnostics": {
                    "status": "needs_human_review",
                    "fallback_reason": "character_identity_contract_missing",
                    "score_cap_when_failed": 79,
                    "score_cap_when_contract_missing": 69,
                },
            },
            compliance_check={"score": 100, "issues": []},
        )
    )

    assert assessment["raw_overall_score"] == 100
    assert assessment["overall_score"] == 69
    assert assessment["quality_grade"] != "Excellent"
    assert assessment["approval_status"] == "needs_revision"
    assert assessment["requires_human_review"] is True
    assert assessment["detailed_scores"]["contract_readiness"] == 0
    assert "role_continuity" not in assessment["detailed_scores"]
    assert assessment["quality_score_cap_applied"] == 69
    assert assessment["fallback_reason"] == "character_identity_contract_missing"


def test_quality_assessment_caps_excellent_when_role_continuity_visual_evidence_missing():
    agent = object.__new__(QualityCheckerAgent)
    agent.logger = logging.getLogger("test.quality_checker.role_gate_unverified")

    assessment = asyncio.run(
        agent._generate_quality_assessment(
            technical_quality={"score": 100, "issues": [], "recommendations": []},
            content_quality={
                "score": 100,
                "issues": [],
                "recommendations": [],
                "contract_readiness": {"status": "ready", "score": 100},
                "role_continuity_score": None,
                "identity_drift_findings": [],
                "visual_evidence_verified": False,
                "role_continuity_diagnostics": {
                    "status": "not_evaluated",
                    "fallback_reason": "role_continuity_visual_evidence_missing",
                    "score_cap_when_failed": 79,
                    "score_cap_when_contract_missing": 69,
                    "score_cap_when_unverified": 89,
                },
            },
            compliance_check={"score": 100, "issues": []},
        )
    )

    assert assessment["raw_overall_score"] == 100
    assert assessment["overall_score"] == 89
    assert assessment["quality_grade"] != "Excellent"
    assert assessment["approval_status"] == "conditional"
    assert assessment["requires_human_review"] is True
    assert assessment["detailed_scores"]["contract_readiness"] == 100
    assert "role_continuity" not in assessment["detailed_scores"]
    assert assessment["visual_evidence_verified"] is False
    assert assessment["fallback_reason"] == "role_continuity_visual_evidence_missing"


def test_quality_assessment_caps_excellent_when_role_continuity_failed():
    agent = object.__new__(QualityCheckerAgent)
    agent.logger = logging.getLogger("test.quality_checker.role_gate_failed")

    findings = [{"scene_number": 3, "message": "child identity drifts outside allowed variant"}]
    assessment = asyncio.run(
        agent._generate_quality_assessment(
            technical_quality={"score": 100, "issues": [], "recommendations": []},
            content_quality={
                "score": 100,
                "issues": [],
                "recommendations": [],
                "role_continuity_score": 40,
                "identity_drift_findings": findings,
                "role_continuity_diagnostics": {
                    "status": "failed",
                    "score_cap_when_failed": 79,
                    "score_cap_when_contract_missing": 69,
                },
            },
            compliance_check={"score": 100, "issues": []},
        )
    )

    assert assessment["raw_overall_score"] == 100
    assert assessment["overall_score"] == 79
    assert assessment["quality_grade"] != "Excellent"
    assert assessment["requires_human_review"] is True
    assert assessment["quality_score_cap_applied"] == 79
    assert assessment["identity_drift_findings"] == findings


def test_quality_assessment_caps_when_media_completeness_incomplete():
    agent = object.__new__(QualityCheckerAgent)
    agent.logger = logging.getLogger("test.quality_checker.media_gate")

    assessment = asyncio.run(
        agent._generate_quality_assessment(
            technical_quality={"score": 100, "issues": [], "recommendations": []},
            content_quality={
                "score": 100,
                "issues": [],
                "recommendations": [],
                "media_completeness": {
                    "status": "incomplete",
                    "expected_scene_numbers": [1, 2],
                    "video_output_scene_numbers": [1],
                    "missing_scene_numbers": [2],
                },
            },
            compliance_check={"score": 100, "issues": []},
        )
    )

    assert assessment["raw_overall_score"] == 100
    assert assessment["overall_score"] == 79
    assert assessment["quality_grade"] != "Excellent"
    assert assessment["approval_status"] == "needs_revision"
    assert assessment["requires_human_review"] is True
    assert assessment["quality_score_cap_applied"] == 79
    assert assessment["media_completeness"]["missing_scene_numbers"] == [2]
    assert assessment["media_completeness_fallback_reason"] == "scene_video_outputs_incomplete"


def test_real_sample_does_not_raise_intro_outro_issues_when_scene_types_are_absent():
    service = _build_service()
    workflow_id = "wf-quality-intro-outro-real-sample-analysis"
    published, composer = _load_intro_outro_real_sample()

    write_shared_fact(
        workflow_id,
        "project.concept_plan",
        published.get("concept_plan", {}),
        service=service,
    )
    write_shared_fact(
        workflow_id,
        "scene_overview",
        published.get("scene_overview", {}),
        service=service,
    )
    write_shared_fact(
        workflow_id,
        "scene_outputs.video",
        {
            str(scene["scene_number"]): {
                "scene_number": scene["scene_number"],
                "duration_sec": scene.get("duration", 0.0),
            }
            for scene in composer.get("scenes", [])
            if isinstance(scene, dict) and scene.get("scene_number") is not None
        },
        service=service,
    )

    result = build_quality_checker_context(workflow_id, service=service)
    context = result["context"]

    agent = object.__new__(QualityCheckerAgent)
    agent.logger = logging.getLogger("test.quality_checker.real_sample")

    async def _fake_ai_content_analysis(*_args, **_kwargs):
        return {"overall_assessment": "stub"}

    agent._ai_content_analysis = _fake_ai_content_analysis

    content_result = asyncio.run(
        agent._analyze_content_quality(
            context["concept_plan"],
            context["composition_timeline"],
            "",
            context["original_requirements"],
            context["video_metadata"],
        )
    )

    assert "Missing introduction scene" not in content_result["issues"]
    assert "Missing conclusion scene" not in content_result["issues"]
    assert content_result["scene_breakdown"]["scene_type_label_status"] == "missing"
    assert content_result["scene_breakdown"]["unlabeled_scene_count"] == 5
    assert content_result["scene_type_diagnostics"]["intro_outro_check_applied"] is False


@pytest.mark.asyncio
async def test_ai_content_analysis_renders_original_requirements_and_video_metadata(monkeypatch):
    agent = object.__new__(QualityCheckerAgent)
    agent.logger = logging.getLogger("test.quality_checker.prompt")

    captured = {}

    def _render_prompt(name, **kwargs):
        captured["template"] = name
        captured.update(kwargs)
        return "quality prompt"

    async def _llm_function_call(**_kwargs):
        return {
            "content": json.dumps(
                {
                    "overall_assessment": "ok",
                    "quality_score": 8.0,
                },
                ensure_ascii=False,
            )
        }

    class _ModelConfig:
        temperature = 0.3
        max_tokens = 1000

    class _AIConfig:
        def get_model_for_agent(self, _agent_name):
            return "test-model"

        def get_model_config(self, _model_name):
            return _ModelConfig()

    class _PromptManager:
        def render_template(self, *_args, **_kwargs):
            return ""

    agent.render_prompt = _render_prompt
    agent.llm_function_call = _llm_function_call

    monkeypatch.setattr("app.core.ai_config.get_ai_config", lambda: _AIConfig())
    monkeypatch.setattr("app.core.prompt_manager.get_prompt_manager", lambda: _PromptManager())

    result = await agent._ai_content_analysis(
        concept_plan={"overview": "effective plan"},
        composition_timeline=[{"scene_number": 1, "duration": 10.0}],
        original_requirements={"overview": "original brief"},
        video_metadata={"duration": 12.5, "format": "mp4"},
    )

    assert result["overall_assessment"] == "ok"
    assert captured["template"] == "video_quality_analysis"
    assert json.loads(captured["concept_plan"])["overview"] == "effective plan"
    assert json.loads(captured["original_requirements"])["overview"] == "original brief"
    assert json.loads(captured["video_metadata"])["duration"] == 12.5
