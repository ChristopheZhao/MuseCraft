"""Centralized logging configuration for API and Celery worker processes."""

from __future__ import annotations

import logging
import logging.config
from typing import Any, Dict

from .config import settings
from .logging_utils import SuppressTaskPollingAccessFilter, mas_log_file_path

_LOGGING_CONFIGURED = False


def _level(name: str, fallback: int) -> int:
    return getattr(logging, str(name).upper(), fallback)


def build_logging_dict() -> Dict[str, Any]:
    """Build the canonical dictConfig payload for runtime logging."""

    root_level_name = str(getattr(settings, "LOG_LEVEL", "INFO")).upper()
    root_level = _level(root_level_name, logging.INFO)
    mas_level_name = str(getattr(settings, "MAS_LOG_LEVEL", root_level_name)).upper()
    tool_registry_level_name = str(
        getattr(settings, "TOOL_REGISTRY_LOG_LEVEL", "WARNING")
    ).upper()
    httpx_level_name = str(getattr(settings, "HTTPX_LOG_LEVEL", "WARNING")).upper()

    handlers: Dict[str, Any] = {
        "console": {
            "class": "logging.StreamHandler",
            "level": root_level_name,
            "formatter": "standard",
            "stream": "ext://sys.stdout",
        },
    }

    root_handlers = ["console"]
    try:
        handlers["mas_file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "level": mas_level_name,
            "formatter": "standard",
            "filename": mas_log_file_path(),
            "maxBytes": int(getattr(settings, "MAS_LOG_MAX_BYTES", 10_485_760)),
            "backupCount": int(getattr(settings, "MAS_LOG_BACKUP_COUNT", 5)),
            "encoding": "utf-8",
        }
        root_handlers.append("mas_file")
    except Exception:
        pass

    access_handlers = list(root_handlers)
    access_filters = (
        ["suppress_task_polling_access"]
        if getattr(settings, "SUPPRESS_UVICORN_RUNTIME_POLLING_ACCESS_LOGS", True)
        else []
    )

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "suppress_task_polling_access": {
                "()": SuppressTaskPollingAccessFilter,
            }
        },
        "formatters": {
            "standard": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            }
        },
        "handlers": handlers,
        "root": {
            "level": root_level_name,
            "handlers": root_handlers,
        },
        "loggers": {
            "uvicorn": {
                "level": root_level_name,
                "handlers": root_handlers,
                "propagate": False,
            },
            "uvicorn.error": {
                "level": root_level_name,
                "handlers": root_handlers,
                "propagate": False,
            },
            "uvicorn.access": {
                "level": "INFO",
                "handlers": access_handlers,
                "filters": access_filters,
                "propagate": False,
            },
            "tool_registry": {
                "level": tool_registry_level_name,
                "handlers": root_handlers,
                "propagate": False,
            },
            "httpx": {
                "level": httpx_level_name,
                "handlers": root_handlers,
                "propagate": False,
            },
            "celery": {
                "level": root_level_name,
                "handlers": root_handlers,
                "propagate": False,
            },
            "celery.app.trace": {
                "level": root_level_name,
                "handlers": root_handlers,
                "propagate": False,
            },
        },
    }


def configure_logging(force: bool = False) -> None:
    """Configure process logging once from the centralized dictConfig."""

    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED and not force:
        return
    logging.config.dictConfig(build_logging_dict())
    _LOGGING_CONFIGURED = True
