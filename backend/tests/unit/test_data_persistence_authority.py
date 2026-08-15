import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.domain import TaskStatus, TaskType
from app.models import Resource, Task
from app.services.data_persistence import DataPersistenceService


@pytest.fixture
def persistence_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    db = session_factory()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def _create_task(db, *, task_id="task-existing"):
    task = Task(
        task_id=task_id,
        title="Existing task",
        description="",
        task_type=TaskType.VIDEO_GENERATION,
        status=TaskStatus.IN_PROGRESS.value,
        progress_percentage=55,
        current_step="video_generation",
        input_parameters={},
        output_metadata={},
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@pytest.mark.parametrize("authority_value", [False, None])
def test_projection_without_explicit_authority_cannot_create_task(
    persistence_db,
    authority_value,
):
    result = DataPersistenceService().persist_from_event_payload(
        {
            "task_id": "task-missing",
            "runtime_authoritative": authority_value,
            "status": "COMPLETED",
            "progress": 100,
            "resources": [
                {
                    "kind": "final_video",
                    "scope": "task",
                    "resource_type": "video",
                    "path": "/tmp/final.mp4",
                }
            ],
        },
        persistence_db,
    )

    assert result["status"] == "skipped"
    assert result["reason_code"] == "non_authoritative_task_projection_target_missing"
    assert persistence_db.query(Task).count() == 0


def test_non_authoritative_projection_preserves_lifecycle_and_projects_committed_video(
    persistence_db,
):
    task = _create_task(persistence_db)

    result = DataPersistenceService().persist_from_event_payload(
        {
            "task_id": task.task_id,
            "runtime_authoritative": False,
            "runtime_session_id": 17,
            "runtime_terminal_committed": True,
            "status": "COMPLETED",
            "progress": 100,
            "current_step": "completed",
            "final_video_url": "/files/final.mp4",
            "final_video_path": "/tmp/final.mp4",
            "resources": [
                {
                    "kind": "final_video",
                    "scope": "task",
                    "resource_type": "video",
                    "url": "/files/final.mp4",
                    "path": "/tmp/final.mp4",
                    "filename": "final_video.mp4",
                }
            ],
        },
        persistence_db,
    )

    persistence_db.refresh(task)
    assert result["status"] == "success"
    assert task.status == TaskStatus.IN_PROGRESS.value
    assert task.progress_percentage == 55
    assert task.current_step == "video_generation"
    assert task.output_metadata["final_video_url"] == "/files/final.mp4"
    final_resource = persistence_db.query(Resource).filter(Resource.task_id == task.id).one()
    assert final_resource.is_final_output is True


def test_final_video_projection_requires_runtime_terminal_commit_marker(persistence_db):
    task = _create_task(persistence_db)

    result = DataPersistenceService().persist_from_event_payload(
        {
            "task_id": task.task_id,
            "runtime_authoritative": False,
            "status": "COMPLETED",
            "final_video_url": "/files/too-early.mp4",
            "final_video_path": "/tmp/too-early.mp4",
            "resources": [
                {
                    "kind": "final_video",
                    "scope": "task",
                    "resource_type": "video",
                    "path": "/tmp/too-early.mp4",
                }
            ],
        },
        persistence_db,
    )

    persistence_db.refresh(task)
    assert result["status"] == "partial"
    assert result["reported_gaps"] == ["final_video_projection_not_committed"]
    assert "final_video_url" not in (task.output_metadata or {})
    assert persistence_db.query(Resource).count() == 0
