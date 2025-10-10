"""
Diagnostic script for ScriptWriterAgent to inspect tool-call sequence
and context payload without modifying business logic or tests.

Usage (run from backend directory):
  UV_CACHE_DIR=.uv_cache PYTHONPATH=. uv run python scripts/diagnose_scriptwriter.py

Optional flags:
  --no-mock-tools   Use real tool execution (may require environment setup)
  --verbose         Print parameter keys for each tool call
"""

from __future__ import annotations

import argparse
import asyncio
from types import SimpleNamespace
from typing import Any, Dict, List, Tuple


def build_default_inputs() -> Tuple[Dict[str, Any], Dict[str, Any]]:
    episode_context = {
        "episode_index": 1,
        "episode_count": 3,
        "sequence_index": 0,
        "title": "Episode 1",
        "summary": "赵子龙回马",
        "narrative_purpose": "Set up",
        "target_duration_seconds": 60,
        "approved_script": "00:00-00:10 战况紧急，赵子龙回马。",
    }
    project_context = {
        "project_brief": "长坂坡忠勇叙事",
        "global_theme": "loyalty",
    }
    return episode_context, project_context


async def run_diagnosis(use_mock_tools: bool, verbose: bool) -> None:
    from app.agents.script_writer import ScriptWriterAgent
    from app.core.workflow_state import WorkflowState, SceneData

    agent = object.__new__(ScriptWriterAgent)

    # Minimal logger to make internal warnings visible during diagnosis
    agent.logger = SimpleNamespace(info=print, warning=print, error=print)

    # Prepare a simple workflow state with a single scene (mirrors the unit test)
    wf = WorkflowState(
        task_id="wf1",
        user_prompt="Episode prompt",
        duration=60,
        aspect_ratio="16:9",
        resolution="720p",
    )
    wf.scenes = [
        SceneData(
            scene_number=1,
            visual_description="Scene",
            narrative_description="Battle",
            duration=10.0,
        )
    ]

    concept_plan = {"genre_and_theme": {"theme": "loyalty"}}
    episode_context, project_context = build_default_inputs()

    calls: List[Tuple[str, str, Dict[str, Any]]] = []

    if use_mock_tools:
        async def fake_use_tool(name: str, action: str, params: Dict[str, Any]):
            # Record shallow snapshot of params for inspection
            calls.append((name, action, {k: type(v).__name__ for k, v in params.items()}))
            return {
                "result": {
                    "success": True,
                    "script_text": "脚本段落",
                    "voice_over_text": "旁白",
                }
            }

        agent.use_tool = fake_use_tool  # type: ignore[attr-defined]

    try:
        result = await agent._batch_generate_scripts(  # type: ignore[attr-defined]
            scenes=wf.scenes,
            concept_plan=concept_plan,
            workflow_state=wf,
            task=None,
            episode_context=episode_context,
            project_context=project_context,
            approved_script_text=episode_context.get("approved_script", ""),
        )
    except Exception as exc:  # report fatal errors
        print("FATAL exception in _batch_generate_scripts:", exc)
        return

    # Print summary
    print("\n=== ScriptWriter Diagnosis ===")
    print("Tool calls count:", len(calls))
    if calls:
        for i, (name, action, params_types) in enumerate(calls, 1):
            if verbose:
                print(f"  #{i}: {name}.{action} params={sorted(params_types.keys())}")
            else:
                print(f"  #{i}: {name}.{action}")

    # Key result fields from agent output
    if isinstance(result, dict):
        failed = result.get("failed_voice_scenes")
        warnings = result.get("voice_over_warnings")
        print("Result keys:", sorted(list(result.keys())))
        print("failed_voice_scenes:", failed)
        print("voice_over_warnings:", warnings)
    else:
        print("Unexpected result type:", type(result))


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnose ScriptWriter tool calls")
    parser.add_argument(
        "--no-mock-tools",
        action="store_true",
        help="Use real tools (may require provider env setup)",
    )
    parser.add_argument("--verbose", action="store_true", help="Print parameter keys for each tool call")
    args = parser.parse_args()

    asyncio.run(run_diagnosis(use_mock_tools=not args.no_mock_tools, verbose=args.verbose))


if __name__ == "__main__":
    main()

