"""Consistency policy loader for episode-level orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

import yaml

from .config import settings


@dataclass
class MergePolicy:
    style_constraints: str = "memory_over_fc"
    character_constraints: str = "memory_over_fc"
    negative_constraints: str = "memory_over_fc"


@dataclass
class GuardPolicy:
    mode: str = "advisory"
    face_similarity_threshold: float = 0.7
    palette_distance_threshold: float = 0.2
    require_signature_props: bool = True
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PromptSafetyPolicy:
    enabled: bool = True
    level: str = "moderate"  # moderate | strict
    preserve_locked_sections: bool = True
    rewrite_model: str | None = None
    enable_rewrite_on_sensitive_error: bool = False
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConsistencyPolicy:
    merge_policy: MergePolicy = field(default_factory=MergePolicy)
    lock_sections: List[str] = field(default_factory=list)
    guard: GuardPolicy = field(default_factory=GuardPolicy)
    prompt_safety: PromptSafetyPolicy = field(default_factory=PromptSafetyPolicy)


def _resolve_policy_path() -> Path:
    path = getattr(settings, "CONSISTENCY_POLICY_PATH", "backend/config/consistency_policy.yaml")
    policy_path = Path(path)
    if not policy_path.is_absolute():
        base_dir = getattr(settings, "BASE_DIR", None)
        if base_dir:
            policy_path = Path(base_dir).joinpath(policy_path).resolve()
        else:
            policy_path = Path(__file__).resolve().parents[3].joinpath(policy_path).resolve()
    return policy_path


def _parse_merge_policy(data: Dict[str, Any]) -> MergePolicy:
    mp = data or {}
    return MergePolicy(
        style_constraints=str(mp.get("style_constraints", "memory_over_fc")),
        character_constraints=str(mp.get("character_constraints", "memory_over_fc")),
        negative_constraints=str(mp.get("negative_constraints", "memory_over_fc")),
    )


def _parse_guard(data: Dict[str, Any]) -> GuardPolicy:
    gd = data or {}
    return GuardPolicy(
        mode=str(gd.get("mode", "advisory")),
        face_similarity_threshold=float(gd.get("face_similarity_threshold", 0.7)),
        palette_distance_threshold=float(gd.get("palette_distance_threshold", 0.2)),
        require_signature_props=bool(gd.get("require_signature_props", True)),
        extra={k: v for k, v in gd.items() if k not in {
            "mode", "face_similarity_threshold", "palette_distance_threshold", "require_signature_props"
        }},
    )


def _parse_prompt_safety(data: Dict[str, Any]) -> PromptSafetyPolicy:
    ps = data or {}
    return PromptSafetyPolicy(
        enabled=bool(ps.get("enabled", True)),
        level=str(ps.get("level", "moderate")),
        preserve_locked_sections=bool(ps.get("preserve_locked_sections", True)),
        rewrite_model=ps.get("rewrite_model"),
        enable_rewrite_on_sensitive_error=bool(ps.get("enable_rewrite_on_sensitive_error", False)),
        extra={
            k: v
            for k, v in ps.items()
            if k not in {"enabled", "level", "preserve_locked_sections", "rewrite_model", "enable_rewrite_on_sensitive_error"}
        },
    )


@lru_cache(maxsize=1)
def get_consistency_policy() -> ConsistencyPolicy:
    policy_path = _resolve_policy_path()
    if not policy_path.exists():
        return ConsistencyPolicy()

    try:
        with policy_path.open("r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}
    except Exception:
        return ConsistencyPolicy()

    merge_policy = _parse_merge_policy(raw.get("merge_policy") or {})
    lock_sections = list(raw.get("lock_sections") or [])
    guard_policy = _parse_guard(raw.get("guard") or {})
    prompt_safety = _parse_prompt_safety(raw.get("prompt_safety") or {})

    return ConsistencyPolicy(
        merge_policy=merge_policy,
        lock_sections=lock_sections,
        guard=guard_policy,
        prompt_safety=prompt_safety,
    )


def reload_consistency_policy() -> None:
    """Clear cache so next call reloads from disk."""

    get_consistency_policy.cache_clear()
