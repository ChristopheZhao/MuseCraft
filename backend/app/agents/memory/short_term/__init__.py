"""短期记忆子包（Working Memory 层）

职责：
- 管理 per-workflow, per-agent 的 WorkingMemory 实例（短期工作区）
- 提供构建/同步 WM 的工具（assembler 等）

当前实现通过现有模块重导出：
- WorkingMemory: 来自 memory.short_term.working_memory
- WorkingMemoryService: 来自 memory.short_term.service
- WorkingMemoryAssembler: 来自 memory.short_term.assembler
"""
from __future__ import annotations

from .working_memory import WorkingMemory
from ..operators.video_scene import SceneSnapshot, SceneArtifact
from .service import WorkingMemoryService, MemoryNotInitializedError
from .assembler import WorkingMemoryAssembler
from .workflow_facts import WorkflowFactStore, WorkflowFactStoreError, load_fact_aliases
from ..storage.in_memory import ShortTermMemoryStore, InMemoryShortTermStore

__all__ = [
    "WorkingMemory",
    "SceneSnapshot",
    "SceneArtifact",
    "WorkingMemoryService",
    "WorkingMemoryAssembler",
    "MemoryNotInitializedError",
    "WorkflowFactStore",
    "WorkflowFactStoreError",
    "load_fact_aliases",
    "ShortTermMemoryStore",
    "InMemoryShortTermStore",
]
