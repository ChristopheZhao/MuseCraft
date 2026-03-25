import pytest
import json

from app.agents.adapters.memory_views import (
    build_video_composer_context,
    build_image_generation_context,
    build_video_generation_context,
)
from app.agents.adapters.state.mas_state import build_mas_state_view
from app.agents.memory.short_term.service import (
    MemoryNotInitializedError,
    WorkingMemoryService,
)
from app.agents.memory.storage.in_memory import InMemoryShortTermStore
from app.agents.utils.memory_helpers import (
    agent_scope,
    ensure_agent_working_memory,
    ensure_mas_working_memory,
    get_mas_working_memory,
    write_shared_fact,
)


def _build_service() -> WorkingMemoryService:
    return WorkingMemoryService(store_factory=lambda: InMemoryShortTermStore())


def _seed_shared_media_facts(service: WorkingMemoryService, workflow_id: str) -> None:
    write_shared_fact(
        workflow_id,
        "project.concept_plan",
        {
            "overview": "Han Li teaser",
            "intelligent_style_design": {"style": "xianxia anime"},
            "scenes": [
                {
                    "scene_number": 1,
                    "title": "Immortal cave",
                    "image_url": "https://example.com/reference-1.png",
                    "motion_beats": ["mist swirls", "camera push in"],
                    "characters_present": ["Han Li"],
                    "character_descriptions": ["young cultivator in dark robe"],
                }
            ],
        },
        service=service,
    )
    write_shared_fact(
        workflow_id,
        "scene_overview",
        {
            "scenes": [
                {
                    "scene_number": 1,
                    "visual_description": "Han Li stands in a misty cave lit by spiritual energy.",
                    "narrative_description": "The teaser opens on Han Li preparing to advance.",
                    "duration": 6.0,
                    "motion_beats": ["mist swirls", "energy pulses"],
                }
            ]
        },
        service=service,
    )
    write_shared_fact(
        workflow_id,
        "project.scene_scripts",
        {
            1: {
                "script_text": "Han Li gathers spiritual energy in silence.",
                "voice_over_text": "A lone cultivator steps into destiny.",
                "motion_beats": ["slow inhale", "energy surge"],
                "characters_present": ["Han Li"],
                "character_descriptions": ["young cultivator in dark robe"],
            }
        },
        service=service,
    )


def test_cleanup_workflow_preserves_mas_scope_and_clears_agent_scopes():
    service = _build_service()
    workflow_id = "wf-cleanup"

    ensure_mas_working_memory(workflow_id, service=service)
    ensure_agent_working_memory(workflow_id, "concept_planner", service=service)
    ensure_agent_working_memory(workflow_id, "script_writer", service=service)
    write_shared_fact(
        workflow_id,
        "project.concept_plan",
        {"scenes": [{"scene_number": 1, "title": "Opening"}]},
        service=service,
    )

    service.cleanup_workflow(workflow_id)

    shared = get_mas_working_memory(workflow_id, service=service)
    assert shared.get("project.concept_plan") == {"scenes": [{"scene_number": 1, "title": "Opening"}]}
    with pytest.raises(MemoryNotInitializedError):
        service.get(workflow_id, agent_scope(workflow_id, "concept_planner"))
    with pytest.raises(MemoryNotInitializedError):
        service.get(workflow_id, agent_scope(workflow_id, "script_writer"))


def test_reset_workflow_still_clears_all_scopes():
    service = _build_service()
    workflow_id = "wf-reset-all"

    ensure_mas_working_memory(workflow_id, service=service)
    ensure_agent_working_memory(workflow_id, "concept_planner", service=service)

    service.reset_workflow(workflow_id)

    with pytest.raises(MemoryNotInitializedError):
        service.get(workflow_id, f"mas:{workflow_id}")
    with pytest.raises(MemoryNotInitializedError):
        service.get(workflow_id, agent_scope(workflow_id, "concept_planner"))


def test_media_context_builders_require_explicit_published_script_payload_after_agent_cleanup():
    service = _build_service()
    workflow_id = "wf-media-context"

    _seed_shared_media_facts(service, workflow_id)
    ensure_agent_working_memory(workflow_id, "concept_planner", service=service)
    ensure_agent_working_memory(workflow_id, "script_writer", service=service)

    service.cleanup_workflow(workflow_id)

    with pytest.raises(ValueError, match="published_payload is required"):
        build_image_generation_context(workflow_id, service=service)
    with pytest.raises(ValueError, match="published_payload is required"):
        build_video_generation_context(workflow_id, service=service)


def test_media_context_builders_use_explicit_published_script_payload(monkeypatch, tmp_path):
    service = _build_service()
    workflow_id = "wf-published-script"

    # Conflicting live WM facts should not become the downstream boundary input once a
    # published deliverable is projected into the new execution segment.
    write_shared_fact(
        workflow_id,
        "project.concept_plan",
        {"overview": "stale overview", "scenes": [{"scene_number": 99, "title": "stale"}]},
        service=service,
    )
    write_shared_fact(
        workflow_id,
        "scene_overview",
        {"scenes": [{"scene_number": 99, "visual_description": "stale scene"}]},
        service=service,
    )
    write_shared_fact(
        workflow_id,
        "project.scene_scripts",
        {99: {"script_text": "stale script"}},
        service=service,
    )

    payload_dir = tmp_path / "published_deliverables"
    payload_dir.mkdir(parents=True, exist_ok=True)
    payload_path = payload_dir / "script_resume.json"
    payload_path.write_text(
        json.dumps(
            {
                "deliverable_type": "script",
                "workflow_state_id": workflow_id,
                "concept_plan": {
                    "overview": "published overview",
                    "scenes": [{"scene_number": 1, "title": "Immortal cave"}],
                },
                "scene_overview": {
                    "scenes": [
                        {
                            "scene_number": 1,
                            "visual_description": "published scene",
                            "narrative_description": "published narrative",
                            "duration": 6.0,
                        }
                    ]
                },
                "scene_scripts": {
                    "1": {
                        "script_text": "published script",
                        "voice_over_text": "published voice",
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    published_payload = json.loads(payload_path.read_text(encoding="utf-8"))

    image_ctx = build_image_generation_context(
        workflow_id,
        service=service,
        published_payload=published_payload,
    )
    assert image_ctx["scene_info_payload"]["total_scenes"] == 1
    assert image_ctx["scene_info_payload"]["scene_overview"]["scenes"][0]["scene_number"] == 1
    assert image_ctx["scene_info_payload"]["scenes_to_generate"][0]["script_text"] == "published script"

    write_shared_fact(
        workflow_id,
        "scene_outputs.image",
        {
            1: {
                "image_url": "https://example.com/published-1.png",
            }
        },
        service=service,
    )

    video_ctx = build_video_generation_context(
        workflow_id,
        service=service,
        published_payload=published_payload,
    )
    assert video_ctx["scene_info_payload"]["total_scenes"] == 1
    assert video_ctx["scene_info_payload"]["scenes_to_generate"][0]["scene_number"] == 1
    assert video_ctx["scene_info_payload"]["scene_overview"]["scenes"][0]["scene_number"] == 1


def test_video_composer_context_does_not_promote_legacy_nested_scene_outputs():
    service = _build_service()
    workflow_id = "wf-composer-legacy-nested"

    write_shared_fact(
        workflow_id,
        "scene_outputs",
        {
            "scene_outputs.video": {
                1: {
                    "file_path": "/tmp/legacy-video.mp4",
                    "url": "https://example.com/legacy-video.mp4",
                    "ts": 10,
                }
            },
            "scene_outputs.audio": {
                1: {
                    "file_path": "/tmp/legacy-bgm.mp3",
                    "url": "https://example.com/legacy-bgm.mp3",
                    "duration_sec": 8.0,
                    "ts": 11,
                }
            },
        },
        service=service,
    )

    composer_ctx = build_video_composer_context(workflow_id, service=service)

    assert composer_ctx["final_video"] == {"path": "", "url": ""}
    assert composer_ctx["background_music"] == {
        "path": "",
        "url": "",
        "duration": 0.0,
        "style": "",
    }


def test_mas_state_view_ignores_legacy_nested_scene_outputs():
    service = _build_service()
    workflow_id = "wf-mas-state-legacy-nested"

    write_shared_fact(
        workflow_id,
        "scene_overview",
        {
            "scenes": [
                {"scene_number": 1},
                {"scene_number": 2},
            ]
        },
        service=service,
    )
    write_shared_fact(
        workflow_id,
        "scene_outputs",
        {
            "scene_outputs.video": {
                1: {"file_path": "/tmp/legacy.mp4"},
            }
        },
        service=service,
    )

    state = build_mas_state_view(workflow_id, service=service)

    assert state["completed_scenes"] == 0
    assert state["pending_scenes"] == 2
    assert state["outputs_count"] == {}
