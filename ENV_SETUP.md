# 环境变量配置指南

## 概述

本项目采用**前后端分离的环境变量管理**：

- **后端环境变量**: 放在项目根目录的 `.env` 文件中
- **前端环境变量**: 放在 `frontend/.env.local` 文件中

这种分离确保了：
✅ 前后端配置解耦，独立管理
✅ 减少配置冲突和错误
✅ 符合Next.js和FastAPI的最佳实践
✅ 便于独立测试和部署

---

## 快速开始

### 1. 配置后端环境变量

```bash
# 1. 复制模板文件
cp backend/.env.example .env

# 2. 编辑 .env 文件，填入实际值
# 必填项：
# - DATABASE_URL
# - REDIS_URL
# - AI服务API密钥 (KIMI_API_KEY, GLM_API_KEY 等)

# 3. 不要将 .env 提交到Git（已在.gitignore中排除）
```

### 2. 配置前端环境变量

```bash
# 1. 进入前端目录
cd frontend

# 2. 复制模板文件
cp .env.example .env.local

# 3. 编辑 .env.local，填入实际值
# 必填项：
# - NEXT_PUBLIC_API_URL (后端API地址)
# - NEXT_PUBLIC_HERO_VIDEO_URL (营销页面视频)

# 4. 不要将 .env.local 提交到Git（已在.gitignore中排除）
```

---

## 环境变量详解

### 后端环境变量 (`.env`)

#### 核心配置
```bash
# 应用基础
DEBUG=false
SECRET_KEY=your-super-secret-key-change-this
LOG_LEVEL=INFO

# 数据库
DATABASE_URL=mysql://user:password@localhost:3306/short_video_maker
REDIS_URL=redis://localhost:6379/0

# Celery任务队列
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2
```

#### AI服务配置
```bash
# 推荐配置（中国服务）
KIMI_API_KEY=sk-your-kimi-key          # 文本生成
GLM_API_KEY=your-glm-key                # 图像+视频生成
ALIYUN_TTS_APP_KEY=your-aliyun-key      # 语音合成

# 可选配置（国际服务）
OPENAI_API_KEY=sk-your-openai-key
STABILITY_API_KEY=your-stability-key
```

#### 文件存储配置
```bash
# 本地存储（开发环境）
STORAGE_TYPE=local
UPLOAD_PATH=./storage/uploads
GENERATED_PATH=./storage/generated

# 阿里云OSS（生产环境推荐）
STORAGE_TYPE=oss
OSS_ENDPOINT=http://oss-cn-shanghai.aliyuncs.com
OSS_BUCKET_NAME=your-bucket-name
OSS_ACCESS_KEY_ID=your-access-key-id
OSS_ACCESS_KEY_SECRET=your-access-key-secret
```

### 前端环境变量 (`frontend/.env.local`)

```bash
# API端点（必填）
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000

# 营销资源（必填）
NEXT_PUBLIC_HERO_VIDEO_URL=https://your-cdn.example.com/video/hero.mp4

# 可选配置
NEXT_PUBLIC_GA_MEASUREMENT_ID=G-XXXXXXXXXX  # Google Analytics
```

⚠️ **重要提示**:
- 所有 `NEXT_PUBLIC_` 前缀的变量会暴露给浏览器
- 不要在前端变量中存放敏感信息（API密钥、数据库密码等）
- 敏感配置应放在后端 `.env` 中

---

## 环境差异配置

### 开发环境

**后端 (`.env`):**
```bash
DEBUG=true
LOG_LEVEL=DEBUG
DATABASE_URL=mysql://root:password@localhost:3306/short_video_dev
```

**前端 (`frontend/.env.local`):**
```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### 生产环境

**后端 (通过环境变量注入):**
```bash
DEBUG=false
LOG_LEVEL=WARNING
DATABASE_URL=mysql://prod_user:prod_pass@db.example.com:3306/short_video
```

**前端 (部署平台配置):**
```bash
NEXT_PUBLIC_API_URL=https://api.yourdomain.com
NEXT_PUBLIC_HERO_VIDEO_URL=https://cdn.yourdomain.com/video/hero.mp4
```

---

## CI/CD 配置

### GitHub Actions 示例

```yaml
# .github/workflows/backend-test.yml
env:
  DATABASE_URL: ${{ secrets.TEST_DATABASE_URL }}
  REDIS_URL: ${{ secrets.TEST_REDIS_URL }}
  KIMI_API_KEY: ${{ secrets.KIMI_API_KEY }}
```

### Vercel/Netlify 部署

前端环境变量在部署平台的设置页面配置：

```
NEXT_PUBLIC_API_URL=https://api.yourdomain.com
NEXT_PUBLIC_WS_URL=wss://api.yourdomain.com
NEXT_PUBLIC_HERO_VIDEO_URL=https://cdn.yourdomain.com/hero.mp4
```

### Docker 部署

```yaml
# docker-compose.yml
services:
  backend:
    env_file:
      - .env  # 后端环境变量

  frontend:
    environment:
      - NEXT_PUBLIC_API_URL=http://backend:8000
      # 其他前端变量通过 build args 传入
```

---

## 常见问题

### Q: pytest 报 `ValidationError: NEXT_PUBLIC_HERO_VIDEO_URL Extra inputs are not permitted`

**原因**: 后端Settings类读取了前端环境变量。

**解决**:
```bash
# 方法1: 确保前端变量在 frontend/.env.local 中
cd frontend && cp .env.example .env.local

# 方法2: 测试前临时unset前端变量
unset NEXT_PUBLIC_HERO_VIDEO_URL
pytest backend/tests/

# 方法3: 确保 .env 文件中没有 NEXT_PUBLIC_* 变量
grep -v "^NEXT_PUBLIC_" .env > .env.tmp && mv .env.tmp .env
```

### Q: 前端无法连接后端API

**检查清单**:
1. `frontend/.env.local` 中 `NEXT_PUBLIC_API_URL` 是否正确
2. 后端是否在运行 (`http://localhost:8000`)
3. CORS配置是否允许前端域名

### Q: 环境变量更改后不生效

**解决**:
```bash
# 后端: 重启服务
uv run python backend/app/main.py

# 前端: 重启开发服务器（Next.js会自动重载.env.local）
npm run dev
```

### Q: 如何在代码中访问环境变量？

**后端 (Python):**
```python
from app.core.config import settings
print(settings.KIMI_API_KEY)  # ✅ 正确
```

**前端 (Next.js):**
```typescript
const apiUrl = process.env.NEXT_PUBLIC_API_URL;  // ✅ 正确
const secretKey = process.env.SECRET_KEY;  // ❌ 错误！前端无法访问后端变量
```

---

## 安全最佳实践

1. ✅ **永远不要提交 `.env` 和 `.env.local` 到Git**
2. ✅ **使用强密码和定期轮换API密钥**
3. ✅ **生产环境通过部署平台注入环境变量**
4. ✅ **前端只暴露必要的公开配置（`NEXT_PUBLIC_`）**
5. ✅ **敏感信息（密钥、密码）只存在后端环境变量**
6. ✅ **定期审计 `.env.example` 确保无敏感信息泄露**

---

## 相关文件

- `backend/.env.example` - 后端环境变量模板
- `frontend/.env.example` - 前端环境变量模板
- `.gitignore` - 确保敏感配置不被提交
- `API_KEYS_GUIDE.md` - AI服务API密钥申请指南

---

## 技术支持

如遇环境配置问题，请：
1. 检查 `.env.example` 模板
2. 查看本文档的常见问题部分
3. 提交Issue并附上错误信息（注意隐藏敏感信息）
