"""Shared prompt-safety rewrite helpers (supplier-agnostic).

This module provides:
- is_sensitive_error: classify provider errors as policy violations via configurable markers
- rewrite_prompt_preserving_locks: perform a one-shot, minimal rewrite that preserves locked segments

Design notes:
- Tools call these helpers only when providers return explicit sensitive/violation errors.
- Do not use these helpers to proactively inject advisory text; sanitize/filters live elsewhere.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple
import inspect

from ...services.enhanced_ai_client import enhanced_ai_client, TaskType


def _normalize_markers(markers: Optional[Iterable[str]]) -> List[str]:
    base = [
        "SensitiveContent",
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


def is_sensitive_error(err: Any, markers: Optional[Iterable[str]] = None) -> bool:
    """Return True only if error indicates policy-sensitive content.

    Args:
        err: ToolError/Exception or string message
        markers: optional iterable of marker substrings for error_code/message
    """
    try:
        code = getattr(err, "error_code", None) or ""
        msg = str(err) if err is not None else ""
        low_code = str(code).lower()
        low_msg = msg.lower()
        for marker in _normalize_markers(markers):
            mlow = marker.lower()
            if mlow in low_code or mlow in low_msg:
                return True
        return False
    except Exception:
        return False


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

    try:
        # Allow both async and sync clients in tests
        maybe = enhanced_ai_client.generate_text(
            prompt=payload,
            task_type=TaskType.PROMPT_ENHANCEMENT,
            model=model,
            max_tokens=800,
            temperature=0.2,
        )
        resp = await maybe if inspect.isawaitable(maybe) else maybe
        rewritten = (resp or {}).get("content")
        telemetry["tokens"] = ((resp or {}).get("usage") or {}).get("total_tokens")
        if isinstance(rewritten, str) and rewritten.strip():
            text = rewritten.strip()
            # restore placeholders
            for token, seg in ph_map.items():
                text = text.replace(token, seg)
            telemetry["result"] = "success"
            return text, telemetry
        telemetry["result"] = "empty"
        return None, telemetry
    except Exception as exc:
        telemetry["result"] = "error"
        telemetry["error"] = str(exc)[:200]
        return None, telemetry
