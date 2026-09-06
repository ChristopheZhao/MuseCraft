# 文档入口

本文按职责指向现行约束，不复制架构规则或计划状态。历史方案不能作为待执行队列；冲突按相同职责与适用范围核对，不按更新时间自动决定。

## 当前约束

| 领域 | 入口与适用范围 |
| --- | --- |
| Agent 开发原则 | [根指令](../AGENTS.md)、[后端状态边界](../backend/AGENTS.md) |
| 单集架构与术语 | [Single-Episode Harness](architecture/single_episode_harness_architecture_20260311.md)、[术语对齐](architecture/mas_architecture_alignment_note_20260323.md) |
| Runtime 状态与存储 | [runtime 设计](architecture/mas_runtime_control_plane_detailed_design_20260308.md)、[存储边界](architecture/runtime_control_plane_store_boundary_20260719.md) |
| Agent / 数据库 / 应用层 | [数据库与 Agent 隔离](architecture/backend_database_agent_boundary_freeze_20260718.md)、[项目与 runtime 权威边界](architecture/project_runtime_authority_boundary_20260719.md) |
| 场景、规划与交付 | [SceneContract v2](architecture/scene_contract_v2_freeze_20260329.md)、[规划/执行/交付/进度边界](architecture/planner_execution_output_progress_boundary_freeze_20260402.md) |
| 报告、失败处置与最终发布 | [PLAN-069 A1–A5](plans/active/PLAN-20260808-069.md)：partial/failed 的接纳、处置、promotion 分属不同边界；旧 completed-only 协议规则按该计划的明确替代范围理解。实施与验收进度见计划索引，不能从规范推断已验收。 |
| 记忆与上下文 | [编排/上下文/记忆边界](architecture/orchestration_context_memory_boundary_freeze_20260330.md)、[长期迁移护栏](deferred-plans/CURRENT.md) |
| 创作与角色一致性 | [角色身份合同](architecture/character_identity_contract_v1_freeze_20260510.md)、[PLAN-065](plans/active/PLAN-20260510-065.md) |
| 工具与合成 | [Composer 指南](agents/composer_guidelines.md)、[ReAct 提示原则](agents/react_prompting_guidelines.md) |
| 数据库配置与部署 | [统一组装边界](architecture/database_composition_boundary_20260719.md)、[迁移](database-migrations.md)、[部署](deployment/deployment-guide.md) |
| 测试与证据 | [测试策略](testing.md)、[后端测试入口](../backend/tests/README.md) |

## 计划与文档治理

- [执行计划索引](plans/PLAN_INDEX.json) 是生命周期记录；计划正文状态是镜像。完成记录不能替代当前版本的运行证据。
- [Deferred 索引](deferred-plans/DEFERRED_PLAN_INDEX.json) 独立管理延期架构护栏；CURRENT 是摘要。
- [文档维护规则](governance.md) 定义替代关系、附件归属、证据锚点与本地/CI 检查范围。
- [本轮治理计划](plans/active/PLAN-20260906-070.md) 记录治理执行进度，不接管业务架构或 PLAN-069 验收。

## 使用与历史资料

新开发者先读 [项目 README](../README.md) 和上述职责表，再进入具体代码。部署可参考 [后端启动](../backend/README.md) 与 [Windows/WSL](deployment/windows-native-setup.md)。

以下仅为历史研究材料，不能用于选择当前实现路径：

- [早期 Pipeline/ReAct 设计比较](architecture/agent-design-patterns.md)
- [早期 MAS 分析](architecture/multi-agent-system-analysis.md)
- [旧通信快照](architecture/multi-agent-communication-architecture.md)
- [项目模式 MVP 草稿](architecture/project_mode_mvp.md)
- [旧两段式工具调用提案](URGENT/video_agent_two_stage_migration.md)

更新日期：2026-09-06
