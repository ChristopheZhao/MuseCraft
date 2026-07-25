"""Application service for versioned project-definition commands."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Dict, Optional, Sequence

from ..core.story_plan import EpisodeEditorialStatus, EpisodePlan, ProjectDefinition
from ..domain import (
    JsonObjectPayload,
    ProjectDefinitionError,
    ProjectDefinitionReason,
    ProjectDefinitionRecord,
    ProjectDefinitionUnitOfWork,
    ProjectDefinitionWrite,
)


@dataclass(frozen=True, slots=True)
class VersionedProjectDefinition:
    definition: ProjectDefinition
    version: int


class ProjectDefinitionApplicationService:
    def __init__(
        self,
        uow_factory: Callable[[], ProjectDefinitionUnitOfWork],
    ) -> None:
        self._uow_factory = uow_factory

    @staticmethod
    def _snapshot(record: ProjectDefinitionRecord) -> VersionedProjectDefinition:
        return VersionedProjectDefinition(
            definition=ProjectDefinition.from_dict(record.payload.to_dict()),
            version=record.version,
        )

    def load_optional(self, project_id: str) -> Optional[VersionedProjectDefinition]:
        with self._uow_factory() as uow:
            record = uow.store.load(project_id)
        return self._snapshot(record) if record is not None else None

    def get(self, project_id: str) -> VersionedProjectDefinition:
        snapshot = self.load_optional(project_id)
        if snapshot is None:
            raise ProjectDefinitionError(
                reason_code=ProjectDefinitionReason.RECORD_NOT_FOUND,
                operation="get_project_definition",
                project_id=project_id,
                message=f"Project definition {project_id} was not found",
            )
        return snapshot

    def list_definitions(self) -> Sequence[VersionedProjectDefinition]:
        with self._uow_factory() as uow:
            records = tuple(uow.store.list_records())
        return tuple(self._snapshot(record) for record in records)

    def create(self, definition: ProjectDefinition) -> VersionedProjectDefinition:
        with self._uow_factory() as uow:
            record = uow.store.save(
                ProjectDefinitionWrite(
                    project_id=definition.project_id,
                    mode=definition.mode,
                    payload=JsonObjectPayload.from_mapping(
                        definition.to_dict(),
                        field_path="project_definition.create",
                    ),
                    expected_version=None,
                )
            )
            uow.commit()
        return self._snapshot(record)

    def replace(
        self,
        definition: ProjectDefinition,
        *,
        expected_version: int,
    ) -> VersionedProjectDefinition:
        with self._uow_factory() as uow:
            record = uow.store.save(
                ProjectDefinitionWrite(
                    project_id=definition.project_id,
                    mode=definition.mode,
                    payload=JsonObjectPayload.from_mapping(
                        definition.to_dict(),
                        field_path="project_definition.replace",
                    ),
                    expected_version=int(expected_version),
                )
            )
            uow.commit()
        return self._snapshot(record)

    def remove(self, project_id: str, *, expected_version: int) -> None:
        with self._uow_factory() as uow:
            uow.store.remove(project_id, expected_version=expected_version)
            uow.commit()

    def update_episode_script(
        self,
        *,
        project_id: str,
        episode_id: str,
        script_text: str,
        approve: bool,
        expected_version: int,
        additional_notes: Optional[Dict[str, str]] = None,
    ) -> VersionedProjectDefinition:
        snapshot = self.get(project_id)
        if snapshot.version != int(expected_version):
            raise ProjectDefinitionError(
                reason_code=ProjectDefinitionReason.VERSION_CONFLICT,
                operation="update_episode_script",
                project_id=project_id,
                message=(
                    f"Project definition {project_id} version mismatch; "
                    f"expected {expected_version}, observed {snapshot.version}"
                ),
            )
        episode = _locate_episode(snapshot.definition, episode_id)
        if episode is None:
            raise ProjectDefinitionError(
                reason_code=ProjectDefinitionReason.RECORD_NOT_FOUND,
                operation="update_episode_script",
                project_id=project_id,
                message=f"Episode {episode_id} was not found",
            )

        episode.script_draft = str(script_text or "")
        episode.editorial_revision += 1
        if approve:
            episode.status = EpisodeEditorialStatus.APPROVED
            episode.approved_script = str(script_text or "")
        elif episode.status == EpisodeEditorialStatus.APPROVED:
            episode.status = EpisodeEditorialStatus.NEEDS_REVISION
        else:
            episode.status = EpisodeEditorialStatus.PENDING_APPROVAL
        if additional_notes:
            review_notes = dict(episode.continuity_notes.get("review_notes") or {})
            review_notes.update(additional_notes)
            episode.continuity_notes["review_notes"] = review_notes

        return self.replace(snapshot.definition, expected_version=snapshot.version)

    def approve_episodes(
        self,
        *,
        project_id: str,
        episode_ids: Sequence[str],
        expected_version: int,
    ) -> VersionedProjectDefinition:
        snapshot = self.get(project_id)
        if snapshot.version != int(expected_version):
            raise ProjectDefinitionError(
                reason_code=ProjectDefinitionReason.VERSION_CONFLICT,
                operation="approve_project_episodes",
                project_id=project_id,
                message=(
                    f"Project definition {project_id} version mismatch; "
                    f"expected {expected_version}, observed {snapshot.version}"
                ),
            )

        selected = {str(episode_id) for episode_id in episode_ids}
        matched = 0
        for episode in snapshot.definition.story_plan.episodes:
            if episode.episode_id not in selected:
                continue
            matched += 1
            if episode.status in {
                EpisodeEditorialStatus.DRAFT,
                EpisodeEditorialStatus.PENDING_APPROVAL,
                EpisodeEditorialStatus.NEEDS_REVISION,
            }:
                episode.status = EpisodeEditorialStatus.APPROVED
                episode.approved_script = episode.script_draft
                episode.editorial_revision += 1

        if matched != len(selected):
            missing = sorted(
                selected
                - {episode.episode_id for episode in snapshot.definition.story_plan.episodes}
            )
            raise ProjectDefinitionError(
                reason_code=ProjectDefinitionReason.RECORD_NOT_FOUND,
                operation="approve_project_episodes",
                project_id=project_id,
                message="Episodes were not found: " + ", ".join(missing),
            )
        return self.replace(snapshot.definition, expected_version=snapshot.version)


def _locate_episode(
    project_definition: ProjectDefinition,
    episode_id: str,
) -> Optional[EpisodePlan]:
    for episode in project_definition.story_plan.episodes:
        if episode.episode_id == episode_id:
            return episode
    return None
