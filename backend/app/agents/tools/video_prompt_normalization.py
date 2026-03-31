"""Shared helpers for compacting video prompt surface text."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any, Iterable, List


_CLAUSE_SPLIT_RE = re.compile(r"[，,；;。.!?！？\n]+")
_COMPARE_NORMALIZE_RE = re.compile(r"[\s，,；;。.!?！？:：\-、]+")
_META_SUMMARY_MARKERS = (
    "营造",
    "增强",
    "暗示",
    "烘托",
    "突出",
    "埋下",
    "强化",
    "体现",
    "展现",
    "表现",
    "引入",
    "铺垫",
    "悬念",
    "期待",
)


def clip_text(value: Any, max_len: int) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    if max_len <= 3:
        return text[:max_len]
    return text[: max_len - 3] + "..."


def split_clauses(value: Any, *, max_clauses: int | None = None) -> List[str]:
    text = str(value or "").strip()
    if not text:
        return []
    parts = [
        part.strip(" ，,；;。.!?！？")
        for part in _CLAUSE_SPLIT_RE.split(text)
    ]
    clauses = [part for part in parts if part]
    if max_clauses is not None:
        return clauses[:max_clauses]
    return clauses


def normalize_compare_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return _COMPARE_NORMALIZE_RE.sub("", text)


def is_similar(a: Any, b: Any, *, threshold: float = 0.72) -> bool:
    left = normalize_compare_text(a)
    right = normalize_compare_text(b)
    if not left or not right:
        return False
    if left == right:
        return True
    if len(left) >= 4 and left in right:
        return True
    if len(right) >= 4 and right in left:
        return True
    return SequenceMatcher(a=left, b=right).ratio() >= threshold


def dedupe_clauses(
    clauses: Iterable[str],
    *,
    existing: Iterable[str] | None = None,
    threshold: float = 0.72,
) -> List[str]:
    result: List[str] = []
    prior = [str(item).strip() for item in (existing or []) if str(item).strip()]
    for clause in clauses:
        text = str(clause).strip()
        if not text:
            continue
        if any(is_similar(text, item, threshold=threshold) for item in prior):
            continue
        if any(is_similar(text, item, threshold=threshold) for item in result):
            continue
        result.append(text)
    return result


def is_meta_summary_clause(clause: Any) -> bool:
    text = str(clause or "").strip()
    if not text:
        return False
    normalized = normalize_compare_text(text)
    if any(text.startswith(marker) for marker in _META_SUMMARY_MARKERS):
        return True
    return len(normalized) <= 12 and any(marker in text for marker in _META_SUMMARY_MARKERS)


def compact_action_pair(
    phase: Any,
    observable: Any,
    *,
    phase_max_len: int = 64,
    extra_max_len: int = 64,
) -> tuple[str, str]:
    phase_clauses = dedupe_clauses(split_clauses(phase, max_clauses=2))
    extra_source = [
        clause
        for clause in split_clauses(observable, max_clauses=4)
        if not is_meta_summary_clause(clause)
    ]
    extra_clauses = dedupe_clauses(extra_source, existing=phase_clauses)

    phase_text = clip_text("，".join(phase_clauses), phase_max_len)
    extra_text = clip_text("，".join(extra_clauses[:2]), extra_max_len)

    if not phase_text and extra_text:
        return extra_text, ""
    if extra_text and is_similar(extra_text, phase_text):
        extra_text = ""
    return phase_text, extra_text


def compact_story_detail(
    candidate: Any,
    *,
    action_text: Any = "",
    max_len: int = 80,
    max_clauses: int = 2,
) -> str:
    clauses = split_clauses(candidate, max_clauses=4)
    if not clauses:
        return ""
    action_clauses = split_clauses(action_text, max_clauses=8)
    kept = dedupe_clauses(
        [
            clause
            for clause in clauses
            if not is_similar(clause, action_text)
            and not any(is_similar(clause, action_clause) for action_clause in action_clauses)
        ]
    )
    if not kept:
        return ""
    return clip_text("，".join(kept[:max_clauses]), max_len)


def compact_lock_text(
    value: Any,
    *,
    max_len: int = 64,
    max_clauses: int = 2,
    drop_meta: bool = False,
) -> str:
    clauses = split_clauses(value, max_clauses=max_clauses + 2)
    if drop_meta:
        clauses = [clause for clause in clauses if not is_meta_summary_clause(clause)]
    clauses = dedupe_clauses(clauses)
    if not clauses:
        return ""
    return clip_text("，".join(clauses[:max_clauses]), max_len)
