# 记忆服务命名与职责错配

## 问题概述
- 短期记忆使用 `WorkingMemoryService`，职责清晰（scope 化短期 WM 管理）。
- （已重命名）长期记忆实现改为 `LongTermMemoryManager`，名称体现 long-term 语义。
- 缺少对称/抽象层命名：短期是 *Service，长期却是 *Manager，容易混淆长短期边界和管理职责。
- BaseAgent 仍裸露 `memory_manager` 等句柄，强化了“Manager = 总管”这一误导。

## 风险
- 概念混淆：开发者误以为 MemoryManager 统一管理长短期，可能错误使用或绕过预期接口。
- 重构阻力：命名错配会干扰后续封装（如只暴露 helper、禁用裸句柄）。
- 接口不对称：短期/长期暴露方式不同，破坏一致性，易引入耦合。

## 原因分析
- 命名历史导致的错位：WorkingMemoryService 已明确短期职责，MemoryManager 早期命名已重命名为 LongTermMemoryManager 以消歧。
- 边界模糊：名称不对称使开发者难以分辨“短期 vs 长期”接口，可能绕过预期的封装/协调层。
- 可替换性受损：长记忆实现被直接暴露为 “manager”，调用方可能绑定具体实现，降低后续替换/扩展（如切换长记忆后端、引入策略层）的灵活性。
- 治理成本：在收敛暴露、禁用单例的同时，如果命名继续混淆，会增加代码审阅和培训成本，影响新成员理解。

## 建议方向（后续重构）
- 调整命名/封装：将长期实现重命名或封装为 `LongTermMemoryService/Manager`，与 `WorkingMemoryService` 对称；保留 MemoryCoordinator/MemoryServices 作为组合/协调层，统一入口。
- 收敛暴露：BaseAgent 不再裸露 `memory_manager` 等，改为受控 helper/接口，避免直接操作底层实现，方便未来替换长记忆后端或增加治理策略。
- 文档同步：在规划文档中澄清短期/长期职责与命名，明确 LongTermMemoryManager 代表长记忆实现，避免被误认为统一管理器。
