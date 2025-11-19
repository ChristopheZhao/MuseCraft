#!/usr/bin/env python3
"""Run ConceptPlannerAgent end-to-end with a single prompt.

Usage:
    uv run python backend/scripts/run_concept_agent.py \
        "写一部古风冒险短片" --duration 45 --aspect-ratio 16:9

The script instantiates `ConceptPlannerAgent`, executes one planning pass, and
prints the generated concept summary, intelligent style design block, and scene
titles. It removes `NEXT_PUBLIC_*` environment variables up front to avoid
front-end settings breaking backend config loading.

Notable flags:
    --style                 Inline style taxonomy summary string.
    --predefined-style      JSON string for predefined style profile.
    --mode                  `episode` (default) or `project`.
    --workflow-id           Tagged onto the agent iteration context for tracing.
"""

import argparse
import asyncio
import json
import os
from dataclasses import dataclass
from typing import Any, Dict

# Remove front-end injected env vars that break backend config loading
for key in list(os.environ):
    if key.startswith("NEXT_PUBLIC_"):
        os.environ.pop(key, None)

from app.agents.concept_planner import ConceptPlannerAgent


@dataclass
class StubTask:
    task_id: str
    status: str = "pending"

    def update_progress(self, *_args: Any, **_kwargs: Any) -> None:  # pragma: no cover - stub
        return None


class StubExecution:
    def __init__(self) -> None:
        self.output_data: Dict[str, Any] = {}
        self.tokens_used: int = 0
        self.api_calls_made: int = 0
        self.model_parameters: Dict[str, Any] = {}
        self.progress_percentage: int = 0
        self.current_substep: str | None = None

    def update_progress(self, percentage: int, substep: str | None = None) -> None:
        self.progress_percentage = percentage
        self.current_substep = substep

    def estimate_cost(self) -> None:  # pragma: no cover - stub
        return None


class StubDB:
    def add(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def commit(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def refresh(self, *_args: Any, **_kwargs: Any) -> None:
        return None


class StubWebSocket:
    async def broadcast_to_task(self, *_args: Any, **_kwargs: Any) -> None:
        return None


async def run_concept_agent(args: argparse.Namespace) -> Dict[str, Any]:
    agent = ConceptPlannerAgent()
    agent.websocket_manager = StubWebSocket()

    # Optional: skip creative guidance persistence if desired
    async def noop_store_guidance(*_args: Any, **_kwargs: Any) -> bool:
        return False

    agent.store_creative_guidance = noop_store_guidance  # type: ignore

    workflow_id = args.workflow_id or "debug-workflow"
    agent.iteration_context = {"workflow_state_id": workflow_id, "task_id": "debug-task"}

    task = StubTask(task_id="debug-task")
    execution = StubExecution()
    db = StubDB()

    input_payload: Dict[str, Any] = {
        "user_prompt": args.prompt,
        "duration": args.duration,
        "aspect_ratio": args.aspect_ratio,
        "workflow_state_id": workflow_id,
        "concept_mode": args.mode,
    }
    if args.style:
        input_payload["style_taxonomy_summary"] = args.style
    if args.predefined_style:
        input_payload["predefined_style_profile"] = json.loads(args.predefined_style)

    result = await agent._execute_impl(task, input_payload, execution, db)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ConceptPlannerAgent with a custom prompt")
    parser.add_argument("prompt", help="User prompt for concept planner")
    parser.add_argument("--duration", type=int, default=60, help="Target video duration in seconds")
    parser.add_argument("--aspect-ratio", default="16:9", help="Video aspect ratio")
    parser.add_argument("--mode", default="episode", choices=["episode", "project"], help="Concept mode")
    parser.add_argument("--workflow-id", default="wf-debug", help="Workflow state identifier")
    parser.add_argument("--style", help="Optional style taxonomy summary")
    parser.add_argument("--predefined-style", help="JSON string for predefined style profile")

    args = parser.parse_args()

    result = asyncio.run(run_concept_agent(args))

    print("\n=== Concept Plan Overview ===")
    print(result.get("video_concept", "<no overview>"))

    style = result.get("concept_plan", {}).get("intelligent_style_design")
    print("\n=== Intelligent Style Design ===")
    if style:
        print(json.dumps(style, ensure_ascii=False, indent=2))
    else:
        print("<style data missing>")

    print("\n=== Scenes ({}) ===".format(len(result.get("concept_plan", {}).get("scenes", []))))
    for scene in result.get("concept_plan", {}).get("scenes", []):
        print(f"- Scene {scene.get('scene_number')}: {scene.get('title', '')}")


if __name__ == "__main__":
    main()
