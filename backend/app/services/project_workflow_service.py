"""Application commands spanning project definition and project task creation."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from ..core.story_plan import EpisodeEditorialStatus, ProjectDefinition
from ..domain import (
    JsonObjectPayload,
    ProjectCommandUnitOfWork,
    ProjectDefinitionError,
    ProjectDefinitionReason,
    ProjectDefinitionWrite,
    ProjectTaskCompletion,
    ProjectTaskCreate,
    ProjectTaskRecord,
    TaskType,
)
from .project_service import VersionedProjectDefinition


@dataclass(frozen=True, slots=True)
class ProjectCommandReceipt:
    project: VersionedProjectDefinition
    task: ProjectTaskRecord


class ProjectWorkflowApplicationService:
    def __init__(
        self,
        uow_factory: Callable[[], ProjectCommandUnitOfWork],
    ) -> None:
        self._uow_factory = uow_factory

    def create_project(
        self,
        *,
        definition: ProjectDefinition,
        planning_input: dict[str, object],
        title: str,
        description: str,
    ) -> ProjectCommandReceipt:
        with self._uow_factory() as uow:
            record = uow.store.save(
                ProjectDefinitionWrite(
                    project_id=definition.project_id,
                    mode=definition.mode,
                    payload=JsonObjectPayload.from_mapping(
                        definition.to_dict(),
                        field_path="project_workflow.create.definition",
                    ),
                    expected_version=None,
                )
            )
            task_payload = dict(planning_input)
            task_payload["project_definition_version"] = record.version
            task = uow.add_task(
                ProjectTaskCreate(
                    title=title,
                    description=description,
                    task_type=TaskType.SCRIPT_WRITING,
                    project_id=definition.project_id,
                    input_data=JsonObjectPayload.from_mapping(
                        task_payload,
                        field_path="project_workflow.create.task_input",
                    ),
                )
            )
            uow.commit()
        return ProjectCommandReceipt(
            project=self._snapshot(record),
            task=task,
        )

    def enqueue_episode_execution(
        self,
        *,
        project_id: str,
        expected_version: int,
        episode_ids: Sequence[str],
        episode_indices: Sequence[int],
        auto_approve: bool,
        execution_input: dict[str, object],
        title: str,
        description: str,
    ) -> ProjectCommandReceipt:
        with self._uow_factory() as uow:
            record = uow.store.load(project_id)
            if record is None:
                raise ProjectDefinitionError(
                    reason_code=ProjectDefinitionReason.RECORD_NOT_FOUND,
                    operation="enqueue_episode_execution",
                    project_id=project_id,
                    message=f"Project definition {project_id} was not found",
                )
            if record.version != int(expected_version):
                raise ProjectDefinitionError(
                    reason_code=ProjectDefinitionReason.VERSION_CONFLICT,
                    operation="enqueue_episode_execution",
                    project_id=project_id,
                    message=(
                        f"Project definition {project_id} version mismatch; "
                        f"expected {expected_version}, observed {record.version}"
                    ),
                )

            definition = ProjectDefinition.from_dict(record.payload.to_dict())
            selected = self._selected_episodes(
                definition,
                episode_ids=episode_ids,
                episode_indices=episode_indices,
            )
            if not selected:
                raise ProjectDefinitionError(
                    reason_code=ProjectDefinitionReason.INVALID_PAYLOAD,
                    operation="enqueue_episode_execution",
                    project_id=project_id,
                    message="No project episodes matched the execution command",
                )

            if not auto_approve and any(
                episode.status is not EpisodeEditorialStatus.APPROVED for episode in selected
            ):
                raise ProjectDefinitionError(
                    reason_code=ProjectDefinitionReason.INVALID_PAYLOAD,
                    operation="enqueue_episode_execution",
                    project_id=project_id,
                    message="All selected episodes must be approved before execution",
                )

            target_record = record
            if auto_approve:
                changed = False
                for episode in selected:
                    if episode.status is EpisodeEditorialStatus.APPROVED:
                        continue
                    episode.status = EpisodeEditorialStatus.APPROVED
                    episode.approved_script = episode.script_draft
                    episode.editorial_revision += 1
                    changed = True
                if changed:
                    target_record = uow.store.save(
                        ProjectDefinitionWrite(
                            project_id=project_id,
                            mode=definition.mode,
                            payload=JsonObjectPayload.from_mapping(
                                definition.to_dict(),
                                field_path="project_workflow.enqueue.definition",
                            ),
                            expected_version=record.version,
                        )
                    )

            task_payload = dict(execution_input)
            task_payload["project_id"] = project_id
            task_payload["project_definition_version"] = target_record.version
            task = uow.add_task(
                ProjectTaskCreate(
                    title=title,
                    description=description,
                    task_type=TaskType.VIDEO_GENERATION,
                    project_id=project_id,
                    input_data=JsonObjectPayload.from_mapping(
                        task_payload,
                        field_path="project_workflow.enqueue.task_input",
                    ),
                )
            )
            uow.commit()
        return ProjectCommandReceipt(
            project=self._snapshot(target_record),
            task=task,
        )

    def apply_planning_result(
        self,
        *,
        definition: ProjectDefinition,
        expected_version: int,
        task_id: str,
        character_references_requested: bool,
    ) -> ProjectCommandReceipt:
        """Atomically apply the authored plan and complete its application task."""

        with self._uow_factory() as uow:
            record = uow.store.save(
                ProjectDefinitionWrite(
                    project_id=definition.project_id,
                    mode=definition.mode,
                    payload=JsonObjectPayload.from_mapping(
                        definition.to_dict(),
                        field_path="project_workflow.apply_planning_result.definition",
                    ),
                    expected_version=int(expected_version),
                )
            )
            task = uow.complete_task(
                ProjectTaskCompletion(
                    task_id=task_id,
                    output_metadata=JsonObjectPayload.from_mapping(
                        {
                            "project_id": definition.project_id,
                            "project_job": {
                                "job_kind": "project_workflow",
                                "handler_key": "plan_project",
                            },
                            "character_references": {
                                "status": (
                                    "queued" if character_references_requested else "skipped"
                                ),
                                "error": None,
                            },
                        },
                        field_path="project_workflow.apply_planning_result.task_metadata",
                    ),
                    progress_step="Project planning completed",
                )
            )
            uow.commit()
        return ProjectCommandReceipt(project=self._snapshot(record), task=task)

    @staticmethod
    def _selected_episodes(
        definition: ProjectDefinition,
        *,
        episode_ids: Sequence[str],
        episode_indices: Sequence[int],
    ):
        requested_ids = {str(value) for value in episode_ids}
        requested_indices = {int(value) for value in episode_indices}
        if not requested_ids and not requested_indices:
            return list(definition.story_plan.episodes)
        return [
            episode
            for episode in definition.story_plan.episodes
            if episode.episode_id in requested_ids or episode.sequence_index in requested_indices
        ]

    @staticmethod
    def _snapshot(record) -> VersionedProjectDefinition:
        return VersionedProjectDefinition(
            definition=ProjectDefinition.from_dict(record.payload.to_dict()),
            version=record.version,
        )
