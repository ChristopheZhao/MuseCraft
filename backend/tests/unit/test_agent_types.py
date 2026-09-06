"""Domain enum contract tests."""

import importlib

import pytest

from app.domain import AgentStatus, AgentType, ResourceType, SceneType, TaskType
import app.models as models_package
from app.models import Resource, Scene, Task


def test_agent_type_values_are_unique_and_normalized() -> None:
    values = [member.value for member in AgentType]

    assert len(values) == len(set(values))
    assert all(value == value.strip().lower() for value in values)
    assert AgentType.VIDEO_GENERATOR.value == "video_generator"
    assert AgentType.VOICE_SYNTHESIZER.value == "voice_synthesizer"


def test_agent_status_values_are_unique_and_normalized() -> None:
    values = [member.value for member in AgentStatus]

    assert len(values) == len(set(values))
    assert all(value == value.strip().lower() for value in values)


def test_orm_enum_columns_reference_domain_enum_types() -> None:
    assert Task.__table__.c.task_type.type.enum_class is TaskType
    assert Scene.__table__.c.scene_type.type.enum_class is SceneType
    assert Resource.__table__.c.resource_type.type.enum_class is ResourceType


def test_orm_package_does_not_reexport_domain_enums() -> None:
    assert not hasattr(models_package, "AgentType")
    assert not hasattr(models_package, "TaskType")
    assert not hasattr(models_package, "WorkflowSessionStatus")

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("app.models.agent")
