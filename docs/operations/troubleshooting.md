# 故障排查指南

## 常见问题

### 1. API服务无法启动

**症状**: FastAPI服务启动失败

**可能原因**:
- 端口被占用
- 数据库连接失败
- 环境变量未配置

**解决方法**:
```bash
# 检查端口占用
lsof -i :8000

# 验证数据库连接
python -c "from app.core.database import engine; engine.connect()"

# 检查环境变量
python scripts/validate_system.py
```

### 2. AI服务调用失败

**症状**: AI服务返回错误或超时

**可能原因**:
- API密钥无效
- 网络连接问题
- 服务限流

**解决方法**:
```bash
# 测试API连接
curl -H "Authorization: Bearer $OPENAI_API_KEY" https://api.openai.com/v1/models

# 检查代理设置
echo $HTTP_PROXY
echo $HTTPS_PROXY

# 查看错误日志
grep "AI service error" logs/app.log | tail -20
```

### 3. 视频生成失败

**症状**: 视频合成步骤报错

**可能原因**:
- FFmpeg未安装
- 内存不足
- 临时文件权限问题

**解决方法**:
```bash
# 验证FFmpeg
ffmpeg -version

# 检查磁盘空间
df -h

# 清理临时文件
rm -rf storage/temp/*
```

### 4. WebSocket连接断开

**症状**: 实时进度更新中断

**可能原因**:
- 反向代理配置错误
- 超时设置过短
- 网络不稳定

**解决方法**:
```nginx
# Nginx配置示例
location /ws {
    proxy_pass http://backend:8000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_read_timeout 86400;
}
```

## 调试技巧

### 1. 启用调试日志
```bash
export LOG_LEVEL=DEBUG
python scripts/start_dev.py
```

### 2. 使用调试工具
```bash
# Python调试器
python -m pdb app/main.py

# 性能分析
python -m cProfile -o profile.out app/main.py
```

### 3. 数据库查询分析
```sql
-- 查看慢查询
SELECT query, calls, mean_time
FROM pg_stat_statements
ORDER BY mean_time DESC
LIMIT 10;
```

## 性能优化

### 1. 数据库优化
- 添加适当的索引
- 使用连接池
- 定期VACUUM

### 2. Redis优化
- 设置合理的过期时间
- 使用Pipeline批量操作
- 监控内存使用

### 3. 应用优化
- 使用异步处理
- 实现请求缓存
- 优化图片/视频处理

## 紧急恢复

### 1. 服务重启流程
```bash
# 停止所有服务
docker-compose down

# 清理异常状态
redis-cli FLUSHDB

# 重启服务
docker-compose up -d

# 验证服务状态
curl http://localhost:8000/health
```

### 2. 数据恢复
```bash
# 从备份恢复数据库
pg_restore -d short_video_maker backup.dump

# 恢复文件存储
rsync -av backup/storage/ storage/
```

### 3. 回滚部署
```bash
# 回滚到上一个版本
git checkout previous-tag
docker-compose build
docker-compose up -d
```