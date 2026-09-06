from app.agents.base import BaseAgent
from app.domain import AgentExecutionRequest, AgentType
from app.services.memory_provider import build_memory_services


class _ReportBoundaryAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            agent_type=AgentType.VIDEO_GENERATOR,
            agent_name="video_generator",
            tools=[],
            memory_services=build_memory_services(),
        )

    async def _execute_impl(self, request: AgentExecutionRequest):
        return {}


def test_base_agent_does_not_synthesize_orchestration_report():
    agent = _ReportBoundaryAgent()

    output = {"success": True, "subtask_state": "completed"}

    normalized = agent._normalize_execution_result(output)

    assert normalized.output_data.to_dict() == output
    assert normalized.orchestration_report is None


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

    normalized = agent._normalize_execution_result(output)

    assert normalized.output_data.to_dict() == {"success": True}
    assert normalized.require_orchestration_report().to_dict() == report
