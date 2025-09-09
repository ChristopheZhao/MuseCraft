# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Quick Reference Commands

```bash
# Backend development
uv run python scripts/start_dev.py    # Start full development environment
uv run python scripts/validate_system.py  # System validation
uv run python tests/run_all_tests.py  # Run comprehensive tests

# Frontend development  
npm run dev          # Start development server
npm run build        # Build for production
npm run type-check   # TypeScript checking
npm run lint         # Code linting

# Testing specific components
uv run python test_llm_driven_system.py  # Test LLM-driven system
uv run python test_mas_integration.py    # Test multi-agent system
```

# Code Style Guidelines

- **Python**: Use type hints, async/await patterns, follow PEP 8
- **TypeScript**: Strict mode enabled, prefer interfaces over types
- **Import Style**: Use absolute imports, destructuring when possible
- **Error Handling**: Always include proper error handling and logging
- **Testing**: Write tests BEFORE implementation (TDD approach)
- **Commits**: Use conventional commit format with Chinese descriptions

# Architecture Principles

**IMPORTANT**: This system follows LLM-driven architecture principles:
- ❌ NO hardcoded decision logic (scene counts, durations, parameters, **video styles**)
- ✅ LLM Function Call for all dynamic decisions including intelligent style design
- ✅ Tools are pure executors, Agents make decisions
- ✅ Each Agent gets specialized tool allocation only
- ✅ Service abstraction layers separate from business tools
- ✅ **Style Intelligence**: Agents create custom styles rather than choosing from preset options
- ✅ **Agent Responsibility Boundaries**: Each Agent has clear, non-overlapping decision-making scope to avoid conflicts and redundancy

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

### Core Design Philosophy: LLM-Driven Video Composition

**MuseCraft's fundamental innovation** lies in its **Multi-Agent Composition Architecture** that transcends individual AI video generation API limitations through intelligent orchestration:

#### **Video API Capability Constraints & Amplification Strategy**
- **Current Reality**: Video generation APIs have discrete capabilities (e.g., CogVideoX-3 supports exactly 5s or 10s clips, not ranges)
- **Amplification Principle**: Instead of being limited by API constraints, the system **combines multiple discrete video segments** to create longer, more complex videos
- **Composition Formula**: `Final Video = Smart Assembly of [5s|10s] × N scenes`
  - Minimum: 4 scenes × 5s = 20s video
  - Maximum: 10+ scenes × 10s = 100s+ video
  - **Decision Making**: Agents intelligently choose 5s vs 10s per scene based on content complexity

#### **LLM-Driven Duration Intelligence**
- **No Hardcoded Limits**: Scene count, individual durations, and composition strategies are **entirely decided by AI agents**
- **Content-Aware Decisions**: Agents analyze content complexity to determine optimal scene breakdown and timing
- **Dynamic Adaptation**: As video APIs evolve (15s, 20s options), the system automatically leverages new capabilities while maintaining composition advantages

#### **Intelligent Style Design System** 🎨
- **Smart Style Creation**: ConceptGenerationTool intelligently designs video styles based on user content, not limited to preset options
- **Multi-Dimensional Style Framework**:
  - **表现形式**: 真人实拍/动画制作/混合媒体
  - **叙事风格**: 纪录片式/商业推广式/电影叙事式
  - **制作品味**: 极简主义/精致奢华/真实质朴
  - **情感基调**: 专业权威/温馨亲和/活力动感/神秘艺术
- **Creative Flexibility**: Can handle any user style request (e.g., "cyberpunk", "90s VHS", "Miyazaki anime style") by intelligent style composition
- **User Intent Preservation**: Original user requests retained for video generation while intelligent style guides visual execution

#### **Future-Proof Amplification Design**
- **API Evolution Independence**: System value increases with API improvements rather than being replaced
- **Scalable Architecture**: `amplification_ratio` ensures the system can generate increasingly longer videos as base capabilities improve
- **Style Evolution Support**: As video APIs support more style options, intelligent composition scales automatically
- **Competitive Advantage**: Professional video composition through multi-agent orchestration, not just single API calls

### Agent Design Patterns

- **Pipeline Mode**: Fixed sequential execution (Concept → Script → Images → Videos → Composition → Quality Check)
- **ReAct Mode**: Iterative OBSERVE → THINK → PLAN → ACT → REFLECT loops with dynamic strategy adjustment
- **Tool System**: Each agent uses a registry of specialized tools (AI services, video processing, storage, etc.)
- **Memory Management**: Agents maintain short-term, long-term, and episodic memory
- **Prompt Templates**: Centralized Jinja2-based template management
- **Function Call Architecture**: LLM-driven tool selection and parameter optimization
- **Composition-First Design**: Every decision optimized for intelligent video segment assembly
- **Clear Responsibility Boundaries**: Each Agent owns specific decision domains without overlap:
  - **ConceptPlanner**: Scene count, duration selection (5s/10s based on API constraints), style design
  - **ScriptWriter**: Script content, scene continuity analysis, narrative structure
  - **ImageGenerator**: Visual generation, first frame creation
  - **VideoGenerator**: Video synthesis using existing decisions, no re-planning
  - **Tools**: Pure executors with no decision logic - only analysis and suggestions

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
- **Function Call Support**: Native GLM-4-plus function calling via `self.llm_function_call()`
- **Specialized Tool Allocation**: Each agent receives only relevant tools, avoiding tool overload

### Tool System Architecture

Tools follow a plugin architecture:
- **Base Tool Class**: `AsyncTool` with metadata, validation, and execution patterns
- **Tool Registry**: Centralized discovery and dependency management
- **Tool Categories**: AI services, video processing, storage, composition, analysis
- **Configuration**: YAML-based configuration with environment variable support
- **Agent-Tool Allocation**: Dynamic assignment of specialized tools per agent type
- **Pure Executor Pattern**: Tools execute without internal decision logic - decisions made by LLM

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

### Intelligent Style Design Workflow 🎨

The system creates custom video styles through multi-dimensional analysis rather than preset selection:

#### **User Input → Style Intelligence**
```bash
# Traditional approach (WRONG)
User: "Make a video about my grandmother"
System: Choose from [professional, cinematic, documentary...]

# MAS Intelligent Approach (CORRECT)  
User: "Make a video about my grandmother teaching me to cook"
ConceptGenerationTool: Analyzes → Creates "Warm Family Heritage Style"
  - 表现形式: 真人实拍 (authentic family moments)
  - 叙事风格: 纪录片式 (natural documentation)  
  - 制作品味: 真实质朴 (unpolished, genuine)
  - 情感基调: 温馨亲和 (warm, intimate)
```

#### **Style Design Data Flow**
1. **Input**: `user_prompt` + optional `style_preference`
2. **Analysis**: ConceptGenerationTool applies professional video style framework
3. **Creation**: `intelligent_style_design` with custom style composition
4. **Preservation**: Original `user_prompt` retained for content understanding
5. **Application**: All downstream agents use both content and style guidance

### Video Composition Pipeline: API-Constrained to Long-Form Intelligence

The system transforms discrete API capabilities into cinematic experiences through intelligent composition:

#### **Stage 1: Content-Aware Scene Planning**
- **LLM Analysis**: Agents analyze user prompt complexity and determine optimal scene breakdown  
- **Style Integration**: Intelligent style design guides visual direction decisions
- **Duration Intelligence**: Each scene assigned **5s or 10s** based on content density and narrative requirements
- **Composition Strategy**: Agents decide total scene count (4-10+) to achieve desired video length

#### **Stage 2: Per-Scene Asset Creation**
- **Script Generation** → Professional scene scripts optimized for 5s/10s segments
- **Image Generation** → Key frame images designed for video segment initialization
- **Video Generation** → **Exactly 5s or 10s clips** using CogVideoX-3 discrete capabilities

#### **Stage 3: Multi-Agent Video Assembly**
- **Intelligent Composition** → FFmpeg-based assembly with AI-generated transitions
- **Temporal Optimization** → Smart pacing across concatenated segments
- **Quality Validation** → Content coherence across assembled video segments

#### **Core Innovation: Amplification Through Composition**
```
User Request: "60-second cooking tutorial"
↓ LLM Analysis
Scene Breakdown: [10s intro + 8×5s steps + 10s outro] = 60s total
↓ Asset Generation  
9 Discrete Video Segments: API generates exactly 5s or 10s each
↓ Intelligent Assembly
Professional 60s Video: Seamless composition with transitions
```

This architecture ensures the system's value **increases** rather than decreases as video APIs evolve, maintaining composition advantages over single-call solutions.

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

## MAS (Multi-Agent System) Design Principles

### Core Architecture Evolution

The system has evolved from hardcoded decision trees to **LLM-driven intelligent decision making**:

```
❌ Old Pattern: Agent → Hardcoded Logic → Fixed Parameters → Tool Execution
✅ New Pattern: Agent → LLM Function Call → Dynamic Tool Selection → Intelligent Parameters → Tool Execution
```

### Agent vs Tool Responsibilities

**Agent Responsibilities:**
- Workflow orchestration and coordination
- LLM-driven decision making via Function Call
- Memory management and context sharing
- Progress tracking and error handling
- Cross-agent communication

**Tool Responsibilities:**
- Pure execution of specific tasks (no decision logic)
- Parameter validation and processing
- Integration with external services
- Atomic operation completion
- Result formatting and reporting

### Key Design Decisions

1. **No Hardcoded Limits**: Scene counts, durations, and parameters dynamically determined by LLM analysis
2. **Specialized Tool Allocation**: Each agent receives only relevant tools to avoid cognitive overload
3. **Function Call Native**: Uses GLM-4-plus native function calling instead of custom prompt engineering
4. **Pure Executor Tools**: Tools contain no business logic - all decisions flow through LLM reasoning
5. **Intelligent Fallbacks**: Smart degradation when LLM services unavailable

### Agent Tool Allocation Matrix

```python
# Each agent gets specialized tools, not all tools
CONCEPT_PLANNER: ["concept_generation", "intelligent_scene_planning", "content_analysis"]
VIDEO_GENERATOR: ["video_generation", "scene_analysis", "parameter_optimization"] 
SCRIPT_WRITER: ["script_generation", "scene_continuity_analysis", "narrative_analysis"]
IMAGE_GENERATOR: ["image_generation", "style_extraction", "visual_consistency_check"]
```

### Intelligence Distribution

- **LLM Layer**: High-level reasoning, planning, and parameter optimization
- **Agent Layer**: Workflow coordination and memory management  
- **Tool Layer**: Atomic task execution and service integration
- **Service Layer**: External API abstractions (OpenAI, Zhipu, etc.)

### Function Call Implementation

Agents use native LLM function calling:

```python
# Agent decides which tools to use and with what parameters
result = await self.llm_function_call(
    messages=context_messages,
    context_description="Generate video for complex action scene",
    temperature=0.3
)

# LLM selects: video_generation_generate_video with optimized duration
if result.get("tool_calls"):
    for tool_call in result["tool_calls"]:
        await self._execute_function_call(tool_call["function"]["name"], 
                                         tool_call["function"]["arguments"])
```

### Benefits of This Architecture

1. **Adaptability**: System adapts to different content complexities without code changes
2. **Extensibility**: New tools and agents can be added without modifying existing logic
3. **Intelligence**: Decisions based on content analysis rather than fixed rules
4. **Maintainability**: Clear separation of concerns between reasoning and execution
5. **Scalability**: Agent specialization prevents tool overload and improves focus

## Agent Design Principles

### Thinking Mode Policy
- **Planning agents**: Enable thinking (concept planning, scene design, orchestration)
- **Execution agents**: Disable thinking (single-pass generation, media ops, file operations)
- **Mixed agents**: Split phases — upstream planning with thinking, downstream finalization without thinking
- **No hardcoded complexity rules**: Selection is a priori by agent role, with optional per-call overrides

### Token Budgeting
- **Two-tier defaults**: Standard (thinking disabled) vs Thinking (larger budget when enabled)
- **Centralized configuration**: Global defaults in config with .env overrides
- **No call-site hardcoding**: Keep per-call token overrides optional

### Function Call Constraints
- **Tool routing**: All tool steps use FC — expose function list to LLM for autonomous tool selection
- **Thinking decoupling**: Thinking only affects reasoning budget, not FC decision capability
- **Pure LLM abilities**: Internal capabilities (prompt enhancement, text polishing) use direct LLM calls, not tools
- **Chinese FC constraints**:
  - If tools needed: Return only tool_calls
  - If no tools needed: Return final Chinese answer in content
  - No explanations, headings, or code blocks

### Tool Architecture Principles
- **Single extension path**: Tools are the ONLY way for Agents to extend LLM capabilities
- **External integration mandate**: All side-effects (IO/network/system) MUST be tools
- **Centralized registration**: Tools registered in tool layer for reuse; implementation swapping doesn't affect Agent code
- **Tool layer responsibilities**: Dependency validation, timeout/retry/rate limiting, observability
- **Agent restrictions**: Only orchestration, strategy selection, pure function transforms, prompt assembly

### Memory and Fallback Principles
- **Memory decoupling**: Context/creative guidance through shared memory interface
- **Graceful degradation**: Memory unavailability causes warnings, not workflow blocks
- **External policies**: Read/write rules, tags, TTL through configuration, not hardcoded
- **Systematic fallbacks**: Tool unavailability triggers fallback paths through tools/memory, not temporary IO
- **Limited retries**: Configurable retry limits with fallback to minimal viable results

### Anti-Hardcoding Guidelines
- **Prohibited hardcoding**: No if/else/rule-trees replacing LLM semantic understanding, tool selection, parameter decisions
- **Tool names/schemas**: Centrally defined in tool registry (configuration, not hardcoding)
- **Business thresholds**: Move to config files, not scattered magic numbers in code
- **Domain priors**: Inject into LLM context (system prompts, few-shot) rather than code branches
- **Decision autonomy**: Preserve LLM Function Call decision rights; Agents declare capability boundaries only