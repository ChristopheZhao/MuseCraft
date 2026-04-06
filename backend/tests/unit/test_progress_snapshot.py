from __future__ import annotations

import asyncio
import json

from app.agents.utils.progress_snapshot import emit_progress_snapshot


class _LoggerCapture:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def info(self, message: str) -> None:
        self.lines.append(message)


class _SnapshotHarness:
    def __init__(self) -> None:
        self.workflow_state_id = "wf-progress-snapshot"
        self.agent_name = "image_generator"
        self.logger = _LoggerCapture()

    @emit_progress_snapshot
    async def reflect(self, action_result, current_state, task, iteration):
        return {
            "success": True,
            "reflection_summary": "generated one scene successfully",
        }


def test_emit_progress_snapshot_logs_round_local_digest_only():
    harness = _SnapshotHarness()

    asyncio.run(
        harness.reflect(
            {
                "executed_calls": [
                    {"success": True, "tool": "image_prompt_composer.generate"},
                    {"success": False, "tool": "image_prompt_composer.generate"},
                ],
                "processed": 2,
                "subtask_state": "partial",
            },
            {},
            None,
            3,
        )
    )

    assert len(harness.logger.lines) == 1
    message = harness.logger.lines[0]
    assert message.startswith("PROGRESS_SNAPSHOT ")
    payload = json.loads(message[len("PROGRESS_SNAPSHOT "):])
    assert payload["wf_id"] == "wf-progress-snapshot"
    assert payload["agent"] == "image_generator"
    assert payload["iteration"] == 3
    assert payload["action_result_summary"]["executed_call_count"] == 2
    assert payload["action_result_summary"]["successful_call_count"] == 1
    assert payload["action_result_summary"]["failed_call_count"] == 1
    assert payload["action_result_summary"]["processed"] == 2
    assert payload["action_result_summary"]["subtask_state"] == "partial"
    assert payload["reflection_summary"]["success"] is True
    assert payload["reflection_summary"]["reflection_summary"] == "generated one scene successfully"
    assert "totals" not in payload
    assert "agent_view" not in payload
