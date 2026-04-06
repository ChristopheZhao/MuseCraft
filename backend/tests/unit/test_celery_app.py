import pytest

from app.services import celery_app as celery_module


def test_process_video_task_reports_progress_and_returns_success(monkeypatch):
    state_updates = []
    real_task = celery_module.process_video_task._get_current_object()

    monkeypatch.setattr(
        real_task,
        "update_state",
        lambda **kwargs: state_updates.append(kwargs),
    )
    monkeypatch.setattr(
        celery_module,
        "_load_sync_process_video_task",
        lambda: (lambda task_id: {"status": "skipped", "task_id": task_id}),
    )

    result = real_task.run(42)

    assert result == {"status": "skipped", "task_id": 42}
    assert state_updates == [
        {
            "state": "PROGRESS",
            "meta": {
                "current": 0,
                "total": 100,
                "status": "Starting video processing...",
            },
        }
    ]


def test_process_video_task_raises_standard_exception_for_business_error(monkeypatch):
    state_updates = []
    real_task = celery_module.process_video_task._get_current_object()

    monkeypatch.setattr(
        real_task,
        "update_state",
        lambda **kwargs: state_updates.append(kwargs),
    )
    monkeypatch.setattr(
        celery_module,
        "_load_sync_process_video_task",
        lambda: (lambda task_id: {"error": "boom"}),
    )

    with pytest.raises(celery_module.ProcessVideoTaskError, match="boom"):
        real_task.run(42)

    assert state_updates == [
        {
            "state": "PROGRESS",
            "meta": {
                "current": 0,
                "total": 100,
                "status": "Starting video processing...",
            },
        }
    ]


def test_process_video_task_wraps_import_error_without_manual_failure_meta(monkeypatch):
    state_updates = []
    real_task = celery_module.process_video_task._get_current_object()

    monkeypatch.setattr(
        real_task,
        "update_state",
        lambda **kwargs: state_updates.append(kwargs),
    )

    def _raise_import_error():
        raise ImportError("missing task runner")

    monkeypatch.setattr(celery_module, "_load_sync_process_video_task", _raise_import_error)

    with pytest.raises(
        celery_module.ProcessVideoTaskError,
        match="Failed to import sync_process_video_task: missing task runner",
    ):
        real_task.run(42)

    assert state_updates == [
        {
            "state": "PROGRESS",
            "meta": {
                "current": 0,
                "total": 100,
                "status": "Starting video processing...",
            },
        }
    ]
