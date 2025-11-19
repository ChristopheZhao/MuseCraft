"""Memory provider interface for tools.

定义工具如何访问记忆服务的接口，支持依赖注入和测试。
"""

from typing import Any, Dict, Optional, Protocol


class MemoryProvider(Protocol):
    """记忆提供者接口 - 工具通过此接口访问记忆数据。

    设计说明：
    - 提供场景参考、动作指导、连续性数据访问
    - 异步接口，涉及可能的 I/O 操作
    - 异常上抛，由工具层决定降级策略
    """

    async def retrieve_scene_references(
        self,
        workflow_state_id: str,
        scene_number: int,
        agent_name: str,
    ) -> Dict[str, Any]:
        """检索场景参考信息。

        Args:
            workflow_state_id: 工作流 ID
            scene_number: 场景编号
            agent_name: 代理名称

        Returns:
            场景参考数据字典

        Raises:
            Exception: 底层服务异常，由调用方处理
        """
        ...

    async def retrieve_motion_guidance(
        self,
        workflow_state_id: str,
        scene_number: int,
        agent_name: str,
    ) -> Dict[str, Any]:
        """检索动作指导信息。

        Args:
            workflow_state_id: 工作流 ID
            scene_number: 场景编号
            agent_name: 代理名称

        Returns:
            动作指导数据字典

        Raises:
            Exception: 底层服务异常，由调用方处理
        """
        ...

    async def store_scene_final_frame(
        self,
        scene_number: int,
        frame_url: str,
    ) -> None:
        """存储场景最后一帧。

        Args:
            scene_number: 场景编号
            frame_url: 帧图像 URL

        Raises:
            Exception: 底层服务异常，由调用方处理
        """
        ...

    async def retrieve_previous_frame_url(
        self,
        scene_number: int,
    ) -> Optional[str]:
        """检索前一个场景的最后一帧 URL。

        Args:
            scene_number: 当前场景编号

        Returns:
            前一个场景的尾帧 URL，如果不存在返回 None

        Raises:
            Exception: 底层服务异常，由调用方处理
        """
        ...

    async def get_scene_continuity_info(
        self,
        scene_number: int,
    ) -> Dict[str, Any]:
        """检索场景的完整连续性信息。"""
        ...


from ....services.memory_provider import get_memory_services, MemoryServices


class DefaultMemoryProvider:
    """默认记忆提供者实现 - 使用真实的全局记忆服务。

    生产环境使用此实现，内部调用现有的全局服务。
    异常不在此处捕获，上抛给工具层处理。
    """

    def __init__(self, memory_services: Optional[MemoryServices] = None):
        from ....core.scene_continuity_memory import get_scene_continuity_memory

        services = memory_services or get_memory_services()
        self._global_memory = services.global_service
        self._continuity_memory = get_scene_continuity_memory()

    async def retrieve_scene_references(
        self,
        workflow_state_id: str,
        scene_number: int,
        agent_name: str,
    ) -> Dict[str, Any]:
        """从全局记忆服务检索场景参考，异常上抛。"""
        result = await self._global_memory.retrieve_scene_references(
            workflow_state_id, scene_number, agent_name
        )
        return result if isinstance(result, dict) else {}

    async def retrieve_motion_guidance(
        self,
        workflow_state_id: str,
        scene_number: int,
        agent_name: str,
    ) -> Dict[str, Any]:
        """从全局记忆服务检索动作指导，异常上抛。"""
        result = await self._global_memory.retrieve_motion_guidance(
            workflow_state_id, scene_number, agent_name
        )
        return result if isinstance(result, dict) else {}

    async def store_scene_final_frame(
        self,
        scene_number: int,
        frame_url: str,
    ) -> None:
        await self._continuity_memory.store_scene_final_frame(scene_number, frame_url)

    async def retrieve_previous_frame_url(
        self,
        scene_number: int,
    ) -> Optional[str]:
        return await self._continuity_memory.get_previous_scene_final_frame(scene_number)

    async def get_scene_continuity_info(
        self,
        scene_number: int,
    ) -> Dict[str, Any]:
        info = await self._continuity_memory.get_scene_continuity_info(scene_number)
        return info if isinstance(info, dict) else {}
