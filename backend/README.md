# Short Video Maker Backend API

A comprehensive backend API for AI-powered short video generation using multi-agent orchestration.

## Features

- **Multi-Agent Workflow**: Orchestrated system with 7 specialized agents
  - Concept Planner: Analyzes requirements and creates video concepts
  - Script Writer: Generates detailed scripts and voice-over text
  - Voice Synthesizer: Produces per-scene narration using configurable TTS providers
  - Image Generator: Creates visual assets using AI image generation
  - Video Generator: Generates video clips from images and prompts
  - Video Composer: Combines clips into final video with transitions; can be re-entered to add audio/subtitles later
  - Quality Checker: Validates output quality and compliance

- **Real-time Communication**: WebSocket support for live progress updates
- **Task Queue System**: Asynchronous processing with Celery and Redis
- **File Management**: Comprehensive storage and resource management
- **RESTful API**: Well-documented endpoints with OpenAPI/Swagger
- **Database Integration**: MySQL/PostgreSQL with SQLAlchemy ORM
- **Error Handling**: Robust error handling and retry mechanisms

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Frontend      │    │   FastAPI       │    │   Celery        │
│   (Next.js)     │◄──►│   Backend       │◄──►│   Workers       │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                              │                        │
                       ┌──────▼──────┐         ┌──────▼──────┐
                       │    MySQL    │         │   Redis     │
                       │  Database   │         │   Broker    │
                       └─────────────┘         └─────────────┘
```

## System Requirements

### Required Dependencies

- **FFmpeg**: Required for video composition and processing
  ```bash
  # Ubuntu/Debian
  sudo apt update && sudo apt install -y ffmpeg
  
  # macOS
  brew install ffmpeg
  
  # Windows
  # Download from https://ffmpeg.org/download.html
  ```

### Python Requirements
- Python 3.8+
- PostgreSQL 12+
- Redis 6+

## Quick Start

### Using Docker (Recommended)

1. **Clone and setup**:
   ```bash
   cd backend
   cp ../.env.example .env
   # Edit .env with your API keys
   ```

2. **Start all services**:
   ```bash
   docker-compose up -d
   ```

3. **Run database migrations**:
   ```bash
   docker-compose exec api alembic upgrade head
   ```

4. **Access the API**:
   - API Documentation: http://localhost:8000/api/v1/docs
   - Health Check: http://localhost:8000/health
   - Celery Monitor: http://localhost:5555

### Manual Installation

1. **Prerequisites**:
   - Python 3.11+
   - MySQL 8.0+ (or PostgreSQL 13+)
   - Redis 6+
   - FFmpeg
   - UV (Python package manager)

   **Note for Windows users**: We recommend using WSL2 (Windows Subsystem for Linux) for development to ensure compatibility with all dependencies.

2. **Install UV and dependencies**:
   ```bash
   # Install UV if not already installed
   curl -LsSf https://astral.sh/uv/install.sh | sh
   
   # Sync dependencies using UV
   uv sync
   ```

3. **Setup environment**:
   ```bash
   cp ../.env.example .env
   # Edit .env with your configuration
   ```

4. **Setup database**:
   ```bash
   python scripts/setup_database.py
   ```

5. **Start development server**:
   ```bash
   python scripts/start_dev.py
   ```

## Configuration

### Environment Variables

Key configuration options in `.env`:

```bash
# Database (MySQL example, also supports PostgreSQL)
DATABASE_URL=mysql://videouser:videopass123@localhost:3306/short_video_maker

# Redis
REDIS_URL=redis://localhost:6379/0

# AI Services (choose at least one from each category)
# Text Generation (必选其一)
KIMI_API_KEY=your_kimi_key           # 月之暗面 Kimi (推荐国内用户)
GLM_API_KEY=your_glm_key             # 智谱AI GLM-4.5 (推荐国内用户)
OPENAI_API_KEY=your_openai_key       # OpenAI GPT (国际用户)

# Image Generation (必选其一)
STABILITY_API_KEY=your_stability_key  # Stability AI
TONGYI_API_KEY=your_tongyi_key       # 阿里通义万相

# Video Generation (必选其一)  
RUNWAY_API_KEY=your_runway_key       # Runway ML
MINIMAX_API_KEY=your_minimax_key     # MiniMax abab-video

# File Storage
STORAGE_TYPE=local
MAX_FILE_SIZE=100  # MB

# Audio mixing strategy (defaults shown)
AUDIO_MIXING_MODE=composer   # composer | agent
AUDIO_FADE_IN_DURATION=1.0
AUDIO_FADE_OUT_DURATION=1.0
```

## Storage Layout

- `storage/temp`: 临时工件，任务结束后可安全清理。
- `storage/generated`: 中间资产（场景视频、音频片段等）。
- `storage/outputs/videos`: 最终交付的成品视频（自动设为只读并同步至 OSS）。


### AI Service Configuration

The system supports multiple AI services:

**Text Generation**:
- **Kimi (月之暗面)**: K2 model with 128K context, optimized for Chinese (推荐国内用户)
- **GLM-4.5 (智谱AI)**: Advanced Chinese language model with multimodal capabilities
- **OpenAI**: GPT-4/GPT-3.5 models for text generation

**Image Generation**:
- **Stability AI**: Stable Diffusion models for high-quality images
- **Tongyi Wanxiang (通义万相)**: Alibaba's image generation service
- **DALL-E**: OpenAI's image generation (if using OpenAI key)

**Video Generation**:
- **Runway ML**: Gen-2/Gen-3 for video generation from images
- **MiniMax**: abab-video-1 model for text/image to video
- **CogVideoX**: Available through GLM API for video generation

## API Endpoints

### Task Management

- `POST /api/v1/tasks/` - Create new video generation task
- `GET /api/v1/tasks/` - List all tasks
- `GET /api/v1/tasks/{task_id}` - Get task details
- `GET /api/v1/tasks/{task_id}/status` - Get task status and progress
- `POST /api/v1/tasks/{task_id}/retry` - Retry failed task
- `DELETE /api/v1/tasks/{task_id}` - Cancel task

### File Management

- `POST /api/v1/files/upload` - Upload files
- `GET /api/v1/files/uploads/{filename}` - Serve uploaded files
- `GET /api/v1/files/generated/{filename}` - Serve generated files
- `GET /api/v1/files/resource/{resource_id}` - Get file by resource ID

### WebSocket

- `WS /api/v1/ws/connect?task_id={task_id}` - Real-time updates

## Agent Workflow

The system supports two execution modes:

### Pipeline Mode (Default)
Sequential execution of agents in a fixed order:

1. **Concept Planner**: Analyzes user prompt and creates detailed video concept
2. **Script Writer**: Generates scripts and narratives for each scene
3. **Image Generator**: Creates visual assets using AI image generation
4. **Video Generator**: Converts images to video clips with motion
5. **Video Composer**: Combines clips into final video with transitions (video-only)
6. **Audio Generator**: Generates, analyzes and aligns background music (delivers aligned BGM asset)
7. **Video Composer (re-entry)**: Adds background music onto final video (and later VO/SRT)
8. **Quality Checker**: Validates output quality and compliance

Notes:
- In composer mode (default), AudioAgent does not mix audio into video; Composer performs the mixing.
- Audio alignment is enforced by analysis + smart adjust to ensure exact match with video duration and smooth fade-out.

## Audio Mixing Architecture (Composer-first)

- Goals
  - AudioAgent 专注“专业配乐交付”：观测 → 规划 → 生成 → 分析 → 智能对齐；输出等长、可用的 BGM 资产。
  - VideoComposerAgent 统一“装配”：先视频拼接（video-only），随后多次可重入添加 BGM/配音/字幕等。
  - Orchestrator 在关键节点多次调用 Composer，保证每步仅做当前所需的最小合成工作。

- Tools (supplier-agnostic)
  - `suno_client`：中立的配乐生成工具（自由文本风格/情绪）。
  - `audio_analysis_tool`（新增）：时长/静音窗口/候选截断点分析（ffmpeg/ffprobe）。
  - `audio_processor`（扩展）：`adjust_duration_smart` 与 `apply_edit_plan` 执行智能对齐（trim/loop/crossfade/fade）。
  - `ffmpeg_tool`：Composer `add_bgm` 混流导出。

## Integration Tests (Audio)

- `backend/tests/integration/test_audio_mixing.py`：AudioAgent 产 BGM → Composer `add_bgm` 混流 → 断言最终视频存在。
- `backend/tests/integration/test_audio_smart_truncation.py`：过长 BGM → 分析+编辑计划对齐 → Composer 混流 → 断言最终视频存在。

Run:
- `uv run pytest -k "audio_mixing or smart_truncation" -q`
- Tests are skipped automatically when ffmpeg/ffprobe is missing.

### ReAct Mode
Iterative reasoning-acting pattern with dynamic strategy adjustment:
- Agents can observe, think, plan, act, and reflect
- Supports backtracking and strategy changes based on results
- More flexible but potentially longer execution time

Each agent can be configured independently and supports retry mechanisms.

## Database Schema

### Core Models

- **Task**: Main task record with status and progress tracking
- **Scene**: Individual video scenes with timing and content
- **Resource**: Generated and uploaded files (images, videos, audio)
- **AgentExecution**: Execution records for each agent in the workflow

### Relationships

```
Task (1) ──→ (N) Scene
Task (1) ──→ (N) Resource  
Task (1) ──→ (N) AgentExecution
Scene (1) ──→ (N) Resource
```

## Development

### Project Structure

```
backend/
├── app/
│   ├── agents/          # AI agent implementations
│   ├── api/             # FastAPI routes and endpoints
│   ├── core/            # Core configuration and database
│   ├── models/          # SQLAlchemy database models
│   ├── services/        # Business logic and external services
│   └── utils/           # Utility functions
├── scripts/             # Deployment and setup scripts
├── storage/             # File storage directories
├── tests/               # Test suite
└── alembic/             # Database migrations
```

### Adding New Agents

1. Create agent class inheriting from `BaseAgent`
2. Implement `_execute_impl` method
3. Register agent in `OrchestratorAgent`
4. Add agent type to models

### Running Tests

```bash
# Activate virtual environment
source .venv/bin/activate

# Run all tests
python tests/run_all_tests.py

# Run specific test categories
python tests/run_all_tests.py --tests unit integration

# Run with coverage
pytest tests/ -v --cov=app --cov-report=html
```

### Database Migrations

```bash
# Create migration
alembic revision --autogenerate -m "Description"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

## Monitoring

### Health Checks

- API: `GET /health`
- Individual services via Docker health checks
- Celery monitoring via Flower: http://localhost:5555

### Logging

Structured logging with configurable levels:
- Application logs: `logs/app.log`
- Celery logs: captured by worker processes
- Database logs: configurable via SQLAlchemy

### Metrics

Key metrics to monitor:
- Task completion rates
- Agent execution times
- File storage usage
- API response times
- Queue length and processing times

## Deployment

### Production Setup

1. **Use production database**: Configure MySQL/PostgreSQL cluster
2. **Redis cluster**: Set up Redis cluster for high availability
3. **Scale workers**: Run multiple Celery workers
4. **Load balancing**: Use nginx or similar for API load balancing
5. **Monitoring**: Set up proper monitoring and alerting

### Environment Variables for Production

```bash
DEBUG=false
LOG_LEVEL=WARNING
SECRET_KEY=your_production_secret
# MySQL example
DATABASE_URL=mysql://prod_user:prod_pass@db_host:3306/prod_db
# Or PostgreSQL
# DATABASE_URL=postgresql://prod_user:prod_pass@db_host:5432/prod_db
```

## Troubleshooting

### Common Issues

1. **Database connection failures**: Check MySQL/PostgreSQL configuration
   - For MySQL on WSL: Ensure MySQL service is running: `sudo service mysql status`
   - Check credentials in DATABASE_URL
2. **Celery workers not processing**: Verify Redis connection
   - Check Redis is running: `redis-cli ping`
3. **AI generation failures**: Check API keys and quotas
   - Verify at least one service per category is configured
   - Check API key validity and remaining credits
4. **File permission errors**: Ensure proper storage directory permissions
   - Run: `chmod -R 755 storage/`
5. **UV command not found**: Install UV package manager
   - Run: `curl -LsSf https://astral.sh/uv/install.sh | sh`

### Debugging

Enable debug mode:
```bash
DEBUG=true
LOG_LEVEL=DEBUG
```

Check service status:
```bash
docker-compose ps
docker-compose logs api
docker-compose logs celery_worker
```

## Contributing

1. Fork the repository
2. Create feature branch
3. Add tests for new functionality
4. Run test suite
5. Submit pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For support, please:
1. Check the documentation
2. Search existing issues
3. Create a new issue with detailed description
4. Include logs and configuration details
### ReActAgent 关键规范（无状态 + 合同优先）

- PLAN 的 system 提示词为必需项：若 `agents/<agent>.system` 加载失败或为空，直接抛 AgentError（Fail‑Fast，便于审计）。
- OBS 仅包含事实：`scenes`、`completed_scene_numbers`、`failed_scene_numbers` 以及当前回合的 `act_log`；不包含统计、建议或“准备清单”。
- 观察压缩默认关闭：可通过 `REACT_OBS_AUGMENT_ENABLED=true` 开启，并用 `REACT_OBS_SCENE_THRESHOLD`、`REACT_OBS_SIZE_THRESHOLD` 配置阈值。即便开启，PLAN 输入也会过滤 `aug`/`aug_meta`，避免将模型衍生文本回灌到规划提示词。
- PLAN 产出 `tool_calls`（响应总是存在，调用列表可能为空）；ACT 执行 `tool_calls` 并写入 WM 事件；REFLECT 仅做领域事实写回，并叠加最小合同字段 `{task_complete, completed_reason}`。若本轮实际执行过调用，则忽略该轮合同中的 `task_complete`。
- 工具失败必须抛出 ToolError；Agent 仅依据 `ToolOutput.success` 判断成败。业务层不要返回 `{"success": false}` 而不抛异常。
- WorkingMemory 是迭代事实的唯一来源；Agent 不缓存跨回合状态。每次调用会记录 `{scene_number, action, success, error_type}` 事件，可追溯。
