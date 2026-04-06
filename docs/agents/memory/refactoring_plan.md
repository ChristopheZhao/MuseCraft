# 记忆系统重构方案

## 执行原则

1. **小步迭代**：每个阶段独立可验证
2. **向后兼容**：保留临时兼容层，标记deprecation
3. **测试驱动**：每个阶段有对应的单元测试
4. **文档同步**：代码和文档同步更新

---

## Phase 1: 设计目标架构和接口定义

### 目标
建立清晰的架构蓝图和抽象接口，为后续重构提供指导。

### 1.1 定义目标架构

#### 分层结构
```
backend/app/agents/memory/
├── interfaces/              # 接口层（新增）
│   ├── __init__.py
│   ├── storage.py          # 存储接口定义
│   ├── memory_service.py   # 记忆服务接口
│   └── event.py            # 事件模型定义
│
├── storage/                # 存储实现层（新增）
│   ├── __init__.py
│   ├── base.py            # 基础存储抽象
│   ├── slot/              # Slot实现
│   │   ├── __init__.py
│   │   ├── backend.py     # SlotBackend实现
│   │   ├── registry.py    # SlotRegistry（内部）
│   │   └── schema.py      # Slot Schema
│   └── memory/            # 内存实现（用于短期记忆）
│       └── backend.py
│
├── services/              # 服务层（重构）
│   ├── __init__.py
│   ├── short_term.py     # 短期记忆服务
│   ├── long_term.py      # 长期记忆服务
│   ├── episodic.py       # 情景记忆服务（新增）
│   ├── coordinator.py    # 记忆协调器
│   └── factories.py      # 服务工厂（新增）
│
├── models/               # 数据模型（新增）
│   ├── __init__.py
│   ├── event.py         # Event事件模型
│   ├── state.py         # State-of-Truth模型
│   └── observation.py   # Observation模型
│
├── config/              # 配置（新增）
│   ├── __init__.py
│   └── memory_config.py
│
├── management.py        # 依赖装配器（重构）
└── utils.py            # 工具函数

# 删除的目录
# ├── operators/          # 删除，领域逻辑回归Agent
# ├── adapters/          # 删除，过度抽象
# ├── short_term/        # 合并到services/
# ├── long_term/         # 合并到services/
```

### 1.2 定义核心接口

#### storage.py - 存储接口
```python
# memory/interfaces/storage.py
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, TypeVar

T = TypeVar('T')

class MemoryBackend(ABC):
    """记忆存储的抽象接口"""

    @abstractmethod
    async def read(self, key: str) -> Optional[Any]:
        """读取单个值"""
        pass

    @abstractmethod
    async def write(self, key: str, value: Any, **metadata) -> None:
        """写入值，metadata可包含scope、ttl等"""
        pass

    @abstractmethod
    async def query(self, filters: Dict[str, Any]) -> List[Any]:
        """根据过滤条件查询"""
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """删除值"""
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """检查key是否存在"""
        pass
```

#### memory_service.py - 服务接口
```python
# memory/interfaces/memory_service.py
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from .event import Event
from .state import StateOfTruth

class ShortTermMemory(ABC):
    """短期记忆服务接口"""

    @abstractmethod
    async def get_state(self) -> StateOfTruth:
        """获取当前SoT"""
        pass

    @abstractmethod
    async def update_state(self, updates: Dict[str, Any]) -> None:
        """更新SoT"""
        pass

    @abstractmethod
    async def append_event(self, event: Event) -> None:
        """追加事件"""
        pass

    @abstractmethod
    async def get_recent_events(self, k: int = 5) -> List[Event]:
        """获取最近k个事件"""
        pass

class LongTermMemory(ABC):
    """长期记忆服务接口"""

    @abstractmethod
    async def store_fact(self, key: str, value: Any, **metadata) -> None:
        """存储长期事实"""
        pass

    @abstractmethod
    async def retrieve_fact(self, key: str) -> Optional[Any]:
        """检索事实"""
        pass

    @abstractmethod
    async def query_facts(self, filters: Dict) -> List[Any]:
        """查询事实"""
        pass

class EpisodicMemory(ABC):
    """情景记忆服务接口"""

    @abstractmethod
    async def record_step(
        self,
        iteration: int,
        thought: str,
        action: Dict,
        observation: Dict,
        **metadata
    ) -> None:
        """记录一个完整步骤"""
        pass

    @abstractmethod
    async def get_trajectory(
        self,
        workflow_id: str,
        start: int = 0,
        end: Optional[int] = None
    ) -> List[Dict]:
        """获取轨迹"""
        pass
```

#### event.py - 事件模型
```python
# memory/interfaces/event.py
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from datetime import datetime

@dataclass
class Event:
    """中立的事实事件"""
    event_type: str              # 事件类型：artifact_created, task_completed等
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())
    entity_id: Optional[str] = None  # 实体ID（如scene_id, task_id）
    artifact_refs: Dict[str, str] = field(default_factory=dict)  # 产物引用
    metadata: Dict[str, Any] = field(default_factory=dict)  # 其他元数据

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "entity_id": self.entity_id,
            "artifact_refs": self.artifact_refs,
            "metadata": self.metadata
        }
```

### 1.3 输出物

- [ ] `memory/interfaces/storage.py` - 存储接口
- [ ] `memory/interfaces/memory_service.py` - 服务接口
- [ ] `memory/interfaces/event.py` - 事件模型
- [ ] `memory/models/state.py` - SoT模型
- [ ] `memory/models/observation.py` - Observation模型
- [ ] `docs/agents/memory/architecture_v2.md` - 架构文档

### 1.4 验证标准

- [ ] 接口定义清晰，无循环依赖
- [ ] 架构文档审核通过
- [ ] 与现有AGENTS.md和agent_memory_design_practise.md一致

---

## Phase 2: 重构存储层（接口与实现分离）

### 目标
将Slot等存储实现与服务层解耦，建立可替换的存储backend。

### 2.1 创建存储层结构

#### 目录结构
```
memory/storage/
├── __init__.py
├── base.py              # 基础存储抽象
├── slot/
│   ├── __init__.py
│   ├── backend.py      # SlotBackend实现MemoryBackend
│   ├── registry.py     # SlotRegistry（内部实现）
│   └── schema.py       # Slot相关数据结构
└── memory/
    ├── __init__.py
    └── backend.py      # InMemoryBackend（用于短期记忆）
```

### 2.2 实现SlotBackend

```python
# memory/storage/slot/backend.py
from typing import Any, Dict, List, Optional
from ...interfaces.storage import MemoryBackend
from .registry import SlotRegistry

class SlotBackend(MemoryBackend):
    """基于Slot的存储实现"""

    def __init__(self, registry: SlotRegistry):
        self._registry = registry

    async def read(self, key: str) -> Optional[Any]:
        return self._registry.read_slot(key)

    async def write(self, key: str, value: Any, **metadata) -> None:
        scope = metadata.get("scope", "workflow")
        ttl = metadata.get("ttl")
        self._registry.write_slot(key, value, scope=scope, ttl=ttl)

    async def query(self, filters: Dict[str, Any]) -> List[Any]:
        return self._registry.query_slots(filters)

    async def delete(self, key: str) -> bool:
        return self._registry.delete_slot(key)

    async def exists(self, key: str) -> bool:
        return self._registry.exists_slot(key)
```

### 2.3 迁移现有Slot实现

#### 步骤
1. **移动文件**
   ```bash
   # 从 long_term/semantic/ 移动到 storage/slot/
   mv memory/long_term/semantic/slots.py memory/storage/slot/registry.py
   mv memory/long_term/semantic/shared_manager.py memory/storage/slot/manager.py
   ```

2. **调整导入**
   - 所有`from ..long_term.semantic.slots import`改为`from ..storage.slot.registry import`
   - 标记旧路径为deprecated

3. **创建兼容层**（临时）
   ```python
   # memory/long_term/semantic/slots.py (deprecated)
   import warnings
   from ...storage.slot.registry import SlotRegistry

   warnings.warn(
       "Importing from memory.long_term.semantic.slots is deprecated. "
       "Use memory.storage.slot.registry instead.",
       DeprecationWarning,
       stacklevel=2
   )

   __all__ = ['SlotRegistry']
   ```

### 2.4 实现InMemoryBackend

```python
# memory/storage/memory/backend.py
from typing import Any, Dict, List, Optional
from collections import defaultdict
from ...interfaces.storage import MemoryBackend

class InMemoryBackend(MemoryBackend):
    """内存存储实现（用于短期记忆）"""

    def __init__(self):
        self._data: Dict[str, Any] = {}

    async def read(self, key: str) -> Optional[Any]:
        return self._data.get(key)

    async def write(self, key: str, value: Any, **metadata) -> None:
        self._data[key] = value

    async def query(self, filters: Dict[str, Any]) -> List[Any]:
        # 简单实现，可以后续优化
        results = []
        for key, value in self._data.items():
            if self._matches_filters(value, filters):
                results.append(value)
        return results

    async def delete(self, key: str) -> bool:
        if key in self._data:
            del self._data[key]
            return True
        return False

    async def exists(self, key: str) -> bool:
        return key in self._data

    def _matches_filters(self, value: Any, filters: Dict) -> bool:
        if not isinstance(value, dict):
            return False
        for k, v in filters.items():
            if value.get(k) != v:
                return False
        return True
```

### 2.5 输出物

- [ ] `memory/storage/slot/backend.py` - Slot Backend实现
- [ ] `memory/storage/memory/backend.py` - 内存Backend实现
- [ ] 迁移测试：`tests/unit/test_slot_backend.py`
- [ ] 兼容层和deprecation警告

### 2.6 验证标准

- [ ] SlotBackend通过所有原有slot测试
- [ ] InMemoryBackend单元测试通过
- [ ] 旧代码通过兼容层仍能运行（带警告）
- [ ] 无新增的循环依赖

---

## Phase 3: 重构服务层（清理Working Memory）

### 目标
简化WorkingMemory，移除暗示性字段和领域特定逻辑。

### 3.1 重新设计WorkingMemory

#### 核心原则
- **只存事实**：不包含prepared_assets、ready_xxx等暗示性字段
- **领域中立**：不预设scene等领域概念
- **依赖抽象**：使用MemoryBackend接口

#### 新的WorkingMemory设计

```python
# memory/services/short_term.py
from typing import Any, Dict, List
from collections import deque
from ..interfaces.storage import MemoryBackend
from ..interfaces.memory_service import ShortTermMemory
from ..models.event import Event
from ..models.state import StateOfTruth

class WorkingMemoryService(ShortTermMemory):
    """短期记忆服务（领域中立）"""

    def __init__(
        self,
        workflow_id: str,
        backend: MemoryBackend,
        max_events: int = 100
    ):
        self.workflow_id = workflow_id
        self.backend = backend
        self._events: deque[Event] = deque(maxlen=max_events)
        self._sot: StateOfTruth = StateOfTruth()

    async def get_state(self) -> StateOfTruth:
        """获取当前状态快照"""
        return self._sot

    async def update_state(self, updates: Dict[str, Any]) -> None:
        """更新状态（通用键值更新）"""
        for key, value in updates.items():
            self._sot.set(key, value)

        # 可选：持久化到backend
        await self.backend.write(
            f"sot:{self.workflow_id}",
            self._sot.to_dict()
        )

    async def append_event(self, event: Event) -> None:
        """追加事件"""
        self._events.append(event)

        # 可选：持久化
        await self.backend.write(
            f"event:{self.workflow_id}:{event.timestamp}",
            event.to_dict()
        )

    async def get_recent_events(self, k: int = 5) -> List[Event]:
        """获取最近k个事件"""
        return list(self._events)[-k:]
```

#### StateOfTruth模型

```python
# memory/models/state.py
from typing import Any, Dict

class StateOfTruth:
    """状态事实（领域中立的键值存储）"""

    def __init__(self):
        self._data: Dict[str, Any] = {}

    def set(self, key: str, value: Any) -> None:
        """设置状态"""
        self._data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """获取状态"""
        return self._data.get(key, default)

    def to_dict(self) -> Dict[str, Any]:
        """导出为字典"""
        return self._data.copy()

    def from_dict(self, data: Dict[str, Any]) -> None:
        """从字典加载"""
        self._data = data.copy()
```

### 3.2 迁移策略

#### 对于现有的场景相关逻辑

**选项A：放入Agent内部**（推荐）
```python
# agents/video_generator.py
class VideoGeneratorAgent:
    def __init__(self, wm: WorkingMemoryService):
        self.wm = wm
        self.scene_manager = SceneManager(wm)  # 领域逻辑管理器

    async def _observe(self, action_result):
        # 使用scene_manager处理场景逻辑
        completed = self.scene_manager.extract_completed_scenes(action_result)

        # 更新WM的通用状态
        await self.wm.update_state({
            "completed_count": len(completed),
        })

        # 追加事件
        for scene_id in completed:
            await self.wm.append_event(Event(
                event_type="scene_completed",
                entity_id=str(scene_id),
                artifact_refs={"video_url": "..."}
            ))
```

**选项B：放入shared utils**（如果多Agent复用）
```python
# agents/shared/video_utils.py
class SceneManager:
    """视频场景管理器（领域逻辑）"""

    def __init__(self, wm: WorkingMemoryService):
        self.wm = wm

    async def get_completed_scenes(self) -> List[int]:
        """从WM事件中提取已完成场景"""
        events = await self.wm.get_recent_events(k=100)
        completed = [
            int(e.entity_id)
            for e in events
            if e.event_type == "scene_completed" and e.entity_id
        ]
        return sorted(set(completed))
```

### 3.3 删除的字段和逻辑

从WorkingMemory中删除：
- ❌ `prepared_assets: Dict[int, Dict]` - 暗示性字段
- ❌ `ready_scenes: List[int]` - 暗示性字段
- ❌ `depends_on_scene` - 领域特定逻辑
- ❌ `mark_completed()` - 领域特定方法
- ❌ `get_ready_scenes()` - 领域特定方法

保留为通用接口：
- ✅ `update_state(updates)` - 通用状态更新
- ✅ `append_event(event)` - 通用事件追加
- ✅ `get_state()` - 获取SoT
- ✅ `get_recent_events(k)` - 获取最近事件

### 3.4 输出物

- [ ] `memory/services/short_term.py` - 新的WorkingMemoryService
- [ ] `memory/models/state.py` - StateOfTruth模型
- [ ] `agents/shared/video_utils.py` - 场景管理器（如果需要）
- [ ] 更新所有Agent使用WorkingMemoryService
- [ ] 迁移测试

### 3.5 验证标准

- [ ] WorkingMemoryService不包含领域特定逻辑
- [ ] 所有暗示性字段已移除
- [ ] Agent测试通过（使用新的WM接口）
- [ ] 领域逻辑在Agent层或shared utils中

---

## Phase 4: 重构ReAct循环（OBS与State分离）

### 目标
正确实现ReAct的OBSERVE阶段，区分observation（本轮事件）和state（累积状态）。

### 4.1 重新定义Observation

```python
# memory/models/observation.py
from dataclasses import dataclass, field
from typing import Any, Dict, List

@dataclass
class Observation:
    """本轮行动的观察结果（不是整个状态）"""
    iteration: int
    action_summary: str          # 本轮做了什么
    tool_results: List[Dict]     # 工具执行结果
    state_delta: Dict[str, Any]  # 本轮引起的状态变化
    success_count: int = 0
    fail_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "iteration": self.iteration,
            "action_summary": self.action_summary,
            "tool_results": self.tool_results,
            "state_delta": self.state_delta,
            "success_count": self.success_count,
            "fail_count": self.fail_count,
            "metadata": self.metadata
        }
```

### 4.2 重构ReActAgent的OBSERVE阶段

```python
# agents/react_agent.py
class ReActAgent(BaseAgent):

    async def _execute_impl(self, task, input_data, execution, db):
        """ReAct循环"""

        last_observation: Optional[Observation] = None

        for iteration in range(self.max_iterations):
            # === OBSERVE ===
            # 构建当前观察（基于上一轮结果）
            if last_observation:
                # 将observation写入WM
                await self._record_observation(last_observation)

            # === THINK & PLAN ===
            # 构建上下文：SoT + 最近事件 + 本轮observation
            context = await self._build_context(last_observation)
            action_plan = await self._think_and_plan(context)

            # === ACT ===
            action_result = await self._execute_action(action_plan)

            # === 生成本轮Observation ===
            last_observation = self._extract_observation(
                iteration=iteration,
                action_plan=action_plan,
                action_result=action_result
            )

            # === REFLECT ===
            reflection = await self._reflect_on_results(last_observation)
            if reflection.get("should_stop"):
                break

        return final_result

    def _extract_observation(
        self,
        iteration: int,
        action_plan: Dict,
        action_result: Dict
    ) -> Observation:
        """从action结果提取observation（不是读WM）"""
        tool_results = action_result.get("executed_calls", [])

        # 统计本轮成功/失败
        success_count = sum(1 for r in tool_results if r.get("success"))
        fail_count = len(tool_results) - success_count

        # 提取状态变化（delta）
        state_delta = self._compute_state_delta(tool_results)

        return Observation(
            iteration=iteration,
            action_summary=f"Executed {len(tool_results)} tools",
            tool_results=tool_results,
            state_delta=state_delta,
            success_count=success_count,
            fail_count=fail_count
        )

    async def _record_observation(self, obs: Observation) -> None:
        """将observation记录到WM"""
        # 更新SoT
        await self.wm.update_state(obs.state_delta)

        # 追加事件
        for tool_result in obs.tool_results:
            event = Event(
                event_type=tool_result.get("tool_name"),
                entity_id=tool_result.get("entity_id"),
                metadata={
                    "success": tool_result.get("success"),
                    "error": tool_result.get("error")
                }
            )
            await self.wm.append_event(event)

    async def _build_context(
        self,
        last_observation: Optional[Observation]
    ) -> Dict:
        """构建THINK阶段的上下文"""
        # 从WM读取SoT和历史
        sot = await self.wm.get_state()
        recent_events = await self.wm.get_recent_events(k=5)

        context = {
            "sot": sot.to_dict(),  # 全局状态统计
            "recent_history": [e.to_dict() for e in recent_events],
        }

        # 添加本轮observation
        if last_observation:
            context["last_observation"] = last_observation.to_dict()

        return context
```

### 4.3 删除错误的实现

删除：
- ❌ `build_observation_from_wm()` - 这个函数混淆了observation和state
- ❌ 在_observe中直接读取WM的全量状态作为observation

### 4.4 输出物

- [ ] `memory/models/observation.py` - Observation模型
- [ ] 更新`react_agent.py`的OBSERVE阶段
- [ ] 更新所有ReAct子类Agent
- [ ] 删除`obs_builder.py`中的错误实现
- [ ] 更新相关测试

### 4.5 验证标准

- [ ] Observation只包含本轮action结果
- [ ] State通过WM独立维护
- [ ] Context = SoT + 历史事件 + 本轮observation
- [ ] 所有ReAct Agent测试通过

---

## Phase 5: 实现情景记忆（Episodic Memory）

### 目标
建立长期的完整轨迹记录，用于审计、微调和经验复用。

### 5.1 设计EpisodicMemory服务

```python
# memory/services/episodic.py
from typing import Any, Dict, List, Optional
from ..interfaces.memory_service import EpisodicMemory
from ..interfaces.storage import MemoryBackend

class EpisodicMemoryService(EpisodicMemory):
    """情景记忆服务（完整轨迹持久化）"""

    def __init__(self, backend: MemoryBackend):
        self.backend = backend

    async def record_step(
        self,
        iteration: int,
        thought: str,
        action: Dict,
        observation: Dict,
        **metadata
    ) -> None:
        """记录一个完整的ReAct步骤"""
        workflow_id = metadata.get("workflow_id")
        agent_name = metadata.get("agent_name")

        step_record = {
            "iteration": iteration,
            "thought": thought,
            "action": action,
            "observation": observation,
            "timestamp": metadata.get("timestamp"),
            "agent": agent_name,
            "workflow_id": workflow_id
        }

        # 持久化到backend
        key = f"episodic:{workflow_id}:{agent_name}:{iteration}"
        await self.backend.write(key, step_record, scope="project")

    async def get_trajectory(
        self,
        workflow_id: str,
        start: int = 0,
        end: Optional[int] = None
    ) -> List[Dict]:
        """获取完整轨迹"""
        filters = {
            "workflow_id": workflow_id,
            "iteration_gte": start
        }
        if end is not None:
            filters["iteration_lt"] = end

        trajectory = await self.backend.query(filters)
        return sorted(trajectory, key=lambda x: x["iteration"])
```

### 5.2 在ReAct循环中记录

```python
# agents/react_agent.py
class ReActAgent(BaseAgent):
    def __init__(self, ..., episodic: Optional[EpisodicMemoryService] = None):
        super().__init__(...)
        self.episodic = episodic

    async def _execute_impl(self, task, input_data, execution, db):
        for iteration in range(self.max_iterations):
            # OBSERVE, THINK, PLAN, ACT...

            # === 记录到情景记忆 ===
            if self.episodic:
                await self.episodic.record_step(
                    iteration=iteration,
                    thought=action_plan.get("reasoning", ""),
                    action=action_plan,
                    observation=last_observation.to_dict(),
                    workflow_id=task.workflow_state_id,
                    agent_name=self.agent_name,
                    timestamp=time.time()
                )
```

### 5.3 配置Episodic Backend

```yaml
# config/memory.yaml
episodic:
  backend:
    type: slot
    storage_path: ./data/episodic
    scope: project  # 持久化级别
```

### 5.4 输出物

- [ ] `memory/services/episodic.py` - 情景记忆服务
- [ ] 在ReActAgent中集成记录
- [ ] 配置文件支持
- [ ] 查询和重放工具
- [ ] 测试

### 5.5 验证标准

- [ ] 每个ReAct步骤都被记录
- [ ] 可以查询完整轨迹
- [ ] 数据格式适合微调使用
- [ ] 不影响主流程性能

---

## Phase 6: 更新Management和依赖注入

### 目标
完善依赖装配，移除全局单例，实现完全的依赖注入。

### 6.1 重构MemoryManagement

```python
# memory/management.py
from typing import Dict, Optional
from .config.memory_config import MemoryConfig
from .services.factories import (
    create_memory_backend,
    create_short_term_service,
    create_long_term_service,
    create_episodic_service
)
from .services.coordinator import MemoryCoordinator

class MemoryManagement:
    """记忆系统依赖装配器"""

    def __init__(self, config: MemoryConfig):
        self.config = config

        # 创建服务（不暴露backend细节）
        self.short_term = create_short_term_service(config.short_term)
        self.long_term = create_long_term_service(config.long_term)
        self.episodic = create_episodic_service(config.episodic)

        # 创建协调器
        self.coordinator = MemoryCoordinator(
            short_term=self.short_term,
            long_term=self.long_term,
            episodic=self.episodic
        )

    # 只暴露服务接口
    def get_coordinator(self) -> MemoryCoordinator:
        return self.coordinator
```

### 6.2 工厂函数

```python
# memory/services/factories.py
from ..config.memory_config import StorageConfig
from ..interfaces.storage import MemoryBackend
from ..storage.slot.backend import SlotBackend
from ..storage.memory.backend import InMemoryBackend
from .short_term import WorkingMemoryService
from .long_term import LongTermMemoryService
from .episodic import EpisodicMemoryService

def create_memory_backend(config: StorageConfig) -> MemoryBackend:
    """根据配置创建backend"""
    if config.type == "slot":
        from ..storage.slot.registry import SlotRegistry
        registry = SlotRegistry(storage_path=config.storage_path)
        return SlotBackend(registry)

    elif config.type == "memory":
        return InMemoryBackend()

    # 未来可以添加redis、vector等
    else:
        raise ValueError(f"Unknown backend type: {config.type}")

def create_short_term_service(config: Dict) -> WorkingMemoryService:
    """创建短期记忆服务"""
    backend = create_memory_backend(config.get("backend", {}))
    return WorkingMemoryService(
        workflow_id=config.get("workflow_id", "default"),
        backend=backend,
        max_events=config.get("max_events", 100)
    )
```

### 6.3 删除全局单例

删除：
```python
# ❌ 删除这种代码
global_memory_service = create_global_memory_service()
```

改为：
```python
# ✅ 在启动时创建，通过参数传递
def create_app():
    memory_config = load_memory_config()
    memory_mgmt = MemoryManagement(memory_config)

    # 注入到需要的地方
    orchestrator = create_orchestrator(
        memory=memory_mgmt.get_coordinator()
    )
```

### 6.4 输出物

- [ ] 更新`memory/management.py`
- [ ] 创建`memory/services/factories.py`
- [ ] 创建`memory/config/memory_config.py`
- [ ] 删除所有`global_memory_service`引用
- [ ] 更新所有调用方使用依赖注入

### 6.5 验证标准

- [ ] 没有全局单例
- [ ] 所有服务通过参数传递
- [ ] 测试可以注入mock对象
- [ ] 配置文件驱动backend选择

---

## Phase 7: 清理遗留代码和文档更新

### 目标
删除临时兼容层，更新文档，确保代码库整洁。

### 7.1 删除deprecated代码

- [ ] 删除`memory/operators/`目录
- [ ] 删除`memory/adapters/`目录
- [ ] 删除`memory/short_term/`目录（旧结构）
- [ ] 删除`memory/long_term/semantic/`中的旧文件
- [ ] 删除所有deprecation警告和兼容层

### 7.2 更新文档

- [ ] 更新`AGENTS.md`
- [ ] 更新`docs/agents/memory/agent_memory_design_practise.md`
- [ ] 创建`docs/agents/memory/migration_guide.md`
- [ ] 更新API文档
- [ ] 更新架构图

### 7.3 代码审查检查项

- [ ] 无循环依赖
- [ ] 所有import路径正确
- [ ] 类型注解完整
- [ ] 文档字符串完整
- [ ] 测试覆盖率 > 80%

### 7.4 验证标准

- [ ] 所有测试通过（单元+集成+E2E）
- [ ] 代码静态检查通过
- [ ] 文档审核通过
- [ ] 性能无明显下降

---

## 风险控制

### 分支策略
- 每个Phase在独立分支开发
- 完成并测试通过后才合并到主分支
- 保留临时兼容层直到所有Phase完成

### 回滚计划
- 每个Phase完成后打tag
- 保留旧代码的备份分支
- 准备快速回滚脚本

### 测试策略
- 每个Phase都有对应的测试
- 保持现有测试通过（兼容层）
- 新功能100%测试覆盖

---

## 时间估算

| Phase | 预估工作量 | 依赖 |
|-------|----------|------|
| Phase 1 | 2天 | 无 |
| Phase 2 | 3天 | Phase 1 |
| Phase 3 | 4天 | Phase 2 |
| Phase 4 | 5天 | Phase 3 |
| Phase 5 | 3天 | Phase 4 |
| Phase 6 | 3天 | Phase 2-5 |
| Phase 7 | 2天 | Phase 1-6 |
| **总计** | **22天** | - |

---

## 成功标准

### 架构指标
- [x] 接口与实现分离
- [x] 无全局单例
- [x] 领域逻辑与基础设施解耦
- [x] 存储方式可配置切换

### 代码质量
- [x] 无循环依赖
- [x] 测试覆盖率 > 80%
- [x] 类型注解完整
- [x] 文档完整

### 功能完整性
- [x] 所有现有功能保持
- [x] 新增情景记忆功能
- [x] OBS语义正确
- [x] ReAct循环符合标准

---

## 下一步

建议从**Phase 1**开始，先建立清晰的接口定义和架构蓝图，然后逐步推进。

需要我开始执行Phase 1吗？
