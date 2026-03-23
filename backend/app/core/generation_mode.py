"""Lightweight generation-mode resolution helpers."""

from __future__ import annotations

from typing import Optional

from .config import settings
from .constants import GenerationMode


def resolve_generation_mode(
    explicit_mode: Optional[str] = None,
    *,
    route_default: Optional[GenerationMode] = None,
) -> GenerationMode:
    """Resolve generation mode without importing orchestrator-heavy dispatch code."""

    if explicit_mode:
        mode_value = explicit_mode.strip().lower()
        if mode_value in GenerationMode._value2member_map_:
            return GenerationMode(mode_value)

    if route_default is not None:
        return route_default

    default_value = getattr(settings, "DEFAULT_GENERATION_MODE", GenerationMode.QUICK.value)
    default_value = str(default_value).lower()
    if default_value not in GenerationMode._value2member_map_:
        return GenerationMode.QUICK
    return GenerationMode(default_value)
