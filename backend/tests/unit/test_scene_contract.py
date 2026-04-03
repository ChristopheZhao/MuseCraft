from app.agents.adapters.memory_views import (
    build_image_generation_context,
    build_video_generation_context,
)
from app.agents.memory.short_term.service import WorkingMemoryService
from app.agents.memory.storage.in_memory import InMemoryShortTermStore
from app.services.scene_contract import (
    SCENE_CONTRACT_DOC_REF,
    SCENE_CONTRACT_VERSION,
    annotate_scene_info_payload,
    build_scene_owner_matrix,
)


def _build_service() -> WorkingMemoryService:
    return WorkingMemoryService(store_factory=lambda: InMemoryShortTermStore())


def test_annotate_scene_info_payload_marks_in_place_scene_contract_boundary():
    payload = {
        "task_type": "batch_video_generation",
        "workflow_state_id": "wf-scene-contract",
        "scenes_to_generate": [{"scene_number": 1, "visual_description": "韩立半跪"}],
    }

    annotated = annotate_scene_info_payload(payload, mode="video_generation")

    assert annotated["scenes_to_generate"] == payload["scenes_to_generate"]
    assert "scene_contract_payload" not in annotated
    meta = annotated["scene_contract_meta"]
    assert meta["contract_version"] == SCENE_CONTRACT_VERSION
    assert meta["doc_ref"] == SCENE_CONTRACT_DOC_REF
    assert meta["timing_model"]["projection"] == "relative_phases"
    assert meta["owner_matrix"]["authoritative_carrier_path"] == "scene_info_payload.scenes_to_generate[]"
    assert meta["owner_matrix"]["parallel_carrier_forbidden"] is True


def test_build_scene_owner_matrix_freezes_validation_surfaces_only():
    matrix = build_scene_owner_matrix()

    assert matrix["runtime_owner"] == "control_plane"
    assert "docs/plans/active" in matrix["validation_surfaces"]
    assert "runtime_input_payload" in matrix["forbidden_surfaces"]
    assert "published_deliverables" in matrix["forbidden_surfaces"]


def test_build_image_generation_context_attaches_scene_contract_meta():
    service = _build_service()
    payload = {
        "concept_plan": {
            "overview": "修仙故事",
            "scenes": [{"scene_number": 1, "title": "秘境入口"}],
            "intelligent_style_design": {"style_name": "仙侠动态水墨"},
        },
        "scene_overview": {
            "scenes": [
                {
                    "scene_number": 1,
                    "visual_description": "韩立站在秘境入口前",
                    "narrative_description": "韩立试探性观察入口符文",
                    "duration": 5.0,
                }
            ]
        },
        "scene_scripts": {
            "1": {
                "script_text": "韩立停步观察。",
                "motion_beats": [{"start": 0.0, "end": 5.0, "visual_focus": "入口", "beat_summary": "观察"}],
            }
        },
    }

    result = build_image_generation_context("wf-image-contract", service=service, published_payload=payload)

    meta = result["scene_info_payload"]["scene_contract_meta"]
    assert meta["mode"] == "image_generation"
    assert meta["semantic_unit"] == "local_event"
    scene_payload = result["scene_info_payload"]["scenes_to_generate"][0]
    assert scene_payload["scene_number"] == 1
    assert "generation_diagnostics" not in result["scene_info_payload"]
    assert "generation_diagnostics" not in result["context"]
    assert "image_purpose" not in scene_payload
    assert "frame_thesis" not in scene_payload


def test_build_video_generation_context_attaches_scene_contract_meta():
    service = _build_service()
    payload = {
        "concept_plan": {
            "overview": "修仙故事",
            "scenes": [{"scene_number": 1, "title": "力量爆发"}],
            "intelligent_style_design": {"style_name": "仙侠动态水墨"},
        },
        "scene_overview": {
            "scenes": [
                {
                    "scene_number": 1,
                    "visual_description": "韩立半跪稳住身形",
                    "narrative_description": "为后续反击蓄势",
                    "duration": 10.0,
                    "image_url": "https://example.com/scene_1.jpg",
                }
            ]
        },
        "scene_scripts": {
            "1": {
                "script_text": "韩立稳住身形，灵光翻涌。",
                "motion_beats": [{"start": 0.0, "end": 10.0, "visual_focus": "韩立", "beat_summary": "蓄势"}],
            }
        },
    }

    result = build_video_generation_context("wf-video-contract", service=service, published_payload=payload)

    meta = result["scene_info_payload"]["scene_contract_meta"]
    assert meta["mode"] == "video_generation"
    assert meta["owner_matrix"]["carrier_evolution"] == "in_place_only"
    scene_payload = result["scene_info_payload"]["scenes_to_generate"][0]
    assert scene_payload["image_url"] == "https://example.com/scene_1.jpg"
    assert "generation_diagnostics" not in result["scene_info_payload"]
    assert "generation_diagnostics" not in result["context"]
    assert "image_purpose" not in scene_payload
    assert "frame_thesis" not in scene_payload
