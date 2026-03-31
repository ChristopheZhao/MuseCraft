"""Shared prompt-safety rewrite helpers (supplier-agnostic).

This module provides:
- is_sensitive_error: classify provider errors as policy violations via configurable markers
- rewrite_prompt_preserving_locks: perform a one-shot, minimal rewrite that preserves locked segments

Design notes:
- Tools call these helpers only when providers return explicit sensitive/violation errors.
- Do not use these helpers to proactively inject advisory text; sanitize/filters live elsewhere.
"""

from __future__ import annotations

import inspect
import logging
from functools import lru_cache
from typing import Any, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger("prompt_safety")


def _normalize_markers(markers: Optional[Iterable[str]]) -> List[str]:
    base = [
        "SensitiveContent",
        "InputTextSensitiveContentDetected",
        "NSFW",
        "PolicyViolation",
        "OutputVideoSensitiveContentDetected",
    ]
    if not markers:
        return base
    try:
        custom = [str(m).strip() for m in markers if str(m).strip()]
    except Exception:
        custom = []
    # keep order: custom first to allow overrides, then base
    seen = set()
    ordered: List[str] = []
    for s in list(custom) + base:
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(s)
    return ordered


def _collect_error_fragments(err: Any) -> List[str]:
    fragments: List[str] = []
    try:
        code = getattr(err, "error_code", None)
        if code is not None:
            fragments.append(str(code))
    except Exception:
        pass
    try:
        details = getattr(err, "details", None)
        if isinstance(details, dict):
            for key in (
                "provider_error_code",
                "provider_error_message",
                "provider_raw_message",
                "provider_response_text",
            ):
                value = details.get(key)
                if value is not None:
                    fragments.append(str(value))
    except Exception:
        pass
    if err is not None:
        fragments.append(str(err))
    return [frag for frag in fragments if isinstance(frag, str) and frag.strip()]


def is_sensitive_error(err: Any, markers: Optional[Iterable[str]] = None) -> bool:
    """Return True only if error indicates policy-sensitive content.

    Args:
        err: ToolError/Exception or string message
        markers: optional iterable of marker substrings for error_code/message
    """
    try:
        fragments = [frag.lower() for frag in _collect_error_fragments(err)]
        for marker in _normalize_markers(markers):
            mlow = marker.lower()
            if any(mlow in fragment for fragment in fragments):
                return True
        return False
    except Exception:
        return False


def _model_prefers_project_text_client(model: Optional[str]) -> bool:
    model_name = str(model or "").strip().lower()
    return model_name.startswith(("glm-", "kimi-")) or "zhipu" in model_name


@lru_cache(maxsize=1)
def _get_enhanced_ai_client_objects():
    from ...services.enhanced_ai_client import enhanced_ai_client, TaskType

    return enhanced_ai_client, TaskType


def _enhanced_client_supports_prompt_rewrite() -> bool:
    try:
        enhanced_ai_client, task_type_enum = _get_enhanced_ai_client_objects()
        return any(
            task_type_enum.PROMPT_ENHANCEMENT in getattr(cfg, "capabilities", [])
            for cfg in getattr(enhanced_ai_client, "service_configs", {}).values()
        )
    except Exception:
        return False


@lru_cache(maxsize=1)
def _get_project_text_client():
    from ...services.ai_client import AIClient

    return AIClient()


async def _call_text_rewrite_backend(
    backend: str,
    payload: str,
    *,
    model: Optional[str],
) -> Dict[str, Any]:
    if backend == "enhanced_ai_client":
        enhanced_ai_client, task_type_enum = _get_enhanced_ai_client_objects()
        maybe = enhanced_ai_client.generate_text(
            prompt=payload,
            task_type=task_type_enum.PROMPT_ENHANCEMENT,
            model=model,
            max_tokens=800,
            temperature=0.2,
        )
        return await maybe if inspect.isawaitable(maybe) else maybe

    if backend == "project_ai_client":
        client = _get_project_text_client()
        maybe = client.generate_text(
            prompt=payload,
            model=model,
            max_tokens=800,
            temperature=0.2,
        )
        return await maybe if inspect.isawaitable(maybe) else maybe

    raise ValueError(f"Unsupported rewrite backend: {backend}")


async def rewrite_prompt_preserving_locks(
    prompt: str,
    locked_segments: Optional[Iterable[str]] = None,
    *,
    model: Optional[str] = None,
    language: str = "zh",
    metadata: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[str], Dict[str, Any]]:
    """One-shot minimal rewrite that preserves locked segments.

    - Replaces locked segments with placeholders
    - Asks a lightweight model to rewrite for policy compliance (PG-13 style)
    - Restores locked segments into rewritten text
    - Returns (rewritten_text_or_None, telemetry_dict)
    """
    telemetry: Dict[str, Any] = {
        "model": model,
        "locked_count": 0,
        "result": "error",
    }
    locked = [str(x).strip() for x in (locked_segments or []) if str(x).strip()]
    telemetry["locked_count"] = len(locked)

    # Build placeholder mapping
    ph_map: Dict[str, str] = {}
    prompt_for_llm = str(prompt or "")
    if locked:
        for i, seg in enumerate(locked):
            token = f"<<LOCKED_{i}>>"
            if seg in prompt_for_llm:
                prompt_for_llm = prompt_for_llm.replace(seg, token)
                ph_map[token] = seg

    # Compose instruction (no advisory text injection to final prompt)
    instruction = (
        "你是一名提示词合规优化助手。"
        "请在不改变下方锁定片段原文的前提下，对提示词进行最小改动以符合平台合规（PG-13）：避免露骨暴力/色情/仇恨等词汇。"
        "仅输出改写后的提示词文本，不要输出任何解释。"
    )
    locked_lines = "\n".join(f"- {seg}" for seg in locked) if locked else "(无)"
    payload = (
        f"{instruction}\n\n锁定片段：\n{locked_lines}\n\n原始提示词：\n{prompt_for_llm.strip()}\n"
    )

    backends: List[str] = []
    if _model_prefers_project_text_client(model):
        backends.append("project_ai_client")
    if _enhanced_client_supports_prompt_rewrite():
        backends.append("enhanced_ai_client")
    if "project_ai_client" not in backends:
        backends.append("project_ai_client")

    errors: List[str] = []
    for backend in backends:
        try:
            resp = await _call_text_rewrite_backend(backend, payload, model=model)
            rewritten = (resp or {}).get("content")
            telemetry["backend"] = backend
            telemetry["provider"] = (resp or {}).get("provider")
            telemetry["tokens"] = ((resp or {}).get("usage") or {}).get("total_tokens")
            telemetry["model"] = (resp or {}).get("model") or model
            if isinstance(rewritten, str) and rewritten.strip():
                text = rewritten.strip()
                for token, seg in ph_map.items():
                    text = text.replace(token, seg)
                telemetry["result"] = "success"
                return text, telemetry
            telemetry["result"] = "empty"
            telemetry["error"] = f"{backend}: empty response"
            return None, telemetry
        except Exception as exc:
            errors.append(f"{backend}: {str(exc)[:200]}")
            logger.warning("Prompt safety rewrite failed via %s: %s", backend, exc)

    telemetry["result"] = "error"
    telemetry["error"] = " | ".join(errors[:2]) if errors else "no rewrite backend available"
    return None, telemetry
