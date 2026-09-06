import pytest

from app.core.story_plan import (
    CharacterProfile,
    EpisodeEditorialStatus,
    EpisodePlan,
    ProjectDefinition,
    StoryPlan,
)
from app.domain import (
    AgentExecutionResult,
    AgentTaskReference,
    EpisodeExecutionReadModel,
    EpisodeWorkflowExecutionReceipt,
    JsonObjectPayload,
    ProjectExecutionReadModel,
    ProjectOperationReadModel,
)
from app.services.episode_execution_coordinator import (
    EpisodeExecutionCoordinationError,
    EpisodeExecutionCoordinator,
)
from app.services.project_service import VersionedProjectDefinition


def _definition(*, approved: bool = True) -> tuple[ProjectDefinition, EpisodePlan]:
    story = StoryPlan(
        project_id="project-episode",
        user_prompt="Overall project brief",
        target_duration_seconds=60,
        aspect_ratio="16:9",
        global_theme="Courage",
        character_bible={"hero": CharacterProfile(canonical_id="hero", display_name="Hero")},
    )
    episode = EpisodePlan.create(0, "Episode 1", 60, summary="Mission begins")
    episode.script_draft = "Draft script"
    episode.approved_script = "Approved script" if approved else ""
    episode.status = EpisodeEditorialStatus.APPROVED if approved else EpisodeEditorialStatus.DRAFT
    story.add_episode(episode)
    return (
        ProjectDefinition(
            project_id=story.project_id,
            mode="project",
            story_plan=story,
            global_settings={"resolution": "1080p"},
            character_bible=story.character_bible,
        ),
        episode,
    )


class _Definitions:
    def __init__(self, definition):
        self.snapshot = VersionedProjectDefinition(definition=definition, version=3)

    def get(self, project_id):
        assert project_id == self.snapshot.definition.project_id
        return self.snapshot


class _ExecutionQuery:
    def __init__(self, definition, episode_status="idle"):
        self.definition = definition
        self.episode_status = episode_status

    def get(self, project_id):
        episode = self.definition.story_plan.episodes[0]
        return ProjectExecutionReadModel(
            project_id=project_id,
            mode="project",
            definition_version=3,
            definition=JsonObjectPayload.from_mapping(
                self.definition.to_dict(), field_path="test.definition"
            ),
            planning=ProjectOperationReadModel(status="completed"),
            character_references=ProjectOperationReadModel(status="completed"),
            episodes=(
                EpisodeExecutionReadModel(
                    episode_id=episode.episode_id,
                    status=self.episode_status,
                    approved_script=episode.approved_script,
                ),
            ),
        )


class _Executor:
    def __init__(self, output=None):
        self.calls = []
        self.output = (
            {"status": "completed", "workflow_state_id": "child-task"}
            if output is None
            else dict(output)
        )

    async def execute_episode(self, **kwargs):
        self.calls.append(kwargs)
        return EpisodeWorkflowExecutionReceipt(
            task_id="child-task",
            result=AgentExecutionResult(
                output_data=JsonObjectPayload.from_mapping(
                    self.output,
                    field_path="test.output",
                )
            ),
        )


@pytest.mark.asyncio
async def test_episode_coordinator_builds_identity_bound_payload_without_runtime_writes():
    definition, episode = _definition()
    executor = _Executor()
    coordinator = EpisodeExecutionCoordinator(
        project_definitions=_Definitions(definition),
        execution_query=_ExecutionQuery(definition),
        episode_executor=executor,
    )

    result = await coordinator.execute(
        parent_task=AgentTaskReference(task_id="parent-task", task_type="video_generation"),
        input_data={
            "project_id": definition.project_id,
            "project_definition_version": 3,
            "episode_ids": [episode.episode_id],
        },
    )

    payload = executor.calls[0]["input_data"].to_dict()
    assert payload["project_id"] == definition.project_id
    assert payload["episode_id"] == episode.episode_id
    assert payload["project_definition_version"] == 3
    assert payload["episode_editorial_revision"] == episode.editorial_revision
    assert payload["episode_context"]["approved_script"] == "Approved script"
    assert result["episodes"][0]["task_id"] == "child-task"


@pytest.mark.parametrize(
    "output",
    [
        {},
        {"status": ""},
        {"status": " completed "},
        {"status": "success"},
        {"status": 42},
    ],
)
@pytest.mark.asyncio
async def test_episode_coordinator_rejects_missing_or_noncanonical_child_status(output):
    definition, episode = _definition()
    executor = _Executor(output)
    coordinator = EpisodeExecutionCoordinator(
        project_definitions=_Definitions(definition),
        execution_query=_ExecutionQuery(definition),
        episode_executor=executor,
    )

    with pytest.raises(EpisodeExecutionCoordinationError) as exc_info:
        await coordinator.execute(
            parent_task=AgentTaskReference(
                task_id="parent-task",
                task_type="video_generation",
            ),
            input_data={
                "project_id": definition.project_id,
                "project_definition_version": 3,
                "episode_ids": [episode.episode_id],
            },
        )

    assert exc_info.value.reason_code == "child_execution_status_invalid"


@pytest.mark.asyncio
async def test_episode_coordinator_preserves_explicit_waiting_gate_child_status():
    definition, episode = _definition()
    executor = _Executor(
        {"status": "waiting_gate", "workflow_state_id": "child-task"}
    )
    coordinator = EpisodeExecutionCoordinator(
        project_definitions=_Definitions(definition),
        execution_query=_ExecutionQuery(definition),
        episode_executor=executor,
    )

    result = await coordinator.execute(
        parent_task=AgentTaskReference(
            task_id="parent-task",
            task_type="video_generation",
        ),
        input_data={
            "project_id": definition.project_id,
            "project_definition_version": 3,
            "episode_ids": [episode.episode_id],
        },
    )

    assert result["status"] == "completed"
    assert result["episodes"][0]["status"] == "waiting_gate"


@pytest.mark.asyncio
async def test_episode_coordinator_fails_explicitly_when_no_episode_is_eligible():
    definition, episode = _definition(approved=False)
    executor = _Executor()
    coordinator = EpisodeExecutionCoordinator(
        project_definitions=_Definitions(definition),
        execution_query=_ExecutionQuery(definition),
        episode_executor=executor,
    )

    with pytest.raises(EpisodeExecutionCoordinationError) as exc_info:
        await coordinator.execute(
            parent_task=AgentTaskReference(task_id="parent-task", task_type="video_generation"),
            input_data={
                "project_id": definition.project_id,
                "project_definition_version": 3,
                "episode_ids": [episode.episode_id],
            },
        )

    assert exc_info.value.reason_code == "no_eligible_episodes"
    assert executor.calls == []
