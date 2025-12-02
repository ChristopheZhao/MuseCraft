from __future__ import annotations

"""WorkingMemoryService - 短期工作记忆管理服务

职责：
- 为每个 (workflow_state_id, agent_name) 管理一份 WorkingMemory 实例
- 提供受控写入接口（带审计日志）

注意：这是对旧 IterationMemoryService 的重命名与归位，
不再承载“迭代记忆”概念，仅代表短期 Working Memory 管理。
"""

import logging
import threading
from typing import Callable, Dict, Optional

from ..short_term.assembler import WorkingMemoryAssembler
from ..short_term.working_memory import WorkingMemory
from ..storage.in_memory import ShortTermMemoryStore, InMemoryShortTermStore


class MemoryNotInitializedError(RuntimeError):
    """Raised when requesting a WorkingMemory that has not been created yet."""


class MemoryAlreadyExistsError(RuntimeError):
    """Raised when attempting to create a WorkingMemory that already exists (strict mode)."""


class WorkingMemoryService:
    """Central service that manages per-agent WorkingMemory instances (short-term memory)."""

    def __init__(
        self,
        assembler: Optional[WorkingMemoryAssembler] = None,
        *,
        store_factory: Optional[callable[[], ShortTermMemoryStore]] = None,
    ) -> None:
        factory = store_factory or (lambda: InMemoryShortTermStore())
        self._assembler = assembler or WorkingMemoryAssembler(store_factory=factory)
        self._cache: Dict[tuple[str, str], WorkingMemory] = {}
        self._lock = threading.RLock()
        self._logger = logging.getLogger("working_memory.service")

    def create_or_get(
        self,
        workflow_state_id: str,
        scope: str,
        *,
        owner_agent: Optional[str] = None,
        strict: bool = False,
        context: Optional[Dict] = None,
        shared_view: Optional[WorkingMemory] = None,
    ) -> WorkingMemory:
        """Create WorkingMemory if absent, otherwise return existing instance.

        Args:
            workflow_state_id: workflow identifier.
            scope: WorkingMemory scope identifier.
            owner_agent: logical owner agent name (for context population).
            strict: when True, raise MemoryAlreadyExistsError if memory already exists.
        """
        key = (str(workflow_state_id), str(scope))
        with self._lock:
            existing = self._cache.get(key)
        if existing is not None:
            if strict:
                raise MemoryAlreadyExistsError(f"Working memory already exists: workflow={key[0]} scope={key[1]}")
            return existing

        wm = self._assembler.get_or_create(
            task_id=key[0],
            scope=key[1],
            shared_view=shared_view,
            owner_agent=owner_agent,
            context=context,
        )
        with self._lock:
            self._cache[key] = wm
        self._logger.info("WM_CREATE workflow=%s scope=%s size=%s", key[0], key[1], len(str(wm)))
        return wm

    def get(self, workflow_state_id: str, scope: str) -> WorkingMemory:
        """Return previously created WorkingMemory. Raises if not initialised."""
        key = (str(workflow_state_id), str(scope))
        with self._lock:
            wm = self._cache.get(key)
        if wm is None:
            raise MemoryNotInitializedError(f"Working memory not initialised: workflow={key[0]} scope={key[1]}")
        return wm

    def memory_write(
        self,
        workflow_state_id: str,
        scope: str,
        apply_patch: Callable[[WorkingMemory], None],
        *,
        expected_version: Optional[int] = None,
        operation: str = "write",
    ) -> None:
        """Apply a controlled mutation to WorkingMemory with auditing."""
        wm = self.get(workflow_state_id, scope)
        try:
            apply_patch(wm)
            self._logger.info(
                "WM_WRITE workflow=%s scope=%s op=%s expected_version=%s",
                workflow_state_id,
                scope,
                operation,
                expected_version,
            )
        except Exception as exc:
            self._logger.error(
                "WM_WRITE_FAILED workflow=%s scope=%s op=%s error=%s",
                workflow_state_id,
                scope,
                operation,
                exc,
                exc_info=True,
            )
            raise

    def delete(self, workflow_state_id: str, scope: str) -> None:
        """Delete cached WorkingMemory for a given agent/workflow."""
        key = (str(workflow_state_id), str(scope))
        with self._lock:
            wm = self._cache.pop(key, None)
        if wm is None:
            return
        self._logger.info("WM_DELETE workflow=%s scope=%s", key[0], key[1])

    def get_optional(self, scope: str, workflow_state_id: Optional[str]) -> Optional[WorkingMemory]:
        if not workflow_state_id:
            return None
        key = (str(workflow_state_id), str(scope))
        with self._lock:
            wm = self._cache.get(key)
        return wm

    def reset(self, scope: str, workflow_state_id: Optional[str]) -> None:
        if not workflow_state_id:
            return
        key = (str(workflow_state_id), str(scope))
        with self._lock:
            self._cache.pop(key, None)
        try:
            self._assembler.invalidate(key[0], key[1])
        except Exception:
            self._logger.debug("WorkingMemoryService.invalidate failed for %s/%s", key[0], key[1], exc_info=True)

    def reset_workflow(self, workflow_state_id: str) -> None:
        """Invalidate all agent memories for a workflow."""
        wf_id = str(workflow_state_id)
        keys_to_drop = []
        with self._lock:
            for key in list(self._cache.keys()):
                if key[0] == wf_id:
                    keys_to_drop.append(key)
                    self._cache.pop(key, None)
        self._logger.info("WM_CLEANUP workflow=%s scopes=%s", wf_id, len(keys_to_drop))

    # Backwards-compatible alias
    def cleanup_workflow(self, workflow_state_id: str) -> None:
        """Alias for reset_workflow for orchestrator compatibility."""
        self.reset_workflow(workflow_state_id)

__all__ = [
    "WorkingMemoryService",
    "MemoryNotInitializedError",
    "MemoryAlreadyExistsError",
]
