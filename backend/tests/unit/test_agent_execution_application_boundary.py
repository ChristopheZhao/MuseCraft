from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import Base
from app.domain import (
    AgentExecutionContractError,
    AgentExecutionContractReason,
    AgentExecutionResult,
    AgentTaskReference,
    AgentType,
    JsonObjectPayload,
    TaskStatus,
    TaskType,
)
from app.infrastructure import SqlAlchemyRuntimeAttemptStore
from app.models import Task
from app.services.agent_execution_boundary import build_agent_execution_request
from app.services.episode_workflow_execution import PersistentEpisodeWorkflowExecutor
from app.services.runtime_read_model_service import RuntimeReadModelService


def test_application_boundary_snapshots_orm_task_into_typed_agent_request():
    input_data = {
        "workflow_state_id": "wf-application-boundary",
        "nested": {"items": [1, "two"]},
    }
    task = SimpleNamespace(
        task_id="task-application-boundary",
        task_type=TaskType.VIDEO_GENERATION,
        user_id="user-1",
        session_id="session-1",
    )

    request = build_agent_execution_request(
        task=task,
        agent_type=AgentType.IMAGE_GENERATOR,
        input_data=input_data,
        execution_order=4,
    )
    input_data["nested"]["items"].append("mutated-after-boundary")

    assert request.task == AgentTaskReference(
        task_id="task-application-boundary",
        task_type=TaskType.VIDEO_GENERATION.value,
        user_id="user-1",
        session_id="session-1",
    )
    assert request.agent_type == AgentType.IMAGE_GENERATOR.value
    assert request.workflow_state_id == "wf-application-boundary"
    assert request.execution_order == 4
    assert request.input_data.to_dict()["nested"] == {"items": [1, "two"]}


def test_application_boundary_rejects_non_json_orm_payload_values():
    task = SimpleNamespace(
        task_id="task-invalid-payload",
        task_type=TaskType.VIDEO_GENERATION,
        user_id=None,
        session_id=None,
    )

    with pytest.raises(AgentExecutionContractError) as exc_info:
        build_agent_execution_request(
            task=task,
            agent_type=AgentType.ORCHESTRATOR,
            input_data={"runtime_object": object()},
            execution_order=0,
        )

    assert exc_info.value.reason_code == AgentExecutionContractReason.INVALID_JSON_VALUE
    assert exc_info.value.field_path == "agent_execution.input_data.runtime_object"


class _TrackingSession(Session):
    created_sessions = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.was_closed = False
        self.created_sessions.append(self)

    def close(self) -> None:
        self.was_closed = True
        super().close()


def _episode_session_factory(tmp_path):
    _TrackingSession.created_sessions = []
    engine = create_engine(f"sqlite:///{(tmp_path / 'episode-boundary.db').as_posix()}")
    Base.metadata.create_all(bind=engine)
    return engine, sessionmaker(
        bind=engine,
        class_=_TrackingSession,
        autocommit=False,
        autoflush=False,
    )


@pytest.mark.asyncio
async def test_episode_executor_closes_persistence_session_before_agent_invocation(tmp_path):
    engine, session_factory = _episode_session_factory(tmp_path)
    captured = {}

    class _Orchestrator:
        async def execute(self, request):
            assert len(_TrackingSession.created_sessions) == 1
            assert _TrackingSession.created_sessions[0].was_closed is True
            captured["request"] = request
            return AgentExecutionResult(
                output_data=JsonObjectPayload.from_mapping(
                    {"status": "completed", "workflow_state_id": request.workflow_state_id},
                    field_path="test.output_data",
                )
            )

    executor = PersistentEpisodeWorkflowExecutor(
        orchestrator=_Orchestrator(),
        session_factory=session_factory,
    )
    parent_task = AgentTaskReference(
        task_id="project-task-1",
        task_type="project_workflow",
        user_id="user-1",
        session_id="session-1",
    )
    input_data = JsonObjectPayload.from_mapping(
        {
            "user_prompt": "episode one",
            "project_id": "project-1",
            "episode_id": "episode-1",
        },
        field_path="episode.input_data",
    )

    receipt = await executor.execute_episode(
        parent_task=parent_task,
        title="Episode 1 workflow",
        description="Project episode 1",
        input_data=input_data,
        execution_order=2,
    )

    assert all(session.was_closed for session in _TrackingSession.created_sessions)
    request = captured["request"]
    assert request.task.task_id == receipt.task_id
    assert request.task.user_id == "user-1"
    assert request.task.session_id == "session-1"
    assert request.workflow_state_id == receipt.task_id
    assert request.execution_order == 2

    db = session_factory()
    try:
        persisted = db.query(Task).filter(Task.task_id == receipt.task_id).one()
        assert persisted.status == TaskStatus.PENDING.value
        assert persisted.input_parameters == {
            "user_prompt": "episode one",
            "project_id": "project-1",
            "episode_id": "episode-1",
        }
        assert persisted.error_message is None
        runtime = RuntimeReadModelService(
            SqlAlchemyRuntimeAttemptStore(db)
        ).load_for_task(receipt.task_id)
        assert runtime is not None
        assert runtime.session.task_id == receipt.task_id
        assert runtime.session.shared_memory_id == receipt.task_id
        assert runtime.session.mode == "quick"
        assert runtime.session.project_id == "project-1"
        assert runtime.session.episode_id == "episode-1"
    finally:
        db.close()
        engine.dispose()


@pytest.mark.asyncio
async def test_episode_executor_does_not_invent_runtime_failure_on_invalid_agent_result(
    tmp_path,
):
    engine, session_factory = _episode_session_factory(tmp_path)

    class _InvalidOrchestrator:
        async def execute(self, _request):
            return {"status": "completed"}

    executor = PersistentEpisodeWorkflowExecutor(
        orchestrator=_InvalidOrchestrator(),
        session_factory=session_factory,
    )

    with pytest.raises(AgentExecutionContractError) as exc_info:
        await executor.execute_episode(
            parent_task=AgentTaskReference(
                task_id="project-task-invalid-result",
                task_type="project_workflow",
            ),
            title="Episode invalid workflow",
            description="Invalid result contract",
            input_data=JsonObjectPayload.from_mapping(
                {"user_prompt": "episode invalid"},
                field_path="episode.input_data",
            ),
            execution_order=1,
        )

    assert exc_info.value.reason_code == AgentExecutionContractReason.INVALID_CONTRACT_MEMBER
    db = session_factory()
    try:
        persisted = db.query(Task).one()
        assert persisted.status == TaskStatus.PENDING.value
        assert persisted.error_message is None
    finally:
        db.close()
        engine.dispose()
