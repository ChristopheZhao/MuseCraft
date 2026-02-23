标题: Orchestrator 从固定队列到 Agenda 动态编排的后续计划
状态: Deferred（下一次提交后启动）
范围: orchestrator 调度模型 + 任务图契约 + 回归测试

## 背景
- 当前中心化编排仍以 `workflow_order` 固定队列推进，运行中通过门控跳过部分 agent。
- 该模式可用，但随着模型能力增长，容易在 Orchestrator 中累积大量“是否跳过”规则，削弱可扩展智能。

## 本轮决策（已确认）
1) 本次提交保持现有队列模型，优先完成音频/配音能力路由改造与回归修复。
2) 固定队列重构为 agenda 动态任务池，放到下一次提交执行，避免本轮变更面过大。

## 待解决问题
1) “执行顺序”与“能力选择”耦合过高，导致策略演进需要改主循环。
2) 运行中跳过规则增多，会把编排器推向预定义 pipeline。
3) 缺少统一的 `ready tasks` 选择机制（依赖、优先级、成本、事实完整度）。

## 下一阶段目标
1) 将“按 agent 顺序执行”升级为“按任务意图执行”。
2) 引入 `agenda`（动态任务池）与 `task graph`（依赖图）契约。
3) 将执行期门控收敛到少量硬保障：交付缺失、质量失败、超时重规划。

## 迁移边界
- 保留中心化 orchestrator，不做去中心化重写。
- 保留 ReAct 子 agent 内部 observe→plan→act→reflect 循环。
- 不在本阶段引入跨进程分布式调度。

## 执行拆分（下次提交建议）
### Phase 1: 引入执行计划契约（兼容队列）
- 新增 `execution_plan`：
  - `active_agents`
  - `task_sequence`
  - `conditional_tasks`
  - `fallback_workflow_order`
- 主循环优先消费 `task_sequence`，缺失时回退 `workflow_order`。

### Phase 2: 引入 agenda 选择器
- 新增 `agenda` 数据结构：
  - `pending`
  - `ready`
  - `running`
  - `blocked`
  - `completed`
- 将“下一步执行谁”从 `for agent in workflow_order` 改为 `select_ready_task(...)`。

### Phase 3: 失败补偿与重规划
- 当关键事实失败（如音频不可用、成片质量不达标）时，不堆 skip 规则，触发有限重规划。
- 保持 fail-fast 上限，避免无限补偿循环。

## 验收标准
1) 正常流程不依赖固定队列顺序也可完成。
2) 新增能力无需改主循环，只需扩展任务图/能力契约。
3) 执行期中途跳过规则显著减少，调度逻辑可解释。
4) 保持现有核心回归（成片、音频、配音）通过。

## 风险与缓解
- 风险: 调度模型改动影响面大。
- 缓解:
  - 先做“契约 + 兼容模式”，后切默认路径；
  - 每阶段均保留可回退开关；
  - 增加调度可观测日志与最小集成测试。
