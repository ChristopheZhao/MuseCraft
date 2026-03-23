"""
Execution host for queued task runs.

Owns worker-side bootstrap concerns that should not live in the queue adapter:
- tool registry initialization
- worker event-bus reset
- event-loop lifecycle for sync Celery entrypoints
- MAS mainline invocation
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

from ..core.constants import GenerationMode
from ..events.provider import reset_event_bus


def prepare_queued_execution_host(*, logger: logging.Logger | None = None) -> None:
    """Prepare worker-local bootstrap state before entering the MAS mainline."""

    logger = logger or logging.getLogger("celery_task")

    logger.info("Initializing tool registry for queued execution host...")
    from ..agents.tools import register_default_tools

    register_default_tools()
    logger.info("Queued execution host tool registry initialized")

    reset_event_bus()
    logger.info("Queued execution host event bus reset")


def run_generation_in_host(
    mode: GenerationMode,
    *,
    task: Any,
    input_data: Dict[str, Any],
    db: Any,
    route: str,
    execution_order: int = 1,
) -> Dict[str, Any]:
    """Run the MAS mainline inside a worker-owned execution host."""

    logger = logging.getLogger("celery_task")
    prepare_queued_execution_host(logger=logger)

    logger.info("Setting up queued execution host event loop...")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        if mode == GenerationMode.QUICK:
            from ..agents.orchestrator import OrchestratorAgent

            logger.info(
                "Routing task %s directly through quick orchestrator mainline (reason=%s, mode=%s)",
                getattr(task, "id", None),
                route,
                mode.value,
            )
            orchestrator = OrchestratorAgent.create_default()
            result = loop.run_until_complete(
                orchestrator.execute(
                    task=task,
                    input_data=input_data,
                    db=db,
                    execution_order=execution_order,
                )
            )
        elif mode == GenerationMode.PROJECT:
            from ..agents.episode_orchestrator import EpisodeOrchestratorAgent

            logger.info(
                "Routing task %s directly through project orchestrator mainline (reason=%s, mode=%s)",
                getattr(task, "id", None),
                route,
                mode.value,
            )
            orchestrator = EpisodeOrchestratorAgent.create_default()
            result = loop.run_until_complete(
                orchestrator.execute(
                    task=task,
                    input_data=input_data,
                    db=db,
                    execution_order=execution_order,
                )
            )
        else:
            raise ValueError(f"Unsupported generation mode for queued execution host: {mode.value}")
        logger.info("Queued execution host completed with result: %s", result)
        return {
            "status": result.get("status") or result.get("workflow_status") or "completed",
            "result": result,
            "route": route,
            "mode": mode.value,
        }
    finally:
        logger.info("Closing queued execution host event loop...")
        loop.close()
        asyncio.set_event_loop(None)
