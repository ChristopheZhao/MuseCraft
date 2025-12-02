# Agent 使用 WorkingMemory 的规范与重构方案（聚焦 WM）

## 背景与问题
- 短期记忆（WorkingMemory）是 MAS/Agent 事实与轨迹的承载，但当前 Agent 通过全局单例 `get_working_memory_service()` 直接访问，隐式依赖、耦合度高，不利于测试/替换存储后端。
- MemoryServices 注入存在，但短期路径未使用，依赖注入原则被破坏；Agent 上直接暴露 `wm` 等句柄，未来若长记忆等也照此暴露，会放大耦合面。
- 虽已引入存储抽象（ShortTermMemoryStore）与领域适配器（VideoMemoryAdapter），但访问路径仍绑定单例，抽象层与应用层间缺少注入封装。

## 当前状态校准
- ✅ MemoryServices dataclass 已存在，但缺少短期服务字段。
- ✅ WorkingMemoryService 已支持 store_factory，ShortTermMemoryStore 抽象已落地。
- ✅ Orchestrator 在构造各 Agent 时注入同一份 memory_services。
- ❌ BaseAgent 的短期记忆访问仍走全局单例（base.py:166/189）。
- ❌ memory_helpers、快照导出等辅助模块仍通过全局单例获取 WM。
- ❌ 尚未提供注入式短期服务字段，导致注入路径与全局路径并存。

## 目标
- 短期记忆通过注入的 WorkingMemoryService/MemoryServices 管理，移除硬编码单例依赖，保持 MAS/Agent 单一通道（scope 区分）。
- 记忆模型与应用层解耦：Agent 通过受保护接口/Helper 访问，不直接暴露底层服务句柄；scope 继续用 `mas:{wf_id}` / `agent:{wf_id}:{agent}`。
- 支持可替换存储后端：ShortTermMemoryStore 抽象 + store_factory 注入，默认内存后端，可按需替换。

## 分层与角色
- **基础实现层**：短期存储后端（ShortTermMemoryStore 及实现，如 in_memory；slot 等可选后端需适配后启用）。
- **抽象层**：WorkingMemory 模型 + 领域适配器（VideoMemoryAdapter 等）；MemoryServices 持有短期/长期服务实例。
- **应用层**：Agent/工具/编排，通过注入的服务/Helper 访问 WM，不触碰存储实现；MAS/Agent 作用域由 scope 管理。

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
- **Phase 1（P0，短期服务注入）**
  - backend/app/services/memory_provider.py：MemoryServices dataclass 新增 short_term 字段；`build_memory_services` 构造 short_term，移除 `set_working_memory_service` 调用。
  - backend/app/agents/base.py：`wm`/`memory_write` 改用注入的 short_term_service，清理全局单例引用。
  - backend/app/agents/orchestrator.py：初始化 MAS/Agent WM 时改用注入的 short_term_service，不再调用全局单例。
  - 覆盖基础单测：BaseAgent 在无全局单例时可正常读取/写入 WM；自定义 store_factory 能被注入。
- **Phase 2（P1，辅助模块去全局）**
  - backend/app/agents/utils/memory_helpers.py：改为接受 MemoryServices/WorkingMemoryService（参数或构造注入，必填），删除全局单例使用；更新调用方。
  - backend/app/agents/memory/long_term/snapshots.py 及工具 provider：同上，改为注入获取 WM。
  - 运行/补充集成测试，验证无全局 WM 依赖下的快照导出与工具使用。
- **Phase 3（P1，守护与验证）**
  - 静态检查：全局搜索生产路径不再出现 `get_working_memory_service` 引用；删除 `memory.short_term.registry` 的生产导出（保留时直接抛异常，防止误用）。
  - 清理 `memory/short_term/__init__.py` 等 re-export 入口，避免新代码误用单例。
  - 覆盖工厂替换测试：短期存储切换（内存 → 自定义后端）不影响 Agent/辅助模块。
  - CI 增加无全局单例模式下的冒烟用例（可通过禁用 registry 默认实例来验证）。
- **Phase 4（P2，可选收敛）**
  - 收敛 BaseAgent 公开的长记忆句柄（memory_manager 等）：改为受控 helper/接口，只保留 MemoryServices 作为注入入口，避免子类直接操作底层管理器。

## 风险与注意事项
- 确保 MAS/Agent scope 唯一性不变（mas:{wf} / agent:{wf}:{agent}），仅替换服务来源。
- 移除全局单例后，遗漏注入会直接报错，需在构造/调用链保证 memory_services 提供到位。
- 存储后端可替换（ShortTermMemoryStore），但仍需遵循单一通道读写 MAS/Agent WM。
 - 测试便利：若需复用构造，可在 tests/fixtures 或 testutils 中提供 MemoryServices/WorkingMemoryService 工厂，但不在生产包内保留可调用单例。

## 验收与测试
- 禁用/移除全局 WorkingMemoryService 单例后，工作流与单测仍可运行。
- 覆盖可替换 `short_term_store_factory` 的注入测试，确保不同后端下 BaseAgent/辅助模块正常工作。
- 通过 lint/静态检查确认无残留 `get_working_memory_service` 生产路径依赖。
