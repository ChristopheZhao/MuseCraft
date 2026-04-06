import logging

from app.core.logging_config import build_logging_dict
from app.core.logging_utils import SuppressTaskPollingAccessFilter


def _make_record(message: str) -> logging.LogRecord:
    return logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )


def test_task_polling_access_filter_suppresses_task_status_and_runtime_paths():
    filt = SuppressTaskPollingAccessFilter()

    assert not filt.filter(_make_record('127.0.0.1 - "GET /api/v1/tasks/abc123 HTTP/1.1" 200'))
    assert not filt.filter(
        _make_record('127.0.0.1 - "GET /api/v1/tasks/abc123/runtime HTTP/1.1" 200')
    )


def test_task_polling_access_filter_keeps_non_polling_requests():
    filt = SuppressTaskPollingAccessFilter()

    assert filt.filter(_make_record('127.0.0.1 - "GET /health HTTP/1.1" 200'))
    assert filt.filter(_make_record('127.0.0.1 - "POST /api/v1/tasks/ HTTP/1.1" 201'))


def test_build_logging_dict_uses_unified_access_filter(monkeypatch):
    monkeypatch.setattr(
        "app.core.logging_config.mas_log_file_path",
        lambda: "/tmp/mas_workflow.log",
    )

    config = build_logging_dict()

    assert config["version"] == 1
    assert "console" in config["handlers"]
    assert "suppress_task_polling_access" in config["filters"]
    assert "uvicorn.access" in config["loggers"]
    assert config["loggers"]["uvicorn.access"]["propagate"] is False
    assert config["loggers"]["uvicorn.access"]["filters"] == ["suppress_task_polling_access"]
    assert "mas_file" in config["handlers"]
