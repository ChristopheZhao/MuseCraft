"""
Sibling project-job execution host for project-level workflow handlers.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Tuple

from ..core.story_plan import ProjectOperationState, project_state_repository
from ..events.provider import reset_event_bus
from .project_job_contract import is_project_plan_contract


ProjectJobHandler = Callable[..., Awaitable[Dict[str, Any]]]


def prepare_project_job_execution_host(*, logger: logging.Logger | None = None) -> None:
    """Prepare worker-local bootstrap state before entering a project workflow handler."""

    logger = logger or logging.getLogger("project_job")

    logger.info("Initializing tool registry for project job host...")
    from ..agents.tools import register_default_tools

    register_default_tools()
    logger.info("Project job host tool registry initialized")

    reset_event_bus()
    logger.info("Project job host event bus reset")


async def _run_project_plan_handler(
    *,
    task: Any,
    input_data: Dict[str, Any],
    db: Any,
    execution_order: int,
    logger: logging.Logger,
) -> Dict[str, Any]:
    from ..agents import SeriesPlannerAgent
    from ..agents.utils.llm_policy import LLMPolicyManager
    from .character_reference_images import ensure_project_character_reference_images

    project_id = str(input_data.get("project_id") or "").strip() or None

    policy_path = Path(__file__).resolve().parents[1].joinpath("config", "llm_policies.yaml")
    policy_manager = LLMPolicyManager(str(policy_path))
    planner_llms = policy_manager.build_llms_for_agent("series_planner")

    planner = SeriesPlannerAgent.create_default(llms=planner_llms)
    result = await planner.execute(
        task=task,
        input_data=input_data,
        db=db,
        execution_order=execution_order,
    )

    try:
        if project_id:
            task.update_progress("Generating character references", 90)
            db.commit()
            refs_started = await ensure_project_character_reference_images(
                project_id,
                enabled=bool(input_data.get("generate_character_references", True)),
                logger=getattr(planner, "logger", None),
            )
            project_state = project_state_repository.get(project_id)
            if project_state and not refs_started:
                project_state.progress.character_references.status = ProjectOperationState.SKIPPED
                project_state.progress.character_references.error = None
                project_state_repository.save(project_state)
    except Exception as exc:  # noqa: BLE001
        if project_id:
            project_state = project_state_repository.get(project_id)
            if project_state:
                project_state.progress.character_references.status = ProjectOperationState.FAILED
                project_state.progress.character_references.error = str(exc)
                project_state_repository.save(project_state)
        logger.warning("Project character reference generation failed for %s: %s", project_id, exc)

    return result


def _resolve_handler(job_kind: str, handler_key: str) -> Tuple[str, ProjectJobHandler]:
    if is_project_plan_contract(job_kind, handler_key):
        return "project_plan", _run_project_plan_handler
    raise ValueError(
        f"Unsupported project job contract: job_kind={job_kind!r}, handler_key={handler_key!r}"
    )


def run_project_job_in_host(
    job_kind: str,
    handler_key: str,
    *,
    task: Any,
    input_data: Dict[str, Any],
    db: Any,
    execution_order: int = 1,
) -> Dict[str, Any]:
    """Run a project workflow handler inside a worker-owned project job host."""

    logger = logging.getLogger("project_job")
    prepare_project_job_execution_host(logger=logger)

    handler_name, handler = _resolve_handler(job_kind, handler_key)

    logger.info(
        "Setting up project job host event loop for task %s (job_kind=%s, handler_key=%s)",
        getattr(task, "id", None),
        job_kind,
        handler_key,
    )
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        result = loop.run_until_complete(
            handler(
                task=task,
                input_data=input_data,
                db=db,
                execution_order=execution_order,
                logger=logger,
            )
        )
        logger.info("Project job host completed handler %s with result: %s", handler_name, result)
        return {
            "status": result.get("status") or "completed",
            "result": result,
            "job_kind": job_kind,
            "handler_key": handler_key,
        }
    finally:
        logger.info("Closing project job host event loop...")
        loop.close()
        asyncio.set_event_loop(None)
