# Windows 原生开发环境

此路径用于本地开发，不是生产部署合同。生产或 Linux 一致性验证优先使用 WSL2 + Docker Desktop。

## 前置条件

- Python 3.11
- uv 0.5.20+
- Node.js 18.18+
- PostgreSQL 15+
- Redis 7+
- FFmpeg 6+

确保 `python`、`uv`、`node`、`psql`、`redis-cli` 与 `ffmpeg` 在 `PATH` 中。

## 初始化

从仓库根目录执行：

```powershell
Copy-Item .env.example .env
uv sync --project backend --frozen --extra dev --extra test
npm ci
```

编辑根目录 `.env`，设置本地 PostgreSQL、Redis、强随机 `SECRET_KEY`，以及实际启用的 provider 凭据。前端本地覆盖使用 `.env.local`，可从 `.env.local.example` 创建。

## 数据库

创建空 PostgreSQL 数据库后运行：

```powershell
uv run --project backend alembic -c backend/alembic.ini upgrade head
uv run --project backend alembic -c backend/alembic.ini check
```

SQLite 仅用于迁移 contract 的隔离测试，不是公开运行路径。

## 启动

终端一：

```powershell
uv run --project backend uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
```

终端二：

```powershell
npm run dev
```

访问 `http://localhost:3000/home`。Celery worker/beat 只有在需要异步生成流程时才需另行启动，命令与队列配置以 `backend/docker-compose.yml` 为准。

## 验证

```powershell
npm run lint
npm run type-check
npm run test:ci
uv run --project backend pytest -q backend/tests/unit/test_env_loading.py backend/tests/unit/test_release_migration_contract.py
```

如果仓库中的 `backend/.venv` 来自 WSL 或其他主机，设置独立的 `UV_PROJECT_ENVIRONMENT`，不要把平台不兼容的虚拟环境提交到 Git。
