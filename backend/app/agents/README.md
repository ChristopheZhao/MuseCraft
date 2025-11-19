# Agent系统架构说明

## 📁 目录结构

```
agents/
├── __init__.py                    # Agent模块初始化
├── README.md                      # 架构说明文档
├── 
├── core/                          # 核心组件
│   ├── __init__.py
│   ├── base_agent.py             # Agent基类
│   ├── agent_registry.py         # Agent注册管理
│   ├── execution_engine.py       # 执行引擎
│   └── exceptions.py             # 异常定义
│
├── orchestrators/                 # 编排器agents
│   ├── __init__.py
│   ├── pipeline_orchestrator.py  # 管道式编排器
│   ├── react_orchestrator.py     # ReAct编排器
│   └── hybrid_orchestrator.py    # 混合编排器
│
├── specialists/                   # 专业智能体
│   ├── __init__.py
│   ├── concept_planner.py        # 概念规划
│   ├── script_writer.py          # 脚本编写
│   ├── image_generator.py        # 图像生成
│   ├── video_generator.py        # 视频生成
│   ├── video_composer.py         # 视频合成
│   └── quality_checker.py        # 质量检查
│
├── tools/                         # 工具模块
│   ├── __init__.py
│   ├── base_tool.py              # 工具基类
│   ├── tool_registry.py          # 工具注册
│   ├── 
│   ├── ai_services/              # AI服务工具
│   │   ├── __init__.py
│   │   ├── openai_client.py      # OpenAI集成
│   │   ├── stability_client.py   # Stability AI集成
│   │   ├── runway_client.py      # Runway ML集成
│   │   └── anthropic_client.py   # Anthropic集成
│   │
│   ├── media_processing/         # 媒体处理工具
│   │   ├── __init__.py
│   │   ├── image_processor.py    # 图像处理
│   │   ├── video_processor.py    # 视频处理
│   │   ├── audio_processor.py    # 音频处理
│   │   └── ffmpeg_wrapper.py     # FFmpeg封装
│   │
│   ├── file_management/          # 文件管理工具
│   │   ├── __init__.py
│   │   ├── storage_manager.py    # 存储管理
│   │   ├── file_validator.py     # 文件验证
│   │   └── cloud_uploader.py     # 云存储上传
│   │
│   └── utilities/                # 通用工具
│       ├── __init__.py
│       ├── text_processor.py     # 文本处理
│       ├── json_parser.py        # JSON解析
│       ├── validator.py          # 数据验证
│       └── formatter.py          # 格式化工具
│
├── memory/                        # 记忆管理模块
│   ├── __init__.py
│   ├── short_term/               # 短期记忆（WorkingMemory 层）
│   └── long_term/                # 长期记忆（语义/情景层）
│       ├── stores/base.py        # 记忆基类 & 存储抽象
│       └── manager/memory_manager.py  # 记忆管理器实现
│
├── prompts/                       # 提示词模板管理
│   ├── __init__.py
│   ├── template_manager.py       # 模板管理器
│   ├── prompt_builder.py         # 提示词构建器
│   ├── 
│   ├── templates/                # 模板文件
│   │   ├── concept_planning/     # 概念规划模板
│   │   │   ├── basic.yaml
│   │   │   ├── creative.yaml
│   │   │   └── technical.yaml
│   │   ├── script_writing/       # 脚本编写模板
│   │   │   ├── narrative.yaml
│   │   │   ├── educational.yaml
│   │   │   └── commercial.yaml
│   │   ├── quality_assessment/   # 质量评估模板
│   │   │   ├── content.yaml
│   │   │   ├── technical.yaml
│   │   │   └── creative.yaml
│   │   └── react_reasoning/      # ReAct推理模板
│   │       ├── observe.yaml
│   │       ├── think.yaml
│   │       ├── plan.yaml
│   │       └── reflect.yaml
│   │
│   └── validators/               # 模板验证器
│       ├── __init__.py
│       ├── syntax_validator.py   # 语法验证
│       └── content_validator.py  # 内容验证
│
└── utils/                         # 工具函数
    ├── __init__.py
    ├── logging.py                # 日志工具
    ├── metrics.py                # 指标收集
    ├── decorators.py             # 装饰器
    └── helpers.py                # 辅助函数
```

## 🏗️ 架构设计原则

### 1. 分离关注点
- **Agents**: 专注于业务逻辑和决策
- **Tools**: 专注于具体功能实现
- **Memory**: 专注于信息存储和检索
- **Prompts**: 专注于AI交互优化

### 2. 可扩展性
- 工具系统支持插件化扩展
- 记忆模块支持多种存储后端
- 提示词模板支持版本管理和A/B测试

### 3. 复用性
- 工具可在多个Agent间共享
- 提示词模板可复用和组合
- 记忆系统支持跨Agent共享

### 4. 可测试性
- 每个组件都有清晰的接口
- 支持模拟和依赖注入
- 完整的单元测试覆盖

### 5. 思维链与Tokens（设计原则）
- 分类先验：按 Agent 职能划分是否启用 thinking，而非在代码里写启发式规则。
  - 规划类（开启 thinking）：概念/场景规划、叙事结构设计、任务拆解与策略决策、跨工具编排。
  - 执行类（关闭 thinking）：一步到位的生成/转换/增强、落地输出（如一行提示词）、媒体/文件处理。
- 双档 tokens：为 thinking/非 thinking 分别配置默认 `max_tokens`（全局配置统一管理），避免到处硬编码。
  - 示例：`LLM_MAX_TOKENS_STANDARD`、`LLM_MAX_TOKENS_THINKING`（可由环境覆盖）。
- Agent 级配置：每个 Agent 选择其默认模式（thinking/standard）；调用点可显式覆盖但不改变默认。
- 输出约束：即使开启 thinking，最终“落地输出”建议只在 `message.content` 返回，避免 reasoning 吃满配额导致空内容。
- 日志与观测：记录 `finish_reason` 与 tokens 使用的摘要信号；不持久化 reasoning 全量文本。

## 🔧 核心概念

### Agent
- 具有特定能力的智能体
- 可以使用工具执行任务
- 具有记忆和学习能力
- 通过提示词与LLM交互

### Tool
- 封装特定功能的可复用组件
- 支持同步和异步执行
- 具有输入验证和错误处理
- 可以被多个Agent共享使用

### Memory
- 存储Agent的经验和知识
- 支持语义搜索和关联检索
- 跨会话持久化状态
- 支持不同粒度的记忆管理

### Prompt Template
- 结构化的LLM交互模板
- 支持参数化和条件逻辑
- 版本控制和A/B测试
- 多语言和本地化支持

## 🚀 使用示例

### 创建新Agent（增强版）

```python
from .base import BaseAgent
from ..models import AgentType

class CustomAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            agent_type=AgentType.CUSTOM,
            agent_name="custom_agent",
            timeout_seconds=180,
            tools=["openai_client", "file_manager"],  # 加载工具
            memory_config={
                "short_term_ttl": 3600,
                "enable_consolidation": True
            },
            prompt_templates=["custom_template"]  # 使用提示词模板
        )
    
    def _initialize_agent(self):
        """Agent特定初始化"""
        self.logger.info("Initializing Custom Agent")
    
    async def _execute_impl(self, task, input_data, execution, db):
        # 存储输入到记忆
        await self.store_memory(
            content=input_data,
            tags=["task_input"],
            importance="high"
        )
        
        # 检索相关记忆
        memories = await self.retrieve_memories(
            query="similar task",
            limit=5
        )
        
        # 渲染提示词模板
        prompt = await self.render_prompt(
            "custom_template",
            {"input": input_data, "context": memories}
        )
        
        # 使用工具
        result = await self.use_tool(
            "openai_client",
            "chat_completion",
            {"messages": [{"role": "user", "content": prompt}]}
        )
        
        return {"result": result}
```

### 工具使用示例

```python
# 注册新工具
from .tools.tool_registry import get_tool_registry
from .tools.base_tool import AsyncTool, ToolMetadata, ToolType

class CustomTool(AsyncTool):
    @classmethod
    def get_metadata(cls):
        return ToolMetadata(
            name="custom_tool",
            description="Custom functionality",
            tool_type=ToolType.UTILITY
        )
    
    async def _execute_impl(self, tool_input):
        return {"status": "success"}

# 注册工具
registry = get_tool_registry()
registry.register_tool("custom_tool", CustomTool())
```

### 记忆管理示例

```python
# 在Agent中使用记忆
async def process_with_memory(self, data):
    # 存储记忆
    memory_id = await self.store_memory(
        content=data,
        tags=["processing", "important"],
        importance="high"
    )
    
    # 检索相关记忆
    related = await self.retrieve_memories(
        query="processing data",
        tags=["processing"],
        limit=10
    )
    
    # 获取记忆统计
    stats = await self.get_memory_stats()
    return {"memory_id": memory_id, "related_count": len(related)}
```

### 提示词模板示例

```python
# 创建新模板
from .prompts.template_manager import get_template_manager

manager = get_template_manager()

# 动态创建模板
template = manager.create_template(
    name="custom_template",
    template_content="Process this data: {{ data }}\nContext: {{ context }}",
    metadata={
        "description": "Custom processing template",
        "variables": ["data", "context"]
    }
)

# 渲染模板
rendered = manager.render_template(
    "custom_template",
    {"data": "input", "context": "background info"}
)
```

### Agent完整示例

```python
from .examples.enhanced_concept_planner import EnhancedConceptPlannerAgent

# 创建增强版概念规划Agent
agent = EnhancedConceptPlannerAgent()

# 获取Agent状态
status = await agent.get_agent_status()
print(f"Available tools: {status['available_tools']}")
print(f"Memory stats: {status['memory_stats']}")

# 使用Agent的高级功能
async with agent:  # 自动资源管理
    # 存储记忆
    memory_id = await agent.store_memory(
        content="Important concept insight",
        tags=["insight", "concept"],
        importance="high"
    )
    
    # 检索相关记忆
    memories = await agent.retrieve_memories(
        query="concept insight",
        limit=5
    )
    
    # 渲染提示词
    prompt = await agent.render_prompt(
        "concept_planner",
        {
            "user_description": "AI-powered video",
            "video_style": "futuristic",
            "target_duration": 30,
            "target_audience": "tech enthusiasts"
        }
    )
    
    # 使用工具
    result = await agent.use_tool(
        "openai_client",
        "chat_completion",
        {
            "messages": [{"role": "user", "content": prompt}],
            "model": "gpt-4",
            "temperature": 0.7
        }
    )
```
