标题: 基于模型能力增长的音频/配音编排自适应改造计划
状态: 草案
范围: orchestrator + video_config_manager + video_generation_tool_v2 + doubao_services + composition_tool + adapters + tests + .env.example

## 背景与问题
- 当前链路已支持 `VIDEO_AUDIO_STRATEGY`，能在 provider 支持原生音频时跳过 `AUDIO_GENERATOR`，但 `VOICE_SYNTHESIZER` 尚未纳入同层级能力决策。
- provider 能力契约仅到 `supports_native_audio` 粒度，无法表达“是否支持可控配音、多人对白、精确时序”等关键差异。
- `conditional_tasks` 当前对 `video_composer_bgm_mix` 为全局硬要求，不符合“按路由需要才强制”的编排原则。
- 任务分解已改为严格 fail-fast，这是正确方向，后续改造必须保持该策略，不引入伪规划兜底。

## 目标
1) 将配音链路纳入编排前置决策，形成能力驱动路由，而非固定流程。
2) 用“能力契约 + 需求契约 + 路由契约”替代模型名硬编码分支。
3) 保持 Orchestrator 规划失败即终止，避免高成本错误执行。
4) 将 `conditional_tasks` 改为条件必需，不做全局硬约束。

## 非目标
- 不重写现有 ReAct 主循环。
- 不引入针对单一模型的特例 if/else。
- 不改变现有 memory SoT 基本结构（仅新增必要路由事实）。
- 本轮不重构中心化编排的固定队列执行模型（`workflow_order` 仍保留）。

## 契约设计
### 1) Provider 音频能力契约（配置层）
- 新增字段（示例）：
  - `supports_native_audio`
  - `supports_native_voiceover`
  - `supports_multi_speaker`
  - `supports_voice_identity_control`
  - `supports_precise_timing`
  - `native_audio_param_name`
- 产出位置：
  - `VideoProviderConfig` dataclass
  - `get_provider_audio_capability()`
  - `get_system_duration_capability()` 扩展字段透出

### 2) 工作流音频需求契约（编排层）
- 统一写入 `workflow.audio_requirements`（示例）：
  - `need_bgm`
  - `need_voiceover`
  - `need_brand_voice`
  - `need_precise_timing`
  - `need_multi_speaker`
- 来源优先级：
  - 用户显式输入 > concept/voice_plan 推导 > 系统默认。

### 3) 音频路由契约（编排层）
- 统一写入 `workflow.audio_route`（示例）：
  - `mode`: `provider_full` | `provider_audio_mas_voice` | `mas_full` | `hybrid`
  - `run_audio_generator` (bool)
  - `run_voice_synthesizer` (bool)
  - `video_generate_audio` (bool)
  - `required_conditional_tasks` (array)
  - `decision_reason` (string)

## 编排改造主线
1) 预路由：在任务分解前计算 `audio_route` 并写入 MAS SoT。
2) 规划输入：将 capability + requirements + route 注入 `_llm_decompose_tasks` 提示。
3) 条件任务门控：仅对 `route.required_conditional_tasks` 做必需校验。
4) 执行门控：`_should_run_agent` 优先按 `audio_route` 决定 `AUDIO_GENERATOR` 与 `VOICE_SYNTHESIZER`。
5) 工具透传：`video_generation_tool_v2` 与 provider service 使用 `video_generate_audio` 决策，`composition_tool` 使用路由决策 `preserve_audio`。

## 提交拆分（执行顺序）
### Commit 1: capability contract 扩展
- 目标: 扩展 provider 音频能力表达，打通配置读取。
- 文件:
  - `backend/app/core/video_config_manager.py`
  - `backend/app/core/config.py`
  - `.env.example`
- 验收:
  - 能从统一接口读到完整音频能力字段；
  - 默认值向后兼容，旧 provider 不报错。

### Commit 2: orchestrator 音频需求/路由预计算
- 目标: 在 Orchestrator 前置生成 `workflow.audio_requirements` 与 `workflow.audio_route`。
- 文件:
  - `backend/app/agents/orchestrator.py`
  - `backend/app/agents/adapters/state/`（新增 route resolver）
- 验收:
  - workflow 启动后可在 MAS WM 看到 `workflow.audio_route`；
  - 日志出现可审计 `AUDIO_ROUTE_DECISION` 记录。

### Commit 3: 规划门控与 conditional_tasks 条件必需
- 目标: 按 route 强制条件任务，不再全局强制 `video_composer_bgm_mix`。
- 文件:
  - `backend/app/agents/orchestrator.py`
- 验收:
  - route 不需要 BGM 时，缺少 `video_composer_bgm_mix` 不失败；
  - route 需要 BGM 时，缺失则 fail-fast；
  - 保持任务分解失败即终止，不启用 fallback task。

### Commit 4: 工具链路由对齐（视频生成/合成）
- 目标: 工具层消费路由，统一 `generate_audio/preserve_audio` 行为。
- 文件:
  - `backend/app/agents/tools/ai_services/video_generation_tool_v2.py`
  - `backend/app/agents/tools/ai_services/doubao_services.py`
  - `backend/app/agents/tools/video_composition/composition_tool.py`
- 验收:
  - provider_full 路由可开启原生音频；
  - mas_full 路由强制关闭 provider 原生音频；
  - 合成阶段音轨保留策略与路由一致。

### Commit 5: voice 分支激活逻辑收敛
- 目标: `VOICE_SYNTHESIZER` 激活逻辑改为“route 优先，voice_plan 补充”。
- 文件:
  - `backend/app/agents/orchestrator.py`
  - `backend/app/agents/adapters/memory_views.py`
  - `backend/app/agents/adapters/state/agent_outputs.py`
- 验收:
  - 严格配音需求下即使 provider 支持有声也会触发 voice agent；
  - 非严格需求且 provider_full 时，voice agent 可跳过。

### Commit 6: 测试与可观测性补齐
- 目标: 增加路由矩阵、条件任务门控、回归用例。
- 文件:
  - `backend/tests/unit/`（新增 route resolver 与 orchestrator gate 测试）
  - `backend/tests/integration/`（新增 provider_full / mas_full 核心流）
- 验收:
  - 至少覆盖 4 类路由：provider_full / provider_audio_mas_voice / mas_full / hybrid；
  - 条件任务门控与 fail-fast 行为有断言。

## 建议提交信息（可直接使用）
1. `feat(audio-capability): extend provider audio/voice capability contract`
2. `feat(orchestrator): add preflight audio requirements and route decision`
3. `refactor(orchestrator): gate conditional_tasks by audio route requirements`
4. `refactor(tools): align native-audio and compose preserve-audio with route`
5. `refactor(orchestrator): route-first activation for voice/audio agents`
6. `test(orchestration): add audio-route matrix and conditional-task gate coverage`

## 风险与回滚
- 风险: 路由规则错误导致 agent 误跳过或误执行。
- 缓解:
  - 每次路由决策写入 `workflow.audio_route` + 结构化日志；
  - Commit 粒度回滚，优先回滚最近路由逻辑提交（2/3/5）。
- 回滚策略:
  - 保留旧 `VIDEO_AUDIO_STRATEGY` 作为最低兼容路径；
  - 出现线上异常时可临时切 `mas_only` 保证可控输出。

## 完成判定
- 在同一代码基线下，能根据 provider 能力与任务需求自动切换是否编排 `VOICE_SYNTHESIZER` / `AUDIO_GENERATOR`。
- `conditional_tasks` 仅在路由需要时强制。
- 规划失败仍严格终止，无 fallback 伪规划执行。

## 后续衔接（下一次提交）
- 固定队列向动态任务池（agenda）迁移不在本计划内，单独跟踪为后续改造项：
  - `backend/docs/planning/orchestrator_queue_to_agenda_followup.md`
