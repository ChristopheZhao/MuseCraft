from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.domain import (
    AgentExecutionResult,
    AgentType,
    JsonObjectPayload,
    QueuedExecutionCommand,
    QueuedExecutionContractError,
    QueuedExecutionContractReason,
    QueuedExecutionKind,
    TaskStatus,
    TaskType,
    WorkflowSessionStatus,
)
from app.infrastructure import SqlAlchemyRuntimeAttemptStore
from app.models import Task
from app.services import execution_host_lease, queued_task_execution_host, task_queue
from app.services.agent_execution_boundary import build_agent_execution_request
from app.services.queued_execution_use_case import (
    QueuedExecutionApplicationError,
    QueuedExecutionUseCase,
)
from app.services.runtime_session_bootstrap_control_plane import RuntimeSessionBootstrapControlPlane
from app.services.runtime_session_control_plane import RuntimeSessionControlPlane


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    try:
        yield factory
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def _create_task(
    session_factory,
    *,
    input_parameters,
    status=TaskStatus.PENDING.value,
    runtime_input_payload=None,
    create_runtime=True,
):
    db = session_factory()
    try:
        task = Task(
            title="Queue Test",
            description="queue test",
            task_type=TaskType.VIDEO_GENERATION,
            status=status,
            input_parameters=input_parameters,
        )
        db.add(task)
        db.flush()
        db.refresh(task)
        if create_runtime:
            RuntimeSessionBootstrapControlPlane(
                SqlAlchemyRuntimeAttemptStore(db)
            ).create_quick_session(
                task_id=str(task.task_id),
                expected_task_status=TaskStatus(status),
                expected_latest_session_id=None,
                input_payload=JsonObjectPayload.from_mapping(
                    runtime_input_payload or input_parameters,
                    field_path="test.runtime_input_payload",
                ),
            )
        db.commit()
        return str(task.task_id)
    finally:
        db.close()


def _load_task(session_factory, task_id):
    db = session_factory()
    try:
        return db.query(Task).filter(Task.task_id == task_id).first()
    finally:
        db.close()


def _execution_result(payload):
    return AgentExecutionResult(
        output_data=JsonObjectPayload.from_mapping(
            payload,
            field_path="test.output_data",
        )
    )


def test_queued_execution_command_rejects_database_integer_identity():
    with pytest.raises(QueuedExecutionContractError) as exc_info:
        QueuedExecutionCommand(42, QueuedExecutionKind.VIDEO_GENERATION)

    assert exc_info.value.reason_code == QueuedExecutionContractReason.INVALID_TASK_ID


def test_execution_host_runs_typed_request_without_persistence_or_routing(monkeypatch):
    calls = {}

    class _Executor:
        async def execute(self, request):
            calls["request"] = request
            return _execution_result({"status": "completed"})

    request = build_agent_execution_request(
        task=SimpleNamespace(
            task_id="stable-task-1",
            task_type=TaskType.VIDEO_GENERATION,
            user_id=None,
            session_id=None,
        ),
        agent_type=AgentType.ORCHESTRATOR,
        input_data={"user_prompt": "test"},
        execution_order=1,
    )
    reset_calls = []
    monkeypatch.setattr("app.agents.tools.register_default_tools", lambda: None)
    monkeypatch.setattr(
        queued_task_execution_host,
        "reset_event_bus",
        lambda: reset_calls.append(True),
    )

    result = queued_task_execution_host.run_agent_execution_in_host(
        request=request,
        executor=_Executor(),
    )

    assert reset_calls == [True]
    assert result.output_data.to_dict() == {"status": "completed"}
    assert calls["request"] is request


def test_execution_host_exposes_injected_keepalive_context(monkeypatch):
    seen = {}

    class _Keepalive:
        def close(self):
            seen["closed"] = True

    class _Executor:
        async def execute(self, request):
            context = execution_host_lease.get_current_execution_host_lease_context()
            seen["controller"] = context.attempt_lease_keepalive
            return _execution_result({"status": "completed"})

    controller = _Keepalive()
    request = build_agent_execution_request(
        task=SimpleNamespace(
            task_id="stable-task-2",
            task_type=TaskType.VIDEO_GENERATION,
            user_id=None,
            session_id=None,
        ),
        agent_type=AgentType.ORCHESTRATOR,
        input_data={},
        execution_order=1,
    )
    monkeypatch.setattr("app.agents.tools.register_default_tools", lambda: None)
    monkeypatch.setattr(queued_task_execution_host, "reset_event_bus", lambda: None)

    queued_task_execution_host.run_agent_execution_in_host(
        request=request,
        executor=_Executor(),
        attempt_lease_keepalive=controller,
    )

    assert seen == {"controller": controller, "closed": True}
    assert execution_host_lease.get_current_execution_host_lease_context() is None


def test_execution_host_closes_keepalive_when_process_bootstrap_fails(monkeypatch):
    events = {}

    class _Keepalive:
        def close(self):
            events["closed"] = True

    request = build_agent_execution_request(
        task=SimpleNamespace(
            task_id="stable-task-bootstrap-failure",
            task_type=TaskType.VIDEO_GENERATION,
            user_id=None,
            session_id=None,
        ),
        agent_type=AgentType.ORCHESTRATOR,
        input_data={},
        execution_order=1,
    )
    monkeypatch.setattr(
        queued_task_execution_host,
        "prepare_queued_execution_host",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("bootstrap failed")),
    )

    with pytest.raises(RuntimeError, match="bootstrap failed"):
        queued_task_execution_host.run_agent_execution_in_host(
            request=request,
            executor=object(),
            attempt_lease_keepalive=_Keepalive(),
        )

    assert events == {"closed": True}


def test_video_queue_adapter_dispatches_stable_id_through_use_case(monkeypatch):
    events = {}

    class _UseCase:
        def enqueue(self, command, *, dispatch):
            events["command"] = command
            events["receipt"] = dispatch(command.task_id)
            return events["receipt"]

    monkeypatch.setattr(
        "app.services.celery_app.process_video_task",
        SimpleNamespace(delay=lambda task_id: SimpleNamespace(id=f"celery-{task_id}")),
    )

    receipt = task_queue.TaskQueueService(execution_use_case=_UseCase()).queue_task(
        "stable-video-task"
    )

    assert receipt == "celery-stable-video-task"
    assert events["command"] == QueuedExecutionCommand(
        task_id="stable-video-task",
        execution_kind=QueuedExecutionKind.VIDEO_GENERATION,
    )


def test_worker_entrypoint_invokes_same_application_command(monkeypatch):
    events = {}

    class _UseCase:
        def execute(self, command):
            events["command"] = command
            return {"status": "completed"}

    monkeypatch.setattr(task_queue, "QueuedExecutionUseCase", _UseCase)

    result = task_queue.sync_process_video_task("stable-worker-task")

    assert result == {"status": "completed"}
    assert events["command"].task_id == "stable-worker-task"
    assert events["command"].execution_kind == QueuedExecutionKind.VIDEO_GENERATION


def test_use_case_enqueue_owns_eligibility_and_transport_receipt_persistence(session_factory):
    task_id = _create_task(session_factory, input_parameters={"user_prompt": "test"})
    dispatched = []
    use_case = QueuedExecutionUseCase(session_factory=session_factory)

    receipt = use_case.enqueue(
        QueuedExecutionCommand(task_id, QueuedExecutionKind.VIDEO_GENERATION),
        dispatch=lambda stable_id: dispatched.append(stable_id) or "transport-1",
    )

    db = session_factory()
    try:
        task = db.query(Task).filter(Task.task_id == task_id).first()
        assert task.status == TaskStatus.QUEUED.value
        assert task.output_metadata["celery_task_id"] == "transport-1"
    finally:
        db.close()
    assert receipt == "transport-1"
    assert dispatched == [task_id]


def test_use_case_rejects_non_string_transport_receipt(session_factory):
    task_id = _create_task(session_factory, input_parameters={"user_prompt": "test"})
    use_case = QueuedExecutionUseCase(session_factory=session_factory)

    with pytest.raises(QueuedExecutionApplicationError) as exc_info:
        use_case.enqueue(
            QueuedExecutionCommand(task_id, QueuedExecutionKind.VIDEO_GENERATION),
            dispatch=lambda _stable_id: 42,
        )

    assert exc_info.value.reason_code == "transport_receipt_missing"
    db = session_factory()
    try:
        task = db.query(Task).filter(Task.task_id == task_id).first()
        assert task.status == TaskStatus.PENDING.value
        assert not (task.output_metadata or {}).get("celery_task_id")
    finally:
        db.close()


def test_use_case_fails_closed_when_quick_runtime_is_missing(session_factory):
    task_id = _create_task(
        session_factory,
        input_parameters={"user_prompt": "test"},
        create_runtime=False,
    )
    dispatched = []
    use_case = QueuedExecutionUseCase(
        session_factory=session_factory,
        host_runner=lambda **kwargs: pytest.fail("host must not run"),
    )

    receipt = use_case.enqueue(
        QueuedExecutionCommand(task_id, QueuedExecutionKind.VIDEO_GENERATION),
        dispatch=lambda stable_id: dispatched.append(stable_id) or "transport-1",
    )
    result = use_case.execute(QueuedExecutionCommand(task_id, QueuedExecutionKind.VIDEO_GENERATION))

    assert receipt is None
    assert dispatched == []
    assert result == {
        "status": "skipped",
        "skip_reason": "runtime_missing",
        "route": "orchestrator_mainline",
        "mode": "quick",
    }


def test_use_case_prefers_runtime_payload_and_builds_persistence_free_request(session_factory):
    task_id = _create_task(
        session_factory,
        input_parameters={"user_prompt": "task payload"},
        status=TaskStatus.QUEUED.value,
        runtime_input_payload={
            "user_prompt": "runtime payload",
            "runtime_contracts": {"script_review": {"action": "approve"}},
        },
    )

    calls = {}

    def _host(**kwargs):
        calls.update(kwargs)
        return _execution_result({"status": "completed"})

    use_case = QueuedExecutionUseCase(
        session_factory=session_factory,
        host_runner=_host,
        agent_factory=lambda agent_type: calls.setdefault("agent_type", agent_type) or object(),
        keepalive_factory=lambda **kwargs: calls.setdefault("keepalive", object()),
    )

    result = use_case.execute(QueuedExecutionCommand(task_id, QueuedExecutionKind.VIDEO_GENERATION))

    request = calls["request"]
    assert result["route"] == "orchestrator_mainline"
    assert result["mode"] == "quick"
    assert request.task.task_id == task_id
    assert request.input_data.to_dict()["user_prompt"] == "runtime payload"
    assert calls["agent_type"] == AgentType.ORCHESTRATOR
    assert "attempt_lease_keepalive" in calls


@pytest.mark.parametrize(
    "output_payload",
    [
        {},
        {"status": ""},
        {"status": " completed "},
        {"status": "success"},
        {"status": 42},
    ],
)
def test_use_case_rejects_missing_or_noncanonical_host_status(
    session_factory,
    output_payload,
):
    task_id = _create_task(
        session_factory,
        input_parameters={"user_prompt": "test"},
        status=TaskStatus.QUEUED.value,
    )
    use_case = QueuedExecutionUseCase(
        session_factory=session_factory,
        host_runner=lambda **kwargs: _execution_result(output_payload),
        agent_factory=lambda _agent_type: object(),
        keepalive_factory=lambda **kwargs: object(),
    )

    with pytest.raises(QueuedExecutionApplicationError) as exc_info:
        use_case.execute(
            QueuedExecutionCommand(task_id, QueuedExecutionKind.VIDEO_GENERATION)
        )

    assert exc_info.value.reason_code == "execution_status_invalid"
    db = session_factory()
    try:
        task = db.query(Task).filter(Task.task_id == task_id).first()
        runtime_session = SqlAlchemyRuntimeAttemptStore(db).load_latest_session_for_task(
            task_id
        )
        assert task.status == TaskStatus.FAILED.value
        assert runtime_session is not None
        assert runtime_session.status is WorkflowSessionStatus.FAILED
    finally:
        db.close()


@pytest.mark.parametrize("status", ["waiting_gate", "completed"])
def test_use_case_preserves_explicit_canonical_host_status(session_factory, status):
    task_id = _create_task(
        session_factory,
        input_parameters={"user_prompt": "test"},
        status=TaskStatus.QUEUED.value,
    )
    use_case = QueuedExecutionUseCase(
        session_factory=session_factory,
        host_runner=lambda **kwargs: _execution_result({"status": status}),
        agent_factory=lambda _agent_type: object(),
        keepalive_factory=lambda **kwargs: object(),
    )

    result = use_case.execute(
        QueuedExecutionCommand(task_id, QueuedExecutionKind.VIDEO_GENERATION)
    )

    assert result["status"] == status


def test_use_case_rejects_episode_coordination_without_canonical_status(session_factory):
    task_id = _create_task(
        session_factory,
        input_parameters={"mode": "project", "project_id": "project-1"},
        status=TaskStatus.QUEUED.value,
        create_runtime=False,
    )

    class _Coordinator:
        async def execute(self, **kwargs):
            return {}

    use_case = QueuedExecutionUseCase(
        session_factory=session_factory,
        episode_coordinator_factory=lambda: _Coordinator(),
    )

    with pytest.raises(QueuedExecutionApplicationError) as exc_info:
        use_case.execute(
            QueuedExecutionCommand(task_id, QueuedExecutionKind.VIDEO_GENERATION)
        )

    assert exc_info.value.reason_code == "execution_status_invalid"
    task = _load_task(session_factory, task_id)
    assert task.status == TaskStatus.FAILED.value


def test_use_case_rejects_nonterminal_episode_coordination_status(session_factory):
    task_id = _create_task(
        session_factory,
        input_parameters={"mode": "project", "project_id": "project-1"},
        status=TaskStatus.QUEUED.value,
        create_runtime=False,
    )

    class _Coordinator:
        async def execute(self, **kwargs):
            return {"status": "waiting_gate", "episodes": []}

    use_case = QueuedExecutionUseCase(
        session_factory=session_factory,
        episode_coordinator_factory=lambda: _Coordinator(),
    )

    with pytest.raises(QueuedExecutionApplicationError) as exc_info:
        use_case.execute(
            QueuedExecutionCommand(task_id, QueuedExecutionKind.VIDEO_GENERATION)
        )

    assert exc_info.value.reason_code == "execution_status_invalid"
    task = _load_task(session_factory, task_id)
    assert task.status == TaskStatus.FAILED.value


def test_use_case_terminal_runtime_fails_closed_before_host(session_factory):
    task_id = _create_task(
        session_factory,
        input_parameters={"user_prompt": "test"},
        status=TaskStatus.QUEUED.value,
    )
    db = session_factory()
    try:
        store = SqlAlchemyRuntimeAttemptStore(db)
        runtime_session = store.load_latest_session_for_task(task_id)
        assert runtime_session is not None
        RuntimeSessionControlPlane(store).mark_failed(
            runtime_session.session_id,
            error_message="already failed",
        )
        db.commit()
    finally:
        db.close()

    use_case = QueuedExecutionUseCase(
        session_factory=session_factory,
        host_runner=lambda **kwargs: pytest.fail("host must not run"),
    )
    result = use_case.execute(QueuedExecutionCommand(task_id, QueuedExecutionKind.VIDEO_GENERATION))

    assert result == {
        "status": "skipped",
        "skip_reason": "runtime_terminal:failed",
        "route": "orchestrator_mainline",
        "mode": "quick",
    }


def test_use_case_persists_runtime_failure_and_re_raises_host_error(session_factory):
    task_id = _create_task(
        session_factory,
        input_parameters={"user_prompt": "test"},
        status=TaskStatus.QUEUED.value,
    )

    def _raise_host(**kwargs):
        raise RuntimeError("host failed")

    use_case = QueuedExecutionUseCase(
        session_factory=session_factory,
        host_runner=_raise_host,
        agent_factory=lambda _agent_type: object(),
        keepalive_factory=lambda **kwargs: object(),
    )

    with pytest.raises(RuntimeError, match="host failed"):
        use_case.execute(QueuedExecutionCommand(task_id, QueuedExecutionKind.VIDEO_GENERATION))

    db = session_factory()
    try:
        task = db.query(Task).filter(Task.task_id == task_id).first()
        runtime_session = SqlAlchemyRuntimeAttemptStore(db).load_latest_session_for_task(task_id)
        assert runtime_session is not None
        assert task.status == TaskStatus.FAILED.value
        assert task.error_message == "host failed"
        assert runtime_session.status is WorkflowSessionStatus.FAILED
    finally:
        db.close()


def test_use_case_surfaces_failed_failure_transition(session_factory, monkeypatch):
    task_id = _create_task(
        session_factory,
        input_parameters={"user_prompt": "test"},
        status=TaskStatus.QUEUED.value,
    )
    monkeypatch.setattr(
        RuntimeSessionControlPlane,
        "mark_failed",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("transition failed")),
    )
    use_case = QueuedExecutionUseCase(
        session_factory=session_factory,
        host_runner=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("host failed")),
        agent_factory=lambda _agent_type: object(),
        keepalive_factory=lambda **kwargs: object(),
    )

    with pytest.raises(QueuedExecutionApplicationError) as exc_info:
        use_case.execute(QueuedExecutionCommand(task_id, QueuedExecutionKind.VIDEO_GENERATION))

    assert exc_info.value.reason_code == "failure_transition_failed"
    assert "host failed" in str(exc_info.value)
    assert "transition failed" in str(exc_info.value)
