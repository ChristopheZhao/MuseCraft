import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agents.memory.short_term.service import WorkingMemoryService
from app.agents.memory.storage.in_memory import InMemoryShortTermStore
from app.agents.base import AgentError
from app.agents.utils.memory_helpers import read_shared_fact, write_shared_fact
from app.core.database import Base
from app.models import AgentType, Task, TaskStatus, TaskType
from app.services.context_assembler import ContextContractAssembler
from app.services.runtime_session_service import RuntimeSessionService
from app.services.scene_info_reference_service import SceneInfoReferencePersistenceError
from app.services.video_composer_execution_contract import build_video_composer_execution_contract


def _build_service() -> WorkingMemoryService:
    return WorkingMemoryService(store_factory=lambda: InMemoryShortTermStore())


@pytest.fixture
def sync_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    db = session_local()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def _create_task(db):
    task = Task(
        title="ContextContractAssembler Test",
        description="test",
        task_type=TaskType.VIDEO_GENERATION,
        status=TaskStatus.PENDING.value,
        input_parameters={"user_prompt": "test prompt"},
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def test_publish_script_review_boundary_publishes_deliverable_without_shared_wm_projection(sync_db):
    service = _build_service()
    task = _create_task(sync_db)
    session = RuntimeSessionService.get_or_create_session_for_task_sync(sync_db, task, mode="quick")
    attempt = RuntimeSessionService.start_node_attempt_sync(sync_db, session, node_key="script", task=task)
    workflow_id = str(task.task_id)

    write_shared_fact(
        workflow_id,
        "project.concept_plan",
        {"overview": "published overview"},
        service=service,
    )
    write_shared_fact(
        workflow_id,
        "scene_overview",
        {"scenes": [{"scene_number": 1, "visual_description": "scene"}]},
        service=service,
    )
    write_shared_fact(
        workflow_id,
        "project.scene_scripts",
        {"1": {"script_text": "scene 1 script"}},
        service=service,
    )

    assembler = ContextContractAssembler(memory_services=SimpleNamespace(short_term=service))

    boundary = assembler.publish_script_review_boundary_sync(
        db=sync_db,
        session=session,
        workflow_state_id=workflow_id,
        attempt_id=attempt.id,
        script_output={"scenes_generated": 1, "total_scenes": 1},
    )

    artifact_ref = boundary["artifact_ref"]
    projected_ref = read_shared_fact(
        workflow_id,
        "published_deliverables.script.latest",
        None,
        service=service,
    )
    payload_path = Path(artifact_ref["payload_ref"])
    if not payload_path.is_absolute():
        payload_path = Path(__file__).resolve().parents[2] / payload_path

    assert artifact_ref["deliverable_type"] == "script"
    assert boundary["script_preview_text"]
    assert projected_ref is None
    assert payload_path.exists()
    persisted_payload = json.loads(payload_path.read_text(encoding="utf-8"))
    assert persisted_payload["scene_scripts"]["1"]["script_text"] == "scene 1 script"


def test_resolve_published_stage_payload_returns_explicit_receipt_and_payload(tmp_path):
    service = _build_service()
    workflow_id = "wf-stage-payload-resolved"
    assembler = ContextContractAssembler(memory_services=SimpleNamespace(short_term=service))
    payload_path = Path(tmp_path) / "script_payload.json"
    payload_path.write_text(
        json.dumps(
            {
                "deliverable_type": "script",
                "workflow_state_id": workflow_id,
                "concept_plan": {"overview": "resolved overview"},
                "scene_overview": {"scenes": [{"scene_number": 1}]},
                "scene_scripts": {"1": {"script_text": "resolved script"}},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    receipt = assembler.resolve_published_stage_payload(
        workflow_state_id=workflow_id,
        node_key="script",
        prefer_approved=True,
        required=True,
        runtime_input_payload={
            "published_deliverables": {
                "script": {
                    "type": "published_deliverable",
                    "deliverable_id": 13,
                    "deliverable_type": "script",
                    "scope_type": "episode",
                    "scope_id": "episode",
                    "attempt_id": 5,
                    "revision_no": 0,
                    "payload_ref": str(payload_path),
                    "summary": {"total_scenes": 1},
                    "is_candidate": False,
                    "is_approved": True,
                }
            }
        },
    )

    assert receipt["status"] == "resolved"
    assert receipt["ref"]["deliverable_id"] == 13
    assert receipt["payload"]["concept_plan"]["overview"] == "resolved overview"


def test_resolve_published_stage_payload_rejects_unapproved_runtime_ref(tmp_path):
    service = _build_service()
    workflow_id = "wf-stage-payload-unapproved"
    assembler = ContextContractAssembler(memory_services=SimpleNamespace(short_term=service))
    payload_path = Path(tmp_path) / "script_payload.json"
    payload_path.write_text(
        json.dumps(
            {
                "deliverable_type": "script",
                "workflow_state_id": workflow_id,
                "concept_plan": {"overview": "candidate overview"},
                "scene_overview": {"scenes": [{"scene_number": 1}]},
                "scene_scripts": {"1": {"script_text": "candidate script"}},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(AgentError, match="runtime_input_ref_not_approved"):
        assembler.resolve_published_stage_payload(
            workflow_state_id=workflow_id,
            node_key="script",
            prefer_approved=True,
            required=True,
            runtime_input_payload={
                "published_deliverables": {
                    "script": {
                        "type": "published_deliverable",
                        "deliverable_id": 14,
                        "deliverable_type": "script",
                        "scope_type": "episode",
                        "scope_id": "episode",
                        "attempt_id": 6,
                        "revision_no": 0,
                        "payload_ref": str(payload_path),
                        "summary": {"total_scenes": 1},
                        "is_candidate": True,
                        "is_approved": False,
                    }
                }
            },
        )


def test_assemble_agent_context_projects_script_writer_inputs_from_mas_boundary():
    service = _build_service()
    workflow_id = "wf-script-writer-context"
    assembler = ContextContractAssembler(memory_services=SimpleNamespace(short_term=service))

    write_shared_fact(
        workflow_id,
        "project.concept_plan",
        {"overview": "assembler-owned overview"},
        service=service,
    )
    write_shared_fact(
        workflow_id,
        "scene_overview",
        {
            "scenes": [
                {
                    "scene_number": 1,
                    "visual_description": "assembler-owned scene",
                    "narrative_description": "script boundary scene",
                    "duration": 6.0,
                }
            ]
        },
        service=service,
    )

    boundary = assembler.assemble_agent_context(
        agent_type=AgentType.SCRIPT_WRITER,
        workflow_state_id=workflow_id,
        workflow_data={"concept_plan": {"overview": "raw input must not be selected"}},
    )

    static_context = boundary["static_context"]
    diagnostics = boundary["_assembler_diagnostics"]["script_writer_context"]
    assert static_context["concept_plan"]["overview"] == "assembler-owned overview"
    assert static_context["scene_overview"]["scenes"][0]["scene_number"] == 1
    assert diagnostics["status"] == "resolved"
    assert diagnostics["source"] == "mas_working_memory"
    assert diagnostics["scene_count"] == 1


def test_assemble_agent_context_requires_no_projection_when_runtime_input_carries_script_ref(tmp_path):
    service = _build_service()
    workflow_id = "wf-assemble-runtime-input"
    assembler = ContextContractAssembler(memory_services=SimpleNamespace(short_term=service))

    write_shared_fact(
        workflow_id,
        "project.concept_plan",
        {"overview": "stale overview"},
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

    payload_path = Path(tmp_path) / "script_runtime_direct.json"
    payload_path.write_text(
        json.dumps(
            {
                "deliverable_type": "script",
                "workflow_state_id": workflow_id,
                "concept_plan": {
                    "overview": "runtime-direct overview",
                    "scenes": [{"scene_number": 1, "title": "Immortal cave"}],
                },
                "scene_overview": {
                    "scenes": [
                        {
                            "scene_number": 1,
                            "visual_description": "runtime-direct scene",
                            "narrative_description": "runtime-direct narrative",
                            "duration": 6.0,
                        }
                    ]
                },
                "scene_scripts": {
                    "1": {
                        "script_text": "runtime-direct script",
                        "voice_over_text": "runtime-direct voice",
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    boundary = assembler.assemble_agent_context(
        agent_type=AgentType.IMAGE_GENERATOR,
        workflow_state_id=workflow_id,
        workflow_data={},
        runtime_input_payload={
            "published_deliverables": {
                "script": {
                    "type": "published_deliverable",
                    "deliverable_id": 31,
                    "deliverable_type": "script",
                    "scope_type": "episode",
                    "scope_id": "episode",
                    "attempt_id": 9,
                    "revision_no": 1,
                    "payload_ref": str(payload_path),
                    "summary": {"total_scenes": 1},
                    "is_candidate": False,
                    "is_approved": True,
                }
            }
        },
    )

    static_context = boundary["static_context"]
    diagnostics = boundary["_assembler_diagnostics"]["script_stage_payload"]
    assert static_context["concept_plan"]["overview"] == "runtime-direct overview"
    assert static_context["scenes_to_generate"][0]["script_text"] == "runtime-direct script"
    assert diagnostics["status"] == "resolved"
    assert diagnostics["source"] == "runtime_input"


def test_assemble_agent_context_emits_scene_info_ref_without_payload_fallback(tmp_path, monkeypatch):
    service = _build_service()
    workflow_id = "wf-image-scene-info-ref"
    assembler = ContextContractAssembler(memory_services=SimpleNamespace(short_term=service))

    payload_path = Path(tmp_path) / "script_runtime_direct.json"
    payload_path.write_text(
        json.dumps(
            {
                "deliverable_type": "script",
                "workflow_state_id": workflow_id,
                "concept_plan": {
                    "overview": "runtime-direct overview",
                    "scenes": [{"scene_number": 1, "title": "Immortal cave"}],
                },
                "scene_overview": {
                    "scenes": [
                        {
                            "scene_number": 1,
                            "visual_description": "runtime-direct scene",
                            "narrative_description": "runtime-direct narrative",
                            "duration": 6.0,
                        }
                    ]
                },
                "scene_scripts": {
                    "1": {
                        "script_text": "runtime-direct script",
                        "voice_over_text": "runtime-direct voice",
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "app.services.context_assembler.persist_scene_info_ref",
        lambda **kwargs: "/tmp/runtime-direct-scene-info.json",
    )

    boundary = assembler.assemble_agent_context(
        agent_type=AgentType.IMAGE_GENERATOR,
        workflow_state_id=workflow_id,
        workflow_data={},
        runtime_input_payload={
            "published_deliverables": {
                "script": {
                    "type": "published_deliverable",
                    "deliverable_id": 31,
                    "deliverable_type": "script",
                    "scope_type": "episode",
                    "scope_id": "episode",
                    "attempt_id": 9,
                    "revision_no": 1,
                    "payload_ref": str(payload_path),
                    "summary": {"total_scenes": 1},
                    "is_candidate": False,
                    "is_approved": True,
                }
            }
        },
    )

    static_context = boundary["static_context"]
    assert static_context["scene_info_ref"] == "/tmp/runtime-direct-scene-info.json"
    assert "scene_info_payload" not in static_context


def test_assemble_agent_context_fails_closed_when_scene_info_ref_persistence_fails(tmp_path, monkeypatch):
    service = _build_service()
    workflow_id = "wf-image-scene-info-persist-fail"
    assembler = ContextContractAssembler(memory_services=SimpleNamespace(short_term=service))

    payload_path = Path(tmp_path) / "script_runtime_direct.json"
    payload_path.write_text(
        json.dumps(
            {
                "deliverable_type": "script",
                "workflow_state_id": workflow_id,
                "concept_plan": {
                    "overview": "runtime-direct overview",
                    "scenes": [{"scene_number": 1, "title": "Immortal cave"}],
                },
                "scene_overview": {
                    "scenes": [
                        {
                            "scene_number": 1,
                            "visual_description": "runtime-direct scene",
                            "narrative_description": "runtime-direct narrative",
                            "duration": 6.0,
                        }
                    ]
                },
                "scene_scripts": {
                    "1": {
                        "script_text": "runtime-direct script",
                        "voice_over_text": "runtime-direct voice",
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    def _raise_persist_error(**kwargs):
        raise SceneInfoReferencePersistenceError(
            "Scene info persistence failed: workflow_id=wf-image-scene-info-persist-fail "
            "agent_type=image_generator detail=disk_full"
        )

    monkeypatch.setattr(
        "app.services.context_assembler.persist_scene_info_ref",
        _raise_persist_error,
    )

    with pytest.raises(AgentError, match="Scene info ref persistence failed"):
        assembler.assemble_agent_context(
            agent_type=AgentType.IMAGE_GENERATOR,
            workflow_state_id=workflow_id,
            workflow_data={},
            runtime_input_payload={
                "published_deliverables": {
                    "script": {
                        "type": "published_deliverable",
                        "deliverable_id": 32,
                        "deliverable_type": "script",
                        "scope_type": "episode",
                        "scope_id": "episode",
                        "attempt_id": 10,
                        "revision_no": 1,
                        "payload_ref": str(payload_path),
                        "summary": {"total_scenes": 1},
                        "is_candidate": False,
                        "is_approved": True,
                    }
                }
            },
        )


def test_resolve_published_stage_payload_raises_explicitly_when_required_runtime_input_missing():
    service = _build_service()
    assembler = ContextContractAssembler(memory_services=SimpleNamespace(short_term=service))

    with pytest.raises(AgentError, match="missing_runtime_input_ref"):
        assembler.resolve_published_stage_payload(
            workflow_state_id="wf-stage-payload-missing",
            node_key="script",
            prefer_approved=True,
            required=True,
        )


def test_assemble_agent_context_projects_video_composer_from_execution_contract():
    service = _build_service()
    workflow_id = "wf-video-composer-boundary-compose"
    assembler = ContextContractAssembler(memory_services=SimpleNamespace(short_term=service))

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
        "scene_overview",
        {"scenes": [{"scene_number": 1, "duration": 1.0}]},
        service=service,
    )

    boundary = assembler.assemble_agent_context(
        agent_type=AgentType.VIDEO_COMPOSER,
        workflow_state_id=workflow_id,
        workflow_data={},
        execution_contract=build_video_composer_execution_contract(
            workflow_state_id=workflow_id,
            compose_mode="compose",
        ),
    )

    static_context = boundary["static_context"]
    assert static_context["scene_videos"][0]["local_path"] == "/tmp/scene-1.mp4"
    assert "final_video" not in static_context


def test_assemble_agent_context_fails_closed_when_video_composer_bgm_boundary_lacks_final_video():
    service = _build_service()
    workflow_id = "wf-video-composer-boundary-bgm"
    assembler = ContextContractAssembler(memory_services=SimpleNamespace(short_term=service))

    write_shared_fact(
        workflow_id,
        "project.background_music",
        {"audio_path": "/tmp/bgm.wav", "audio_url": "file:///tmp/bgm.wav"},
        service=service,
    )

    with pytest.raises(AgentError, match="missing final_video"):
        assembler.assemble_agent_context(
            agent_type=AgentType.VIDEO_COMPOSER,
            workflow_state_id=workflow_id,
            workflow_data={},
            execution_contract=build_video_composer_execution_contract(
                workflow_state_id=workflow_id,
                compose_mode="bgm",
            ),
        )
