"""Logging helpers for MAS workflow debugging."""
import logging
import os
from logging.handlers import RotatingFileHandler

from .config import settings

_HANDLER_NAME = "mas_log_handler"


def configure_mas_logging() -> None:
    """Attach a rotating file handler for MAS workflow logs if configured."""
    log_dir = getattr(settings, "MAS_LOG_DIR", "") or ""
    if not log_dir:
        return

    try:
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.abspath(os.path.join(log_dir, "mas_workflow.log"))

        root_logger = logging.getLogger()

        if not root_logger.handlers:
            logging.basicConfig(
                level=getattr(logging, settings.LOG_LEVEL),
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
        if any(getattr(handler, "name", "") == _HANDLER_NAME for handler in root_logger.handlers):
            return

        handler = RotatingFileHandler(
            log_path,
            maxBytes=getattr(settings, "MAS_LOG_MAX_BYTES", 10_485_760),
            backupCount=getattr(settings, "MAS_LOG_BACKUP_COUNT", 5),
            encoding="utf-8",
        )
        handler.set_name(_HANDLER_NAME)
        level_name = getattr(settings, "MAS_LOG_LEVEL", settings.LOG_LEVEL)
        handler.setLevel(getattr(logging, level_name.upper(), logging.INFO))
        handler.setFormatter(
            logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        )
        root_logger.addHandler(handler)
    except Exception as exc:  # noqa: BLE001
        logging.getLogger(__name__).warning("Failed to configure MAS logging: %s", exc)
