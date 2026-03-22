"""Centralized orchestration mode resolution and dispatch."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from ..models import Task
from ..agents.orchestrator import OrchestratorAgent
from ..agents.episode_orchestrator import EpisodeOrchestratorAgent
from ..services.memory_provider import build_memory_services
from .constants import GenerationMode
from .config import settings

logger = logging.getLogger("mode_router")


def resolve_generation_mode(
    explicit_mode: Optional[str] = None,
    *,
    route_default: Optional[GenerationMode] = None,
) -> GenerationMode:
    """Resolve generation mode for current request.

    Precedence: explicit_mode (payload/param) > route_default > settings.DEFAULT_GENERATION_MODE
    """

    if explicit_mode:
        mode_value = explicit_mode.strip().lower()
        if mode_value in GenerationMode._value2member_map_:
            return GenerationMode(mode_value)

    if route_default is not None:
        return route_default

    default_value = getattr(settings, "DEFAULT_GENERATION_MODE", GenerationMode.QUICK.value)
    default_value = str(default_value).lower()
    if default_value not in GenerationMode._value2member_map_:
        return GenerationMode.QUICK
    return GenerationMode(default_value)


async def dispatch_generation(
    mode: GenerationMode,
    *,
    task: Task,
    input_data: Dict[str, Any],
    db: Session,
    execution_order: int = 1,
) -> Dict[str, Any]:
    """Execute orchestration for the given mode."""

    if mode == GenerationMode.PROJECT:
        memory_services = build_memory_services()
        logger.info("MODE_ROUTER project dispatch: built memory services for task %s", task.id)
        coordinator = EpisodeOrchestratorAgent(memory_services=memory_services)
        logger.info("MODE_ROUTER project dispatch: coordinator constructed for task %s", task.id)
        return await coordinator.execute(
            task=task,
            input_data=input_data,
            db=db,
            execution_order=execution_order,
        )

    memory_services = build_memory_services()
    logger.info("MODE_ROUTER quick dispatch: built memory services for task %s", task.id)
    orchestrator = OrchestratorAgent(memory_services=memory_services)
    logger.info("MODE_ROUTER quick dispatch: orchestrator constructed for task %s", task.id)
    return await orchestrator.execute(
        task=task,
        input_data=input_data,
        db=db,
        execution_order=execution_order,
    )
