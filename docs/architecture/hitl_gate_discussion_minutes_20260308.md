# HITL Gate 与 MAS 解耦讨论纪要

日期：2026-03-08

状态：讨论结论纪要

用途：作为后续综合评估与技术规划输入，不作为执行计划替代物。

说明：

- 本文档是讨论纪要，不承担正式架构术语定义
- 如与正式架构冲突，以 [single_episode_harness_architecture_20260311.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/architecture/single_episode_harness_architecture_20260311.md) 为准

## 1. 讨论背景

当前项目已经形成两条主路径：

- `quick mode`：本质上是单 `episode` 的 one-shot 生成链路。
- `project mode`：在外层增加多 `episode` 规划与调度，复用单集生成能力。

现状问题：

- 视频模型调用成本高，one-shot 链路在高成本节点缺少人工确认，返工代价高。
- `project mode` 已经具备一定脚本审批与单集生成能力，但尚未形成统一的节点级 `HITL review gate` 机制。
- 如果现在把 `HITL` 逻辑直接耦合进 `MAS` agent 或 prompt，后续随着模型能力提升，从“人工频繁确认”迁移到“少量门控 / 默认自动通过”会非常困难。

本次讨论目标：

- 判断是否应引入节点式 `HITL review gate`
- 明确 `HITL` 与 `MAS` 的解耦边界
- 明确 `quick mode` 与 `project mode` 的复用关系
- 形成后续技术规划的输入约束

## 2. 参会角色

- 产品负责人
- 前端/交互负责人
- 后端/工作流负责人
- 模型能力/成本负责人
- 系统架构负责人
- 算法工程师

## 3. 当前实现基础

与本次讨论直接相关的现状如下：

- `quick mode` 与 `project mode` 已在入口层分流：`src/pages/HomePage.tsx`
- `project mode` 已具备项目规划、脚本编辑、单集生成入口：`src/components/project/ProjectModeView.tsx`
- 路由层已体现 “单集内核 + 多集外层编排” 的雏形：`backend/app/core/mode_router.py`
- `project mode` 当前仍以 `episode` 级状态为主，缺少 node-level review 与局部重跑表达：`backend/app/api/v1/endpoints/projects.py`
- `ProjectStateRepository` 当前仍为内存实现，无法支撑持久化暂停、恢复、幂等补偿与长期 `HITL`：`backend/app/core/story_plan.py`

## 4. 各角色核心观点

### 4.1 产品负责人

支持：

- `gate` 要少而重，只放在高成本、高返工代价节点。
- 用户修改粒度应从“整片重来”下降到“局部返工”。
- `HITL` 应是稳定、可预期、可配置的产品规则，不能让 `MAS` 临时决定什么时候问人。

反对：

- 所有节点都加 review gate。
- 先整片自动生成，最后一次性给用户提意见。
- 把 quick mode 也做成重审批流。

最强挑战：

- 架构必须证明 review gate 可插拔，不能因为增删 gate 就重写 `MAS`。

### 4.2 前端/交互负责人

支持：

- “节点式执行，非节点式编辑”。
- 底层可以是 DAG，但默认 UI 不暴露 DAG，不让用户理解 agent/tool 粒度。
- `project mode` 应该演进为统一工作台：列表 + 当前待审产物 + 可执行动作。

反对：

- 暴露内部编排图或做画布式节点编辑器。
- 每个节点都停下来等确认。
- 用聊天流承载所有 review。

最强挑战：

- 前后端必须先把 `review contract` 定死，否则节点工作流会退化成后台调试器。

### 4.3 后端/工作流负责人

支持：

- 统一分层状态机：`project -> episode -> node(attempt)`。
- `quick mode` 与 `project mode` 复用同一单 `episode` 内核，不做两套编排。
- 引入两类一等节点：
  - `work node`
  - `review gate node`
- 所有重跑都新建 `attempt/revision`，不原地覆盖旧结果。
- API 需要升级为 control plane，而不是继续依赖粗粒度 `/orchestrate`。

反对：

- 把“何时停下来等人审”交给 `MAS/LLM/agent prompt`。
- 继续用 `episode` 级粗状态承载 node-level `HITL`。
- 后台线程 + 内存状态支撑长流程暂停/恢复。

最强挑战：

- 必须先定义“局部修改”的原子单位和失效传播规则，否则不会承诺局部重跑。

### 4.4 模型能力/成本负责人

支持：

- 双轨制 + 选择性 review gate。
- `gate` 只放在高成本且可显著纠偏的节点，例如：
  - `storyboard`
  - `keyframe / first frame`
  - `scene video`
- 用户反馈必须定位到“镜头 / 分镜 / 场景”，而不是“整片再来一版”。

反对：

- 全节点 review
- 只在最终成片 review
- 一处不满意就整片重生成
- 把 gate 逻辑耦合进 agent 推理

最强挑战：

- 如果高成本产物不能被拆成“可审、可定位、可局部重算”的稳定节点，`HITL` 只会放大等待时间和成本。

### 4.5 系统架构负责人

支持：

- 把 `review gate` 放在编排层 / control plane，建模为一等 `gate node`。
- agent 只负责产出候选结果、证据、自检信号。
- 是否进入人工审核、审核后继续/重试/回退，都由 orchestrator 驱动。
- agent 恢复执行时，仅把 review 结论当新的外部观察输入，不感知 `HITL` 机制本身。

反对：

- 把 review gate 下沉到 agent prompt、agent 状态、tool 或业务节点内部。
- 让前端拥有流程语义。

最强挑战：

- 如果 `gate node` 不是 control plane 原生概念，而只是普通节点加状态字段，`pause/resume/reject` 语义最终会泄漏回 agent。

### 4.6 算法工程师

支持：

- “少而重的 HITL gate + 节点式执行”，但编辑粒度必须是：
  - `shot`
  - `storyboard`
  - `scene`
- 局部修改仅在“可计算的影响闭包”内成立。
- 系统必须维护统一 `continuity state`，至少覆盖：
  - 角色外观
  - 服装
  - 场景
  - 时间
  - 镜头语言
  - 旁白语义
  - 音乐情绪
- 所有修改都需要 `revision lineage`。

反对：

- 把“局部修改”当默认承诺。
- 在未计算影响范围时仍向用户承诺“只改这一处”。

必须升级为 `replan` 的典型情况：

- 跨场景叙事意图变化
- 人物设定变化
- 时空设定变化
- 全片节奏/时长变化
- 镜头顺序变化
- 旁白主文案变化
- 全局风格基调变化

最强挑战：

- 谁主张“局部可改”，谁就必须证明：
  - 用户反馈能稳定锚定到镜头 / 分镜 / 场景
  - 连续性破坏能被自动检测
  - 何时必须强制升级为 `replan`

## 5. 已达成共识

### 5.1 架构原则

- `HITL` 必须与 `MAS` 解耦。
- `review gate` 属于 workflow / control plane 能力，不属于 agent 内部行为。
- `MAS` 负责生成候选，不负责决定何时问人。
- `replan` 必须是显式升级动作，不能靠 agent 从自由文本反馈中隐式猜测。

### 5.2 产品与交互原则

- `gate` 要少而重，只放高成本节点。
- UI 应呈现“节点式执行”，但不暴露底层 DAG 细节。
- 用户可理解的对象应是 `episode / scene / storyboard / scene video`，不是 agent/tool。
- review 动作需要收敛，不能放任自由扩张。

### 5.3 工作流与状态原则

- `quick mode` 与 `project mode` 应复用同一单 `episode` 工作流内核。
- `project mode` 只是多 `episode` 的外层编排。
- 所有重跑都应保留 `attempt/revision lineage`。
- 后续必须支持 node-level 状态、局部失效、局部重跑、持久化暂停与恢复。

### 5.4 算法与连续性原则

- “局部修改”只在影响范围可计算时才成立。
- 系统需要显式维护 `continuity state`，而不是只做状态机不做连续性约束传播。
- 任何超出局部影响闭包的修改都应升级为 `replan`。

## 6. 仍未最终拍板的问题

以下问题需要在综合评估中明确：

1. `quick mode` 默认是否完全自动通过 gate，还是保留 1 个可选关键 gate。
2. 第一阶段最值得设 gate 的节点组合是什么：
   - `storyboard + scene_video`
   - `keyframe + scene_video`
   - `storyboard + scene_video + final compose`
3. “局部修改”的最小原子单位最终定在：
   - `scene`
   - `shot`
   - `storyboard node`
4. durable runtime 的落地顺序：
   - 先 `DB + queue`
   - 还是直接引入 `Temporal`
5. review 动作集合是否收敛为：
   - `approve`
   - `revise`
   - `replan`
   或需要额外加入：
   - `reject`
   - `pause`
   - `cancel`

## 7. 后续技术规划必须回答的问题

后续规划阶段必须基于本纪要回答以下问题：

### 7.1 交互层

- 用户进入 `project mode` 后，默认看到的工作台结构是什么？
- 每个 review 节点对用户必须展示哪些信息？
- 用户如何理解“局部修改会影响哪些下游节点”？

### 7.2 架构层

- `gate node` 如何作为 control plane 原生概念落地？
- orchestrator 如何暂停、恢复、拒绝与重跑，而不把控制语义泄漏回 agent？
- `quick mode` 与 `project mode` 共享内核的边界如何定义？

### 7.3 后端层

- node-level 状态机如何定义？
- `attempt/revision lineage` 如何存储？
- `review decision`、`rerun`、`command` API 如何设计？
- 暂停/恢复/失败补偿的持久化语义如何保证？

### 7.4 算法层

- `continuity state` 如何建模、更新与传播？
- 哪类反馈可局部修复，哪类必须升级为 `replan`？
- 连续性破坏是否可自动检测，最小可行检测器是什么？

## 8. 规划输入结论

本次讨论不建议再继续发散式争论。下一步应进入：

1. 综合评估
2. 评估结论收口
3. 基于结论生成正式技术规划

规划时应默认采用以下前提：

- `MAS Core`、`Gate Layer`、`Policy Layer` 三层分离
- `quick mode = 单 episode 内核 + 更轻 gate policy`
- `project mode = 多 episode 编排 + 同一单 episode 内核`
- `HITL` 逐步向“少量门控 / 高置信自动通过 / 低置信介入”迁移

## 9. 附注

本纪要刻意不展开执行排期、里程碑与任务拆分。那部分应在综合评估完成后，以正式技术规划文档单独输出。
