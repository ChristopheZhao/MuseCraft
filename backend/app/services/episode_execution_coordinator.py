"""Deterministic application coordinator for project episode execution."""

from __future__ import annotations

from typing import Any

from ..core.story_plan import EpisodeEditorialStatus, EpisodePlan, ProjectDefinition
from ..domain import (
    AgentTaskReference,
    EpisodeWorkflowExecutionPort,
    JsonObjectPayload,
    ProjectDefinitionError,
    ProjectDefinitionReason,
    ProjectExecutionReadModelQuery,
)
from .project_service import ProjectDefinitionApplicationService


class EpisodeExecutionCoordinationError(RuntimeError):
    def __init__(self, *, reason_code: str, message: str) -> None:
        self.reason_code = str(reason_code or "episode_coordination_failed")
        super().__init__(message)


class EpisodeExecutionCoordinator:
    """Select approved episodes and invoke the MAS workflow through an injected port."""

    def __init__(
        self,
        *,
        project_definitions: ProjectDefinitionApplicationService,
        execution_query: ProjectExecutionReadModelQuery,
        episode_executor: EpisodeWorkflowExecutionPort,
    ) -> None:
        self._project_definitions = project_definitions
        self._execution_query = execution_query
        self._episode_executor = episode_executor

    async def execute(
        self,
        *,
        parent_task: AgentTaskReference,
        input_data: dict[str, Any],
    ) -> dict[str, Any]:
        project_id = str(input_data.get("project_id") or "").strip()
        if not project_id:
            raise EpisodeExecutionCoordinationError(
                reason_code="project_id_missing",
                message="Episode execution command is missing project_id",
            )
        expected_version = input_data.get("project_definition_version")
        if not isinstance(expected_version, int):
            raise EpisodeExecutionCoordinationError(
                reason_code="project_definition_version_missing",
                message="Episode execution command is missing project_definition_version",
            )

        snapshot = self._project_definitions.get(project_id)
        if snapshot.version != expected_version:
            raise ProjectDefinitionError(
                reason_code=ProjectDefinitionReason.VERSION_CONFLICT,
                operation="coordinate_episode_execution",
                project_id=project_id,
                message=(
                    f"Project definition {project_id} version mismatch; "
                    f"expected {expected_version}, observed {snapshot.version}"
                ),
            )
        projection = self._execution_query.get(project_id)
        runtime_by_episode = {item.episode_id: item for item in projection.episodes}
        selected = self._select_episodes(snapshot.definition, input_data)
        if not selected:
            raise EpisodeExecutionCoordinationError(
                reason_code="episode_selection_empty",
                message="No project episodes matched the execution command",
            )

        force_rerun = bool(input_data.get("force_rerun", False))
        results: list[dict[str, Any]] = []
        for order, episode in enumerate(selected, start=1):
            if episode.status is not EpisodeEditorialStatus.APPROVED:
                results.append(
                    {
                        "episode_id": episode.episode_id,
                        "status": "skipped",
                        "reason_code": "episode_not_approved",
                    }
                )
                continue
            runtime = runtime_by_episode.get(episode.episode_id)
            runtime_status = runtime.status if runtime is not None else "idle"
            if runtime_status in {"queued", "generating"}:
                results.append(
                    {
                        "episode_id": episode.episode_id,
                        "status": "skipped",
                        "reason_code": "episode_execution_active",
                    }
                )
                continue
            if runtime_status == "completed" and not force_rerun:
                results.append(
                    {
                        "episode_id": episode.episode_id,
                        "status": "skipped",
                        "reason_code": "episode_already_completed",
                    }
                )
                continue

            receipt = await self._episode_executor.execute_episode(
                parent_task=parent_task,
                title=f"Episode {episode.sequence_index + 1} workflow",
                description=(f"Project {project_id} episode {episode.sequence_index + 1}"),
                input_data=JsonObjectPayload.from_mapping(
                    self._episode_payload(
                        snapshot.definition,
                        episode,
                        definition_version=snapshot.version,
                    ),
                    field_path=f"episode_execution[{episode.episode_id}].input_data",
                ),
                execution_order=order,
            )
            output = receipt.result.output_data.to_dict()
            results.append(
                {
                    "episode_id": episode.episode_id,
                    "status": str(output.get("status") or "completed"),
                    "task_id": receipt.task_id,
                    "workflow_state_id": output.get("workflow_state_id"),
                    "output": output,
                }
            )

        if not any(item.get("task_id") for item in results):
            raise EpisodeExecutionCoordinationError(
                reason_code="no_eligible_episodes",
                message="No selected episode was eligible for execution",
            )
        return {
            "status": "completed",
            "project_id": project_id,
            "project_definition_version": snapshot.version,
            "episodes": results,
        }

    @staticmethod
    def _select_episodes(
        definition: ProjectDefinition,
        input_data: dict[str, Any],
    ) -> list[EpisodePlan]:
        requested_ids = {str(value) for value in input_data.get("episode_ids", []) or []}
        requested_indices = {int(value) for value in input_data.get("episode_indices", []) or []}
        if not requested_ids and not requested_indices:
            return list(definition.story_plan.episodes)
        return [
            episode
            for episode in definition.story_plan.episodes
            if episode.episode_id in requested_ids or episode.sequence_index in requested_indices
        ]

    @staticmethod
    def _episode_payload(
        definition: ProjectDefinition,
        episode: EpisodePlan,
        *,
        definition_version: int,
    ) -> dict[str, Any]:
        story_plan = definition.story_plan
        character_source = definition.character_bible or story_plan.character_bible
        character_payload = {
            key: value.to_dict() if hasattr(value, "to_dict") else value
            for key, value in character_source.items()
        }
        title = episode.title.strip() or f"Episode {episode.sequence_index + 1}"
        summary = episode.summary.strip() or "N/A"
        prompt_lines = [
            f"Episode {episode.sequence_index + 1}/{len(story_plan.episodes)}: {title}",
            f"Episode summary: {summary}",
            f"Target duration: {episode.target_duration_seconds}s",
        ]
        if episode.narrative_purpose:
            prompt_lines.append(f"Narrative purpose: {episode.narrative_purpose}")
        return {
            "project_id": definition.project_id,
            "episode_id": episode.episode_id,
            "project_definition_version": definition_version,
            "episode_editorial_revision": episode.editorial_revision,
            "user_prompt": "\n".join(prompt_lines),
            "duration": episode.target_duration_seconds,
            "aspect_ratio": story_plan.aspect_ratio,
            "resolution": definition.global_settings.get("resolution"),
            "style_preference": definition.global_settings.get("style_preference"),
            "intelligent_style_design": definition.style_profile,
            "predefined_style_profile": definition.style_profile,
            "character_bible": character_payload,
            "visual_style": story_plan.visual_style,
            "episode_context": {
                "episode_index": episode.sequence_index + 1,
                "sequence_index": episode.sequence_index,
                "episode_count": len(story_plan.episodes),
                "title": title,
                "summary": summary,
                "narrative_purpose": episode.narrative_purpose,
                "target_duration_seconds": episode.target_duration_seconds,
                "continuity_notes": episode.continuity_notes,
                "approved_script": episode.approved_script,
                "required_assets": episode.required_assets,
            },
            "project_context": {
                "project_brief": story_plan.user_prompt[:200],
                "global_theme": story_plan.global_theme,
                "character_bible": character_payload,
                "visual_style": story_plan.visual_style,
                "tone_and_mood": story_plan.tone_and_mood,
                "additional_notes": story_plan.additional_notes,
                "style_profile": definition.style_profile,
            },
            "concept_mode": "episode",
        }
