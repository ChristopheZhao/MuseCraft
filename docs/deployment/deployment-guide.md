# 生产部署指南

本指南只描述当前经过验证的 PostgreSQL 部署路径。请从已检出的仓库根目录执行命令；仓库地址由你的发布平台或 fork 提供。

## 前置条件

- Docker Engine 24+ 与 Docker Compose v2
- 可访问的 AI/媒体服务凭据
- FFmpeg 6+（仅手工部署时需要；容器镜像已安装）
- 足够的持久化数据库、Redis 与媒体存储空间

## 配置

```bash
cp .env.example .env
```

至少替换以下值：

```dotenv
SECRET_KEY=replace-with-a-long-random-value
DATABASE_NAME=short_video_maker
DATABASE_USER=musecraft
DATABASE_PASSWORD=replace-with-a-url-safe-password
REDIS_URL=redis://redis:6379/0
```

Compose 会用这些组件变量构造容器内的 PostgreSQL URL。只配置实际启用的 provider 凭据。不要把 `.env`、备份或生成媒体加入 Git。

## 启动

```bash
docker compose -f backend/docker-compose.yml up --build -d
docker compose -f backend/docker-compose.yml ps
```

Compose 会先运行一次 `alembic upgrade head`；迁移成功后才启动 API、worker 和 beat。不要用 `metadata.create_all()` 或手工 `alembic stamp` 绕过迁移。

验证 API：

```bash
curl --fail http://localhost:8000/health
```

前端生产构建可单独部署：

```bash
npm ci
npm run build
npm run start
```

部署平台应注入 `NEXT_PUBLIC_API_URL` 与 `NEXT_PUBLIC_WS_URL`，并把 API/WS 暴露在受 TLS 保护的地址上。

## 升级与回滚

1. 备份 PostgreSQL 和媒体存储。
2. 在候选版本运行 `npm audit`、release tests 和 Alembic check。
3. 拉取目标提交并重新构建镜像。
4. 运行迁移服务，确认成功后再切换流量。
5. 应用回滚前先检查目标 revision 是否支持 downgrade；不要把数据库版本号直接改写到旧 revision。

已有数据库接入发布 baseline 前，必须遵循 [数据库迁移说明](../database-migrations.md)。

## 运维边界

- PostgreSQL 是业务状态的持久化源；Redis/Celery 仅承载队列与执行传输。
- 队列健康不能替代 MAS runtime/read-model 状态。
- 外部访问必须经 TLS、访问控制和限流。
- 日志不得记录 provider 密钥、用户上传内容或完整 prompt payload。
