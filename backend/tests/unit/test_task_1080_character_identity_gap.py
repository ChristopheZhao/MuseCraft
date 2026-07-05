import asyncio
import json
import logging
from pathlib import Path
from types import SimpleNamespace

from app.agents.adapters.memory_views import build_quality_checker_context
from app.agents.memory.short_term.service import WorkingMemoryService
from app.agents.memory.storage.in_memory import InMemoryShortTermStore
from app.agents.quality_checker import QualityCheckerAgent
from app.agents.tools.base_tool import ToolInput
from app.agents.tools.consistency_tool import ConsistencyTool
from app.agents.tools.image_prompt_composer_tool import ImagePromptComposerTool
from app.agents.tools.video_prompt_composer_tool import VideoPromptComposerTool
from app.agents.utils.memory_helpers import write_shared_fact
from app.core.config import settings
from app.models import AgentType
from app.services.character_identity_contract import normalize_character_identity_contract
from app.services.scene_info_reference_service import persist_scene_info_ref
from app.services.workflow_completion_adapter import WorkflowCompletionAdapter


FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "task_1080_character_identity_gap.json"
)


class _NoopMemoryProvider:
    async def retrieve_scene_references(self, workflow_state_id: str, scene_number: int, agent_name: str):
        return {}

    async def retrieve_motion_guidance(self, workflow_state_id: str, scene_number: int, agent_name: str):
        return {}

    async def store_scene_final_frame(self, scene_number: int, frame_url: str) -> None:
        return None

    async def retrieve_previous_frame_url(self, scene_number: int):
        return None

    async def get_scene_continuity_info(self, workflow_state_id: str, scene_number: int):
        return {}


def _load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _build_service() -> WorkingMemoryService:
    return WorkingMemoryService(store_factory=lambda: InMemoryShortTermStore())


def _scene_info_payload(fixture: dict, *, mode: str = "image") -> dict:
    image_context = fixture["image_context"]
    if mode == "image":
        return image_context
    video_context = fixture["video_context"]
    scenes = []
    for scene in image_context["scenes_to_generate"]:
        merged = dict(scene)
        image_url = video_context["video_scene_image_urls"].get(str(scene["scene_number"]))
        if image_url:
            merged["image_url"] = image_url
        scenes.append(merged)
    return {
        "task_type": video_context["task_type"],
        "workflow_state_id": video_context["workflow_state_id"],
        "total_scenes": video_context["total_scenes"],
        "concept_plan": image_context["concept_plan"],
        "scenes_to_generate": scenes,
    }


def test_task_1080_fixture_preserves_upstream_character_facts_and_review_evidence():
    fixture = _load_fixture()

    assert fixture["task_id"] == 1080
    assert fixture["workflow_state_id"] == "e47efe5f-6e5f-4735-8f32-ff175f349e08"
    assert fixture["review_summary"]["system_quality_score"] == 92
    assert fixture["media_probe"]["duration_seconds"] == 60.32746
    assert fixture["review_summary"]["contact_sheet_path"].endswith("contact_sheet.jpg")

    for mode in ("image", "video"):
        payload = _scene_info_payload(fixture, mode=mode)
        concept_plan = payload["concept_plan"]
        characters = concept_plan["content_elements"]["characters"]
        by_id = {item["canonical_id"]: item for item in characters}

        assert set(by_id) == {"mother", "child"}
        assert concept_plan.get("roles") in (None, [])
        assert "character_identity_bible" not in payload
        assert "scene_character_locks" not in payload

        assert "暖棕色长发" in by_id["mother"]["visual_identity"]
        assert "围裙" in by_id["mother"]["signature_outfit_or_props"]
        assert "随年龄变化：幼年→少年→青年" in by_id["child"]["visual_identity"]
        assert {"书包", "行李箱", "手机"}.issubset(
            set(by_id["child"]["signature_outfit_or_props"])
        )

        scenes = {scene["scene_number"]: scene for scene in payload["scenes_to_generate"]}
        assert any("幼年" in desc for desc in scenes[1]["character_descriptions"])
        assert any("少年" in desc for desc in scenes[2]["character_descriptions"])
        assert any("白发" in desc for desc in scenes[6]["character_descriptions"])
        assert any("青年" in desc for desc in scenes[6]["character_descriptions"])


def test_task_1080_current_consistency_tool_weakens_and_diagnoses_raw_character_facts(tmp_path):
    fixture = _load_fixture()
    payload = _scene_info_payload(fixture, mode="image")
    scene_path = tmp_path / "task_1080_scene_info.json"
    scene_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    tool = ConsistencyTool(memory_provider=_NoopMemoryProvider())
    result = asyncio.run(
        tool.execute(
            ToolInput(
                action="get_prompt_assets",
                parameters={"scene_number": 6, "scene_info_ref": str(scene_path)},
                context={"workflow_state_id": fixture["workflow_state_id"]},
            )
        )
    )

    assert result.success is True
    concept_characters = payload["concept_plan"]["content_elements"]["characters"]
    assert {item["canonical_id"] for item in concept_characters} == {"mother", "child"}

    character_assets = result.result["assets"]["characters"]
    assert character_assets["characters"] == []
    assert character_assets["global_lock"]["stable_traits"] == []
    assert character_assets["scene_cast"]["present"] == ["妈妈", "孩子"]
    assert any("白发" in desc for desc in character_assets["scene_cast"]["descriptions"])

    diagnostics = result.result["diagnostics"]
    assert diagnostics["source"] == "scene_info_ref"
    assert diagnostics["structured_identity_missing"] is True
    assert diagnostics["character_identity_contract_source"] == "legacy_text"


def test_task_1080_normalized_identity_contract_reaches_consistency_assets(tmp_path):
    fixture = _load_fixture()
    payload = normalize_character_identity_contract(_scene_info_payload(fixture, mode="image"))
    scene_path = tmp_path / "task_1080_normalized_scene_info.json"
    scene_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    tool = ConsistencyTool(memory_provider=_NoopMemoryProvider())
    result = asyncio.run(
        tool.execute(
            ToolInput(
                action="get_prompt_assets",
                parameters={"scene_number": 6, "scene_info_ref": str(scene_path)},
                context={"workflow_state_id": fixture["workflow_state_id"]},
            )
        )
    )

    assert result.success is True
    diagnostics = result.result["diagnostics"]
    character_assets = result.result["assets"]["characters"]

    assert diagnostics["character_identity_contract_source"] == "character_identity_contract"
    assert diagnostics["structured_identity_missing"] is False
    assert character_assets["source"] == "character_identity_contract"
    assert {item["canonical_id"] for item in character_assets["characters"]} == {
        "mother",
        "child",
    }
    assert [item["canonical_id"] for item in character_assets["scene_locks"]] == [
        "mother",
        "child",
    ]
    assert {"暖棕色长发", "围裙", "行李箱"}.issubset(
        set(character_assets["global_lock"]["stable_traits"])
    )
    assert character_assets["scene_cast"]["present"] == ["妈妈", "孩子"]
    assert any(
        item["canonical_id"] == "child"
        and any(variant["age_stage"] == "青年" for variant in item["variants"])
        for item in character_assets["allowed_variants"]
    )


def test_task_1080_prompt_composers_preserve_structured_identity_locks(tmp_path):
    fixture = _load_fixture()
    payload = normalize_character_identity_contract(_scene_info_payload(fixture, mode="video"))
    scene_path = tmp_path / "task_1080_prompt_lock_scene_info.json"
    scene_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    tool = ConsistencyTool(memory_provider=_NoopMemoryProvider())
    result = asyncio.run(
        tool.execute(
            ToolInput(
                action="get_prompt_assets",
                parameters={"scene_number": 6, "scene_info_ref": str(scene_path)},
                context={"workflow_state_id": fixture["workflow_state_id"]},
            )
        )
    )
    assets = result.result["assets"]

    image_composer = ImagePromptComposerTool(metadata=ImagePromptComposerTool.get_metadata())
    block, categories, locked_segments = image_composer._build_consistency_block(assets)
    assert "角色锁定" in block
    assert "妈妈：锚点：暖棕色长发、围裙、柔和微笑" in block
    assert "孩子：阶段：青年" in block
    assert "canonical_id" not in block
    assert "别名：" not in block
    assert any("孩子：阶段：青年" in item for item in locked_segments)
    assert categories == ["global_style_lock", "character_lock", "opening_anchor"]

    video_composer = VideoPromptComposerTool(metadata=VideoPromptComposerTool.get_metadata())
    sections, video_categories = video_composer._build_consistency_sections(assets)
    rendered = video_composer._render_prompt_outline(
        6,
        video_composer._merge_prompt_outline(
            {
                "main_key": "归家拥抱",
                "event_arc": [],
                "motion_guidance": [],
                "style_continuity": [],
                "technical_note": [],
            },
            sections,
        ),
    )
    assert "角色锁定" in rendered
    assert "孩子：阶段：青年" in rendered
    assert "canonical_id" not in rendered
    assert video_categories == ["global_style_lock", "character_lock", "opening_anchor"]


def test_task_1080_prompt_asset_boundary_only_formats_legacy_scene_cast(tmp_path):
    fixture = _load_fixture()
    payload = _scene_info_payload(fixture, mode="video")
    scene_path = tmp_path / "task_1080_video_scene_info.json"
    scene_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    tool = ConsistencyTool(memory_provider=_NoopMemoryProvider())
    result = asyncio.run(
        tool.execute(
            ToolInput(
                action="get_prompt_assets",
                parameters={"scene_number": 1, "scene_info_ref": str(scene_path)},
                context={"workflow_state_id": fixture["workflow_state_id"]},
            )
        )
    )
    assets = result.result["assets"]

    composer = VideoPromptComposerTool(metadata=VideoPromptComposerTool.get_metadata())
    sections, categories = composer._build_consistency_sections(assets)
    prompt_outline = composer._merge_prompt_outline(
        {
            "main_key": "母亲节晨光厨房记忆",
            "event_arc": ["开场状态：厨房充满晨光"],
            "motion_guidance": [],
            "style_continuity": [],
            "technical_note": ["目标时长：10s"],
        },
        sections,
    )
    prompt_text = composer._render_prompt_outline(1, prompt_outline)

    assert "角色锁定" in prompt_text
    assert "出现角色：妈妈、孩子" in prompt_text
    assert "稳定特征：" not in prompt_text
    assert "canonical_id" not in prompt_text
    assert "allowed_variants" not in prompt_text
    assert categories == ["global_style_lock", "character_lock", "opening_anchor"]


def test_task_1080_offline_e2e_projects_role_diagnostics_to_runtime_read_model(
    tmp_path,
    monkeypatch,
):
    fixture = _load_fixture()
    workflow_id = fixture["workflow_state_id"]
    service = _build_service()
    monkeypatch.setattr(settings, "TEMP_PATH", str(tmp_path))
    monkeypatch.setattr(
        "app.agents.adapters.memory_views.probe_local_video_metadata_sync",
        lambda _path: {
            "duration": fixture["media_probe"]["duration_seconds"],
            "format": "mp4",
            "file_size": fixture["media_probe"]["size_bytes"],
            "file_size_mb": round(fixture["media_probe"]["size_bytes"] / 1024 / 1024, 2),
            "resolution": "960x960",
        },
    )

    source_context_path = Path(__file__).resolve().parents[3] / fixture["source_contexts"]["video"]
    source_scene_info = json.loads(source_context_path.read_text(encoding="utf-8"))
    scene_info_payload = normalize_character_identity_contract(source_scene_info)
    scene_info_ref = persist_scene_info_ref(
        workflow_id=workflow_id,
        agent_type=AgentType.VIDEO_GENERATOR,
        payload=scene_info_payload,
    )
    write_shared_fact(
        workflow_id,
        "project.concept_plan",
        scene_info_payload["concept_plan"],
        service=service,
    )
    write_shared_fact(
        workflow_id,
        "scene_overview",
        scene_info_payload.get("scene_overview")
        or {"scenes": scene_info_payload["scenes_to_generate"]},
        service=service,
    )
    write_shared_fact(
        workflow_id,
        "project.final_video",
        {
            "path": fixture["media_probe"]["final_video_path"],
            "url": "/files/outputs/videos/mothers_day_final.mp4",
            "metadata": {
                "duration": fixture["media_probe"]["duration_seconds"],
                "format": "mp4",
                "file_size_mb": round(fixture["media_probe"]["size_bytes"] / 1024 / 1024, 2),
                "resolution": "960x960",
            },
        },
        service=service,
    )

    quality_context = build_quality_checker_context(workflow_id, service=service)["context"]
    carrier = quality_context["character_identity_contract_carrier"]
    assert carrier["source"] == "scene_info_ref"
    assert carrier["agent_type"] == AgentType.VIDEO_GENERATOR.value
    assert carrier["scene_info_ref"] == scene_info_ref
    assert carrier["same_carrier_verified"] is True
    assert {item["canonical_id"] for item in quality_context["character_identity_bible"]["characters"]} == {
        "mother",
        "child",
    }
    assert len(quality_context["scene_character_locks"]) == 6

    consistency_tool = ConsistencyTool(memory_provider=_NoopMemoryProvider())
    consistency_result = asyncio.run(
        consistency_tool.execute(
            ToolInput(
                action="get_prompt_assets",
                parameters={"scene_number": 6, "scene_info_ref": scene_info_ref},
                context={"workflow_state_id": workflow_id},
            )
        )
    )
    assets = consistency_result.result["assets"]
    assert consistency_result.result["diagnostics"]["structured_identity_missing"] is False
    assert assets["characters"]["source"] == "character_identity_contract"

    image_composer = ImagePromptComposerTool(metadata=ImagePromptComposerTool.get_metadata())
    consistency_block, image_categories, locked_segments = image_composer._build_consistency_block(
        assets
    )
    assert "妈妈：锚点：暖棕色长发、围裙、柔和微笑" in consistency_block
    assert "孩子：阶段：青年" in consistency_block
    assert any("孩子：阶段：青年" in item for item in locked_segments)
    assert image_categories == ["global_style_lock", "character_lock", "opening_anchor"]

    agent = object.__new__(QualityCheckerAgent)
    agent.logger = logging.getLogger("test.task_1080.e2e")

    async def _fake_ai_content_analysis(*_args, **_kwargs):
        return {"overall_assessment": "offline_e2e_stub"}

    agent._ai_content_analysis = _fake_ai_content_analysis
    content_quality = asyncio.run(
        agent._analyze_content_quality(
            quality_context["concept_plan"],
            quality_context["composition_timeline"],
            quality_context["final_video"]["path"],
            quality_context["original_requirements"],
            quality_context["video_metadata"],
            character_identity_bible=quality_context["character_identity_bible"],
            scene_character_locks=quality_context["scene_character_locks"],
            quality_expectations=quality_context["quality_expectations"],
            character_identity_diagnostics=quality_context["character_identity_diagnostics"],
            character_identity_contract_carrier=quality_context[
                "character_identity_contract_carrier"
            ],
        )
    )
    assessment = asyncio.run(
        agent._generate_quality_assessment(
            technical_quality={"score": 100, "issues": [], "recommendations": []},
            content_quality=content_quality,
            compliance_check={"score": 100, "issues": []},
        )
    )

    assert content_quality["contract_readiness"]["status"] == "ready"
    assert content_quality["role_continuity_score"] is None
    assert content_quality["visual_evidence_verified"] is False
    assert content_quality["fallback_reason"] == "role_continuity_visual_evidence_missing"
    assert content_quality["role_continuity_diagnostics"]["display_summary"]["character_count"] == 2
    assert assessment["overall_score"] == 89
    assert assessment["quality_grade"] != "Excellent"
    assert assessment["quality_score_cap_applied"] == 89
    assert assessment["requires_human_review"] is True

    quality_result = {
        "quality_score": assessment["overall_score"],
        "quality_grade": assessment["quality_grade"],
        "requires_human_review": assessment["requires_human_review"],
        "content_quality": content_quality,
        "quality_assessment": assessment,
        "approval_status": assessment["approval_status"],
    }
    runtime_summary = WorkflowCompletionAdapter(
        memory_services=SimpleNamespace(short_term=object())
    ).build_runtime_summary_output(
        final_video_url="/files/outputs/videos/mothers_day_final.mp4",
        final_video_path=fixture["media_probe"]["final_video_path"],
        results={"quality_checker": quality_result},
        quality_score=assessment["overall_score"],
    )
    role_read_model = runtime_summary["role_continuity_diagnostics"]

    assert runtime_summary["quality_score"] == 89
    assert role_read_model["status"] == "not_evaluated"
    assert role_read_model["review_status"] == "unverified"
    assert role_read_model["score_cap"] == 89
    assert role_read_model["fallback_reason"] == "role_continuity_visual_evidence_missing"
    assert role_read_model["requires_human_review"] is True
    assert role_read_model["display_summary"]["scene_lock_count"] == 6
    assert "contract_carrier" not in role_read_model
    assert "scene_info_ref" not in json.dumps(role_read_model, ensure_ascii=False)


def test_quality_scoring_caps_excellent_when_role_continuity_contract_missing():
    agent = object.__new__(QualityCheckerAgent)
    agent.logger = logging.getLogger("test.task_1080.quality_gap")

    assessment = asyncio.run(
        agent._generate_quality_assessment(
            technical_quality={"score": 100, "issues": [], "recommendations": []},
            content_quality={
                "score": 90,
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
            compliance_check={"score": 90, "issues": []},
        )
    )

    assert assessment["raw_overall_score"] == 93
    assert assessment["overall_score"] == 69
    assert assessment["quality_grade"] != "Excellent"
    assert assessment["requires_human_review"] is True
    assert assessment["detailed_scores"]["contract_readiness"] == 0
    assert "role_continuity" not in assessment["detailed_scores"]
    assert assessment["identity_drift_findings"] == []
    assert assessment["fallback_reason"] == "character_identity_contract_missing"
