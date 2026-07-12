"""Agent type contract tests."""

from app.models.agent import AgentStatus, AgentType


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
