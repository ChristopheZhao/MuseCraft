"""长期记忆管理入口。

当前重导出 MemoryManager，统一管理 long_term stores/retrievers，
用于情景记忆 / 语义记忆的存取，不直接管理 WorkingMemory。
"""
from __future__ import annotations

from .memory_manager import MemoryManager

__all__ = ["MemoryManager"]
