#!/usr/bin/env python3
"""Probe orchestrator candidate-selection and decomposition latency in isolation."""

from __future__ import annotations

import argparse
import asyncio
import json
import time
import uuid
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.agents.orchestrator import OrchestratorAgent
from app.agents.tools import register_default_tools


DEFAULT_PROMPT = "凡人修仙传预告\n\n生成一个凡人修仙传的预告动漫视频"


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Measure orchestrator candidate-selection and decomposition performance"
    )
    parser.add_argument(
        "--prompt",
        default=DEFAULT_PROMPT,
        help="User prompt passed into orchestrator planning",
    )
    parser.add_argument("--duration", type=int, default=45)
    parser.add_argument("--resolution", default="720p")
    parser.add_argument("--aspect-ratio", default="16:9")
    parser.add_argument(
        "--phase",
        choices=["selection", "decomposition", "both"],
        default="both",
        help="Which planning phase to execute",
    )
    parser.add_argument("--runs", type=int, default=1)
    return parser.parse_args(list(argv))


def _chars(value: Any) -> int:
    if isinstance(value, str):
        return len(value)
    try:
        return len(json.dumps(value, ensure_ascii=False))
    except Exception:
        return 0


def _workflow_data(prompt: str, duration: int, resolution: str, aspect_ratio: str) -> Dict[str, Any]:
    return {
        "user_prompt": prompt,
        "prompt": prompt,
        "duration": duration,
        "resolution": resolution,
        "target_resolution": resolution,
        "aspect_ratio": aspect_ratio,
        "voice_settings": None,
        "style_preference": None,
    }


def _llm_descriptor(llm: Any) -> Dict[str, Any]:
    service = getattr(llm, "_service", None)
    provider = None
    model = getattr(llm, "_model", None)
    try:
        if service is not None and hasattr(service, "get_provider_name"):
            provider = service.get_provider_name()
    except Exception:
        provider = None
    return {
        "provider": provider,
        "model": model,
    }


async def _run_once(args: argparse.Namespace) -> Dict[str, Any]:
    workflow_id = str(uuid.uuid4())
    register_default_tools()
    orchestrator = OrchestratorAgent()
    llm = orchestrator.get_llm("plan")
    llm_meta = _llm_descriptor(llm)

    workflow_data = _workflow_data(
        prompt=args.prompt,
        duration=args.duration,
        resolution=args.resolution,
        aspect_ratio=args.aspect_ratio,
    )
    audio_capability = orchestrator._get_video_audio_capability()
    audio_contract = orchestrator._orchestration_state.build_audio_contract(
        workflow_state_id=workflow_id,
        input_data=workflow_data,
    )
    workflow_data["audio_capability"] = dict(audio_capability)
    workflow_data["audio_contract"] = dict(audio_contract)

    captured_calls: List[Dict[str, Any]] = []
    current_phase = {"value": "unknown"}
    original_chat_completion = llm.chat_completion

    async def _wrapped_chat_completion(*, messages, **kwargs):
        started = time.perf_counter()
        system_chars = 0
        user_chars = 0
        for message in messages or []:
            if not isinstance(message, dict):
                continue
            if message.get("role") == "system":
                system_chars += _chars(message.get("content"))
            elif message.get("role") == "user":
                user_chars += _chars(message.get("content"))
        model = kwargs.get("model") or llm_meta.get("model")
        explicit_thinking = kwargs.get("thinking")
        request_timeout = kwargs.get("request_timeout")
        max_tokens = kwargs.get("max_tokens")
        response_format = kwargs.get("response_format")
        try:
            response = await original_chat_completion(messages=messages, **kwargs)
            elapsed = time.perf_counter() - started
            captured_calls.append(
                {
                    "phase": current_phase["value"],
                    "ok": True,
                    "elapsed_seconds": round(elapsed, 3),
                    "provider": llm_meta.get("provider"),
                    "model": model,
                    "explicit_thinking": explicit_thinking,
                    "request_timeout": request_timeout,
                    "max_tokens": max_tokens,
                    "response_format": response_format,
                    "messages_count": len(messages or []),
                    "system_chars": system_chars,
                    "user_chars": user_chars,
                    "content_chars": _chars(response.get("content") if isinstance(response, dict) else None),
                    "reasoning_chars": _chars(
                        response.get("reasoning_content") if isinstance(response, dict) else None
                    ),
                    "finish_reason": response.get("finish_reason") if isinstance(response, dict) else None,
                }
            )
            return response
        except Exception as exc:  # noqa: BLE001
            elapsed = time.perf_counter() - started
            captured_calls.append(
                {
                    "phase": current_phase["value"],
                    "ok": False,
                    "elapsed_seconds": round(elapsed, 3),
                    "provider": llm_meta.get("provider"),
                    "model": model,
                    "explicit_thinking": explicit_thinking,
                    "request_timeout": request_timeout,
                    "max_tokens": max_tokens,
                    "response_format": response_format,
                    "messages_count": len(messages or []),
                    "system_chars": system_chars,
                    "user_chars": user_chars,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )
            raise

    llm.chat_completion = _wrapped_chat_completion  # type: ignore[assignment]
    candidate_agents: Optional[List[Any]] = None
    selection_rationale: Optional[str] = None
    task_specs: Optional[Dict[str, Any]] = None
    conditional_task_specs: Optional[Dict[str, Any]] = None
    phase_error: Optional[Dict[str, Any]] = None

    try:
        if args.phase in {"selection", "both"}:
            current_phase["value"] = "candidate_selection"
            selected, rationale = await orchestrator._llm_select_candidate_agents(
                workflow_data=workflow_data,
                workflow_id=workflow_id,
            )
            candidate_agents = list(selected)
            selection_rationale = rationale

        if args.phase in {"decomposition", "both"}:
            if candidate_agents is None:
                candidate_agents = orchestrator._registered_agents()
            current_phase["value"] = "decomposition"
            specs, conditional_specs = await orchestrator._llm_decompose_tasks(
                workflow_data=workflow_data,
                workflow_id=workflow_id,
                candidate_agents=list(candidate_agents),
            )
            task_specs = {
                agent_type.value: dict(spec or {})
                for agent_type, spec in (specs or {}).items()
            }
            conditional_task_specs = {
                str(task_id): dict(spec or {})
                for task_id, spec in (conditional_specs or {}).items()
            }
    except Exception as exc:  # noqa: BLE001
        phase_error = {
            "phase": current_phase["value"],
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
    finally:
        llm.chat_completion = original_chat_completion  # type: ignore[assignment]

    return {
        "workflow_id": workflow_id,
        "phase": args.phase,
        "llm": llm_meta,
        "candidate_agents": [agent.value for agent in (candidate_agents or [])],
        "candidate_agents_count": len(candidate_agents or []),
        "selection_rationale": selection_rationale,
        "task_specs_count": len(task_specs or {}),
        "conditional_task_specs_count": len(conditional_task_specs or {}),
        "task_spec_keys": sorted(list((task_specs or {}).keys())),
        "conditional_task_keys": sorted(list((conditional_task_specs or {}).keys())),
        "calls": captured_calls,
        "error": phase_error,
    }


async def run_probe(args: argparse.Namespace) -> int:
    results: List[Dict[str, Any]] = []
    for idx in range(args.runs):
        result = await _run_once(args)
        result["run"] = idx + 1
        results.append(result)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    failures = [result for result in results if result.get("error")]
    summary = {
        "runs": len(results),
        "phase": args.phase,
        "failures": len(failures),
        "successful_runs": len(results) - len(failures),
        "calls_per_run": [len(result.get("calls") or []) for result in results],
    }
    print("--- summary ---")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if failures else 0


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv or [])
    return asyncio.run(run_probe(args))


if __name__ == "__main__":
    raise SystemExit(main())
