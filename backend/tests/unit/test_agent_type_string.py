import logging

import pytest

from app.models.agent import AgentType, AgentTypeString


def test_agent_type_string_normalizes_uppercase():
    field = AgentTypeString()
    result = field.process_result_value("VIDEO_GENERATOR", dialect=None)
    assert result is AgentType.VIDEO_GENERATOR


def test_agent_type_string_trims_and_lowercases():
    field = AgentTypeString()
    result = field.process_result_value("  Script_Writer  ", dialect=None)
    assert result is AgentType.SCRIPT_WRITER


def test_agent_type_string_passthrough_unknown(caplog: pytest.LogCaptureFixture):
    field = AgentTypeString()
    with caplog.at_level(logging.WARNING):
        result = field.process_result_value("UNKNOWN_AGENT", dialect=None)
    assert result == "UNKNOWN_AGENT"
    assert any("Unknown agent_type value" in record.message for record in caplog.records)
