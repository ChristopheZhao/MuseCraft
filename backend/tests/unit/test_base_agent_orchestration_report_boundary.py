from app.agents.base import BaseAgent
from app.models import AgentType
from app.services.memory_provider import build_memory_services


class _ReportBoundaryAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            agent_type=AgentType.VIDEO_GENERATOR,
            agent_name="video_generator",
            tools=[],
            memory_services=build_memory_services(),
        )

    async def _execute_impl(self, task, input_data, db=None):  # type: ignore[override]
        return {}


def test_base_agent_does_not_synthesize_orchestration_report():
    agent = _ReportBoundaryAgent()

    output = {"success": True, "subtask_state": "completed"}

    normalized = agent._ensure_orchestration_report(output)

    assert normalized == output
    assert "orchestration_report" not in normalized


def test_base_agent_preserves_explicit_orchestration_report():
    agent = _ReportBoundaryAgent()
    report = {
        "status": "completed",
        "boundary_event": "scene_video_completed",
        "gate_triggers": [],
        "artifacts": [],
        "reflection": {
            "completion_state": "completed",
            "reported_gaps": [],
            "reported_hints": [],
        },
    }

    output = {"success": True, "orchestration_report": report}

    assert agent._ensure_orchestration_report(output)["orchestration_report"] == report
