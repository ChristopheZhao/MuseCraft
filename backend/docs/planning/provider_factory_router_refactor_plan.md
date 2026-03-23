标题: 多 Provider 协同下的 Provider Factory + Router 重构计划
状态: Draft
范围: service_interfaces + video_config_manager + video_generation_tool_v2 + provider services/tests

## 1. 背景问题
- 当前实现可运行，但结构上更接近“注册表 + Service Locator + 分散选择逻辑”，不是完整的工厂/路由分层。
- provider 解析逻辑分散在多个位置，存在重复与漂移风险（ServiceManager / zhipu_services / zhipu_client）。
- 回退逻辑偏“可用即回退”，能力约束不完整（模式、音频、首尾帧、模型配置）容易被绕过。
- 单服务内多 provider 协同（按能力与成本动态选择）缺少统一路由契约。

## 2. 目标
1) 建立统一 ProviderFactory（实例创建）与 ProviderRouter（请求路由）双层结构。
2) 将 provider 选择从“配置分散 if/else”收敛为“契约驱动路由决策”。
3) 保证多 provider 协同场景下，按请求能力选择 provider，不因无关 provider 配置失败。
4) 去除工具层硬编码 vendor fallback，统一交给路由层决策并输出可审计原因。

## 3. 非目标
- 不改 Orchestrator 的 ReAct 主循环。
- 不改业务层任务分解策略（保持 fail-fast）。
- 不引入分布式调度或跨进程编排。

## 4. 目标架构
### 4.1 ProviderFactory（创建层）
- 职责: 统一 provider adapter 的注册、实例化、缓存与健康检查。
- 输入: provider_key（如 `doubao` / `cogvideox-3`）。
- 输出: 对应 `VideoModelServiceInterface` 实例。

### 4.2 ProviderRouter（选择层）
- 职责: 根据请求能力与 provider capability 选择执行 provider 与模型。
- 输入: RoutingRequest（mode/duration/audio requirement/first-last support/preferred provider）。
- 输出: RoutingDecision
  - `provider_key`
  - `model`
  - `fallback_chain`
  - `reason`

### 4.3 统一契约
- 请求契约 `RoutingRequest`：
  - `mode`: `text_to_video|image_to_video|first_last_frame`
  - `duration`
  - `need_native_audio`
  - `preferred_provider`（可选）
- 决策契约 `RoutingDecision`：
  - `provider_key`
  - `resolved_model`
  - `supports_native_audio`
  - `fallback_candidates`
  - `decision_reason`

## 5. 分阶段改造
### Phase 1: 契约与注册中心收敛
- 新增 `provider_router.py`（或同层命名）定义 `RoutingRequest/RoutingDecision/ProviderRouter`。
- ServiceManager 仅保留“注册 + 获取实例”职责，不再包含环境变量映射细节。
- provider 字符串映射规则集中到一个入口，移除多处重复映射。

### Phase 2: 路由接管视频 provider 选择
- 新增 `get_video_service_by_route(request)`（或等效接口），先路由再取服务实例。
- `get_video_service()` 退化为兼容快捷入口，内部复用路由层默认请求，不直接做复杂判定。
- 路由输出结构化日志：`provider_route_decision`（provider/model/reason/fallback_chain）。

### Phase 3: 工具层去硬编码 fallback
- `video_generation_tool_v2` 不再直接 fallback 到指定 vendor 工具。
- 工具层通过 Router 获取候选链路并执行，失败时按 `fallback_candidates` 有限重试。
- 失败统一透传 `routing_decision` 与 `fallback_reason`，保证可观测。

### Phase 4: Provider service 收敛
- `zhipu_services.py` / `doubao_services.py` 保留 provider adapter 职责，只消费传入 model 与能力参数。
- 删除/下沉重复 provider_key 选择逻辑，避免 service 内再次决策 provider。
- 统一模式模型解析入口（`resolve_model_for_mode` 由 Router 或 ConfigManager 驱动）。

### Phase 5: 测试与回归
- Router 单测矩阵：
  - mode x provider capability x config completeness
  - 多 provider 可用/部分不可用/模型未配置
- 工具回归测试：
  - 无关 provider 配置缺失不影响当前 provider 请求
  - fallback 按链路生效且 reason 可追踪
  - `supported_models` 不出现空值，能力输出合法

## 6. 分 Commit 计划
1. `重构(provider): 引入统一路由契约与ProviderRouter骨架`
2. `重构(service-manager): 收敛provider映射与服务获取职责`
3. `重构(video-tool): 采用路由决策执行并移除硬编码vendor回退`
4. `重构(provider-services): 下沉模式模型解析并清理重复provider决策`
5. `测试(provider-routing): 补充路由矩阵与多provider回归用例`

## 7. 验收标准
- provider 选择逻辑仅有单一来源（Router），不再分散在多个 service/tool。
- 同一服务可按请求能力在多个 provider 间选择，且决策可审计。
- 不再出现“请求 A 模式却因 B 模式模型缺失失败”的配置耦合问题。
- fallback 行为由路由层统一管理，工具层不含 vendor 特化硬编码。

## 8. 风险与缓解
- 风险: 改造触及入口层，影响面大。
- 缓解:
  - 按 commit 分阶段推进，每阶段保留可回滚点；
  - 先上路由只读日志，再切执行路径；
  - 回归测试覆盖“模式/能力/配置缺失/回退链路”核心组合。
