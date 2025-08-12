# 生产环境部署指南

## 🎯 概述

本指南提供短视频生成平台从开发到生产环境的完整部署流程，包括部署前准备、部署步骤、验证测试和运维配置。

## 📋 部署前准备

### 1. 环境要求

#### 硬件要求
- **CPU**: 最少4核心，推荐8核心+
- **内存**: 最少8GB，推荐16GB+
- **存储**: SSD，至少500GB
- **网络**: 至少100Mbps带宽

#### 软件要求
- **操作系统**: Ubuntu 20.04 LTS 或更高版本
- **Docker**: 20.10+ 和 Docker Compose 2.0+
- **Python**: 3.8+
- **Node.js**: 16+
- **PostgreSQL**: 13+
- **Redis**: 6+
- **FFmpeg**: 4.x+

### 2. API密钥配置

确保以下AI服务的API密钥已准备：
- OpenAI API Key
- Stability AI API Key（或其他图像生成服务）
- 视频生成服务API Key（CogVideoX/Runway等）
- 其他集成服务的密钥

### 3. 域名和SSL证书

- 注册并配置域名
- 获取SSL证书（Let's Encrypt或商业证书）
- 配置DNS解析

## 🚀 部署步骤

### 1. 克隆代码并配置环境

```bash
# 克隆代码仓库
git clone <repository-url>
cd short-video-maker

# 创建环境配置文件
cp .env.example .env

# 编辑环境变量
vim .env
```

必要的环境变量配置：
```bash
# AI服务配置
OPENAI_API_KEY=your_openai_key
STABILITY_API_KEY=your_stability_key
ZHIPU_API_KEY=your_zhipu_key

# 数据库配置
DATABASE_URL=postgresql://user:password@localhost:5432/dbname
REDIS_URL=redis://localhost:6379/0

# 安全配置
JWT_SECRET_KEY=your-secret-key
APP_SECRET_KEY=your-app-secret

# 文件存储
STORAGE_TYPE=local  # 或 s3, minio
```

### 2. 使用Docker Compose部署（推荐）

```bash
# 构建并启动所有服务
docker-compose up -d --build

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f
```

### 3. 手动部署（备选方案）

#### 3.1 数据库初始化
```bash
# 创建数据库
sudo -u postgres psql
CREATE DATABASE short_video_maker;
CREATE USER app_user WITH PASSWORD 'secure_password';
GRANT ALL PRIVILEGES ON DATABASE short_video_maker TO app_user;

# 运行迁移
cd backend
alembic upgrade head
```

#### 3.2 后端服务部署
```bash
cd backend

# 安装依赖
pip install -r requirements.txt

# 启动Celery Worker
celery -A app.services.celery_app worker --loglevel=info &

# 启动API服务
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

#### 3.3 前端部署
```bash
cd frontend

# 安装依赖并构建
npm install
npm run build

# 使用PM2运行
pm2 start npm --name "frontend" -- start
```

### 4. Nginx反向代理配置

```nginx
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    # 前端请求
    location / {
        proxy_pass http://localhost:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # API请求
    location /api/ {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # 文件上传大小限制
        client_max_body_size 100M;
    }
    
    # WebSocket
    location /ws/ {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }
}
```

## ✅ 部署验证

### 1. 基础服务检查

```bash
# 检查数据库连接
psql -h localhost -U app_user -d short_video_maker -c "SELECT version();"

# 检查Redis
redis-cli ping

# 检查API健康状态
curl https://your-domain.com/health

# 检查WebSocket
wscat -c wss://your-domain.com/ws/
```

### 2. 功能测试

运行自动化测试套件：
```bash
cd tests
python run_all_tests.py --quick --production
```

手动测试清单：
- [ ] 用户可以访问前端页面
- [ ] 用户可以创建视频任务
- [ ] AI智能体正常响应
- [ ] 实时进度更新工作
- [ ] 视频生成成功
- [ ] 文件下载正常

### 3. 性能基准测试

```bash
# 运行性能测试
python tests/performance/test_performance_reliability.py

# 负载测试
ab -n 1000 -c 10 https://your-domain.com/api/v1/health
```

性能指标要求：
- API响应时间 < 2秒
- 并发用户数 > 50
- 错误率 < 1%
- 系统可用性 > 99.5%

## 🔧 监控配置

### 1. 应用监控

配置Prometheus和Grafana：
```yaml
# prometheus.yml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'short-video-maker'
    static_configs:
      - targets: ['localhost:8000']
```

### 2. 日志管理

```bash
# 配置日志轮转
cat > /etc/logrotate.d/short-video-maker << EOF
/var/log/short-video-maker/*.log {
    daily
    rotate 30
    compress
    missingok
    notifempty
}
EOF
```

### 3. 告警规则

关键告警配置：
- 服务不可用
- API错误率 > 5%
- 响应时间 > 5秒
- 磁盘空间 < 10%
- 内存使用 > 90%

## 🔐 安全加固

### 1. 系统安全
```bash
# 配置防火墙
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable

# 禁用root登录
sed -i 's/PermitRootLogin yes/PermitRootLogin no/g' /etc/ssh/sshd_config
```

### 2. 应用安全
- 启用HTTPS和HSTS
- 配置CORS白名单
- 实施API速率限制
- 定期更新依赖包
- 配置安全响应头

### 3. 数据安全
- 数据库定期备份
- 敏感数据加密
- 访问日志审计
- 定期安全扫描

## 📊 备份策略

### 1. 数据库备份
```bash
# 创建备份脚本
cat > /opt/backup/db_backup.sh << 'EOF'
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
pg_dump -h localhost -U app_user short_video_maker > /backup/db_$DATE.sql
find /backup -name "db_*.sql" -mtime +7 -delete
EOF

# 配置定时任务
crontab -e
0 2 * * * /opt/backup/db_backup.sh
```

### 2. 文件备份
```bash
# 使用rsync备份
rsync -avz /app/storage/ /backup/storage/
```

## 🚨 故障恢复

### 1. 服务重启流程
```bash
# Docker环境
docker-compose restart

# 手动环境
systemctl restart short-video-maker-api
systemctl restart short-video-maker-worker
systemctl restart nginx
```

### 2. 数据恢复
```bash
# 恢复数据库
psql -h localhost -U app_user short_video_maker < backup.sql

# 恢复文件
rsync -avz /backup/storage/ /app/storage/
```

### 3. 回滚流程
```bash
# 回滚到上一版本
git checkout previous-tag
docker-compose build
docker-compose up -d
```

## 📋 运维检查清单

### 日常检查（每日）
- [ ] 服务健康状态
- [ ] 错误日志检查
- [ ] 磁盘空间检查
- [ ] 备份验证

### 定期维护（每周）
- [ ] 性能指标分析
- [ ] 安全更新检查
- [ ] 数据库优化
- [ ] 日志清理

### 深度维护（每月）
- [ ] 全面安全扫描
- [ ] 性能优化分析
- [ ] 容灾演练
- [ ] 文档更新

## 📞 应急响应

### 联系方式
- 技术负责人: [联系方式]
- 运维团队: [联系方式]
- 云服务商支持: [联系方式]

### 应急预案
1. 服务不可用：执行服务重启流程
2. 数据丢失：执行数据恢复流程
3. 安全事件：隔离系统，联系安全团队
4. 性能问题：扩容或优化配置

---

最后更新：2024-XX-XX