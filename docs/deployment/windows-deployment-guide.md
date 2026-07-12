# Windows 部署指南

Windows 上的推荐部署方式是 WSL2 + Docker Desktop。该路径与 Linux CI、容器和生产脚本保持一致，避免 Windows 原生文件权限与进程模型差异。

## 推荐路径：WSL2 + Docker Desktop

1. 安装 WSL2（Ubuntu）与 Docker Desktop，并启用 WSL integration。
2. 在 WSL 文件系统中检出仓库，或确认当前挂载目录满足 Docker 文件共享要求。
3. 从仓库根目录创建本地配置：

```bash
cp .env.example .env
```

4. 配置强随机 `SECRET_KEY`、PostgreSQL/Redis URL 和实际使用的 provider 凭据。
5. 启动并检查：

```bash
docker compose -f backend/docker-compose.yml up --build -d
docker compose -f backend/docker-compose.yml ps
curl --fail http://localhost:8000/health
```

Compose 的 `migrate` 服务是 schema 推进的唯一入口。API、worker 与 beat 只有在迁移成功后才启动。

## 前端

```bash
npm ci
npm run build
npm run start
```

Node.js 最低版本为 18.18。生产环境应通过平台配置 `NEXT_PUBLIC_API_URL` 与 `NEXT_PUBLIC_WS_URL`。

## Windows 原生限制

Windows 原生模式适合开发和验证，不作为本指南的生产推荐路径。需要原生运行时，请参阅 [Windows 原生开发环境](windows-native-setup.md)。

不要：

- 把 `.env` 或 provider 凭据复制进镜像。
- 用 SQLite 替代发布 PostgreSQL schema contract。
- 从 Celery/Redis 状态推断业务任务是否完成。
- 在未比对 schema 的已有数据库上执行 `alembic stamp head`。
