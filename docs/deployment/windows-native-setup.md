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

`--project backend` 的 canonical 虚拟环境固定为 `backend/.venv`。Windows 与 WSL/Linux 的虚拟环境不可共用；同一份 checkout 切换平台后，应在当前平台原位重建该目录：

```powershell
Remove-Item -Recurse -Force backend/.venv
uv sync --project backend --frozen --extra dev --extra test
```

如果需要同时保留 Windows 与 WSL 两套环境，应使用两个 checkout，而不是在同一 checkout 中引入第二个虚拟环境事实源。

编辑根目录 `.env`，设置本地 PostgreSQL、Redis、强随机 `SECRET_KEY`，以及实际启用的 provider 凭据。前端本地覆盖使用 `.env.local`，可从 `.env.local.example` 创建。

## 数据库

创建空 PostgreSQL 数据库后运行：

```powershell
uv run --project backend alembic -c backend/alembic.ini upgrade head
uv run --project backend alembic -c backend/alembic.ini check
```

SQLite 仅用于迁移 contract 的隔离测试，不是公开运行路径。

## 启动

终端一启动完整后端开发进程组：

```powershell
uv run --project backend --frozen python backend/scripts/start_dev_uv.py
```

该入口会检查 PostgreSQL/Redis、执行 migration，并启动 API、Celery worker 与 beat。任何必需进程启动失败都会返回非零并清理已启动进程。只做前置检查时使用：

```powershell
uv run --project backend --frozen python backend/scripts/start_dev_uv.py --check
```

终端二：

```powershell
npm run dev
```

访问 `http://localhost:3000/home`。如果只开发 API、不执行异步生成任务，可不用 launcher，改为单独运行：

```powershell
uv run --project backend uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
```

API-only 模式不处理队列中的生成任务，不能作为完整生成链路的启动方式。

## 验证

```powershell
npm run lint
npm run type-check
npm run test:ci
uv run --project backend pytest -q backend/tests/unit/test_env_loading.py backend/tests/unit/test_release_migration_contract.py
```

不要提交 `backend/.venv`，也不要把其他平台创建的虚拟环境复制到当前 checkout。
