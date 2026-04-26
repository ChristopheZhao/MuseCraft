"""Logging utility primitives shared by centralized logging configuration."""

from __future__ import annotations

import logging
import os
from pathlib import Path
import re

from .config import settings

TASK_POLLING_ACCESS_RE = re.compile(r'GET /api/v1/tasks/[^/]+(?:/runtime)?/? ')
PROJECT_ROOT = Path(__file__).resolve().parents[3]


class SuppressTaskPollingAccessFilter(logging.Filter):
    """Hide high-frequency task polling access logs from the access logger."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401
        try:
            message = record.getMessage()
        except Exception:
            return True
        return not bool(TASK_POLLING_ACCESS_RE.search(message))


def ensure_mas_log_dir() -> str:
    """Ensure the MAS log directory exists and return its absolute path."""

    log_dir = getattr(settings, "MAS_LOG_DIR", "") or ""
    if not log_dir:
        raise ValueError("MAS_LOG_DIR is not configured")
    log_path = Path(log_dir)
    if not log_path.is_absolute():
        log_path = PROJECT_ROOT / log_path
    os.makedirs(log_path, exist_ok=True)
    return str(log_path.resolve())


def mas_log_file_path() -> str:
    """Return the canonical MAS workflow log file path."""

    return os.path.join(ensure_mas_log_dir(), "mas_workflow.log")
