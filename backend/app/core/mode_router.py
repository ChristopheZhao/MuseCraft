"""Centralized orchestration mode resolution and dispatch."""

from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from ..models import Task
from ..agents.orchestrator import OrchestratorAgent
from ..agents.episode_orchestrator import EpisodeOrchestratorAgent
from .constants import GenerationMode
from .config import settings


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
        coordinator = EpisodeOrchestratorAgent()
        return await coordinator.execute(
            task=task,
            input_data=input_data,
            db=db,
            execution_order=execution_order,
        )

    orchestrator = OrchestratorAgent()
    return await orchestrator.execute(
        task=task,
        input_data=input_data,
        db=db,
        execution_order=execution_order,
    )
