import pytest
import json

from app.agents.adapters.memory_views import (
    build_image_generation_context,
    build_video_generation_context,
)
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
from app.services.published_deliverable_adapter import project_payload_deliverables_to_shared_wm


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


def test_media_context_builders_require_published_script_deliverable_after_agent_cleanup():
    service = _build_service()
    workflow_id = "wf-media-context"

    _seed_shared_media_facts(service, workflow_id)
    ensure_agent_working_memory(workflow_id, "concept_planner", service=service)
    ensure_agent_working_memory(workflow_id, "script_writer", service=service)

    service.cleanup_workflow(workflow_id)

    with pytest.raises(ValueError, match="Missing published script deliverable"):
        build_image_generation_context(workflow_id, service=service)
    with pytest.raises(ValueError, match="Missing published script deliverable"):
        build_video_generation_context(workflow_id, service=service)


def test_media_context_builders_prefer_published_script_deliverable(monkeypatch, tmp_path):
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
    payload = {
        "published_deliverables": {
            "script": {
                "type": "published_deliverable",
                "deliverable_id": 7,
                "deliverable_type": "script",
                "scope_type": "episode",
                "scope_id": "episode",
                "attempt_id": 11,
                "revision_no": 0,
                "payload_ref": str(payload_path),
                "summary": {"total_scenes": 1},
                "is_candidate": False,
                "is_approved": True,
            }
        }
    }
    project_payload_deliverables_to_shared_wm(workflow_id, payload, service=service)

    image_ctx = build_image_generation_context(workflow_id, service=service)
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

    video_ctx = build_video_generation_context(workflow_id, service=service)
    assert video_ctx["scene_info_payload"]["total_scenes"] == 1
    assert video_ctx["scene_info_payload"]["scenes_to_generate"][0]["scene_number"] == 1
    assert video_ctx["scene_info_payload"]["scene_overview"]["scenes"][0]["scene_number"] == 1
