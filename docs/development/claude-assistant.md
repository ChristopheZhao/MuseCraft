# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Architecture Overview

This is **MuseCraft** - a **multi-agent AI-powered creative platform** that automatically creates videos from text descriptions through the collaboration of 6 specialized AI agents. It transforms inspiration into crafted videos through intelligent workflow orchestration. The system supports both **Pipeline** (sequential) and **ReAct** (iterative reasoning) execution modes.

### Core Agent Architecture

The system operates on a **multi-agent orchestration pattern** where each agent has specialized tools and capabilities:

1. **Orchestrator Agent** - Coordinates the entire workflow, supports both Pipeline and ReAct modes
2. **Concept Planner Agent** - Uses LLMs (Kimi/GLM-4.5) for creative concept development
3. **Script Writer Agent** - Generates video scripts using GPT-4/GLM-4.5
4. **Image Generator Agent** - Creates visuals via Stability AI/DALL-E/CogView/Tongyi
5. **Video Generator Agent** - Produces video clips using CogVideoX
6. **Video Composer Agent** - Assembles final video using FFmpeg and smart composition
7. **Quality Checker Agent** - Validates output quality and safety

### Agent Design Patterns

- **Pipeline Mode**: Fixed sequential execution (Concept → Script → Images → Videos → Composition → Quality Check)
- **ReAct Mode**: Iterative OBSERVE → THINK → PLAN → ACT → REFLECT loops with dynamic strategy adjustment
- **Tool System**: Each agent uses a registry of specialized tools (AI services, video processing, storage, etc.)
- **Memory Management**: Agents maintain short-term, long-term, and episodic memory
- **Prompt Templates**: Centralized Jinja2-based template management

### Tech Stack

- **Backend**: FastAPI + SQLAlchemy + PostgreSQL + Redis + Celery
- **Frontend**: Next.js + React + TypeScript + Tailwind CSS + Zustand
- **AI Services**: OpenAI, Kimi (Moonshot), Zhipu AI (GLM-4.5), Stability AI
- **Video Processing**: FFmpeg, OpenCV, MoviePy
- **Storage**: Local/MinIO/S3 with universal file management
- **Real-time**: WebSocket for progress tracking

## Development Commands

### Backend Development

```bash
# Start development environment (includes PostgreSQL, Redis, Celery, FastAPI)
cd backend
python scripts/start_dev.py

# Run database migrations
alembic upgrade head

# Initialize database
python scripts/setup_database.py

# System validation
python scripts/validate_system.py
```

### Frontend Development

```bash
# Start frontend development server
npm run dev

# Build for production
npm run build

# Type checking
npm run type-check

# Linting
npm run lint
```

### Testing

The system has comprehensive test coverage across multiple dimensions:

```bash
# Run all tests with comprehensive reporting
python tests/run_all_tests.py

# Run specific test suites
python tests/run_all_tests.py --tests e2e integration
python tests/run_all_tests.py --tests ai_services performance

# Quick testing (skip long-running tests)
python tests/run_all_tests.py --quick

# Mock mode (no external API calls)
python tests/run_all_tests.py --mock

# Frontend tests
npm run test              # Unit tests
npm run test:integration  # Integration tests
npm run test:e2e         # End-to-end tests
npm run test:performance # Performance tests
npm run test:a11y        # Accessibility tests
npm run test:all         # All frontend tests
```

### Docker Development

```bash
# Start entire stack
docker-compose up -d

# View logs
docker-compose logs -f backend
docker-compose logs -f frontend

# Rebuild services
docker-compose build --no-cache
```

## Key Implementation Details

### Agent Base Class Pattern

All agents inherit from `BaseAgent` with integrated:
- **Tool Registry**: Access to registered tools via `self.use_tool(tool_name, action, parameters)`
- **Memory Manager**: Store/retrieve memories via `self.store_memory()` and `self.retrieve_memories()`
- **Prompt Templates**: Render templates via `self.render_prompt(template_name, variables)`
- **WebSocket Communication**: Real-time progress updates to frontend

### Tool System Architecture

Tools follow a plugin architecture:
- **Base Tool Class**: `AsyncTool` with metadata, validation, and execution patterns
- **Tool Registry**: Centralized discovery and dependency management
- **Tool Categories**: AI services, video processing, storage, composition
- **Configuration**: YAML-based configuration with environment variable support

### ReAct Implementation

The ReAct orchestrator implements the reasoning-acting pattern:
```python
while iteration < max_iterations:
    observation = await self._observe_current_state(workflow_state)
    reasoning = await self._think_and_reason(observation, workflow_state)
    action_plan = await self._plan_next_action(reasoning, workflow_state)
    action_result = await self._execute_action(action_plan, workflow_state, db)
    reflection = await self._reflect_on_results(action_result, workflow_state)
    if reflection.get("workflow_complete"):
        break
```

### API Key Configuration

The system requires multiple AI service API keys. Check `API_KEYS_GUIDE.md` for complete setup:

```bash
# Core LLM services
OPENAI_API_KEY=your_openai_key
KIMI_API_KEY=your_kimi_key  # Moonshot AI
ZHIPU_API_KEY=your_zhipu_key  # GLM-4.5 + CogView + CogVideoX

# Image generation (choose one or more)
STABILITY_API_KEY=your_stability_key
TONGYI_API_KEY=your_tongyi_key

# Storage (optional, defaults to local)
AWS_ACCESS_KEY_ID=your_aws_key
AWS_SECRET_ACCESS_KEY=your_aws_secret
```

### Video Processing Pipeline

The video generation follows this flow:
1. **Concept Planning** → Creative brief and scene breakdown
2. **Script Generation** → Detailed scene scripts with timing
3. **Image Generation** → Key frame images for each scene
4. **Video Generation** → Short video clips from images + prompts
5. **Video Composition** → FFmpeg-based assembly with transitions
6. **Quality Check** → Content validation and optimization

### Error Recovery and Monitoring

- **Automatic Retry Logic**: Failed operations retry with exponential backoff
- **Circuit Breaker Pattern**: Prevents cascading failures in AI service calls
- **Health Checks**: Comprehensive system validation at `/health`
- **Real-time Progress**: WebSocket updates for all workflow stages
- **Performance Monitoring**: Built-in metrics and logging

### Windows Compatibility

The system is designed for cross-platform operation. For Windows development:
- Use `scripts/windows_setup.bat` for initial setup
- FFmpeg must be installed and in PATH
- Python virtual environment recommended
- PostgreSQL and Redis can run via Docker or native Windows installation

## Important Configuration Files

- `backend/app/core/config.py` - Main application configuration
- `TOOLS_CONFIGURATION.md` - Comprehensive tool setup guide
- `AGENT_DESIGN_PATTERNS.md` - Agent architecture patterns
- `DEPLOYMENT_CHECKLIST.md` - Production deployment guide
- `API_KEYS_GUIDE.md` - API key setup instructions

## Testing Architecture

The testing framework covers:
- **E2E Tests**: Complete video generation workflows
- **Integration Tests**: Agent coordination and tool interaction
- **AI Service Tests**: External API integration validation
- **Performance Tests**: Load testing and benchmarking
- **UX Tests**: Frontend interaction and accessibility
- **System Tests**: Database, storage, and infrastructure validation

All tests support both real API mode and mock mode for CI/CD environments.

## Environment Notes

- **Development Environment**
  - 项目使用的是uv环境
  - 项目使用的是uv python环境，要测试需要用uv测试

## Development Philosophy

- **Goal-Oriented Development**
  - 以完成目标为导向，而不是修复bug为导向，例如项目需要合成视频，依赖ffmpeg，虽然有降级措施，如果ffmpeg为安装，就返回第一个场景的视频，但是这样的做法不是冗余性，而完全是为了修复一个issues的"捷径"，这种做法是避免和不应该作为研发思路的。