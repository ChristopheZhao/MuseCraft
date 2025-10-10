"""Project mode API endpoints for long-form episode orchestration."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, status, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ....agents import SeriesPlannerAgent
from ....agents.base import AgentError
from ....core.database import SessionLocal
from ....core.constants import GenerationMode
from ....core.mode_router import resolve_generation_mode, dispatch_generation
from ....core.story_plan import ProjectState, project_state_repository, EpisodeStatus
from ....models import Task, TaskStatus, TaskType
from ....services.project_service import update_episode_script


router = APIRouter()


# -------------------------------
# Pydantic schemas
# -------------------------------


class EpisodePlanModel(BaseModel):
    episode_id: str
    sequence_index: int
    title: str
    target_duration_seconds: int
    summary: str = ""
    narrative_purpose: str = ""
    continuity_notes: Dict[str, Any] = Field(default_factory=dict)
    required_assets: Dict[str, Any] = Field(default_factory=dict)
    script_draft: str = ""
    status: str


class StoryPlanModel(BaseModel):
    project_id: str
    user_prompt: str
    target_duration_seconds: int
    aspect_ratio: str
    episodes: List[EpisodePlanModel]
    global_theme: str = ""
    character_bible: Dict[str, Any] = Field(default_factory=dict)
    visual_style: Dict[str, Any] = Field(default_factory=dict)
    tone_and_mood: str = ""
    additional_notes: Dict[str, Any] = Field(default_factory=dict)


class EpisodeRuntimeModel(BaseModel):
    episode_id: str
    status: str
    approved_script: str = ""
    workflow_task_id: Optional[str] = None
    aggregated_cost: float = 0.0
    aggregated_tokens: int = 0
    output_assets: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None


class ProjectStateResponse(BaseModel):
    project_id: str
    mode: str
    story_plan: StoryPlanModel
    episodes_runtime: Dict[str, EpisodeRuntimeModel] = Field(default_factory=dict)
    global_settings: Dict[str, Any] = Field(default_factory=dict)
    cost_budget: Optional[float] = None
    total_cost: float = 0.0
    total_tokens: int = 0
    completed_episodes: int = 0
    style_profile: Dict[str, Any] = Field(default_factory=dict)
    character_bible: Dict[str, Any] = Field(default_factory=dict)


class ProjectCreateRequest(BaseModel):
    user_prompt: str
    target_duration_seconds: int = Field(..., ge=60)
    mode: str = Field("project", pattern="^(project|quick)$")
    aspect_ratio: str = Field("16:9")
    resolution: Optional[str] = None
    style_preference: Optional[str] = None
    episode_cap_seconds: int = Field(60, ge=30, le=120)
    episode_min_seconds: int = Field(45, ge=20, le=90)
    global_theme: Optional[str] = None
    character_bible: Dict[str, Any] = Field(default_factory=dict)
    visual_style: Dict[str, Any] = Field(default_factory=dict)
    tone_and_mood: Optional[str] = None
    additional_notes: Dict[str, Any] = Field(default_factory=dict)
    project_id: Optional[str] = None


class ProjectCreateResponse(BaseModel):
    project: ProjectStateResponse


class EpisodeScriptRequest(BaseModel):
    script_text: str
    approve: bool = False
    additional_notes: Dict[str, str] = Field(default_factory=dict)


class EpisodeGenerationRequest(BaseModel):
    episode_ids: List[str] = Field(default_factory=list)
    episode_indices: List[int] = Field(default_factory=list)
    auto_approve: bool = False
    force_rerun: bool = False
    runtime_overrides: Dict[str, Any] = Field(default_factory=dict)


class EpisodeGenerationResponse(BaseModel):
    task_id: str
    status: str
    result: Dict[str, Any]
    project: ProjectStateResponse


# -------------------------------
# Helpers
# -------------------------------


def _serialize_project_state(project_state: ProjectState) -> ProjectStateResponse:
    payload = project_state.to_dict()
    runtime_payload = {
        ep_id: EpisodeRuntimeModel(**data)
        for ep_id, data in payload.get("episodes_runtime", {}).items()
    }

    story_dict = payload.get("story_plan", {})
    story_dict["episodes"] = [EpisodePlanModel(**ep) for ep in story_dict.get("episodes", [])]
    story_dict["global_theme"] = story_dict.get("global_theme") or ""
    story_dict["tone_and_mood"] = story_dict.get("tone_and_mood") or ""
    story_dict["character_bible"] = story_dict.get("character_bible") or {}
    story_dict["visual_style"] = story_dict.get("visual_style") or {}
    story_dict["additional_notes"] = story_dict.get("additional_notes") or {}
    story_model = StoryPlanModel(**story_dict)

    return ProjectStateResponse(
        project_id=payload["project_id"],
        mode=payload["mode"],
        story_plan=story_model,
        episodes_runtime=runtime_payload,
        global_settings=payload.get("global_settings", {}),
        cost_budget=payload.get("cost_budget"),
        total_cost=payload.get("total_cost", 0.0),
        total_tokens=payload.get("total_tokens", 0),
        completed_episodes=payload.get("completed_episodes", 0),
        style_profile=payload.get("style_profile", {}),
        character_bible=payload.get("character_bible", {}),
    )


def _create_task(session: Session, title: str, description: str, task_type: TaskType, input_params: Dict[str, Any]) -> Task:
    task = Task(
        title=title,
        description=description,
        task_type=task_type,
        status=TaskStatus.PENDING.value,
        input_parameters=input_params,
    )
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


# -------------------------------
# Endpoints
# -------------------------------


@router.post("/", response_model=ProjectCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_project(request: ProjectCreateRequest) -> ProjectCreateResponse:
    if request.mode != "project":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only project mode supports episode orchestration in this endpoint.",
        )

    project_id = request.project_id or str(uuid.uuid4())

    session = SessionLocal()
    task: Optional[Task] = None
    try:
        payload = {
            "project_id": project_id,
            "user_prompt": request.user_prompt,
            "target_duration_seconds": request.target_duration_seconds,
            "mode": request.mode,
            "aspect_ratio": request.aspect_ratio,
            "resolution": request.resolution,
            "style_preference": request.style_preference,
            "episode_cap_seconds": request.episode_cap_seconds,
            "episode_min_seconds": request.episode_min_seconds,
            "global_theme": request.global_theme,
            "character_bible": request.character_bible,
            "visual_style": request.visual_style,
            "tone_and_mood": request.tone_and_mood,
            "additional_notes": request.additional_notes,
        }

        task = _create_task(
            session,
            title=f"Project plan {project_id}",
            description=request.user_prompt,
            task_type=TaskType.SCRIPT_WRITING,
            input_params=payload,
        )

        from ....agents.utils.llm_policy import LLMPolicyManager

        policy_path = (
            Path(__file__).resolve()
            .parents[3]
            .joinpath('config', 'llm_policies.yaml')
        )
        policy_manager = LLMPolicyManager(str(policy_path))
        planner_llms = policy_manager.build_llms_for_agent('series_planner')

        planner = SeriesPlannerAgent(llms=planner_llms)
        await planner.execute(
            task=task,
            input_data=payload,
            db=session,
            execution_order=1,
        )

        task.status = TaskStatus.COMPLETED.value
        task.update_progress("Series plan completed", 100)
        session.commit()

    except Exception as exc:  # noqa: BLE001
        session.rollback()
        if task:
            session.add(task)
            task.status = TaskStatus.FAILED.value
            task.error_message = str(exc)
            session.commit()
        raise HTTPException(status_code=500, detail=f"Failed to create project plan: {exc}") from exc
    finally:
        session.close()

    project_state = project_state_repository.get(project_id)
    if not project_state:
        raise HTTPException(status_code=500, detail="Project plan not found after generation")

    return ProjectCreateResponse(project=_serialize_project_state(project_state))


@router.get("/{project_id}", response_model=ProjectStateResponse)
async def get_project(project_id: str) -> ProjectStateResponse:
    project_state = project_state_repository.get(project_id)
    if not project_state:
        raise HTTPException(status_code=404, detail="Project not found")
    return _serialize_project_state(project_state)


@router.put("/{project_id}/episodes/{episode_id}/script", response_model=ProjectStateResponse)
async def update_episode(project_id: str, episode_id: str, request: EpisodeScriptRequest) -> ProjectStateResponse:
    try:
        project_state = update_episode_script(
            project_id=project_id,
            episode_id=episode_id,
            script_text=request.script_text,
            approve=request.approve,
            additional_notes=request.additional_notes or None,
        )
    except AgentError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _serialize_project_state(project_state)


@router.post("/{project_id}/orchestrate", response_model=EpisodeGenerationResponse)
async def orchestrate_project(
    project_id: str,
    request: EpisodeGenerationRequest,
    background_tasks: BackgroundTasks,
) -> EpisodeGenerationResponse:
    project_state = project_state_repository.get(project_id)
    if not project_state:
        raise HTTPException(status_code=404, detail="Project not found")

    session = SessionLocal()
    task: Optional[Task] = None
    task_identifier: str = ""
    task_status_value: Optional[str] = None
    try:
        payload = request.dict()
        payload["project_id"] = project_id
        payload["mode"] = GenerationMode.PROJECT.value
        auto_approve = bool(payload.get("auto_approve", False))
        force_rerun = bool(payload.get("force_rerun", False))

        task = _create_task(
            session,
            title=f"Episode orchestration {project_id}",
            description=f"Episodes: {payload.get('episode_ids') or payload.get('episode_indices') or 'all'}",
            task_type=TaskType.VIDEO_GENERATION,
            input_params=payload,
        )
        task.status = TaskStatus.QUEUED.value
        session.commit()
        task_identifier = task.task_id
        task_status_value = task.status

        episode_ids = set(payload.get("episode_ids") or [])
        episode_indices = set(payload.get("episode_indices") or [])
        episodes = project_state.story_plan.episodes
        to_mark = []
        if episode_ids or episode_indices:
            for ep in episodes:
                if ep.episode_id in episode_ids or ep.sequence_index in episode_indices:
                    to_mark.append(ep)
        else:
            to_mark = episodes

        for ep in to_mark:
            runtime = project_state.ensure_runtime_state(ep.episode_id)

            should_run = False
            if force_rerun:
                should_run = True
            elif runtime.status in {
                EpisodeStatus.APPROVED,
                EpisodeStatus.NEEDS_REVISION,
                EpisodeStatus.FAILED,
            }:
                should_run = True
            elif auto_approve and runtime.status in {
                EpisodeStatus.DRAFT,
                EpisodeStatus.PENDING_APPROVAL,
            }:
                runtime.status = EpisodeStatus.APPROVED
                runtime.error = None
                ep.status = EpisodeStatus.APPROVED
                should_run = True

            if should_run:
                runtime.status = EpisodeStatus.GENERATING
                runtime.error = None
                ep.status = EpisodeStatus.GENERATING
        project_state_repository.save(project_state)

    except Exception as exc:  # noqa: BLE001
        session.rollback()
        if task:
            session.add(task)
            task.status = TaskStatus.FAILED.value
            task.error_message = str(exc)
            session.commit()
            task_identifier = task.task_id
            task_status_value = task.status
        else:
            task_status_value = TaskStatus.FAILED.value
        raise HTTPException(status_code=500, detail=f"Episode orchestration failed: {exc}") from exc
    finally:
        session.close()

    background_tasks.add_task(_schedule_episode_orchestration, task.id if task else None, payload)

    status_value = task_status_value or TaskStatus.FAILED.value
    return EpisodeGenerationResponse(
        task_id=task_identifier,
        status=status_value,
        result={},
        project=_serialize_project_state(project_state_repository.get(project_id) or project_state),
    )


def _schedule_episode_orchestration(task_db_id: Optional[int], payload: Dict[str, Any]) -> None:
    if task_db_id is None:
        return
    import asyncio
    import threading

    def runner() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_run_episode_orchestration(task_db_id, payload))
        finally:
            loop.close()

    threading.Thread(target=runner, name=f"episode-orch-{task_db_id}", daemon=True).start()


async def _run_episode_orchestration(task_db_id: int, payload: Dict[str, Any]) -> None:
    session = SessionLocal()
    task: Optional[Task] = None
    try:
        task = session.get(Task, task_db_id)
        if not task:
            return
        task.status = TaskStatus.IN_PROGRESS.value
        session.commit()

        mode = resolve_generation_mode(payload.get("mode"), route_default=GenerationMode.PROJECT)
        await dispatch_generation(
            mode,
            task=task,
            input_data=payload,
            db=session,
            execution_order=1,
        )

        session.commit()

    except Exception as exc:  # noqa: BLE001
        session.rollback()
        if task:
            task.status = TaskStatus.FAILED.value
            task.error_message = str(exc)
            session.commit()
    finally:
        session.close()
