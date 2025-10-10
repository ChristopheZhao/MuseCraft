"""Core enums and constants shared across orchestration layers."""

from enum import Enum


class GenerationMode(str, Enum):
    """Supported orchestration modes."""

    QUICK = "quick"
    PROJECT = "project"


DEFAULT_GENERATION_MODE = GenerationMode.QUICK
