# 项目模式 MVP 技术方案草稿

## 目标

在保留现有「≤60 秒快速创作」流程的前提下，引入多 Episode 长片项目模式（≥3 分钟），实现以下能力：

- SeriesPlanner 负责长片剧情拆解，输出结构化 `StoryPlan`。
- EpisodeOrchestrator 循环调度现有 MAS 1 分钟流水线，按 Episode 串联生成。
- 用户前端获得项目工作台，支持脚本确认、回滚、进度与成本可视化。

## 后端组件

### 新增数据结构

`backend/app/core/story_plan.py` 提供以下核心类型：

- `EpisodeStatus`：Episode 生命周期（draft/pending_approval/approved/generating/completed/...）。
- `EpisodePlan`：单个 Episode 的概要（标题、目标时长、剧情摘要、连续性提示、素材需求等）。
- `StoryPlan`：全局项目规划，包含 Episode 列表、角色设定、视觉风格、主题等共享信息。
- `EpisodeRuntimeState`：运行期状态（审批脚本、生成结果、累积成本、错误信息）。
- `ProjectState`：项目聚合状态（mode、StoryPlan、运行状态、预算与统计数据）。
- `ProjectStateRepository`：MVP 阶段使用内存存储，后续可替换为数据库或缓存服务。

### 新增 Agent

- `SeriesPlannerAgent` (`backend/app/agents/series_planner.py`)
  - 输入：`project_id`、`user_prompt`、`target_duration_seconds`、可选视觉/角色设定。
  - 输出：拆分后的 Episode 规划列表，并写入 `ProjectStateRepository`。
  - 默认把目标时长均分为 45–60 秒的 Episode，后续可注入 LLM 生成更细致的剧情梗概。

- `EpisodeOrchestratorAgent` (`backend/app/agents/episode_orchestrator.py`)
  - 输入：`project_id`、可选 `episode_ids`/`episode_indices`、`auto_approve`、`force_rerun`。
  - 逻辑：
    1. 从 `ProjectStateRepository` 读取 StoryPlan。
    2. 判定需要生成的 Episode（默认全部，或按参数筛选）。
    3. 将 Episode 状态切换为 `generating`，构造 Episode Prompt（整合全局主题、剧情摘要、原始用户需求）。
    4. 调用现有 `OrchestratorAgent` 运行 1 分钟流水线，捕获输出视频、质量检查结果。
    5. 更新 Episode/Project 运行状态与资产，支持失败后记录错误并保持可重试。

### API 草案

| Endpoint | 方法 | 功能 | 说明 |
| --- | --- | --- | --- |
| `/projects` | POST | 创建项目，指定 `mode=project` | 即时触发 SeriesPlanner，返回 StoryPlan 与 `project_id` |
| `/projects/{id}` | GET | 获取 StoryPlan 及 Episode 草案 | 包含审批状态与草稿脚本 |
| `/projects/{id}/episodes/{ep}/script` | PUT | 用户更新/确认 Episode 脚本 | 状态在 `pending_approval` ↔ `approved` 之间切换 |
| `/projects/{id}/orchestrate` | POST | 批量生成 Episode | 由 EpisodeOrchestrator 调用 MAS，可筛选 Episode |

> 当前后端已经实现 `/projects`、`/projects/{id}`、`/projects/{id}/episodes/{ep}/script`、`/projects/{id}/orchestrate` 四个接口，其余管理功能待下一阶段扩展。

事件通知可沿用现有 WebSocket 管线，新增 Topic：`episode.updated`、`project.updated`。

## 前端改动

### 双模式入口

- 保留「快速创作」：直接调现有 1 分钟链路。
- 新增「项目创作」：进入项目向导（填写 Brief → 触发规划 → Episode 看板）。
- 当前实现：控制台首页提供模式切换圆角按钮，`ProjectModeView` 负责项目创建、脚本审批与生成控制。

### 项目工作台

- Episode 看板状态流：`草案 → 待确认 → 生成中 → 完成/失败`。
- 脚本编辑器：SeriesPlanner 自动生成每集草稿（基于分集梗概与剧情使命），用户可修改、保存或确认后进入生成。
- 共享设定：角色卡、场景设定、视觉风格、BGM 主题，集中展示并允许批量修改。
- 成本/进度条：读取后端累计成本、剩余预算、Episode 完成数量。
- 管理操作：重跑 Episode、撤销确认、调整顺序（未来版本）。
- 当前 MVP：推荐总时长卡片（3/4/5/8 分钟）、自动分集草稿、脚本草稿/确认按钮、单集生成触发器、状态刷新与项目重置能力。

### 交互流程

1. 创建项目并设置目标时长（≥180 秒），触发 SeriesPlanner。
2. SeriesPlanner 返回 StoryPlan，前端呈现 Episode 列表与草案脚本。
3. 用户逐 Episode 编辑脚本并确认 → 后端标记为 `approved`。
4. 用户点击「生成 Episode」或「批量生成」，EpisodeOrchestrator 依序调用 MAS。
5. 生成完成后展示视频预览、质量结果；需要修改则回到脚本阶段重新生成。
6. 全部 Episode 完成后可触发最终拼接与导出。

## 后续扩展

- 将 `ProjectStateRepository` 替换为 Redis/数据库，支持并发项目与恢复。
- 引入 Episode 级脚本审稿工具（差分对比、注释回合）。
- Composer 支持跨 Episode 淡入淡出、统一 BGM、配音轨道合并。
- 成本与算力监控面板，结合付费计划提供动态报价。
- 自动测试：增加 StoryPlan schema 校验、Episode orchestration 集成测试。

## 测试与联调建议

- 后端：使用仓库中 `scripts/repro_detached_task.py` 验证数据库会话处理，新增项目 API 建议通过 pytest 或集成脚本覆盖创建、脚本更新与单集生成。
- 前端：使用 `uv run` 启动开发环境，确认模式切换、脚本编辑/确认、单集生成与状态刷新流程；必要时可引入 mock server 复现不同 Episode 状态。
- 手动回归：至少演练一次 3 集项目，逐集确认 → 生成 → 复核 → 重跑，记录成本与失败率供商业化评估。

该文档作为 MVP 的技术蓝图，后续迭代时需同步更新。MD
