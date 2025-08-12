# 🪟 Windows部署指南

## 快速开始

### 🚀 方法一：Docker Desktop（推荐）

```batch
REM 1. 安装Docker Desktop for Windows
REM 2. 克隆并配置项目
git clone <repository-url>
cd short-video-maker
copy .env.example .env

REM 3. 编辑.env文件，添加API密钥
notepad .env

REM 4. 启动服务
docker-compose up -d

REM 5. 访问应用
REM 前端: http://localhost:3000
REM 后端: http://localhost:8000
REM API文档: http://localhost:8000/docs
```

### 🛠️ 方法二：原生Windows安装

```batch
REM 1. 运行Windows兼容性修复
python scripts\fix_windows_compatibility.py

REM 2. 运行自动化设置脚本
scripts\windows_setup.bat

REM 3. 启动平台
start_platform.bat
```

## 系统要求

### 必需软件
- ✅ **Windows 10/11** (Build 1903+)
- ✅ **Python 3.11+** - [下载链接](https://python.org/downloads/)
- ✅ **Node.js 18+** - [下载链接](https://nodejs.org/)
- ✅ **Git** - [下载链接](https://git-scm.com/download/win)

### 推荐软件
- 🐳 **Docker Desktop** - [下载链接](https://docker.com/products/docker-desktop/)
- 🐘 **PostgreSQL 15+** - [下载链接](https://postgresql.org/download/windows/)
- 🔴 **Redis** - [通过Docker或Chocolatey安装](https://redis.io/docs/getting-started/installation/install-redis-on-windows/)
- 🎬 **FFmpeg** - [下载链接](https://ffmpeg.org/download.html#build-windows)

### 可选工具
- **Visual Studio Code** - 开发IDE
- **Windows Subsystem for Linux (WSL2)** - Linux兼容环境
- **Chocolatey** - Windows包管理器

## 详细安装步骤

### 步骤 1: 安装基础软件

#### Python 3.11+
```batch
REM 使用winget安装
winget install Python.Python.3.11

REM 或者手动下载安装，确保勾选"Add Python to PATH"
```

#### Node.js 18+
```batch
REM 使用winget安装
winget install OpenJS.NodeJS

REM 验证安装
node --version
npm --version
```

#### Git
```batch
REM 安装Git
winget install Git.Git

REM 配置Git（可选）
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"
```

### 步骤 2: 安装数据库和缓存

#### 选项A: 使用Docker（推荐）
```batch
REM 安装Docker Desktop
winget install Docker.DockerDesktop

REM 启动Docker服务
REM 无需手动安装PostgreSQL和Redis
```

#### 选项B: 手动安装

**PostgreSQL:**
```batch
REM 下载并安装PostgreSQL
winget install PostgreSQL.PostgreSQL

REM 创建数据库
createdb -U postgres short_video_maker
```

**Redis:**
```batch
REM 使用Chocolatey安装Redis
choco install redis-64

REM 或者使用Docker
docker run -d -p 6379:6379 redis:alpine
```

### 步骤 3: 安装FFmpeg（视频处理）

```batch
REM 选项1: 使用winget
winget install FFmpeg

REM 选项2: 手动安装
REM 1. 从 https://ffmpeg.org/download.html#build-windows 下载
REM 2. 解压到 C:\ffmpeg
REM 3. 添加 C:\ffmpeg\bin 到系统PATH

REM 验证安装
ffmpeg -version
```

### 步骤 4: 克隆和配置项目

```batch
REM 克隆项目
git clone <repository-url>
cd short-video-maker

REM 运行Windows兼容性修复
python scripts\fix_windows_compatibility.py

REM 运行自动设置
scripts\windows_setup.bat
```

### 步骤 5: 配置环境变量

编辑 `.env` 文件：

```env
# 数据库连接
DATABASE_URL=postgresql://postgres:password@localhost:5432/short_video_maker

# Redis连接
REDIS_URL=redis://localhost:6379/0

# AI服务API密钥（至少需要一个）
OPENAI_API_KEY=sk-your-openai-api-key-here
ANTHROPIC_API_KEY=your-anthropic-key-here
STABILITY_API_KEY=your-stability-key-here

# 文件存储路径（Windows格式）
UPLOAD_PATH=.\storage\uploads
GENERATED_PATH=.\storage\generated
TEMP_PATH=.\storage\temp

# Windows特定配置
CELERY_WORKER_POOL=solo
CELERY_WORKER_CONCURRENCY=2
```

### 步骤 6: 启动服务

#### 选项A: 使用批处理脚本
```batch
REM 启动所有服务
start_platform.bat

REM 或单独启动
start_backend.bat    # 仅后端
start_frontend.bat   # 仅前端
```

#### 选项B: 使用Docker
```batch
REM 标准启动
docker-compose up -d

REM 使用Windows优化配置
docker-compose -f docker-compose.yml -f docker-compose.windows.yml up -d
```

#### 选项C: 手动启动
```batch
REM 终端1: 启动后端
cd backend
python -m app.main

REM 终端2: 启动前端
npm run dev
```

## Windows特有问题解决

### 问题 1: psycopg2 安装失败

**错误信息:**
```
error: Microsoft Visual C++ 14.0 is required
```

**解决方案:**
```batch
REM 选项1: 使用二进制包
pip install psycopg2-binary

REM 选项2: 安装Visual Studio Build Tools
winget install Microsoft.VisualStudio.2022.BuildTools
```

### 问题 2: Redis 连接失败

**错误信息:**
```
ConnectionError: Error 10061 connecting to localhost:6379
```

**解决方案:**
```batch
REM 检查Redis服务状态
sc query Redis

REM 启动Redis服务
net start Redis

REM 或使用Docker
docker run -d -p 6379:6379 --name redis redis:alpine
```

### 问题 3: FFmpeg 找不到

**错误信息:**
```
FileNotFoundError: [WinError 2] The system cannot find the file specified: 'ffmpeg'
```

**解决方案:**
```batch
REM 检查FFmpeg是否在PATH中
where ffmpeg

REM 如果没有，添加到环境变量或在.env中指定路径
FFMPEG_PATH=C:\Program Files\FFmpeg\bin\ffmpeg.exe
```

### 问题 4: 端口被占用

**错误信息:**
```
OSError: [WinError 10048] Only one usage of each socket address is normally permitted
```

**解决方案:**
```batch
REM 查找占用端口的进程
netstat -ano | findstr :8000
netstat -ano | findstr :3000

REM 终止进程（替换PID）
taskkill /PID <PID> /F

REM 或更改端口配置
```

### 问题 5: 权限问题

**错误信息:**
```
PermissionError: [WinError 5] Access is denied
```

**解决方案:**
```batch
REM 以管理员身份运行命令提示符
REM 或修改文件夹权限
icacls storage /grant Users:F /T
```

## 性能优化建议

### Windows特定优化

```env
# .env 中的Windows优化设置
CELERY_WORKER_CONCURRENCY=2
MAX_MEMORY_USAGE_PERCENT=70
MAX_CPU_USAGE_PERCENT=75
AI_SERVICE_TIMEOUT=180
```

### 硬件建议
- **内存**: 8GB+ RAM（推荐16GB）
- **存储**: SSD存储提升I/O性能
- **CPU**: 4核心以上处理器

## 开发工具配置

### Visual Studio Code
推荐插件：
- Python
- TypeScript and JavaScript Language Features
- Docker
- GitLens
- Prettier - Code formatter
- ESLint

### PowerShell 配置
```powershell
# 安装Windows Terminal（现代终端）
winget install Microsoft.WindowsTerminal

# 配置执行策略（如果需要）
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

## 监控和日志

### Windows事件查看器
- 打开事件查看器：`eventvwr.msc`
- 查看应用程序日志
- 监控系统错误

### 性能监控
```batch
REM 查看系统资源使用
tasklist /fi "imagename eq python.exe"
tasklist /fi "imagename eq node.exe"

REM 监控网络连接
netstat -an | findstr :8000
netstat -an | findstr :3000
```

## 故障排除清单

### 启动前检查
- [ ] Python 3.11+ 已安装且在PATH中
- [ ] Node.js 18+ 已安装且在PATH中  
- [ ] PostgreSQL/Redis 服务运行中
- [ ] FFmpeg 已安装且在PATH中
- [ ] .env 文件已配置API密钥
- [ ] 防火墙允许端口8000和3000
- [ ] 足够的磁盘空间（至少2GB）

### 常见错误解决
- [ ] 清除npm缓存：`npm cache clean --force`
- [ ] 重新安装Python依赖：`pip install -r requirements.txt --force-reinstall`
- [ ] 检查端口占用：`netstat -ano | findstr :8000`
- [ ] 重启相关服务：`net stop/start servicename`

### 日志位置
- **应用日志**: `backend/logs/`
- **Windows系统日志**: 事件查看器
- **Docker日志**: `docker-compose logs`

## 生产环境部署

### Windows Server 部署
```batch
REM 安装IIS（可选，用于反向代理）
Enable-WindowsOptionalFeature -Online -FeatureName IIS-WebServerRole

REM 配置Windows服务
sc create ShortVideoMakerAPI binpath= "C:\path\to\python.exe C:\path\to\backend\app\main.py"
```

### 安全配置
- 配置Windows防火墙规则
- 设置适当的文件权限
- 配置SSL证书
- 定期更新系统和依赖

## 获取帮助

### 官方文档
- [Python on Windows](https://docs.python.org/3/using/windows.html)
- [Node.js on Windows](https://nodejs.org/en/docs/guides/getting-started-guide/)
- [Docker Desktop for Windows](https://docs.docker.com/desktop/windows/)

### 社区支持
- GitHub Issues
- Stack Overflow
- Python Discord
- Node.js Discord

---

**🎉 恭喜！您已成功在Windows上部署短视频制作平台！**

访问地址：
- 前端应用：http://localhost:3000
- 后端API：http://localhost:8000
- API文档：http://localhost:8000/docs