# 🪟 Windows原生安装指南（无需Docker）

## 🎯 系统要求

### 必需软件
- ✅ **Windows 10/11**
- ✅ **Python 3.11+** - [下载地址](https://python.org/downloads/)
- ✅ **Node.js 18+** - [下载地址](https://nodejs.org/)

### 可选软件（提供备选方案）
- 🐘 **PostgreSQL** - [下载地址](https://postgresql.org/download/windows/)
- 🔴 **Redis** - 或使用内存模式
- 🎬 **FFmpeg** - [下载地址](https://ffmpeg.org/download.html)

## 🚀 快速安装步骤

### 1. 安装基础软件

#### Python 3.11+
```batch
REM 下载并安装Python，确保勾选"Add Python to PATH"
REM 验证安装
python --version
pip --version
```

#### Node.js 18+
```batch
REM 下载并安装Node.js
REM 验证安装
node --version
npm --version
```

### 2. 下载项目
```batch
REM 如果有Git
git clone <repository-url>
cd short-video-maker

REM 如果没有Git，直接下载ZIP解压即可
```

### 3. 运行一键安装脚本
```batch
REM 运行Windows专用安装脚本
scripts\windows_setup.bat
```

这个脚本会自动：
- ✅ 检查系统环境
- ✅ 创建必要目录
- ✅ 安装Python依赖
- ✅ 安装Node.js依赖
- ✅ 创建环境配置文件
- ✅ 生成启动脚本

### 4. 配置API密钥（重要！）
编辑 `.env` 文件，添加你的API密钥（详见下方API密钥配置章节）

### 5. 启动应用
```batch
REM 启动所有服务
start_platform.bat
```

## 🔑 API密钥配置详解

### 必需的API密钥（至少选择一个）

#### 1. OpenAI API Key（推荐）⭐⭐⭐⭐⭐

**用途：** 文本生成、对话、内容创作
**获取方式：**
1. 访问 [OpenAI官网](https://platform.openai.com/)
2. 注册/登录账户
3. 进入 [API Keys页面](https://platform.openai.com/account/api-keys)
4. 点击 "Create new secret key"
5. 复制密钥（格式：`sk-...`）

**配置方式：**
```env
# .env文件中
OPENAI_API_KEY=sk-your-openai-api-key-here
```

**费用：** 按使用量计费，新用户通常有免费额度

#### 2. Anthropic API Key（可选）⭐⭐⭐⭐

**用途：** Claude AI模型，高质量文本生成
**获取方式：**
1. 访问 [Anthropic Console](https://console.anthropic.com/)
2. 注册账户
3. 进入API Keys部分
4. 创建新的API密钥

**配置方式：**
```env
ANTHROPIC_API_KEY=your-anthropic-api-key-here
```

### 可选的API密钥（增强功能）

#### 3. Stability AI API Key（图像生成）⭐⭐⭐

**用途：** AI图像生成、图片处理
**获取方式：**
1. 访问 [Stability AI](https://platform.stability.ai/)
2. 注册账户
3. 获取API密钥

**配置方式：**
```env
STABILITY_API_KEY=your-stability-api-key-here
```

#### 4. Runway ML API Key（视频生成）⭐⭐⭐

**用途：** AI视频生成和编辑
**获取方式：**
1. 访问 [Runway ML](https://runwayml.com/)
2. 注册账户并订阅计划
3. 获取API访问权限

**配置方式：**
```env
RUNWAY_API_KEY=your-runway-api-key-here
```

### 完整的.env配置示例

创建/编辑 `.env` 文件：

```env
# ===================================================================
# API密钥配置（至少需要配置一个AI服务）
# ===================================================================

# OpenAI配置（推荐，功能最全面）
OPENAI_API_KEY=sk-your-openai-api-key-here

# Anthropic配置（可选，高质量文本生成）
# ANTHROPIC_API_KEY=your-anthropic-api-key-here

# Stability AI配置（可选，图像生成）
# STABILITY_API_KEY=your-stability-api-key-here

# Runway ML配置（可选，视频生成）
# RUNWAY_API_KEY=your-runway-api-key-here

# ===================================================================
# 数据库配置（如果不安装PostgreSQL，可以使用SQLite）
# ===================================================================

# 选项1: SQLite（简单，无需安装数据库）
DATABASE_URL=sqlite:///./storage/app.db

# 选项2: PostgreSQL（功能更强，需要安装）
# DATABASE_URL=postgresql://postgres:password@localhost:5432/short_video_maker

# ===================================================================
# 缓存配置（如果不安装Redis，可以使用内存模式）
# ===================================================================

# 选项1: 内存模式（简单，但重启后数据丢失）
REDIS_URL=memory://

# 选项2: Redis（推荐，需要安装Redis）
# REDIS_URL=redis://localhost:6379/0

# ===================================================================
# 基本配置
# ===================================================================

# 应用密钥（请更改为随机字符串）
SECRET_KEY=your-super-secret-key-change-this-in-production

# 调试模式
DEBUG=true

# 日志级别
LOG_LEVEL=INFO

# ===================================================================
# 文件存储配置
# ===================================================================

UPLOAD_PATH=.\storage\uploads
GENERATED_PATH=.\storage\generated
TEMP_PATH=.\storage\temp
MAX_FILE_SIZE=100

# ===================================================================
# Windows特定优化配置
# ===================================================================

# Celery配置（Windows兼容）
CELERY_WORKER_POOL=solo
CELERY_WORKER_CONCURRENCY=2

# 资源限制
MAX_MEMORY_USAGE_PERCENT=70
MAX_CPU_USAGE_PERCENT=75

# AI服务超时设置
AI_SERVICE_TIMEOUT=120
```

## 🎯 最小化配置（仅需OpenAI）

如果你只想快速体验，最简配置：

```env
# 最小化配置 - 仅需要这几行
OPENAI_API_KEY=sk-your-openai-api-key-here
SECRET_KEY=change-this-to-random-string
DATABASE_URL=sqlite:///./storage/app.db
REDIS_URL=memory://
DEBUG=true
```

## 🛠️ 简化的数据库和缓存方案

### 不安装PostgreSQL - 使用SQLite
```env
# SQLite配置（文件数据库，无需安装服务）
DATABASE_URL=sqlite:///./storage/app.db
```

### 不安装Redis - 使用内存模式
```env
# 内存缓存（简单但重启后丢失数据）
REDIS_URL=memory://
```

## 🚀 启动测试

### 1. 检查配置
```batch
REM 运行系统验证
cd backend
python scripts\validate_system.py
```

### 2. 启动服务
```batch
REM 启动后端（新窗口）
start_backend.bat

REM 启动前端（新窗口）  
start_frontend.bat

REM 或者一键启动所有服务
start_platform.bat
```

### 3. 访问应用
- **前端界面：** http://localhost:3000
- **后端API：** http://localhost:8000
- **API文档：** http://localhost:8000/docs

## 🔧 常见问题解决

### 问题1：Python包安装失败
```batch
REM 升级pip
python -m pip install --upgrade pip

REM 使用国内镜像源
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple/
```

### 问题2：Node.js包安装失败
```batch
REM 清除缓存
npm cache clean --force

REM 使用国内镜像源
npm install --registry https://registry.npmmirror.com
```

### 问题3：端口被占用
```batch
REM 查看端口占用
netstat -ano | findstr :8000
netstat -ano | findstr :3000

REM 更改端口（在.env中）
PORT=8001
FRONTEND_PORT=3001
```

### 问题4：权限错误
```batch
REM 以管理员身份运行命令提示符
REM 或者修改文件夹权限
```

## 📝 功能测试清单

安装完成后，测试这些功能：

- [ ] 前端页面正常加载
- [ ] 后端API文档可访问
- [ ] 可以创建视频生成任务
- [ ] WebSocket实时通信正常
- [ ] 文件上传功能正常
- [ ] AI服务调用正常（需要API密钥）

## 💡 开发建议

### IDE推荐
- **Visual Studio Code** - 最佳选择
- **PyCharm** - Python开发
- **WebStorm** - 前端开发

### 有用的VSCode插件
- Python
- TypeScript and JavaScript Language Features
- Prettier - Code formatter
- ESLint
- REST Client

### 调试技巧
```batch
REM 查看后端日志
type backend\logs\app.log

REM 查看前端开发日志
npm run dev

REM 查看系统资源使用
tasklist | findstr python
tasklist | findstr node
```

## 🆘 获取帮助

如果遇到问题：

1. **检查日志文件：** `backend/logs/`
2. **运行诊断：** `python backend/scripts/validate_system.py`
3. **查看文档：** 项目中的各种README文件
4. **社区支持：** GitHub Issues

---

**🎉 完成！你现在可以在Windows上原生运行短视频制作平台了！**

记住：**只需要配置OpenAI API密钥就可以开始使用基本功能**！