# Agent 使用 WorkingMemory 的规范与重构方案（聚焦 WM）

## 背景与问题
- 短期记忆（WorkingMemory）是 MAS/Agent 事实与轨迹的承载，但当前 Agent 通过全局单例 `get_working_memory_service()` 直接访问，隐式依赖、耦合度高，不利于测试/替换存储后端。
- MemoryServices 注入存在，但短期路径未使用，依赖注入原则被破坏；Agent 上直接暴露 `wm` 等句柄，未来若长记忆等也照此暴露，会放大耦合面。
- 虽已引入存储抽象（ShortTermMemoryStore）与领域适配器（VideoMemoryAdapter），但访问路径仍绑定单例，抽象层与应用层间缺少注入封装。

## 当前状态校准
- ✅ MemoryServices dataclass 已补充 short_term 字段，短期记忆仅支持注入（无全局回退）。
- ✅ WorkingMemoryService 支持 store_factory，ShortTermMemoryStore 抽象已落地；单例 registry 已移除/禁用。
- ✅ Orchestrator 在构造各 Agent 时注入同一份 memory_services。
- ✅ BaseAgent 的短期记忆访问已走注入路径；全局单例引用已清理。
- ✅ MemoryServices 不再暴露 management/coordinator；GlobalMemoryService 不再持有/暴露 coordinator，抽象层仅提供受控 Facade（long_term/业务方法）。
- ✅ Agent 迭代状态视图已实现并注入；静态守护/冒烟用例已添加并本地通过。

## 目标
- 短期记忆仅通过注入的 WorkingMemoryService/MemoryServices 管理，无单例回退，保持 MAS/Agent 单一通道（scope 区分）。
- 记忆模型与应用层解耦：Agent 通过受控接口/Helper 访问，不直接暴露底层服务句柄；scope 继续用 `mas:{wf_id}` / `agent:{wf_id}:{agent}`。
- 支持可替换存储后端：ShortTermMemoryStore 抽象 + store_factory 注入，默认内存后端，可按需替换。
- 长期记忆同样通过受控 Facade/Helper 暴露，隐藏 MemoryManager/Coordinator 等实现细节，便于替换与治理。

## 分层与角色
- **基础实现层**：纯存储实现（ShortTermMemoryStore 等），只负责数据持久/缓存，不承载记忆策略或领域逻辑。
- **抽象/服务层**：记忆服务接口与 Facade（WorkingMemoryService、长记忆服务接口、领域适配器等），负责策略/校验/接口统一，屏蔽存储细节；MemoryServices 聚合短期/长期服务。
- **应用层**：Agent/工具/编排，仅通过注入的抽象接口/Facade/Helper 访问记忆，不直接依赖底层存储或管理器；作用域仍用 `mas:{wf_id}` / `agent:{wf_id}:{agent}`。

## 重构方案（WM 相关）
1) **短期记忆注入化（无过渡、移除全局路径）**
   - MemoryServices dataclass 增加 `short_term: WorkingMemoryService` 字段。
   - `build_memory_services` 构造 short_term 并随返回值注入，不再调用 `set_working_memory_service` 或任何全局 setter。
   - Orchestrator/测试继续传入统一的 MemoryServices；MAS/Agent scope create_or_get 流程保持，缓存/同步逻辑不变。

2) **访问封装与属性收敛**
   - BaseAgent 的 `wm`/`memory_write` 改为从注入的 short_term_service 获取，删除对全局单例的引用；评估并收敛 `memory_manager` 等长记忆句柄暴露方式。
   - 辅助模块（memory_helpers、快照导出、工具 provider 等）改为接收可选的 MemoryServices/WorkingMemoryService 注入，不再导入全局单例。
   - 上下文构建仍由编排/context manager 注入，Agent 内不自行拼装跨层上下文。

## 迁移步骤
- 更新 MemoryServices dataclass 与 `build_memory_services`：新增 short_term 字段并返回实例，移除全局 setter/单例。
- BaseAgent 将 `wm`/`memory_write` 切到注入的 short_term_service，禁止调用全局 `get_working_memory_service`。
- 全局辅助路径改注入：memory_helpers、memory/long_term/snapshots 等函数需注入 MemoryServices/WorkingMemoryService（必填，无单例回退），调用方负责传递；删除对全局单例的引用。
- Orchestrator 注入已完成，保持现有构造逻辑，但不再同步/写入全局。

## 行动清单（分阶段/模块/优先级）
- **Phase 1（P0，已完成：短期注入化 + 移除单例回退）**
  - MemoryServices 补充 short_term，`build_memory_services` 构造短期服务，不再设置全局单例。
  - BaseAgent/Orchestrator/Helpers/快照/工具 provider 全部改为注入路径，删除全局引用；`memory.short_term.registry` 生产导出已删除/禁用。
  - ContextAssembler 默认实例移除，必须显式构造传入 memory_services。
- **Phase 2（P1，已完成：长记忆封装与调用迁移）**
  - ✅ 定义/强化长记忆 Facade/Helper（服务层暴露抽象接口，隐藏 LongTermMemoryManager/Coordinator 细节）。
  - ✅ 迁移调用方：MemoryTool、MemoryWriter、GlobalMemoryService、BaseAgent 内部 helper 改用 Facade；BaseAgent 兼容 property 已删除，后续仅暴露受控接口。
  - ✅ MemoryServices 仅暴露抽象接口（global/long_term/short_term）；management/coordinator 已从注入包移除，GlobalMemoryService 内部私有化 coordinator 且不暴露 Slot API。
- **Phase 3（P1，已完成：Agent 视图与守护）**
  - ✅ agent_scope 迭代状态视图：已实现统计/观测快照并由 Orchestrator 注入；字段聚焦迭代计数、场景完成/失败/重试计数、错误/重试热点等汇总指标，明细仍在 agent-scope WM。
  - ✅ 静态守护：已添加静态检查用例（禁用单例/LongTermMemoryManager 暴露）和纯注入冒烟用例，当前在本地执行。
  - 工厂替换测试：短期/长期后端替换仍可运行核心工作流（待补）。
- **Phase 4（P2，收尾与文档）**
  - ✅ BaseAgent 兼容 property 删除；示例/样例已改用 Facade。应用层无 LongTermMemoryManager 直接引用，保留实现层导出供内部使用。
  - ✅ 文档同步：标记单例移除、长记忆封装与视图补全的完成度，明确受控接口使用规范；Coordinator/slot 概念不对外暴露。
  - 如无引用，彻底删除 registry/默认导出；测试 stub 保留在 testutils，不进入生产包。

## 风险与注意事项
- 确保 MAS/Agent scope 唯一性不变（mas:{wf} / agent:{wf}:{agent}），仅替换服务来源。
- 移除全局单例后，遗漏注入会直接报错，需在构造/调用链保证 memory_services 提供到位。
- 存储后端可替换（ShortTermMemoryStore），但仍需遵循单一通道读写 MAS/Agent WM。
 - 测试便利：若需复用构造，可在 tests/fixtures 或 testutils 中提供 MemoryServices/WorkingMemoryService 工厂，但不在生产包内保留可调用单例。

## 验收与测试
- 禁用/移除全局 WorkingMemoryService 单例后，工作流与单测仍可运行。
- 覆盖可替换 `short_term_store_factory` 的注入测试，确保不同后端下 BaseAgent/辅助模块正常工作。
- 通过 lint/静态检查确认无残留 `get_working_memory_service` 生产路径依赖。
