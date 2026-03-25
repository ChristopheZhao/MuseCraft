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
        title="ExecutionBoundaryAssembler Test",
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


def test_project_runtime_payload_deliverables_projects_refs_to_shared_wm():
    service = _build_service()
    workflow_id = "wf-runtime-payload-projection"
    assembler = ContextContractAssembler(memory_services=SimpleNamespace(short_term=service))
    runtime_input_payload = {
        "published_deliverables": {
            "script": {
                "type": "published_deliverable",
                "deliverable_id": 12,
                "deliverable_type": "script",
                "scope_type": "episode",
                "scope_id": "episode",
                "attempt_id": 3,
                "revision_no": 0,
                "payload_ref": "tmp/script_payload.json",
                "summary": {"total_scenes": 1},
                "is_candidate": False,
                "is_approved": True,
            }
        }
    }

    receipt = assembler.project_runtime_payload_deliverables(
        workflow_state_id=workflow_id,
        runtime_input_payload=runtime_input_payload,
    )

    latest_ref = read_shared_fact(
        workflow_id,
        "published_deliverables.script.latest",
        None,
        service=service,
    )
    approved_ref = read_shared_fact(
        workflow_id,
        "published_deliverables.script.approved",
        None,
        service=service,
    )

    assert receipt == {"projected_count": 1, "projected_nodes": ["script"]}
    assert latest_ref["deliverable_id"] == 12
    assert approved_ref["deliverable_id"] == 12


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


def test_resolve_published_stage_payload_prefers_runtime_input_over_projection(tmp_path):
    service = _build_service()
    workflow_id = "wf-stage-payload-runtime-input"
    assembler = ContextContractAssembler(memory_services=SimpleNamespace(short_term=service))

    runtime_payload_path = Path(tmp_path) / "script_runtime_payload.json"
    runtime_payload_path.write_text(
        json.dumps(
            {
                "deliverable_type": "script",
                "workflow_state_id": workflow_id,
                "concept_plan": {"overview": "runtime-input overview"},
                "scene_overview": {"scenes": [{"scene_number": 1}]},
                "scene_scripts": {"1": {"script_text": "runtime-input script"}},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    projected_payload_path = Path(tmp_path) / "script_projected_payload.json"
    projected_payload_path.write_text(
        json.dumps(
            {
                "deliverable_type": "script",
                "workflow_state_id": workflow_id,
                "concept_plan": {"overview": "projected overview"},
                "scene_overview": {"scenes": [{"scene_number": 2}]},
                "scene_scripts": {"2": {"script_text": "projected script"}},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    assembler.project_runtime_payload_deliverables(
        workflow_state_id=workflow_id,
        runtime_input_payload={
            "published_deliverables": {
                "script": {
                    "type": "published_deliverable",
                    "deliverable_id": 17,
                    "deliverable_type": "script",
                    "scope_type": "episode",
                    "scope_id": "episode",
                    "attempt_id": 6,
                    "revision_no": 0,
                    "payload_ref": str(projected_payload_path),
                    "summary": {"total_scenes": 1},
                    "is_candidate": False,
                    "is_approved": True,
                }
            }
        },
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
                    "deliverable_id": 23,
                    "deliverable_type": "script",
                    "scope_type": "episode",
                    "scope_id": "episode",
                    "attempt_id": 8,
                    "revision_no": 1,
                    "payload_ref": str(runtime_payload_path),
                    "summary": {"total_scenes": 1},
                    "is_candidate": False,
                    "is_approved": True,
                }
            }
        },
    )

    assert receipt["status"] == "resolved"
    assert receipt["source"] == "runtime_input"
    assert receipt["ref"]["deliverable_id"] == 23
    assert receipt["payload"]["concept_plan"]["overview"] == "runtime-input overview"


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
