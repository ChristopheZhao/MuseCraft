# MuseCraft

MuseCraft 是一个面向短视频创作的多智能体应用。系统把概念规划、剧本、画面、视频、配音、合成和质量检查组织为可观测的 MAS runtime，并通过显式 gate 与 read model 向前端投影进度。

> 当前处于活跃开发阶段。公开发布路径以 PostgreSQL、Python 3.11、uv 和 Node.js 18.18+ 为准。

![MuseCraft console](public/marketing/musecraft-console.png)

## 核心边界

- MAS control plane 是 session、node、attempt、gate 和 decision 的运行时事实源。
- Celery/Redis 只承担传输与执行容器职责，不决定业务状态。
- Agent 通过注册工具访问外部服务，通过 ContextAssembler/MemoryWriter 读写上下文。
- 前端只消费 runtime/read-model 投影，不从队列状态推断业务完成度。
- 媒体完成以 scene-output acceptance contract 为准，不以非空 URL 代替验收。

## 架构

```text
Next.js UI
    |
FastAPI read/write API
    |
MAS control plane ---- PostgreSQL (runtime source of truth)
    |
Native agents ---- registered tools ---- configured AI/media providers
    |
Redis/Celery (transport and execution only)
```

## 前置条件

- Python 3.11
- [uv](https://docs.astral.sh/uv/)
- Node.js 18.18+ 与 npm
- PostgreSQL 15+ 和 Redis 7+
- FFmpeg/ffprobe
- 可选：Docker Engine 与 Docker Compose v2

Windows 开发建议使用 WSL2 Ubuntu；仓库脚本和 CI 以 Linux 兼容行为为准。

## 快速启动

### 1. 配置

```bash
cp .env.example .env
cp .env.local.example .env.local
```

至少修改 `.env` 中的 `SECRET_KEY`，并配置一个实际使用的 AI provider。`.env` 和 `.env.local` 都不会进入 Git。

### 2. 使用 uv 启动后端

先确保本机 PostgreSQL 和 Redis 已启动。`DATABASE_PROFILE=local` 是默认配置；未提供 `DATABASE_URL` 时，后端使用文档化的本机开发 URL，`.env.example` 也显式给出同一配置。uv 管理 Python 应用与依赖，不替代数据库、Redis 或 FFmpeg 这些系统服务。当前公开 runtime 只支持 PostgreSQL；历史 MySQL 数据库不能由 release baseline 自动接管，处理方式见 [数据库迁移说明](docs/database-migrations.md)。

```bash
uv sync --project backend --frozen
uv run --project backend --frozen python backend/scripts/start_dev_uv.py
```

`--project backend` 以 `backend/pyproject.toml` 为项目入口，uv 默认在 `backend/.venv` 创建和使用虚拟环境。仓库根目录 `.venv` 不属于当前后端运行合同，也不应与 `backend/.venv` 混用。

只验证 uv、Python 版本和 canonical `backend/.venv` 时使用：

```bash
uv run --project backend --frozen python backend/scripts/start_dev_uv.py --environment-check
```

该模式不连接 PostgreSQL/Redis、不执行 Alembic migration，也不检查或启动后台进程。它只回答 uv 后端环境是否正确。

launcher 会渲染统一 database composition preflight 的 typed diagnostic，随后检查 Redis 并执行 Alembic migration；成功后才启动 API、Celery worker 和 beat。任一服务启动失败都会整体失败并清理已启动进程。API 默认监听 `http://localhost:8000`，按 `Ctrl+C` 可停止这组本地进程。

### 3. 启动前端

```bash
npm ci
npm run dev
```

浏览器访问 `http://localhost:3000`。

## Docker 可选启动

需要由容器同时提供 PostgreSQL、Redis 和后端服务时，可改用：

```bash
docker compose -f backend/docker-compose.yml up --build
```

Compose 同样会先运行 Alembic migration，成功后再启动 API、worker 和 beat。Docker 不是本地开发的唯一启动方式。

生产部署必须显式设置 `DATABASE_PROFILE=production` 和远程 PostgreSQL 配置；production profile 会拒绝缺失 URL、localhost 和已知开发凭据。

## 本地后端开发

只开发 API、不执行异步生成任务时，可单独运行：

```bash
uv sync --project backend --frozen --extra dev --extra test
uv run --project backend alembic -c backend/alembic.ini upgrade head
uv run --project backend uvicorn app.main:app --app-dir backend --reload
```

完整生成流程必须同时运行 worker；请使用快速启动中的 uv launcher。可用 `--check` 检查 PostgreSQL、Redis 和 migration，而不启动长期服务；数据库失败不表示 uv 环境失败：

```bash
uv run --project backend --frozen python backend/scripts/start_dev_uv.py --check
```

`backend/pyproject.toml` 与受跟踪的 `backend/uv.lock` 是依赖事实源。`backend/requirements.txt` 仅是由 uv 自动导出的兼容清单，不能手工维护。

## 数据库迁移

公开 release migration 位于 `backend/alembic/release_versions/`。新环境执行：

```bash
uv run --project backend alembic -c backend/alembic.ini upgrade head
uv run --project backend alembic -c backend/alembic.ini check
```

早期本地 MySQL migration 从未进入版本控制，不能作为公开升级链。已有数据库请先阅读 [数据库迁移说明](docs/database-migrations.md)，不要在未比对 schema 时直接 `alembic stamp`。

## 验证

```bash
npm run lint
npm run type-check
npm test
npm run build

uv run --project backend pytest -q \
  backend/tests/unit/test_env_loading.py \
  backend/tests/unit/test_release_migration_contract.py
```

GitHub Actions 还运行 PLAN-066 对应的 MAS control-plane/runtime 回归、Agent/transport/persistence architecture guards，以及真实 PostgreSQL runtime 事务合同。测试分层与当前非门禁 legacy suite 见 [测试策略](docs/testing.md)。

## 配置原则

- 后端配置：仓库根目录 `.env`，模板为 `.env.example`。
- 前端公开配置：仓库根目录 `.env.local`，模板为 `.env.local.example`。
- `NEXT_PUBLIC_*` 会发送到浏览器，禁止放置密钥。
- provider endpoint、model 和能力约束通过配置注入，不在 Agent 代码中硬编码。

## 贡献与安全

提交变更前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。安全问题请按 [SECURITY.md](SECURITY.md) 私密报告，不要在公开 issue 中粘贴密钥、provider payload 或未脱敏日志。

## 许可证

本项目使用 [MIT License](LICENSE)。第三方模型、API 和生成内容仍受各自服务条款约束。
