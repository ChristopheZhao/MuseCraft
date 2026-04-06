"""记忆相关配置子包。

目前包含：
- memory_slots.yaml：长期 Shared slots 配置
"""
from __future__ import annotations

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

MEMORY_SLOTS_CONFIG = BASE_DIR / "memory_slots.yaml"

__all__ = ["MEMORY_SLOTS_CONFIG"]
