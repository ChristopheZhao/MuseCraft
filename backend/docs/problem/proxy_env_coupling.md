# 代理环境变量耦合与兜底不一致问题

## 背景与前因
- 当前 HTTP 请求主要依赖 httpx 默认行为（`trust_env=True`），会自动读取进程环境中的 `HTTP_PROXY/HTTPS_PROXY/NO_PROXY`。
- 启动脚本 `start_dev_uv.py` 仅负责加载 `.env` 并补充 `NO_PROXY`，不会显式设置代理地址。
- 只有 `ZhipuLLMService` 在代理失败时尝试直连兜底，其他客户端（如 `zhipu_client`、`doubao_services`）没有兜底。

## 触发条件
- 进程环境中设置了 `HTTP_PROXY/HTTPS_PROXY`（例如 `http://127.0.0.1:10809`）。
- 代理端口未启动或不可达。

## 现象与后果
- `ZhipuLLMService` 会记录 “proxy connect error; fallback direct ...” 的警告，并可能直连成功。
- `zhipu_client` / `doubao_services` 在同一环境下直接抛出 `ConnectError`，导致部分流程中断。
- 行为不一致，难以确认实际走的是代理还是直连；同一流程可能出现“部分成功、部分失败”。
- 迁移到新环境时，`.env.example` 未明确说明代理策略，导致配置意图不清晰。

## 根因分析
- 网络策略没有集中配置，而是隐式依赖进程环境变量。
- 兜底逻辑仅存在于个别服务，导致不同工具的网络行为分叉。
- `NETWORK_DIRECT_FALLBACK_ON_TIMEOUT` 默认值为 `True`，但注释仍写“默认关闭”，易造成误解。

## 影响
- 代理不可用时出现局部失败，重试/超时策略难以统一。
- 合规/审计风险：在未知情况下可能发生直连。
- 排障成本上升：日志显示代理失败但结果仍成功，易误判网络路径。

## 复现步骤（示例）
1. 设置 `HTTP_PROXY/HTTPS_PROXY` 为本地代理端口（未启动或不可达）。
2. 触发包含 `ZhipuLLMService` 与 `zhipu_client`/`doubao_services` 的流程。
3. 观察前者警告后继续执行，后者直接报错。

## 建议方向（评估）
- 统一 HTTP 客户端/工厂，显式配置代理策略（信任环境 / 固定代理 / 禁用代理）。
- 在 `.env.example` 与 `ENV_SETUP.md` 中写明代理配置与 `NO_PROXY` 用法。
- 引入明确的运行模式：
  - 严格模式：代理不可用即失败（不直连）。
  - 弹性模式：可配置是否允许直连兜底。
- 可选：启动时检测代理可达性并 fail fast（严格模式下）。

## 证据与关联代码
- `backend/app/agents/tools/ai_services/zhipu_services.py`
- `backend/app/agents/tools/ai_services/zhipu_client.py`
- `backend/app/agents/tools/ai_services/doubao_services.py`
- `backend/app/core/config.py`
- `backend/scripts/start_dev_uv.py`
