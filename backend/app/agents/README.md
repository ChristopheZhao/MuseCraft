# Agent 系统说明

本目录只保留当前 canonical MAS agent surface 的简要说明。

## 当前主线
- `OrchestratorAgent` 是唯一的 single-episode canonical mainline。
- `EpisodeOrchestratorAgent` 只是 project / multi-episode wrapper，不是并列 orchestrator engine。
- specialist agents 继续作为 leaf execution actors 存在。

## 已退役语义
- `react_orchestrator.py`
- `enhanced_orchestrator.py`
- 与其绑定的 testing harness / prompt assets

这些旧宿主语义已从 `backend/app` 退役，不再视为可选 app-surface orchestrator。

## 权威架构文档
- `docs/architecture/single_episode_harness_architecture_20260311.md`
- `docs/architecture/mas_architecture_alignment_note_20260323.md`
- `docs/architecture/mas_runtime_control_plane_detailed_design_20260308.md`
- `docs/architecture/mas_runtime_contracts_detailed_design_20260308.md`

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
