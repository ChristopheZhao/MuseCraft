"""Facts provider interface for tools.

定义工具如何访问事实数据（concept_plan、scenes 等）的接口。
使用通用方法设计，保持简洁灵活。
"""

from typing import Any, Dict, Optional, Protocol


class FactsProvider(Protocol):
    """事实提供者接口 - 工具通过此接口访问 WorkingMemory 的事实数据。

    设计说明：
    - 使用通用方法 get_fact()/get_scene()，而不是每种数据一个方法
    - 异步接口，保持一致性，未来可能有 I/O 操作
    - 异常上抛，由工具层决定如何处理
    """

    async def get_fact(self, workflow_state_id: str, key: str) -> Any:
        """获取工作流的特定事实数据。

        Args:
            workflow_state_id: 工作流 ID
            key: 事实键名，如 "concept_plan", "scene_scripts", "roles"

        Returns:
            事实数据，如果不存在返回 None

        Raises:
            Exception: 底层服务异常，由调用方处理
        """
        ...

    async def get_all_facts(self, workflow_state_id: str) -> Dict[str, Any]:
        """获取工作流的所有事实数据。

        Args:
            workflow_state_id: 工作流 ID

        Returns:
            所有事实数据的字典

        Raises:
            Exception: 底层服务异常，由调用方处理
        """
        ...

    async def get_scene(self, workflow_state_id: str, scene_number: int) -> Optional[Any]:
        """获取特定场景的快照。

        Args:
            workflow_state_id: 工作流 ID
            scene_number: 场景编号

        Returns:
            场景快照对象 (SceneSnapshot)，如果不存在返回 None

        Raises:
            Exception: 底层服务异常，由调用方处理
        """
        ...

    async def get_all_scenes(self, workflow_state_id: str) -> Dict[int, Any]:
        """获取所有场景快照。

        Args:
            workflow_state_id: 工作流 ID

        Returns:
            场景编号到快照的映射字典

        Raises:
            Exception: 底层服务异常，由调用方处理
        """
        ...

    async def get_scene_continuity_info(self, workflow_state_id: str, scene_number: int) -> Dict[str, Any]:
        """获取场景的连续性事实（若 Shared WM/Continuity Memory 中存在）。"""
        ...


from ....services.memory_provider import get_memory_services, MemoryServices


class DefaultFactsProvider:
    """默认事实提供者实现 - 使用 SharedWM。

    生产环境使用此实现，内部调用现有的全局服务。
    """

    def __init__(self, memory_services: Optional[MemoryServices] = None):
        # 延迟导入，避免循环依赖
        from ....agents.services.mas_shared_memory import get_shared_wm
        from ....agents.memory.short_term.workflow_facts import WorkflowFactStoreError
        from ....core.scene_continuity_memory import get_scene_continuity_memory

        services = memory_services or get_memory_services()
        self._shared_wm = get_shared_wm()
        self._continuity_memory = get_scene_continuity_memory()
        self._fact_store = services.fact_store
        self._store_error = WorkflowFactStoreError

    async def get_fact(self, workflow_state_id: str, key: str) -> Any:
        """从 SharedWM 获取特定事实。"""
        if self._fact_store is None:
            return None
        try:
            return self._fact_store.get(workflow_state_id, key, default=None)
        except self._store_error:
            return None

    async def get_all_facts(self, workflow_state_id: str) -> Dict[str, Any]:
        """从 SharedWM 获取所有事实。"""
        facts: Dict[str, Any] = {}
        if self._fact_store is None:
            return facts
        try:
            for key in self._fact_store.list_aliases().keys():
                try:
                    value = self._fact_store.get(workflow_state_id, key, default=None)
                except self._store_error:
                    value = None
                if value is not None:
                    facts[key] = value
        except self._store_error:
            return {}

        return facts

    async def get_scene(self, workflow_state_id: str, scene_number: int) -> Optional[Any]:
        """从 SharedWM 获取特定场景。"""
        view = self._shared_wm.get_task(workflow_state_id)
        if not view or not view.scenes:
            return None
        return view.scenes.get(scene_number)

    async def get_all_scenes(self, workflow_state_id: str) -> Dict[int, Any]:
        """从 SharedWM 获取所有场景。"""
        view = self._shared_wm.get_task(workflow_state_id)
        return view.scenes if view and view.scenes else {}

    async def get_scene_continuity_info(self, workflow_state_id: str, scene_number: int) -> Dict[str, Any]:
        """从 Shared WM / 连续性内存获取场景连续性事实。"""
        try:
            info = await self._continuity_memory.get_scene_continuity_info(scene_number)
        except Exception:
            info = {}
        return info if isinstance(info, dict) else {}
