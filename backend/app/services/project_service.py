"""Helper functions for project-mode state management."""

from __future__ import annotations

from typing import Dict, Optional

from ..core.story_plan import (
    EpisodePlan,
    EpisodeEditorialStatus,
    EpisodeExecutionStatus,
    ProjectState,
    project_state_repository,
)
from ..agents.base import AgentError


def get_project_state(project_id: str) -> ProjectState:
    project_state = project_state_repository.get(project_id)
    if not project_state:
        raise AgentError(f"Project state not found: {project_id}")
    return project_state


def update_episode_script(
    project_id: str,
    episode_id: str,
    script_text: str,
    approve: bool = False,
    additional_notes: Optional[Dict[str, str]] = None,
) -> ProjectState:
    project_state = get_project_state(project_id)
    episode = _locate_episode(project_state, episode_id)
    if not episode:
        raise AgentError(f"Episode not found: {episode_id}")

    episode.script_draft = script_text
    runtime = project_state.ensure_runtime_state(episode_id)
    previous_script = str(runtime.approved_script or "").strip()
    next_script = str(script_text or "").strip()
    script_changed = previous_script != next_script

    if approve:
        episode.status = EpisodeEditorialStatus.APPROVED
        runtime.approved_script = script_text
        runtime.error = None
        if script_changed and runtime.status in {
            EpisodeExecutionStatus.COMPLETED,
            EpisodeExecutionStatus.GENERATING,
        }:
            runtime.status = EpisodeExecutionStatus.STALE
        elif runtime.status in {
            EpisodeExecutionStatus.FAILED,
            EpisodeExecutionStatus.STALE,
        }:
            runtime.status = EpisodeExecutionStatus.IDLE
    else:
        if episode.status == EpisodeEditorialStatus.APPROVED:
            episode.status = EpisodeEditorialStatus.NEEDS_REVISION
        else:
            episode.status = EpisodeEditorialStatus.PENDING_APPROVAL
        if runtime.status in {
            EpisodeExecutionStatus.COMPLETED,
            EpisodeExecutionStatus.GENERATING,
        }:
            runtime.status = EpisodeExecutionStatus.STALE

    if additional_notes:
        runtime.output_assets.setdefault("notes", {}).update(additional_notes)

    project_state_repository.save(project_state)
    return project_state


def mark_episode_runtime_status(
    project_id: str,
    episode_id: str,
    status: EpisodeExecutionStatus,
    error: Optional[str] = None,
) -> ProjectState:
    project_state = get_project_state(project_id)
    episode = _locate_episode(project_state, episode_id)
    if not episode:
        raise AgentError(f"Episode not found: {episode_id}")

    runtime = project_state.ensure_runtime_state(episode_id)
    runtime.status = status
    runtime.error = error
    project_state.mark_episode_runtime_status(episode_id, status, error)
    project_state_repository.save(project_state)
    return project_state


def _locate_episode(project_state: ProjectState, episode_id: str) -> Optional[EpisodePlan]:
    for episode in project_state.story_plan.episodes:
        if episode.episode_id == episode_id:
            return episode
    return None
