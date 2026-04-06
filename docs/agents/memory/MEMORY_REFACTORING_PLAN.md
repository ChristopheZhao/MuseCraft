# Working Memory Refactoring Plan
## 基于 2025 最佳实践的短期记忆系统重构方案

**创建时间**: 2025-10-27
**更新时间**: 2025-10-27 (聚焦短期记忆)
**范围**: **仅限 Working Memory（短期记忆）**，暂不涉及长期记忆
**目标**: 解决状态覆盖问题，建立类型安全、Reducer 驱动的短期记忆系统

---

## 📋 目录

1. [为什么聚焦短期记忆](#为什么聚焦短期记忆)
2. [当前问题根因](#当前问题根因)
3. [最佳实践总结](#最佳实践总结)
4. [新架构设计](#新架构设计)
5. [实施路径](#实施路径)
6. [验收标准](#验收标准)

---

## 为什么聚焦短期记忆

### 🎯 核心原则

> **"短期记忆是基础，长期记忆才有依托"**

**原因**：
1. ✅ **当前 Bug 根源**：短期记忆管理混乱导致状态覆盖
2. ✅ **架构优先级**：Working Memory 是 Agent 执行的核心依赖
3. ✅ **风险控制**：同时重构两层记忆风险太大
4. ✅ **渐进式演进**：稳定的短期记忆是长期记忆的基础

**架构依赖关系**：
```
┌─────────────────────────────┐
│  Long-term Memory (RAG)     │  ← 未来扩展
│  - 向量检索                  │
│  - 持久化存储                │
└─────────────────────────────┘
            ↑ 依赖
┌─────────────────────────────┐
│  Working Memory (State)     │  ← 当前重构目标 🎯
│  - 类型安全                  │
│  - Reducer 驱动              │
│  - Slot 管理                 │
└─────────────────────────────┘
```

---

## 当前问题根因

### 🔴 Critical Issue: 状态覆盖导致数据丢失

#### 你的 Bug 现场

```
2025-10-27 14:06:02,192 - WM_SLOT_WRITE ... keys=[] path=assets
```

**日志分析**：
1. `consistency_tool.get_prompt_assets` 被调用 → 返回空 assets
2. 写入 `prepared_assets` → `keys=[]`（空数据）
3. 下一轮读取 → 仍然是空的

**根本原因**：没有 Reducer，状态直接覆盖！

```python
# ❌ 当前代码：直接覆盖
def set_prepared_assets(self, scene_number: int, assets: Dict[str, Any]):
    self.prepared_assets[scene_number] = assets  # 💥 覆盖！

# 第 1 轮：准备 style
prepared_assets[1] = {"style": {...}}

# 第 2 轮：准备 characters
prepared_assets[1] = {"characters": {...}}
#                     ↓
#                  💥 style 丢失了！
```

---

### 🔴 其他问题

#### 1. **业务语义硬编码**

```python
# ❌ 问题：SharedWorkingMemory 硬编码业务字段
class SharedWMView:
    @property
    def scenes(self) -> Dict[int, SceneSnapshot]:  # 硬编码 "场景" 概念
        return self._data.get("scenes", {})

    @property
    def completed(self) -> Dict[int, SceneArtifact]:  # 硬编码 "完成" 状态
        return self._data.get("completed", {})
```

**问题**：
- 无法扩展到非视频场景（对话系统、文案生成、音乐创作）
- 记忆层必须知道 "场景" 是什么
- 新增业务概念需要修改底层记忆结构

#### 2. **缺少类型安全和 Schema 验证**

```python
# ❌ 问题：facts 是无类型的字典
def set_fact(self, task_id: str, key: str, value: Any) -> None:
    data = self._ensure_task(task_id)
    with self._lock:
        data["facts"][key] = value  # 没有验证、没有类型检查
```

**问题**：
- 调用方可以写入任意数据结构
- 没有版本控制和兼容性检查
- 难以调试和追踪数据来源

#### 3. **迭代记忆和共享记忆边界模糊**

```python
# ❌ 问题：WorkingMemory 混合了两种记忆
@dataclass
class WorkingMemory:
    scenes: Dict[int, SceneSnapshot] = field(default_factory=dict)  # 共享状态
    prepared_assets: Dict[int, Dict[str, Any]] = field(default_factory=dict)  # 迭代状态
    iteration_artifacts: Deque[Dict[str, Any]] = field(default_factory=...)  # 迭代状态
```

**问题**：
- 共享记忆（scenes）和迭代记忆（prepared_assets）混在一起
- 生命周期不清晰：谁负责清理？何时过期？
- 多 Agent 并发访问时容易冲突

#### 4. **缺少记忆分层**

当前只有扁平的字典结构，没有：
- Short-term Memory (工作记忆)
- Episodic Memory (情节记忆，需检索)
- Procedural Memory (程序记忆，自动技能)

#### 5. **没有 Reducer 模式**

```python
# ❌ 问题：状态更新是直接覆盖，没有组合策略
def mark_completed(self, scene_number: int, artifact: SceneArtifact):
    self.completed[scene_number] = artifact  # 直接覆盖，没有合并策略
```

**问题**：
- 无法表达 "追加"、"合并"、"取最新" 等语义
- 多个 Agent 写同一个 slot 时会互相覆盖

---

## 最佳实践总结

### 📚 来源：Industry Research (2025)

#### 1. **LangGraph Shared State Pattern**

**核心原则**：
- State 是 shared memory，跨节点记住一切
- 使用 TypedDict 确保类型安全
- Reducer functions 组合状态更新
- Checkpointers 实现持久化

**关键代码模式**：

```python
from typing import TypedDict, Annotated
from operator import add

class State(TypedDict):
    messages: Annotated[list[str], add]  # Reducer: 追加
    counter: Annotated[int, lambda x, y: x + y]  # Reducer: 相加
```

#### 2. **Multi-Agent Working Memory Best Practices (2025)**

**Compact State Design**：
- 紧凑设计：只保留执行必需的信息
- 使用引用：避免重复存储大对象
- 定期清理：迭代级数据自动过期

**Event Sourcing**：
- 记录状态变化的原因，而不只是结果
- 支持回放、审计、回滚

**Explicit State Management**：
- 显式的输入输出
- 避免全局变量
- 状态变更可追溯

#### 3. **Slot-Based Design Pattern**

**核心概念**：

```
Agent → 提出候选值 → Slot Selector → 承诺/写入 → Slot Memory
                           ↓
                      验证/Schema检查
```

**3 阶段流程**：
1. **Generate Candidates**: Agent 提出候选值
2. **Select/Commit**: 通过选择器或承诺过程选择
3. **Evaluate/Reconsider**: 写入后可评估、重新考虑、撤回

#### 4. **OS-Level Principles**

**安全与隔离**：
- 锁机制（RLock）防止数据竞争
- 沙箱隔离（Agent 只能访问授权的 slots）
- 最小权限（基于角色的访问控制）
- 审计日志（所有写操作可追溯）

---

## 新架构设计

### 🏗️ Core Components

#### 1. **MemorySlot - 抽象槽位**

```python
from typing import Protocol, TypedDict, Callable, Any, Optional
from dataclasses import dataclass
from enum import Enum

class SlotScope(Enum):
    """Slot 作用域"""
    WORKFLOW = "workflow"      # 整个工作流共享
    AGENT = "agent"            # 单个 Agent 私有
    ITERATION = "iteration"    # 迭代级别，自动清理

class SlotReducer(Protocol):
    """状态组合策略"""
    def __call__(self, old_value: Any, new_value: Any) -> Any:
        ...

@dataclass
class SlotSchema:
    """Slot 元数据和约束"""
    slot_id: str                           # 唯一标识，如 "project.timeline"
    display_name: str                      # 显示名称
    scope: SlotScope                       # 作用域
    value_type: type                       # Python 类型
    schema_version: str = "1.0.0"          # Schema 版本
    required: bool = False                 # 是否必需
    default_factory: Optional[Callable] = None  # 默认值工厂
    reducer: Optional[SlotReducer] = None  # 状态合并策略
    validator: Optional[Callable] = None   # 自定义验证器
    description: str = ""                  # 文档
    max_size: Optional[int] = None         # 容量限制
    ttl_seconds: Optional[int] = None      # 过期时间

# 内置 Reducers
class Reducers:
    @staticmethod
    def replace(old, new):
        """直接替换（默认）"""
        return new

    @staticmethod
    def append(old, new):
        """追加到列表"""
        if not isinstance(old, list):
            old = []
        return old + (new if isinstance(new, list) else [new])

    @staticmethod
    def merge_dict(old, new):
        """合并字典（深度合并）"""
        if not isinstance(old, dict):
            old = {}
        result = old.copy()
        result.update(new)
        return result

    @staticmethod
    def sum_numeric(old, new):
        """数值相加"""
        return (old or 0) + (new or 0)
```

#### 2. **SlotRegistry - Slot 注册表**

```python
class SlotRegistry:
    """配置驱动的 Slot 注册中心"""

    def __init__(self):
        self._slots: Dict[str, SlotSchema] = {}

    def register(self, schema: SlotSchema) -> None:
        """注册一个 Slot"""
        if schema.slot_id in self._slots:
            raise ValueError(f"Slot {schema.slot_id} already registered")
        self._slots[schema.slot_id] = schema

    def get(self, slot_id: str) -> SlotSchema:
        """获取 Slot Schema"""
        if slot_id not in self._slots:
            raise KeyError(f"Slot {slot_id} not registered")
        return self._slots[slot_id]

    def list_by_scope(self, scope: SlotScope) -> List[SlotSchema]:
        """按作用域列出 Slots"""
        return [s for s in self._slots.values() if s.scope == scope]

    @classmethod
    def from_config(cls, config_path: str) -> 'SlotRegistry':
        """从配置文件加载"""
        # 加载 YAML/JSON 配置
        pass
```

#### 3. **基础设施层 - 共享组件**

```python
from threading import RLock
from typing import Dict, Any, Optional, Protocol
from abc import ABC, abstractmethod

class BaseMemoryStore(ABC):
    """记忆存储的抽象基类 - 所有记忆管理器的基础"""

    def __init__(self, registry: SlotRegistry):
        self._registry = registry
        self._lock = RLock()
        self._audit_log: List[Dict] = []

    @abstractmethod
    def _validate_slot_scope(self, slot_id: str) -> bool:
        """子类必须实现：验证 slot 是否属于当前管理器的作用域"""
        pass

    def _validate_value(self, slot_id: str, value: Any) -> None:
        """通用的值验证逻辑"""
        schema = self._registry.get(slot_id)

        if not isinstance(value, schema.value_type):
            raise TypeError(f"Expected {schema.value_type}, got {type(value)}")

        if schema.validator and not schema.validator(value):
            raise ValueError(f"Validation failed for {slot_id}")

    def _apply_reducer(self, slot_id: str, old_value: Any, new_value: Any) -> Any:
        """通用的 Reducer 应用逻辑"""
        schema = self._registry.get(slot_id)

        if schema.reducer:
            return schema.reducer(old_value, new_value)
        return new_value

    def _log_access(
        self,
        workflow_id: str,
        slot_id: str,
        operation: str,
        agent_name: Optional[str],
        size: int
    ) -> None:
        """通用的审计日志"""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "workflow_id": workflow_id,
            "slot_id": slot_id,
            "operation": operation,
            "agent_name": agent_name,
            "size": size,
        }
        self._audit_log.append(log_entry)
        logger.debug(f"MEMORY_ACCESS: {log_entry}")

class ACLManager:
    """访问控制列表管理器 - 所有记忆管理器共享"""

    def __init__(self):
        self._acl: Dict[str, Dict[str, set]] = defaultdict(lambda: defaultdict(set))

    def grant_permission(
        self,
        workflow_id: str,
        slot_id: str,
        agent_name: str,
        permission: str  # "read" | "write"
    ) -> None:
        """授予权限"""
        self._acl[workflow_id][slot_id].add(f"{agent_name}:{permission}")

    def check_permission(
        self,
        workflow_id: str,
        slot_id: str,
        agent_name: str,
        permission: str
    ) -> bool:
        """检查权限"""
        acl_key = f"{agent_name}:{permission}"
        return acl_key in self._acl[workflow_id][slot_id]
```

#### 4. **SharedMemoryManager - 共享记忆管理器**

```python
from collections import defaultdict

class SharedMemoryManager(BaseMemoryStore):
    """共享记忆管理器 - 管理跨 Agent 的持久化事实

    职责：
    - 管理 workflow scope 的 slots (concept_plan, timeline, etc.)
    - 提供跨 Agent 的数据共享
    - 生命周期：整个工作流期间
    - 不负责清理（由工作流结束时触发）
    """

    def __init__(self, registry: SlotRegistry, acl_manager: ACLManager):
        super().__init__(registry)
        self._acl = acl_manager
        # workflow_id → slot_id → value
        self._store: Dict[str, Dict[str, Any]] = defaultdict(dict)

    def _validate_slot_scope(self, slot_id: str) -> bool:
        """只接受 workflow scope 的 slots"""
        schema = self._registry.get(slot_id)
        return schema.scope == SlotScope.WORKFLOW

    def set_fact(
        self,
        workflow_id: str,
        slot_id: str,
        value: Any,
        agent_name: Optional[str] = None
    ) -> None:
        """设置共享事实（带权限检查和 Reducer）"""
        if not self._validate_slot_scope(slot_id):
            raise ValueError(f"Slot {slot_id} is not workflow scope")

        # 权限检查
        if agent_name and not self._acl.check_permission(workflow_id, slot_id, agent_name, "write"):
            raise PermissionError(f"Agent {agent_name} has no write access to {slot_id}")

        # 值验证
        self._validate_value(slot_id, value)

        with self._lock:
            # 应用 Reducer
            old_value = self._store[workflow_id].get(slot_id)
            merged_value = self._apply_reducer(slot_id, old_value, value)

            self._store[workflow_id][slot_id] = merged_value

            # 审计日志
            self._log_access(workflow_id, slot_id, "write", agent_name, len(str(merged_value)))

    def get_fact(
        self,
        workflow_id: str,
        slot_id: str,
        agent_name: Optional[str] = None
    ) -> Any:
        """获取共享事实"""
        if not self._validate_slot_scope(slot_id):
            raise ValueError(f"Slot {slot_id} is not workflow scope")

        # 权限检查
        if agent_name and not self._acl.check_permission(workflow_id, slot_id, agent_name, "read"):
            raise PermissionError(f"Agent {agent_name} has no read access to {slot_id}")

        with self._lock:
            schema = self._registry.get(slot_id)
            value = self._store[workflow_id].get(slot_id)

            # 返回默认值
            if value is None and schema.default_factory:
                value = schema.default_factory()
                self._store[workflow_id][slot_id] = value

            self._log_access(workflow_id, slot_id, "read", agent_name, 0)
            return value

    def clear_workflow(self, workflow_id: str) -> None:
        """清理工作流的所有共享记忆"""
        with self._lock:
            if workflow_id in self._store:
                del self._store[workflow_id]
                logger.info(f"Cleared shared memory for workflow {workflow_id}")

#### 5. **IterationMemoryManager - 迭代记忆管理器**

```python
class IterationMemoryManager(BaseMemoryStore):
    """迭代记忆管理器 - 管理单个 Agent 的临时状态

    职责：
    - 管理 agent/iteration scope 的 slots (prepared_assets, generation_queue, etc.)
    - 提供 Agent 的工作缓存
    - 生命周期：单次迭代或有 TTL
    - 自动清理过期数据
    """

    def __init__(self, registry: SlotRegistry, acl_manager: ACLManager):
        super().__init__(registry)
        self._acl = acl_manager
        # workflow_id → agent_name → slot_id → value
        self._store: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(
            lambda: defaultdict(dict)
        )
        # TTL 追踪：workflow_id → agent_name → slot_id → expiry_time
        self._expiry: Dict[str, Dict[str, Dict[str, float]]] = defaultdict(
            lambda: defaultdict(dict)
        )

    def _validate_slot_scope(self, slot_id: str) -> bool:
        """只接受 agent/iteration scope 的 slots"""
        schema = self._registry.get(slot_id)
        return schema.scope in [SlotScope.AGENT, SlotScope.ITERATION]

    def set_iteration_data(
        self,
        workflow_id: str,
        agent_name: str,
        slot_id: str,
        value: Any
    ) -> None:
        """设置迭代数据"""
        if not self._validate_slot_scope(slot_id):
            raise ValueError(f"Slot {slot_id} is not agent/iteration scope")

        # 迭代记忆不需要跨 Agent 权限检查（Agent 只能写自己的）
        self._validate_value(slot_id, value)

        with self._lock:
            # 应用 Reducer
            old_value = self._store[workflow_id][agent_name].get(slot_id)
            merged_value = self._apply_reducer(slot_id, old_value, value)

            self._store[workflow_id][agent_name][slot_id] = merged_value

            # 设置 TTL
            schema = self._registry.get(slot_id)
            if schema.ttl_seconds:
                import time
                expiry = time.time() + schema.ttl_seconds
                self._expiry[workflow_id][agent_name][slot_id] = expiry

            # 审计日志
            self._log_access(workflow_id, slot_id, "write", agent_name, len(str(merged_value)))

    def get_iteration_data(
        self,
        workflow_id: str,
        agent_name: str,
        slot_id: str
    ) -> Any:
        """获取迭代数据（自动清理过期数据）"""
        if not self._validate_slot_scope(slot_id):
            raise ValueError(f"Slot {slot_id} is not agent/iteration scope")

        with self._lock:
            # 检查是否过期
            if slot_id in self._expiry[workflow_id][agent_name]:
                import time
                if time.time() > self._expiry[workflow_id][agent_name][slot_id]:
                    # 已过期，删除
                    del self._store[workflow_id][agent_name][slot_id]
                    del self._expiry[workflow_id][agent_name][slot_id]
                    logger.debug(f"Expired slot {slot_id} for {agent_name}")
                    return None

            schema = self._registry.get(slot_id)
            value = self._store[workflow_id][agent_name].get(slot_id)

            # 返回默认值
            if value is None and schema.default_factory:
                value = schema.default_factory()

            self._log_access(workflow_id, slot_id, "read", agent_name, 0)
            return value

    def clear_agent_iteration(self, workflow_id: str, agent_name: str) -> None:
        """清理 Agent 的所有迭代记忆"""
        with self._lock:
            if agent_name in self._store[workflow_id]:
                del self._store[workflow_id][agent_name]
            if agent_name in self._expiry[workflow_id]:
                del self._expiry[workflow_id][agent_name]
            logger.info(f"Cleared iteration memory for {agent_name} in {workflow_id}")

    def cleanup_expired(self, workflow_id: str) -> int:
        """清理所有过期数据（返回清理的条目数）"""
        import time
        cleaned = 0

        with self._lock:
            current_time = time.time()
            for agent_name in list(self._expiry[workflow_id].keys()):
                for slot_id in list(self._expiry[workflow_id][agent_name].keys()):
                    if current_time > self._expiry[workflow_id][agent_name][slot_id]:
                        del self._store[workflow_id][agent_name][slot_id]
                        del self._expiry[workflow_id][agent_name][slot_id]
                        cleaned += 1

        if cleaned > 0:
            logger.info(f"Cleaned {cleaned} expired slots in {workflow_id}")
        return cleaned

#### 6. **MemoryCoordinator - 记忆协调器（可选）**

```python
class MemoryCoordinator:
    """记忆协调器 - 提供统一的高级接口

    职责：
    - 统一入口，简化 Agent 调用
    - 跨记忆类型的操作协调
    - 但不负责具体的存储逻辑
    """

    def __init__(
        self,
        shared_memory: SharedMemoryManager,
        iteration_memory: IterationMemoryManager,
        registry: SlotRegistry
    ):
        self._shared = shared_memory
        self._iteration = iteration_memory
        self._registry = registry

    def get_memory(
        self,
        workflow_id: str,
        slot_id: str,
        agent_name: Optional[str] = None
    ) -> Any:
        """统一的读取接口 - 自动判断 slot 类型"""
        schema = self._registry.get(slot_id)

        if schema.scope == SlotScope.WORKFLOW:
            return self._shared.get_fact(workflow_id, slot_id, agent_name)
        elif schema.scope in [SlotScope.AGENT, SlotScope.ITERATION]:
            if not agent_name:
                raise ValueError(f"agent_name required for {schema.scope} scope")
            return self._iteration.get_iteration_data(workflow_id, agent_name, slot_id)
        else:
            raise ValueError(f"Unknown scope: {schema.scope}")

    def set_memory(
        self,
        workflow_id: str,
        slot_id: str,
        value: Any,
        agent_name: Optional[str] = None
    ) -> None:
        """统一的写入接口 - 自动判断 slot 类型"""
        schema = self._registry.get(slot_id)

        if schema.scope == SlotScope.WORKFLOW:
            self._shared.set_fact(workflow_id, slot_id, value, agent_name)
        elif schema.scope in [SlotScope.AGENT, SlotScope.ITERATION]:
            if not agent_name:
                raise ValueError(f"agent_name required for {schema.scope} scope")
            self._iteration.set_iteration_data(workflow_id, agent_name, slot_id, value)
        else:
            raise ValueError(f"Unknown scope: {schema.scope}")
```

#### 4. **配置驱动的 Slot 定义**

```yaml
# config/memory_slots.yaml

slots:
  # ========== Workflow Scope ==========

  - slot_id: "project.concept_plan"
    display_name: "概念方案"
    scope: workflow
    value_type: dict
    schema_version: "1.0.0"
    required: true
    reducer: merge_dict
    description: "项目级概念规划，包含风格、角色、场景设定"
    max_size: 102400  # 100KB
    ttl_seconds: null  # 永不过期

  - slot_id: "project.timeline"
    display_name: "场景时间线"
    scope: workflow
    value_type: dict  # Dict[int, SceneSnapshot]
    schema_version: "1.0.0"
    required: true
    reducer: merge_dict
    description: "场景列表和依赖关系"

  - slot_id: "project.script_details"
    display_name: "场景脚本"
    scope: workflow
    value_type: dict
    reducer: merge_dict
    description: "详细的场景脚本信息"

  # ========== Agent Scope ==========

  - slot_id: "agent.image_generator.prepared_assets"
    display_name: "图像生成准备资产"
    scope: agent
    value_type: dict  # Dict[int, Dict[str, Any]]
    reducer: merge_dict
    description: "图像生成器的准备资产缓存"
    ttl_seconds: 3600  # 1小时后过期

  - slot_id: "agent.video_generator.generation_queue"
    display_name: "视频生成队列"
    scope: agent
    value_type: list
    reducer: append
    description: "待生成的视频任务队列"
    max_size: 100

  # ========== Iteration Scope ==========

  - slot_id: "iteration.last_action"
    display_name: "上一次动作"
    scope: iteration
    value_type: dict
    reducer: replace
    description: "上一次执行的动作信息"
    ttl_seconds: 300  # 5分钟

  - slot_id: "iteration.error_context"
    display_name: "错误上下文"
    scope: iteration
    value_type: list
    reducer: append
    description: "本次迭代的错误上下文"
    max_size: 10

# ACL 配置
access_control:
  # Slot ID → Agent Name → Permissions
  "project.concept_plan":
    - agent: orchestrator
      permissions: [read, write]
    - agent: concept_planner
      permissions: [read, write]
    - agent: script_writer
      permissions: [read]
    - agent: image_generator
      permissions: [read]

  "project.timeline":
    - agent: orchestrator
      permissions: [read, write]
    - agent: "*"  # 所有 Agent
      permissions: [read]

  "agent.image_generator.prepared_assets":
    - agent: image_generator
      permissions: [read, write]
```

#### 7. **Agent Integration - 集成到 BaseAgent**

```python
class BaseAgent:
    """重构后的 BaseAgent - 使用 MemoryCoordinator"""

    def __init__(
        self,
        agent_name: str,
        workflow_id: str,
        memory_coordinator: MemoryCoordinator
    ):
        self._agent_name = agent_name
        self._workflow_id = workflow_id
        self._memory = memory_coordinator

    # ✅ 统一的记忆访问接口
    def get_memory(self, slot_id: str) -> Any:
        """获取记忆 Slot（协调器自动判断类型）"""
        return self._memory.get_memory(
            workflow_id=self._workflow_id,
            slot_id=slot_id,
            agent_name=self._agent_name
        )

    def set_memory(self, slot_id: str, value: Any) -> None:
        """设置记忆 Slot（协调器自动判断类型）"""
        self._memory.set_memory(
            workflow_id=self._workflow_id,
            slot_id=slot_id,
            value=value,
            agent_name=self._agent_name
        )

    # ✅ 高级便捷方法（业务语义层）
    def get_concept_plan(self) -> Dict[str, Any]:
        """便捷方法：获取概念方案（共享记忆）"""
        return self.get_memory("project.concept_plan") or {}

    def get_timeline(self) -> Dict[int, Any]:
        """便捷方法：获取场景时间线（共享记忆）"""
        return self.get_memory("project.timeline") or {}

    def get_prepared_assets(self, scene_number: int) -> Dict[str, Any]:
        """便捷方法：获取准备资产（迭代记忆）"""
        slot_id = f"agent.{self._agent_name}.prepared_assets"
        all_assets = self.get_memory(slot_id) or {}
        return all_assets.get(scene_number, {})

    def set_prepared_assets(self, scene_number: int, assets: Dict[str, Any]) -> None:
        """便捷方法：设置准备资产（自动合并，不覆盖）"""
        slot_id = f"agent.{self._agent_name}.prepared_assets"
        # 使用 merge_dict reducer 自动合并
        self.set_memory(slot_id, {scene_number: assets})
```

#### 8. **模块目录结构**

```
app/agents/memory/
├── __init__.py                    # 导出公共接口
├── slots/
│   ├── __init__.py
│   ├── schema.py                  # SlotSchema, SlotScope, Reducers
│   └── registry.py                # SlotRegistry
├── managers/
│   ├── __init__.py
│   ├── base.py                    # BaseMemoryStore, ACLManager
│   ├── shared_manager.py          # SharedMemoryManager
│   └── iteration_manager.py       # IterationMemoryManager
├── coordinator.py                  # MemoryCoordinator
├── legacy/
│   ├── __init__.py
│   ├── shared_wm.py               # 旧的 SharedWorkingMemory（逐步废弃）
│   └── adapter.py                 # SharedWorkingMemoryAdapter
└── config/
    └── memory_slots.yaml          # Slot 配置文件
```

---

## 实施路径

### 📅 Phase 0: 近期止血（立即执行）

**目标**: 快速修复当前 `prepared_assets` 空转问题

**任务**:
1. ✅ **写入校验**：所有 `set_fact`、`WM_SLOT_WRITE` 前后打印关键字段
2. ✅ **空 payload 抛错**：WorkingMemory 的 `_collect_prepared_refs` 跳过全空数据
3. ✅ **验证数据链路**：人工检查 + 调试脚本确认 `concept_plan`、`scene_scripts` 已落到 Shared WM

**产出**:
- 临时防御性代码
- 调试脚本验证数据流
- 问题根因报告

### 📅 Phase 1: 基础设施层（Week 1-2）

**目标**: 建立模块化的记忆基础设施

**任务**:
1. ✅ 实现 **共享组件**:
   - `BaseMemoryStore` - 抽象基类
   - `ACLManager` - 访问控制管理器
   - `SlotSchema`, `SlotRegistry`, `Reducers` - Slot 系统核心

2. ✅ 实现 **SharedMemoryManager**:
   - 管理 workflow scope 的 slots
   - 继承 `BaseMemoryStore`
   - 提供 `set_fact()`、`get_fact()` 接口

3. ✅ 实现 **IterationMemoryManager**:
   - 管理 agent/iteration scope 的 slots
   - 继承 `BaseMemoryStore`
   - 提供 TTL 自动清理机制
   - 提供 `set_iteration_data()`、`get_iteration_data()` 接口

4. ✅ 实现 **MemoryCoordinator**:
   - 统一的高级接口
   - 根据 slot scope 自动路由到对应管理器

5. ✅ 编写单元测试（100% 覆盖率）

**产出**:
- `app/agents/memory/slots/` - Slot 系统
- `app/agents/memory/managers/` - 独立的管理器模块
- `app/agents/memory/coordinator.py` - 协调器
- `config/memory_slots.yaml` - Slot 配置
- `tests/unit/test_shared_manager.py` - SharedMemoryManager 测试
- `tests/unit/test_iteration_manager.py` - IterationMemoryManager 测试
- `tests/unit/test_coordinator.py` - MemoryCoordinator 测试

### 📅 Phase 2: 兼容层与首批迁移（Week 3-4）

**目标**: 创建兼容层，迁移核心 Agents

**任务**:
1. ✅ 实现 **SharedWorkingMemoryAdapter**:
   ```python
   class SharedWorkingMemoryAdapter:
       """向后兼容适配器"""
       def __init__(self, coordinator: MemoryCoordinator, workflow_id: str):
           self._coordinator = coordinator
           self._wf_id = workflow_id

       def set_fact(self, task_id: str, key: str, value: Any) -> None:
           slot_id = self._map_legacy_key_to_slot(key)
           self._coordinator.set_memory(task_id, slot_id, value)
   ```

2. ✅ **首批迁移** - Orchestrator + ConceptPlanner:
   - 改用 `memory_coordinator.set_memory("project.concept_plan", ...)`
   - 改用 `memory_coordinator.get_memory("project.timeline")`
   - 保留兼容层以支持其他未迁移 Agents

3. ✅ **ImageGenerator 迁移**（修复 prepared_assets 问题）:
   - 使用 `agent.image_generator.prepared_assets` slot
   - 配置 `merge_dict` reducer
   - 验证多轮写入不会覆盖

**产出**:
- `app/agents/memory/legacy/adapter.py` - 兼容适配器
- Orchestrator、ConceptPlanner、ImageGenerator 迁移完成
- E2E 测试验证迁移正确性

### 📅 Phase 3: 全量迁移（Week 5-6）

**优先级排序**:
1. ✅ **高优先级**: Orchestrator, ConceptPlanner, ImageGenerator（已完成）
2. ✅ **中优先级**: ScriptWriter, VideoGenerator
3. ✅ **低优先级**: AudioComposer, QualityChecker

**迁移步骤**（每个 Agent）:
```python
# Step 1: 更新构造函数
class ScriptWriter(BaseAgent):
    def __init__(
        self,
        agent_name: str,
        workflow_id: str,
        memory_coordinator: MemoryCoordinator,  # 新参数
        **kwargs
    ):
        super().__init__(agent_name, workflow_id, memory_coordinator)

# Step 2: 替换所有记忆访问
# ❌ 旧方式
scene_scripts = self._shared_wm.get_task(workflow_id).facts.get("scene_scripts")

# ✅ 新方式
scene_scripts = self.get_memory("project.script_details")

# Step 3: 替换迭代记忆
# ❌ 旧方式
self._working_memory.prepared_assets[scene_number] = assets

# ✅ 新方式
self.set_prepared_assets(scene_number, assets)  # 自动合并，不覆盖
```

**产出**:
- 所有 Agents 迁移到新记忆系统
- E2E 回归测试通过

### 📅 Phase 4: 清理与强化（Week 7-8）

**任务**:
1. ✅ **移除旧代码**:
   - 删除 `SharedWorkingMemory` 类
   - 删除 `WorkingMemory` 类（保留 dataclass 定义用于类型）
   - 移除兼容层代码

2. ✅ **性能优化**:
   - 批量写入接口 `set_slots_batch()`
   - 缓存层 `get_slot_cached()`
   - 惰性加载 `LazySlotProxy`

3. ✅ **审计与监控**:
   - 完善审计日志输出
   - 监控指标：slot 写入成功率、memref 解析失败率
   - 实时告警

4. ✅ **文档与测试**:
   - 更新开发指南
   - 完成 E2E 回归：memref 链路、prepared_assets、失败回滚
   - 性能基准测试

**产出**:
- 清理后的代码库
- 性能优化报告
- 完整的文档和测试

---

## 兼容性策略

### 🔄 双轨运行期

在迁移过程中，新旧系统并行：

```python
# 全局切换开关
USE_NEW_MEMORY_SYSTEM = os.getenv("USE_NEW_MEMORY", "false").lower() == "true"

def get_memory_manager(workflow_id: str):
    if USE_NEW_MEMORY_SYSTEM:
        return new_memory_manager
    else:
        return legacy_memory_adapter
```

### 📊 数据迁移

```python
# 一次性数据迁移脚本
def migrate_legacy_data():
    """将旧记忆数据迁移到新 Slot 系统"""
    old_wm = get_shared_wm()
    new_mm = MemoryManager(registry)

    for workflow_id in old_wm._store.keys():
        view = old_wm.get_task(workflow_id)

        # 迁移 facts
        for key, value in view.facts.items():
            slot_id = map_legacy_key_to_slot(key)
            new_mm.set_slot(workflow_id, slot_id, value)

        # 迁移 scenes
        for scene_num, snapshot in view.scenes.items():
            timeline = new_mm.get_slot(workflow_id, "project.timeline") or {}
            timeline[scene_num] = snapshot
            new_mm.set_slot(workflow_id, "project.timeline", timeline)
```

---

## 验收标准

### ⚡ 优化策略

#### 1. **批量操作**

```python
class MemoryManager:
    def set_slots_batch(self, workflow_id: str, updates: Dict[str, Any]) -> None:
        """批量设置多个 Slots（减少锁争用）"""
        with self._lock:
            for slot_id, value in updates.items():
                self._store[workflow_id][slot_id] = value
```

#### 2. **缓存层**

```python
from functools import lru_cache

class MemoryManager:
    @lru_cache(maxsize=128)
    def get_slot_cached(self, workflow_id: str, slot_id: str) -> Any:
        """带缓存的 Slot 获取"""
        return self.get_slot(workflow_id, slot_id)
```

#### 3. **惰性加载**

```python
class MemoryManager:
    def get_slot_lazy(self, workflow_id: str, slot_id: str):
        """返回代理对象，只在实际访问时加载"""
        return LazySlotProxy(self, workflow_id, slot_id)
```

### 📈 性能基准

**目标**:
- Slot 写入: < 1ms
- Slot 读取: < 0.5ms
- 批量操作 (10 slots): < 5ms
- 内存占用: < 10MB per workflow

---

---

## 总结

### ✅ 核心价值

1. **解决当前 Bug**：prepared_assets 不再覆盖
2. **防止未来 Bug**：所有状态更新都经过 Reducer
3. **模块化设计**：共享记忆、迭代记忆、长期记忆各司其职
4. **提升可维护性**：类型安全 + 显式状态管理 + 清晰的职责边界
5. **为长期记忆打基础**：稳定的短期记忆系统，清晰的扩展路径

### 架构对比

#### Before（当前架构）
```
SharedWorkingMemory (混合所有类型)
├── facts: Dict[str, Any]              # 共享事实
├── scenes: Dict[int, SceneSnapshot]   # 共享场景
└── prepared_assets: Dict[...]         # 迭代数据（混在一起）

WorkingMemory (混合迭代和共享)
├── scenes: Dict[int, ...]             # 共享？
├── prepared_assets: Dict[...]         # 迭代？
└── iteration_artifacts: Deque[...]    # 迭代？

问题：
❌ 职责不清：共享和迭代混在一起
❌ 直接覆盖：没有 Reducer，数据丢失
❌ 无类型安全：Any 类型，难以调试
❌ 硬编码业务：记忆层知道"场景"、"完成"等概念
❌ 难以扩展：添加长期记忆无从下手
```

#### After（新架构）
```
MemoryCoordinator (统一入口)
├── SharedMemoryManager              # 独立管理共享记忆
│   ├── workflow scope slots
│   ├── 跨 Agent 数据共享
│   └── 生命周期：整个工作流
│
├── IterationMemoryManager           # 独立管理迭代记忆
│   ├── agent/iteration scope slots
│   ├── Agent 工作缓存
│   ├── TTL 自动清理
│   └── 生命周期：单次迭代
│
└── [未来] LongTermMemoryManager     # 预留扩展
    ├── RAG 向量检索
    ├── 持久化存储
    └── 跨会话记忆

优势：
✅ 职责清晰：每个管理器只负责一种记忆类型
✅ Reducer 驱动：所有更新自动合并，不覆盖
✅ 类型安全：SlotSchema 验证所有数据
✅ 配置驱动：业务概念在 YAML 配置，不在代码
✅ 易于扩展：添加 LongTermMemoryManager 不影响现有代码
```

#### 特性对比表

| 特性 | Before | After |
|------|--------|-------|
| **架构** |
| 记忆管理 | ❌ 单个类混合 | ✅ 独立管理器 |
| 共享/迭代分离 | ❌ 混在一起 | ✅ 明确分离 |
| 长期记忆扩展 | ❌ 无路径 | ✅ 清晰路径 |
| **数据安全** |
| 状态更新 | ❌ 直接覆盖 | ✅ Reducer 合并 |
| 数据丢失 | ❌ 频繁发生 | ✅ 不会发生 |
| 并发安全 | ⚠️ RLock | ✅ RLock + Scope 隔离 |
| **可维护性** |
| 类型安全 | ❌ Any | ✅ TypedDict + Schema |
| 业务耦合 | ❌ 硬编码 | ✅ 配置驱动 |
| 可调试性 | ❌ 难以追踪 | ✅ 审计日志 |
| **扩展性** |
| 添加新业务 | ⚠️ 需改代码 | ✅ 添加配置即可 |
| 添加新记忆类型 | ❌ 无法扩展 | ✅ 新增管理器 |

### 🔮 未来扩展路径 - LongTermMemoryManager

**当短期记忆稳定后**，可以轻松扩展长期记忆：

```python
class LongTermMemoryManager(BaseMemoryStore):
    """长期记忆管理器 - 跨会话持久化记忆

    职责：
    - 管理 longterm scope 的 slots
    - RAG 向量检索
    - 持久化到数据库/对象存储
    - 生命周期：跨工作流
    """

    def __init__(
        self,
        registry: SlotRegistry,
        vector_store: VectorStore,  # Pinecone / Qdrant / Chroma
        persistent_store: PersistentStore  # PostgreSQL / Redis
    ):
        super().__init__(registry)
        self._vector_store = vector_store
        self._persistent_store = persistent_store

    async def store_episode(
        self,
        workflow_id: str,
        episode_summary: str,
        metadata: Dict[str, Any]
    ) -> None:
        """存储情节记忆"""
        embedding = await self._embed(episode_summary)
        await self._vector_store.upsert(
            id=workflow_id,
            values=embedding,
            metadata=metadata
        )

    async def retrieve_similar_episodes(
        self,
        query: str,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """检索相似情节"""
        query_embedding = await self._embed(query)
        return await self._vector_store.query(
            vector=query_embedding,
            top_k=top_k
        )
```

**扩展步骤**:
1. 在 `SlotScope` 添加 `LONGTERM` 枚举
2. 实现 `LongTermMemoryManager`
3. 在 `MemoryCoordinator` 添加路由逻辑
4. 配置 `memory_slots.yaml` 添加长期记忆 slots
5. Agent 无需修改，直接使用 `get_memory("longterm.user_preferences")`

### 🚀 下一步行动

1. **Phase 0（立即）**: 临时止血，修复当前 bug
2. **Phase 1（Week 1-2）**: 实现基础设施层（SharedMemoryManager + IterationMemoryManager）
3. **Phase 2（Week 3-4）**: 兼容层 + 首批迁移（Orchestrator、ConceptPlanner、ImageGenerator）
4. **Phase 3（Week 5-6）**: 全量迁移所有 Agents
5. **Phase 4（Week 7-8）**: 清理旧代码，性能优化，完善文档
6. **Phase 5（未来）**: 添加 LongTermMemoryManager

**原则**：等短期记忆稳定后，再考虑长期记忆（RAG、向量检索等）的扩展。
