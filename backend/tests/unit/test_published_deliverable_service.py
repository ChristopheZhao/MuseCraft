import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.database import Base
from app.models import (
    AgentType,
    Task,
    TaskStatus,
    TaskType,
    WorkflowPublishedDeliverable,
    WorkflowSessionStatus,
)
from app.services.published_deliverable_service import (
    PublishedDeliverableService,
    build_deliverable_ref,
    get_published_deliverable_ref,
)
from app.services.published_deliverable_adapter import (
    build_script_deliverable_payload,
)
from app.services.runtime_session_service import RuntimeSessionService
from app.services.orchestration_state_adapter import OrchestrationStateAdapter
from app.agents.memory.short_term.service import WorkingMemoryService
from app.agents.memory.storage.in_memory import InMemoryShortTermStore
from app.agents.utils.memory_helpers import write_shared_fact


def _build_service() -> WorkingMemoryService:
    return WorkingMemoryService(store_factory=lambda: InMemoryShortTermStore())


@pytest.fixture
def sync_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def _create_task(db):
    task = Task(
        title="Deliverable Test",
        description="deliverable test",
        task_type=TaskType.VIDEO_GENERATION,
        status=TaskStatus.PENDING.value,
        input_parameters={"user_prompt": "test prompt"},
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def _seed_script_facts(service: WorkingMemoryService, workflow_id: str) -> None:
    write_shared_fact(
        workflow_id,
        "project.concept_plan",
        {
            "overview": "Han Li teaser",
            "scenes": [{"scene_number": 1, "title": "Immortal cave"}],
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
                    "visual_description": "Han Li stands in a misty cave.",
                    "narrative_description": "The teaser opens on Han Li preparing to advance.",
                    "duration": 6.0,
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
            }
        },
        service=service,
    )


def _build_continuation_checkpoint():
    return OrchestrationStateAdapter.build_continuation_checkpoint(
        task_specs={
            AgentType.CONCEPT_PLANNER: {"run": True, "order": 0},
            AgentType.SCRIPT_WRITER: {"run": True, "order": 1},
        },
        conditional_task_specs={},
        candidate_agents=[AgentType.CONCEPT_PLANNER, AgentType.SCRIPT_WRITER],
        anchor_type=OrchestrationStateAdapter.CONTINUATION_ANCHOR_RUNTIME_CHECKPOINT,
        node_key="script",
        attempt_id=1,
        decision_id=None,
    )


def test_publish_script_deliverable_persists_payload_without_direct_wm_projection(sync_db, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "TEMP_PATH", str(tmp_path))

    task = _create_task(sync_db)
    session = RuntimeSessionService.get_or_create_session_for_task_sync(sync_db, task, mode="quick")
    attempt = RuntimeSessionService.start_node_attempt_sync(
        sync_db,
        session,
        node_key="script",
    )
    service = _build_service()
    workflow_id = str(task.task_id)
    _seed_script_facts(service, workflow_id)

    deliverable = PublishedDeliverableService.publish_script_deliverable_sync(
        sync_db,
        session=session,
        workflow_id=workflow_id,
        attempt_id=attempt.id,
        payload=build_script_deliverable_payload(workflow_id, service=service),
        summary={"total_scenes": 1},
    )

    stored = sync_db.query(WorkflowPublishedDeliverable).filter_by(id=deliverable.id).one()
    assert stored.deliverable_type == "script"
    assert stored.is_candidate is True
    assert stored.is_approved is False

    payload_path = Path(deliverable.payload_ref)
    if not payload_path.is_absolute():
        payload_path = Path(__file__).resolve().parents[2] / deliverable.payload_ref
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    assert payload["concept_plan"]["overview"] == "Han Li teaser"
    assert payload["scene_scripts"]["1"]["script_text"] == "Han Li gathers spiritual energy in silence."

    payload_ref = get_published_deliverable_ref(session.input_payload, node_key="script")
    assert payload_ref is None


def test_submit_gate_decision_approve_marks_deliverable_approved(sync_db, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "TEMP_PATH", str(tmp_path))

    task = _create_task(sync_db)
    session = RuntimeSessionService.get_or_create_session_for_task_sync(sync_db, task, mode="quick")
    attempt = RuntimeSessionService.start_node_attempt_sync(
        sync_db,
        session,
        node_key="script",
    )
    service = _build_service()
    workflow_id = str(task.task_id)
    _seed_script_facts(service, workflow_id)

    deliverable = PublishedDeliverableService.publish_script_deliverable_sync(
        sync_db,
        session=session,
        workflow_id=workflow_id,
        attempt_id=attempt.id,
        payload=build_script_deliverable_payload(workflow_id, service=service),
        summary={"total_scenes": 1},
    )
    artifact_refs = [build_deliverable_ref(deliverable)]
    RuntimeSessionService.complete_node_attempt_sync(
        sync_db,
        session,
        node_key="script",
        attempt_id=attempt.id,
        output_artifacts=artifact_refs,
        metrics={"scenes_generated": 1},
        artifact_refs=artifact_refs,
    )
    attempt.continuation_checkpoint = _build_continuation_checkpoint()
    sync_db.commit()
    RuntimeSessionService.open_human_gate_sync(
        sync_db,
        session,
        node_key="script",
        gate_name="script_review",
        gate_type="human_review",
        attempt_id=attempt.id,
        artifact_refs=artifact_refs,
        facts={"script_preview_text": "draft"},
        allowed_actions=["approve", "revise", "replan"],
        recommended_action="approve",
    )

    decision = RuntimeSessionService.submit_gate_decision_sync(
        sync_db,
        session.id,
        node_key="script",
        action="approve",
    )

    refreshed = sync_db.query(WorkflowPublishedDeliverable).filter_by(id=deliverable.id).one()
    assert decision.action == "approve"
    assert refreshed.is_candidate is False
    assert refreshed.is_approved is True

    refreshed_session = RuntimeSessionService.get_session_by_id_sync(sync_db, session.id)
    assert refreshed_session.status == WorkflowSessionStatus.RESUMING.value
    published_ref = get_published_deliverable_ref(refreshed_session.input_payload, node_key="script")
    assert published_ref is not None
    assert published_ref["is_approved"] is True
    assert published_ref["deliverable_id"] == deliverable.id
