"""Minimal script to reproduce DetachedInstanceError after session close."""

from backend.app.models import Task, TaskType, TaskStatus
from backend.app.core.database import SessionLocal


def repro() -> None:
    session = SessionLocal()

    try:
        task = Task(
            title="repro",
            description="DetachedInstanceError demo",
            task_type=TaskType.VIDEO_GENERATION,
            status=TaskStatus.PENDING.value,
            input_parameters={},
        )
        session.add(task)
        session.commit()
        session.refresh(task)

        # Simulate the endpoint closing the session before reading task fields
        session.close()

        # Accessing expired attribute triggers DetachedInstanceError
        print(task.status)
    finally:
        if session.is_active:
            session.close()


if __name__ == "__main__":
    repro()
