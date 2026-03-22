"""Logging utility primitives shared by centralized logging configuration."""

from __future__ import annotations

import logging
import os
import re

from .config import settings

TASK_POLLING_ACCESS_RE = re.compile(r'GET /api/v1/tasks/[^/]+(?:/runtime)?/? ')


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
    os.makedirs(log_dir, exist_ok=True)
    return os.path.abspath(log_dir)


def mas_log_file_path() -> str:
    """Return the canonical MAS workflow log file path."""

    return os.path.join(ensure_mas_log_dir(), "mas_workflow.log")
