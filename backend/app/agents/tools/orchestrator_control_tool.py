"""
Orchestrator Control Tool - LLM-driven workflow step decisions

Provides lightweight actions for the orchestrator to decide the next move
without hardcoding if/else in the orchestrator code.
"""

from typing import Dict, Any, List

from .base_tool import AsyncTool, ToolMetadata, ToolType, ToolInput, ToolOutput, ToolValidationError


class OrchestratorControlTool(AsyncTool):
    """Lightweight control tool for orchestrator decisions"""

    @classmethod
    def get_metadata(cls) -> ToolMetadata:
        return ToolMetadata(
            name="orchestrator_control",
            version="1.0.0",
            description="Lightweight control tool to decide next orchestrator step",
            tool_type=ToolType.UTILITY,
            author="system",
            tags=["orchestrator", "control", "planning"],
            capabilities=["set_next_step", "repeat_step", "halt_workflow"],
        )

    def _initialize(self):
        pass

    def get_available_actions(self) -> List[str]:
        # Keep surface minimal to reduce model choice entropy
        return [
            "proceed_next",      # proceed to next step in workflow order
            "repeat_agent",      # repeat current agent once with a reason
            "halt_workflow",     # halt workflow with a reason
        ]

    def get_action_schema(self, action: str) -> Dict[str, Any]:
        if action == "proceed_next":
            return {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "Reason for proceeding"}
                }
            }
        if action == "repeat_agent":
            return {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "Reason for repeating current agent"}
                }
            }
        if action == "halt_workflow":
            return {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "Reason for halting the workflow"}
                }
            }
        return {"type": "object", "properties": {}}

    async def _execute_impl(self, tool_input: ToolInput) -> Dict[str, Any]:
        action = tool_input.action
        params = tool_input.parameters or {}

        if action not in self.get_available_actions():
            raise ToolValidationError(f"Unsupported action: {action}", self.metadata.name)

        result: Dict[str, Any] = {"decision": action}
        if isinstance(params, dict) and params.get("reason"):
            result["reason"] = params.get("reason")

        return result

