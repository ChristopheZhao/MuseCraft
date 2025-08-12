# 🎬 MuseCraft - AI驱动的多智能体创作工坊

一个基于多智能体协作的智能创作平台，通过6个专业AI智能体的协同工作，自动化完成从概念规划到视频输出的完整流程。将灵感转化为精美视频的现代工艺。

## ✨ 核心特性

### 🤖 多智能体协作架构
- **Orchestrator Agent** - 总协调器，管理整个工作流
- **Concept Planner Agent** - 概念规划，创意构思和主题设计
- **Script Writer Agent** - 脚本编写，场景描述和旁白生成
- **Image Generator Agent** - 图像生成，视觉素材创作
- **Video Generator Agent** - 视频生成，动态内容制作
- **Video Composer Agent** - 视频合成，最终作品输出
- **Quality Checker Agent** - 质量检查，内容安全和一致性验证

### 🎯 智能化视频生成
- 🧠 **AI驱动创作** - 从文本描述到完整视频的全自动生成
- 🎨 **多样化风格** - 支持科技、创意、商务、教育等多种视频风格
- ⚡ **实时协作** - 智能体间实时通信和任务协调
- 🔄 **自适应优化** - 根据结果质量自动调整生成策略

### 🌐 现代化Web界面
- 📱 **响应式设计** - 完美适配桌面端和移动端
- 🔄 **实时更新** - WebSocket实时显示生成进度
- 🎛️ **直观控制** - 用户友好的参数设置和预览功能
- ♿ **无障碍支持** - 符合WCAG标准的可访问性设计

### 🏗️ 企业级架构
- 🚀 **高性能** - 异步处理和并发优化
- 🔒 **安全可靠** - 多层安全防护和错误恢复
- 📊 **可观测性** - 完整的监控、日志和性能分析
- 🔧 **易扩展** - 模块化设计，支持水平扩展

## 🏛️ 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                    用户界面 (Next.js)                       │
├─────────────────────────────────────────────────────────────┤
│                  API网关 (FastAPI)                         │
├─────────────────────────────────────────────────────────────┤
│                 Orchestrator Agent                          │
├─────────────┬─────────────┬─────────────┬─────────────────┤
│ Concept     │ Script      │ Image       │ Video           │
│ Planner     │ Writer      │ Generator   │ Generator       │
├─────────────┼─────────────┼─────────────┼─────────────────┤
│ Video       │ Quality     │ Monitoring  │ Error Recovery  │
│ Composer    │ Checker     │ Service     │ Service         │
├─────────────────────┬─────────────────┬─────────────────────┤
│  消息队列 (Redis)    │  数据库         │  文件存储           │
│                     │  (MySQL)        │  (MinIO/S3)         │
└─────────────────────┴─────────────────┴─────────────────────┘
```

## 🚀 快速开始

### 前置要求

- **Node.js** 16+ 
- **Python** 3.8+
- **uv** (推荐) 或 **pip** (传统方式)
- **MySQL** 8.0+ (或 **PostgreSQL** 13+)
- **Redis** 6+
- **Docker** (可选，推荐)

> **Windows用户建议**：推荐使用WSL2 (Windows Subsystem for Linux)，可获得最佳开发体验。WSL中的服务端口会自动转发到Windows宿主机。

### 🐳 Docker快速部署（推荐）

```bash
# 克隆项目
git clone <repository-url>
cd short-video-maker

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件，填入API密钥

# 启动所有服务
docker-compose up -d

# 访问应用
# 前端: http://localhost:3000
# 后端API: http://localhost:8000
# API文档: http://localhost:8000/docs
```

### 📦 手动安装

#### 1. 安装数据库服务

**Linux/WSL (推荐)**：
```bash
# Ubuntu/Debian/WSL
sudo apt update
sudo apt install mysql-server redis-server

# 启动服务
sudo service mysql start
sudo service redis-server start

# 创建数据库用户
sudo mysql
CREATE DATABASE short_video_maker;
CREATE USER 'videouser'@'localhost' IDENTIFIED BY 'videopass123';
GRANT ALL PRIVILEGES ON short_video_maker.* TO 'videouser'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

**macOS**：
```bash
# 使用Homebrew  
brew install mysql redis
brew services start mysql
brew services start redis

# 配置MySQL
mysql -u root -p
CREATE DATABASE short_video_maker;
CREATE USER 'videouser'@'localhost' IDENTIFIED BY 'videopass123';
GRANT ALL PRIVILEGES ON short_video_maker.* TO 'videouser'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

**Windows原生**（不推荐，建议使用WSL）：
```bash
# 使用Chocolatey
choco install mysql redis-64
```

**或使用Docker（更简单）**：
```bash
# 启动MySQL
docker run --name mysql-short-video \
  -e MYSQL_ROOT_PASSWORD=rootpass \
  -e MYSQL_DATABASE=short_video_maker \
  -e MYSQL_USER=videouser \
  -e MYSQL_PASSWORD=videopass123 \
  -p 3306:3306 -d mysql:8.0

# 启动Redis
docker run --name redis-short-video \
  -p 6379:6379 -d redis:7-alpine
```

#### 2. 后端设置 (推荐使用uv)

```bash
cd backend

# 方法1: 使用uv (推荐，更快更现代)
# 自动安装uv并设置环境
python scripts/setup_uv_environment.py

# 或手动安装uv
curl -LsSf https://astral.sh/uv/install.sh | sh  # Linux/macOS
# 或 Windows: powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# 创建环境并安装依赖
uv venv
uv pip install -e .
uv pip install -e ".[dev]"

# 方法2: 传统pip方式
pip install -r requirements.txt

# 配置环境变量
cp ../.env.example .env
# 编辑.env文件，至少配置一个AI服务的API密钥

# 初始化数据库（确保MySQL已启动）
python scripts/setup_database.py

# 启动后端服务 (uv版本)
python scripts/start_dev_uv.py
# 或传统版本
python scripts/start_dev.py
```

#### 3. 前端设置

```bash
# 注意：前端代码在根目录，不是单独的frontend文件夹
# 返回根目录或直接在根目录执行

cd .. # 如果在backend目录中，先返回根目录

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

#### 4. 验证部署

```bash
# 运行健康检查
curl http://localhost:8000/health

# 运行测试套件
cd tests
python run_all_tests.py --quick --mock
```

## 🎮 使用指南

### 创建视频项目

1. **输入需求** - 描述你想要的视频内容
2. **选择风格** - 科技、创意、商务、教育等
3. **设置参数** - 时长、分辨率、音乐等
4. **开始生成** - 观看AI智能体协作过程
5. **下载结果** - 预览并下载最终视频

### 监控生成过程

- 📊 **实时进度** - 查看每个智能体的执行状态
- 🎯 **中间结果** - 预览概念、脚本、图像等中间产出
- ⚡ **性能指标** - 监控系统资源和执行效率
- 🔧 **错误处理** - 自动重试和人工干预选项

## 🧪 测试和质量保证

### 完整测试套件

```bash
# 运行所有测试
python tests/run_all_tests.py

# 运行特定测试
python tests/run_all_tests.py --tests e2e integration

# 快速测试（跳过长时间测试）
python tests/run_all_tests.py --quick

# 模拟模式（不调用真实API）
python tests/run_all_tests.py --mock
```

### 测试覆盖

- ✅ **端到端测试** - 完整工作流验证
- ✅ **系统集成测试** - 组件间协作验证  
- ✅ **AI服务测试** - 外部API集成验证
- ✅ **性能测试** - 负载和压力测试
- ✅ **用户体验测试** - 界面和交互验证

### 质量指标

- 🎯 **功能覆盖率** > 95%
- ⚡ **响应时间** < 2秒
- 🔄 **系统可用性** > 99.5%
- 🛡️ **错误恢复率** > 90%
- 📱 **移动端兼容性** 完全支持

## 🔧 配置说明

### 🔑 API密钥要求

根据代码分析，运行短视频生成功能需要以下API密钥配置：

#### 🔴 核心服务（必须配置）
**以下服务必须全部配置才能正常生成短视频**：

**1. 文本生成服务（选择一个即可）**：
- `KIMI_API_KEY` - 月之暗面 Kimi K2模型（🇨🇳 国内推荐）
- `GLM_API_KEY` - 智谱AI GLM-4.5模型（🇨🇳 国内推荐）  
- `OPENAI_API_KEY` - OpenAI GPT模型（🌍 国际用户）

**2. 图像生成服务（选择一个即可）**：
- `GLM_API_KEY` - 智谱AI CogView图像生成（🇨🇳 一键多能）
- `JIMENG_API_KEY` - 即梦图像生成（🇨🇳 国内服务）
- `OPENAI_API_KEY` - DALL-E图像生成（🌍 国际用户）
- `STABILITY_API_KEY` - Stability AI图像生成（🌍 国际用户）

**3. 视频生成服务（选择一个即可）**：
- `GLM_API_KEY` - 智谱AI CogVideoX视频生成（🇨🇳 一键多能）
- `MINIMAX_API_KEY` - MiniMax视频生成（🇨🇳 国内服务）
- `RUNWAY_API_KEY` - Runway ML视频生成（🌍 国际用户）

> ⚠️ **重要提醒**：系统缺少任一类服务都无法完成短视频生成流程

#### 💡 推荐配置方案

**方案1：国内用户最佳（仅需1个API密钥）**
```bash
# 智谱AI一键全能 - 文本+图像+视频全覆盖
GLM_API_KEY=your-glm-api-key-here
```

**方案2：国内用户备选**
```bash
# 分别配置不同服务商
KIMI_API_KEY=your-kimi-key-here      # 文本生成
JIMENG_API_KEY=your-jimeng-key-here   # 图像生成  
MINIMAX_API_KEY=your-minimax-key-here # 视频生成
```

**方案3：国际用户推荐**
```bash
# 使用国际服务
OPENAI_API_KEY=sk-your-openai-key-here    # 文本+图像生成
RUNWAY_API_KEY=your-runway-key-here       # 视频生成
```

### 完整环境变量示例

```bash
# =============================================================================
# AI服务配置（根据选择的方案配置）
# =============================================================================

# 方案1：使用智谱AI一键全能
GLM_API_KEY=your-glm-api-key-here

# 或方案2：使用OpenAI + Runway
# OPENAI_API_KEY=sk-your-openai-key-here
# RUNWAY_API_KEY=your-runway-key-here

# 或方案3：使用国内多个服务商
# KIMI_API_KEY=your-kimi-key-here
# JIMENG_API_KEY=your-jimeng-key-here  
# MINIMAX_API_KEY=your-minimax-key-here

# =============================================================================
# 基础系统配置
# =============================================================================

# 数据库配置 (MySQL为主，也支持PostgreSQL)
DATABASE_URL=mysql://videouser:videopass123@localhost:3306/short_video_maker
# 或使用PostgreSQL: DATABASE_URL=postgresql://user:pass@localhost:5432/db
REDIS_URL=redis://localhost:6379/0

# 文件存储配置
STORAGE_TYPE=local  # local, s3, oss
# AWS_ACCESS_KEY_ID=your_access_key
# AWS_SECRET_ACCESS_KEY=your_secret_key

# 应用配置
DEBUG=false
LOG_LEVEL=INFO
JWT_SECRET_KEY=your_jwt_secret
```

> 📋 查看 [API密钥详细获取指南](docs/api/api-keys-guide.md) 了解如何申请各服务的API密钥

### 性能调优

```bash
# 并发设置
MAX_CONCURRENT_TASKS=10
WORKER_PROCESSES=4
CELERY_WORKERS=8

# 缓存配置
REDIS_CACHE_TTL=3600
IMAGE_CACHE_SIZE=1000

# AI服务优化
AI_REQUEST_TIMEOUT=60
AI_RETRY_ATTEMPTS=3
AI_BATCH_SIZE=5
```

## 📊 监控和运维

### 系统监控

- 📈 **应用性能监控** - API响应时间、吞吐量、错误率
- 💾 **资源监控** - CPU、内存、磁盘、网络使用情况
- 🤖 **AI服务监控** - API调用成功率、成本追踪
- 🔍 **业务监控** - 视频生成成功率、用户活跃度

### 日志管理

```bash
# 查看应用日志
docker-compose logs -f backend

# 查看特定智能体日志
grep "ConceptPlannerAgent" logs/app.log

# 错误日志分析
grep "ERROR" logs/app.log | tail -20
```

### 性能分析

```bash
# 运行性能测试
python tests/performance/test_performance_reliability.py

# 生成性能报告
python scripts/generate_performance_report.py

# 查看系统指标
curl http://localhost:8000/metrics
```

## 🔒 安全说明

### 数据安全
- 🔐 **传输加密** - 所有API通信使用HTTPS
- 🗃️ **数据加密** - 敏感数据库字段加密存储
- 🔑 **访问控制** - JWT认证和角色权限管理
- 🛡️ **内容安全** - AI生成内容安全检查

### API安全
- 🚦 **频率限制** - 防止API滥用
- 🔍 **输入验证** - 严格的输入参数验证
- 🛡️ **SQL注入防护** - ORM和参数化查询
- 🔒 **XSS防护** - 输出内容转义和CSP

## 📚 文档中心

详细的技术文档已整理在 [docs](docs/) 目录下，包括：

- **[架构设计](docs/architecture/)** - 系统架构、设计模式、技术决策
- **[部署指南](docs/deployment/)** - 生产部署、环境配置、运维指南
- **[开发文档](docs/development/)** - 开发流程、最佳实践、优化记录
- **[API文档](docs/api/)** - API接口、服务集成、配置说明
- **[测试文档](docs/testing/)** - 测试策略、执行指南、覆盖报告
- **[运维文档](docs/operations/)** - 监控配置、故障排查、性能调优

查看 [文档索引](docs/README.md) 了解完整的文档结构。

## 🤝 开发指南

### 项目结构

```
short-video-maker/
├── docs/                    # 技术文档中心
├── src/                     # Next.js前端应用源码
│   ├── components/          # React组件
│   ├── pages/              # 页面组件
│   └── store/              # 状态管理
├── package.json             # 前端依赖配置
├── next.config.js           # Next.js配置
├── tailwind.config.js       # Tailwind CSS配置
├── backend/                 # FastAPI后端应用
│   ├── app/agents/         # AI智能体
│   ├── app/api/            # API路由
│   ├── app/models/         # 数据模型
│   └── app/services/       # 业务服务
├── tests/                   # 前端测试套件
│   ├── e2e/               # 端到端测试
│   ├── integration/       # 集成测试
│   ├── performance/       # 性能测试
│   └── ux/                # 用户体验测试
├── backend/tests/           # 后端测试套件
└── docker-compose.yml       # Docker编排配置
```

### 开发工作流

1. **Fork项目** 并创建功能分支
2. **本地开发** 使用Docker环境
3. **运行测试** 确保所有测试通过
4. **代码审查** 提交Pull Request
5. **自动部署** 合并后自动部署

### 添加新智能体

```python
# 1. 创建智能体类
class NewAgent(BaseAgent):
    async def execute(self, context: TaskContext) -> AgentResult:
        # 实现智能体逻辑
        pass

# 2. 注册到编排器
orchestrator.register_agent("new_agent", NewAgent())

# 3. 添加测试
class TestNewAgent(unittest.TestCase):
    def test_execute_success(self):
        # 测试代码
        pass
```

## 📈 路线图

### v1.0 (当前版本)
- ✅ 多智能体协作框架
- ✅ 基础视频生成功能
- ✅ Web用户界面
- ✅ 完整测试套件

### v1.1 (计划中)
- 🔄 模板系统和预设风格
- 🔄 批量处理功能
- 🔄 用户管理和权限
- 🔄 高级编辑功能

### v1.2 (未来)
- 🔮 更多AI服务集成
- 🔮 实时协作编辑
- 🔮 移动端应用
- 🔮 企业级功能

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。

## 🙏 致谢

感谢以下开源项目和服务提供商：

- [FastAPI](https://fastapi.tiangolo.com/) - 现代高性能Web框架
- [Next.js](https://nextjs.org/) - React全栈框架
- [OpenAI](https://openai.com/) - AI模型服务
- [Stability AI](https://stability.ai/) - 图像生成服务

## 📞 支持和反馈

- 📧 **邮箱**: support@short-video-maker.com
- 🐛 **问题报告**: [GitHub Issues](issues)
- 💬 **讨论**: [GitHub Discussions](discussions)
- 📚 **文档**: [在线文档](docs)

---

**⭐ 如果这个项目对你有帮助，请给我们一个星标！**