import pytest
import json
from pathlib import Path

from app.agents.adapters.memory_views import (
    build_video_composer_context,
    build_image_generation_context,
    build_video_generation_context,
    load_scene_overview,
)
from app.agents.adapters.state.mas_state import build_mas_state_view
from app.agents.adapters.video.memory_adapter import VideoMemoryAdapter
from app.agents.memory.short_term import SceneArtifact, SceneSnapshot
from app.agents.memory.short_term.service import (
    MemoryNotInitializedError,
    WorkingMemoryService,
)
from app.agents.memory.storage.in_memory import InMemoryShortTermStore
from app.agents.utils.artifacts import finalize_scene_outputs
from app.agents.utils.memory_helpers import (
    agent_scope,
    ensure_agent_working_memory,
    ensure_mas_working_memory,
    get_mas_working_memory,
    write_shared_fact,
)
from app.services.video_composer_execution_contract import build_video_composer_execution_contract


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

    with pytest.raises(ValueError, match="missing scene_videos"):
        build_video_composer_context(workflow_id, service=service)


def test_video_composer_context_compose_contract_keeps_scene_inputs_even_when_final_video_exists():
    service = _build_service()
    workflow_id = "wf-composer-compose-authority"

    write_shared_fact(
        workflow_id,
        "project.final_video",
        {"path": "/tmp/stale-final.mp4", "url": "file:///tmp/stale-final.mp4"},
        service=service,
    )
    write_shared_fact(
        workflow_id,
        "scene_outputs.video",
        {
            "1": {
                "scene_number": 1,
                "video_path": "/tmp/scene-1.mp4",
                "duration_sec": 1.0,
            }
        },
        service=service,
    )
    write_shared_fact(
        workflow_id,
        "scene_outputs.voice",
        {
            "1": {
                "scene_number": 1,
                "audio_path": "/tmp/scene-1.wav",
                "duration_sec": 1.0,
            }
        },
        service=service,
    )
    write_shared_fact(
        workflow_id,
        "scene_overview",
        {"scenes": [{"scene_number": 1, "duration": 1.0}]},
        service=service,
    )

    composer_ctx = build_video_composer_context(
        workflow_id,
        service=service,
        execution_contract=build_video_composer_execution_contract(
            workflow_state_id=workflow_id,
            compose_mode="compose",
        ),
    )

    assert composer_ctx["scene_videos"][0]["local_path"] == "/tmp/scene-1.mp4"
    assert "final_video" not in composer_ctx
    assert "scene_voiceovers" not in composer_ctx
    assert "voice_assets" not in composer_ctx
    scene_media_ref = composer_ctx.get("scene_media_ref")
    assert scene_media_ref
    payload_path = Path(scene_media_ref)
    if not payload_path.is_absolute():
        payload_path = Path(__file__).resolve().parents[2] / payload_path
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    assert payload["scenes"][0]["video_file"] == "/tmp/scene-1.mp4"
    assert "audio_file" not in payload["scenes"][0]


def test_video_composer_context_rejects_incomplete_scene_video_set():
    service = _build_service()
    workflow_id = "wf-composer-incomplete-scene-videos"

    write_shared_fact(
        workflow_id,
        "scene_outputs.video",
        {
            "1": {
                "scene_number": 1,
                "video_path": "/tmp/scene-1.mp4",
                "duration_sec": 1.0,
            }
        },
        service=service,
    )
    write_shared_fact(
        workflow_id,
        "scene_overview",
        {"scenes": [{"scene_number": 1, "duration": 1.0}, {"scene_number": 2, "duration": 1.0}]},
        service=service,
    )

    with pytest.raises(ValueError, match="incomplete scene_videos"):
        build_video_composer_context(
            workflow_id,
            service=service,
            execution_contract=build_video_composer_execution_contract(
                workflow_state_id=workflow_id,
                compose_mode="compose",
            ),
        )


def test_video_composer_context_rejects_url_only_scene_video_for_compose_mode():
    service = _build_service()
    workflow_id = "wf-composer-compose-url-only"

    write_shared_fact(
        workflow_id,
        "scene_outputs.video",
        {
            "1": {
                "scene_number": 1,
                "video_url": "https://example.com/scene-1.mp4",
                "duration_sec": 1.0,
            }
        },
        service=service,
    )
    write_shared_fact(
        workflow_id,
        "scene_overview",
        {"scenes": [{"scene_number": 1, "duration": 1.0}]},
        service=service,
    )

    with pytest.raises(ValueError, match="missing local scene video files"):
        build_video_composer_context(
            workflow_id,
            service=service,
            execution_contract=build_video_composer_execution_contract(
                workflow_state_id=workflow_id,
                compose_mode="compose",
            ),
        )


def test_video_composer_context_voiceover_contract_includes_scene_audio_in_ref():
    service = _build_service()
    workflow_id = "wf-composer-voice-authority"

    write_shared_fact(
        workflow_id,
        "scene_outputs.video",
        {
            "1": {
                "scene_number": 1,
                "video_path": "/tmp/scene-1.mp4",
                "duration_sec": 1.0,
            }
        },
        service=service,
    )
    write_shared_fact(
        workflow_id,
        "scene_outputs.voice",
        {
            "1": {
                "scene_number": 1,
                "audio_path": "/tmp/scene-1.wav",
                "duration_sec": 1.0,
            }
        },
        service=service,
    )
    write_shared_fact(
        workflow_id,
        "project.voice_assets",
        {
            "1": {
                "local_path": "/tmp/scene-1.wav",
                "duration": 1.0,
            }
        },
        service=service,
    )
    write_shared_fact(
        workflow_id,
        "scene_overview",
        {"scenes": [{"scene_number": 1, "duration": 1.0}]},
        service=service,
    )

    composer_ctx = build_video_composer_context(
        workflow_id,
        service=service,
        execution_contract=build_video_composer_execution_contract(
            workflow_state_id=workflow_id,
            compose_mode="voiceover",
        ),
    )

    assert composer_ctx["scene_media_has_voice"] is True
    scene_media_ref = composer_ctx.get("scene_media_ref")
    assert scene_media_ref
    payload_path = Path(scene_media_ref)
    if not payload_path.is_absolute():
        payload_path = Path(__file__).resolve().parents[2] / payload_path
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    assert payload["scenes"][0]["audio_file"] == "/tmp/scene-1.wav"


def test_video_composer_context_bgm_contract_hides_scene_inputs_and_requires_final_video():
    service = _build_service()
    workflow_id = "wf-composer-bgm-authority"

    write_shared_fact(
        workflow_id,
        "project.background_music",
        {"audio_path": "/tmp/bgm.wav", "audio_url": "file:///tmp/bgm.wav", "duration": 2.0},
        service=service,
    )
    write_shared_fact(
        workflow_id,
        "scene_outputs.video",
        {
            "1": {
                "scene_number": 1,
                "video_path": "/tmp/scene-1.mp4",
                "duration_sec": 1.0,
            }
        },
        service=service,
    )
    contract = build_video_composer_execution_contract(
        workflow_state_id=workflow_id,
        compose_mode="bgm",
    )

    with pytest.raises(ValueError, match="missing final_video"):
        build_video_composer_context(
            workflow_id,
            service=service,
            execution_contract=contract,
        )

    write_shared_fact(
        workflow_id,
        "project.final_video",
        {"path": "/tmp/final.mp4", "url": "file:///tmp/final.mp4"},
        service=service,
    )

    composer_ctx = build_video_composer_context(
        workflow_id,
        service=service,
        execution_contract=contract,
    )

    assert composer_ctx["final_video"]["path"] == "/tmp/final.mp4"
    assert composer_ctx["background_music"]["path"] == "/tmp/bgm.wav"
    assert "scene_videos" not in composer_ctx
    assert "scene_media_ref" not in composer_ctx


def test_load_scene_overview_does_not_fallback_to_legacy_video_memory_adapter():
    service = _build_service()
    workflow_id = "wf-scene-overview-no-legacy-fallback"

    shared = ensure_mas_working_memory(workflow_id, service=service)
    adapter = VideoMemoryAdapter(shared)
    adapter.upsert_scene(
        SceneSnapshot(
            scene_number=1,
            duration=5.0,
            visual_description="legacy adapter scene",
        )
    )
    adapter.mark_completed(
        1,
        SceneArtifact(
            video_url="https://example.com/legacy-video.mp4",
            video_path="/tmp/legacy-video.mp4",
            prompt_text="legacy prompt",
        ),
    )

    assert not shared.get("scene_overview")
    assert load_scene_overview(workflow_id, service=service) == {}


def test_finalize_scene_outputs_does_not_read_failed_scenes_from_legacy_video_memory_adapter():
    service = _build_service()
    workflow_id = "wf-finalize-no-legacy-overview"

    shared = ensure_mas_working_memory(workflow_id, service=service)
    adapter = VideoMemoryAdapter(shared)
    adapter.upsert_scene(SceneSnapshot(scene_number=1, duration=5.0))
    adapter.mark_failed(
        1,
        "legacy failure",
        {"error_type": "temporary"},
        retryable=True,
    )

    completed, failed = finalize_scene_outputs(
        kind="video",
        workflow_id=workflow_id,
        agent_memory=None,
        service=service,
    )

    assert completed == []
    assert failed == []


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
