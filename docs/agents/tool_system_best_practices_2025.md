# LLM-Based Agent Tool System Design Best Practices (2025)

**调研日期**: 2025-01-16
**目标**: 为纯 LLM-driven Agent 系统设计工具架构的最佳实践
**核心原则**: 所有决策由 LLM 通过 Function Call 完成，Agent 不包含硬编码业务逻辑

---

## 一、核心架构原则

### 1.1 三层分离架构

```
┌─────────────────────────────────────┐
│   Agent Layer (业务编排层)          │
│   - ReAct循环（OBSERVE/PLAN/ACT）   │
│   - 决策协调                         │
│   - 记忆管理                         │
└─────────────────────────────────────┘
              ↓ 依赖注入
┌─────────────────────────────────────┐
│   Tool Execution System (执行系统)  │
│   - 工具注册与发现                   │
│   - Function Call映射                │
│   - 批量执行与结果聚合               │
│   - 权限控制与审计                   │
└─────────────────────────────────────┘
              ↓ 依赖
┌─────────────────────────────────────┐
│   Tool Layer (工具实现层)           │
│   - 单个工具实现                     │
│   - 参数验证与Schema                 │
│   - ToolInput/ToolOutput封装         │
└─────────────────────────────────────┘
```

**来源**: Anthropic, LangGraph, OpenAI Swarm

---

### 1.2 LLM-Driven 核心定理

> **定理**: 在纯 LLM-based Agent 系统中，**分配给Agent的工具 = LLM可规划的工具**

**推论**:
1. 不存在"分配但不暴露"的工具（违反最小惊讶原则）
2. 不存在"LLM看不到但Agent要用"的动作（谁来调用它？）
3. 工具分配即意味着 Function Call Schema 暴露

**反例**（错误设计）:
```python
# ❌ 错误：分配了但不暴露给LLM
class VoiceSynthesizerAgent:
    tools = ["voice_synth_tool", "file_storage_tool"]

file_storage_tool.get_fc_visibility():
    return {"expose": False}  # LLM看不到，永远不会被调用
```

**正确设计**:
```python
# ✅ 正确：分配即暴露，安全通过约束保障
class VoiceSynthesizerAgent:
    tools = ["voice_synth_tool", "file_storage_tool"]

file_storage_tool.get_fc_visibility():
    return {
        "expose": True,
        "allowed_actions": ["upload_file", "delete_file"]
    }

file_storage_tool.delete_file(file_path: str):
    # 安全约束在实现层
    if not file_path.startswith(f"workflows/{workflow_id}/"):
        raise PermissionError("Cannot delete files outside workflow scope")
```

**来源**: Anthropic (Building Effective Agents), LangGraph Multi-Agent Systems

---

## 二、工具注册与发现

### 2.1 动态工具注册模式

**Registry 职责**:
- 维护工具的唯一标识符与Schema映射
- 提供工具发现接口（按能力/语义搜索）
- 验证工具元数据完整性
- 支持运行时动态加载

**实现模式**:
```python
class ToolRegistry:
    """中央工具注册表"""

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        self._semantic_index = None  # FAISS索引

    def register(self, tool: BaseTool) -> None:
        """注册工具并验证元数据"""
        visibility = tool.get_fc_visibility()
        if not visibility.get("expose"):
            raise ValueError(f"Tool {tool.name} has no exposed actions")

        # 验证Schema完整性
        for action in visibility.get("allowed_actions", []):
            schema = tool.get_action_schema(action)
            if not schema:
                raise ValueError(f"Action {action} missing schema")

        self._tools[tool.name] = tool
        self._update_semantic_index(tool)

    def discover(self, query: str, top_k: int = 5) -> List[BaseTool]:
        """语义搜索相关工具"""
        # 使用sentence-transformers + FAISS
        return self._semantic_search(query, top_k)

    def get_tools_for_agent(self, agent_name: str) -> Dict[str, BaseTool]:
        """按Agent权限策略返回可用工具"""
        policy = self._load_policy(agent_name)
        return {
            name: tool for name, tool in self._tools.items()
            if name in policy.get("allowed_tools", [])
        }
```

**来源**: MCP Gateway & Registry, LangGraph Tool Discovery

---

### 2.2 工具分配时严格校验

**原则**: Fail-Fast - 在分配阶段而非执行阶段发现配置错误

```python
class BaseAgent:
    def _load_tools(self, tool_names: List[str]) -> None:
        """加载并验证工具分配"""
        for name in tool_names:
            tool = tool_registry.get(name)
            if not tool:
                raise AgentError(f"Tool '{name}' not found in registry")

            visibility = tool.get_fc_visibility()

            # 严格模式：分配的工具必须有至少一个暴露的动作
            if settings.FC_STRICT_ALLOCATION:
                if not visibility.get("expose"):
                    raise AgentError(
                        f"Tool '{name}' is allocated to {self.agent_name} "
                        f"but has no exposed actions (expose=False). "
                        f"This violates LLM-driven principle."
                    )

                allowed = visibility.get("allowed_actions", [])
                if not allowed:
                    raise AgentError(
                        f"Tool '{name}' is exposed but has no allowed_actions"
                    )

            self.allocated_tools[name] = tool
            self.logger.info(
                f"Loaded tool '{name}' with actions: "
                f"{visibility.get('allowed_actions', [])}"
            )
```

**配置**:
```python
# backend/app/core/config.py
FC_STRICT_ALLOCATION: bool = True  # 强制分配即暴露原则
```

**来源**: Claude Code Best Practices, LangGraph Agent Architectures

---

## 三、Function Call Schema 构建

### 3.1 Schema 生成策略

**核心原则**: Schema 完全由工具层声明，Agent 不手动拼接

```python
class BaseAgent:
    def _build_function_call_schema(self) -> List[Dict[str, Any]]:
        """基于分配的工具构建FC schema"""
        schema = []

        for tool_name, tool in self.allocated_tools.items():
            visibility = tool.get_fc_visibility()
            if not visibility.get("expose", False):
                continue

            for action in visibility.get("allowed_actions", []):
                action_schema = tool.get_action_schema(action)
                if not action_schema:
                    continue

                # 构建OpenAI/Anthropic兼容的Function schema
                schema.append({
                    "type": "function",
                    "function": {
                        "name": f"{tool_name}.{action}",
                        "description": action_schema.get("description", ""),
                        "parameters": action_schema.get("parameters", {}),
                        "strict": action_schema.get("strict", False)
                    }
                })

        return schema
```

**反模式**（已废弃）:
```python
# ❌ 不要在Agent运行时手动拼接schema
async def _think_and_plan(self):
    tools_override = []
    t = self._available_tools.get("voice_synth_tool")
    if t:
        sch = t.get_action_schema("synthesize_voice")
        tools_override.append({
            "type": "function",
            "function": {"name": "...", "parameters": sch}
        })

    # 这违反了"工具系统统一管理"原则
    response = await self.llm_function_call(tools=tools_override)
```

**来源**: Anthropic Tool Use Patterns, Pydantic AI

---

### 3.2 参数Schema设计规范

**使用 JSON Schema + Pydantic 验证**:

```python
class BaseTool:
    def get_action_schema(self, action: str) -> Dict[str, Any]:
        """返回符合OpenAI/Anthropic规范的JSON Schema"""
        return {
            "description": "Generate voiceover audio for a scene",
            "parameters": {
                "type": "object",
                "properties": {
                    "scene_number": {
                        "type": "integer",
                        "description": "Scene identifier"
                    },
                    "text": {
                        "type": "string",
                        "description": "Text to synthesize",
                        "minLength": 1,
                        "maxLength": 5000
                    },
                    "voice_id": {
                        "type": "string",
                        "enum": ["alloy", "echo", "fable", "nova"],
                        "description": "Voice preset to use"
                    }
                },
                "required": ["scene_number", "text"],
                "additionalProperties": False
            },
            "strict": True  # OpenAI严格模式
        }
```

**验证最佳实践**:
1. **使用 Pydantic 模型作为 args_schema**（LangChain/LlamaIndex 推荐）
2. **提取 docstring 作为参数描述**（自动生成文档）
3. **Schema 保持简单**（减少LLM理解负担）
4. **使用枚举限制选择范围**（避免无效输入）

**来源**: LangChain Tool Design, Pydantic AI, AI SDK Foundations

---

## 四、权限控制与安全

### 4.1 最小权限原则 (Principle of Least Privilege)

**学术定义**（Progent 2025）:
> "允许Agent仅调用完成用户合法任务所必需的工具，禁止不必要且可能有害的工具调用。"

**实现层次**:

#### Level 1: 工具级权限（Tool-Level）
```python
# Agent只能访问分配给它的工具子集
voice_synthesizer_agent.tools = [
    "voice_synth_tool",      # ✅ 语音合成
    "audio_processor",       # ✅ 音频处理
    "file_storage_tool"      # ✅ 文件上传
    # ❌ 不分配video_generation_tool（超出职责）
]
```

#### Level 2: 动作级权限（Action-Level）
```python
# 同一工具的不同动作可以有不同的权限策略
file_storage_tool.get_fc_visibility():
    return {
        "expose": True,
        "allowed_actions": [
            "upload_file",    # ✅ Voice Agent需要上传
            # ❌ 不暴露delete_file（敏感操作）
        ]
    }
```

#### Level 3: 参数级权限（Parameter-Level）
```python
class FileStorageTool:
    async def upload_file(
        self,
        file_path: str,
        workflow_id: str  # 由框架注入，LLM不可控
    ) -> ToolOutput:
        """上传文件到指定workflow目录"""

        # 范围约束：只能上传到当前workflow
        target_dir = f"workflows/{workflow_id}/audio/"
        if not os.path.abspath(file_path).startswith(target_dir):
            return ToolOutput(
                success=False,
                error="File must be in workflow directory",
                error_type="permission_error"
            )

        # 类型约束：只允许音频文件
        if not file_path.endswith(('.mp3', '.wav', '.m4a')):
            return ToolOutput(
                success=False,
                error="Only audio files allowed",
                error_type="validation_error"
            )

        # 执行上传
        url = await self._upload_to_storage(file_path)
        return ToolOutput(success=True, result={"url": url})
```

**来源**: Progent (AAAI 2025), Prompt Flow Integrity, Claude Code Security

---

### 4.2 上下文隔离（Context Isolation）

**双层Agent架构**（Two-Tier Pattern）:

```python
# Context Agent: 维护全局上下文和对话历史
class OrchestratorAgent:
    def __init__(self):
        self.context = WorkingMemory()
        self.conversation_history = []

    async def delegate_task(self, task: Dict) -> Dict:
        """委托任务给执行Agent"""
        # 只传递任务相关的最小上下文
        minimal_context = self._extract_task_context(task)

        # 执行Agent在隔离环境中运行
        result = await execution_agent.execute(
            task=task,
            context=minimal_context,  # 受限上下文
            session_id=uuid.uuid4()   # 独立会话
        )

        # 只接收结果，不接收执行Agent的完整上下文
        self.context.update(result.artifacts)
        return result

# Execution Agent: 完全隔离的任务执行
class ImageGeneratorAgent:
    def execute(self, task: Dict, context: Dict, session_id: str):
        """纯函数式执行：相同输入→相同输出"""
        # 不访问全局状态
        # 不共享内存
        # 不保留历史
        return self._generate_images(task, context)
```

**隔离级别**:
- **Complete Isolation (80%场景)**: 子Agent只接收任务描述
- **Filtered Context (15%场景)**: 传递特定领域的上下文片段
- **Windowed Context (5%场景)**: 传递时间窗口内的历史记录

**来源**: InfoWorld 2-Agent Architecture, AWS Strands Agents SDK

---

### 4.3 运行时审计与监控

**审计日志设计**:
```python
class ToolExecutor:
    async def execute_tool_call(self, call: Dict) -> ExecutedToolCall:
        """执行单个工具调用并记录完整审计轨迹"""
        start_time = time.time()

        # 前置审计
        self._audit_log({
            "event": "tool_call_start",
            "agent": self.agent_name,
            "tool": call["function"]["name"],
            "arguments": self._sanitize_args(call["function"]["arguments"]),
            "session_id": self.session_id,
            "timestamp": datetime.now().isoformat()
        })

        try:
            result = await self._invoke_tool(call)

            # 成功审计
            self._audit_log({
                "event": "tool_call_success",
                "tool": call["function"]["name"],
                "duration_sec": time.time() - start_time,
                "artifacts": self._extract_artifact_metadata(result),
                "timestamp": datetime.now().isoformat()
            })

            return result

        except Exception as e:
            # 失败审计
            self._audit_log({
                "event": "tool_call_failure",
                "tool": call["function"]["name"],
                "error": str(e),
                "error_type": type(e).__name__,
                "duration_sec": time.time() - start_time,
                "timestamp": datetime.now().isoformat()
            })
            raise
```

**监控指标**:
- Tool call success rate (按工具/Agent统计)
- Average execution time (识别慢工具)
- Permission denial rate (检测权限配置问题)
- Retry counts (识别不稳定的工具)

**来源**: Claude Code Best Practices, Anthropic Engineering

---

## 五、工具执行系统设计

### 5.1 ToolExecutor 架构

**职责边界**:
- ✅ FC映射查找（function name → tool instance）
- ✅ 批量执行与并发控制
- ✅ 结果标准化（ToolOutput → ExecutedToolCall）
- ✅ 错误处理与重试策略
- ✅ 执行度量与审计
- ❌ **不负责决策**（决策由LLM在PLAN阶段完成）

```python
# backend/app/agents/tools/tool_executor.py
from dataclasses import dataclass
from typing import Dict, List, Any, Optional
import asyncio

@dataclass
class ExecutionContext:
    """执行上下文（从Agent注入）"""
    agent_name: str
    workflow_id: str
    iteration: int
    stage: str  # "plan" | "act" | "reflect"
    session_id: str

@dataclass
class ExecutedToolCall:
    """标准化执行记录"""
    tool: str
    action: str
    args: Dict[str, Any]
    success: bool
    output: Dict[str, Any]  # ToolOutput的dict视图
    payload: Any  # 供应商原始返回
    artifact: Optional['ArtifactSnapshot']
    error: Optional[str] = None
    error_type: Optional[str] = None
    duration_sec: float = 0.0
    stage: str = "act"

@dataclass
class ArtifactSnapshot:
    """供应商无关的产物快照"""
    scene_number: Optional[int] = None
    image_url: Optional[str] = None
    video_url: Optional[str] = None
    audio_url: Optional[str] = None
    file_path: Optional[str] = None
    prompt_text: Optional[str] = None
    duration_sec: Optional[float] = None

class ToolExecutor:
    """工具执行引擎：负责FC映射、执行、聚合"""

    def __init__(self, tools: Dict[str, BaseTool]):
        self._tools = tools
        self._fc_map = self._build_fc_map()

    def _build_fc_map(self) -> Dict[str, tuple[BaseTool, str]]:
        """构建 function_name -> (tool, action) 映射"""
        fc_map = {}
        for tool_name, tool in self._tools.items():
            visibility = tool.get_fc_visibility()
            if not visibility.get("expose"):
                continue

            for action in visibility.get("allowed_actions", []):
                fc_name = f"{tool_name}.{action}"
                fc_map[fc_name] = (tool, action)

        return fc_map

    async def execute_tool_calls(
        self,
        tool_calls: List[Dict],
        context: ExecutionContext
    ) -> List[ExecutedToolCall]:
        """批量执行工具调用"""
        results = []

        for call in tool_calls:
            func_name = call["function"]["name"]
            args = call["function"]["arguments"]

            # FC映射查找
            if func_name not in self._fc_map:
                results.append(self._build_error_record(
                    call, "tool_not_found", context
                ))
                continue

            tool, action = self._fc_map[func_name]

            try:
                # 执行工具
                output: ToolOutput = await tool.execute(
                    ToolInput(action=action, parameters=args)
                )

                # 标准化记录
                record = ExecutedToolCall(
                    tool=tool.name,
                    action=action,
                    args=args,
                    success=output.success,
                    output=output.dict(),
                    payload=output.result,
                    artifact=self._extract_artifact(output),
                    duration_sec=output.execution_time,
                    stage=context.stage
                )
                results.append(record)

            except Exception as e:
                results.append(self._build_error_record(
                    call, str(e), context, error_type=type(e).__name__
                ))

        return results

    def _extract_artifact(self, output: ToolOutput) -> Optional[ArtifactSnapshot]:
        """从ToolOutput提取标准化产物快照"""
        if not output.success:
            return None

        result = output.result or {}
        return ArtifactSnapshot(
            scene_number=result.get("scene_number"),
            image_url=result.get("image_url"),
            video_url=result.get("video_url"),
            audio_url=result.get("audio_url"),
            file_path=(
                result.get("file_path") or
                result.get("image_path") or
                result.get("audio_path")
            ),
            prompt_text=(
                result.get("prompt_text") or
                result.get("prompt")
            ),
            duration_sec=result.get("duration"),
        )
```

**来源**: LangChain Tool Execution, LlamaIndex Workflow Agents

---

### 5.2 BaseAgent 委托模式

```python
# backend/app/agents/base.py
class BaseAgent:
    def __init__(self, ...):
        # 依赖注入：ToolExecutor
        self._tool_executor = ToolExecutor(self.allocated_tools)

    async def execute_tool_calls(
        self,
        tool_calls: List[Dict]
    ) -> List[Dict]:
        """公开接口：执行工具调用（向后兼容）"""

        # 构建执行上下文
        context = ExecutionContext(
            agent_name=self.agent_name,
            workflow_id=self.iteration_context.get("workflow_state_id"),
            iteration=self.iteration_context.get("iteration", 0),
            stage=self.iteration_context.get("stage", "act"),
            session_id=self.iteration_context.get("session_id")
        )

        # 委托给ToolExecutor
        results: List[ExecutedToolCall] = await self._tool_executor.execute_tool_calls(
            tool_calls, context
        )

        # Agent级补充：度量与上下文写入
        self._update_react_metrics(results)
        self.iteration_context["last_round_results"] = [
            r.dict() for r in results
        ]

        # 向后兼容：返回dict列表
        return [r.dict() for r in results]

    def _update_react_metrics(self, results: List[ExecutedToolCall]):
        """更新ReAct度量"""
        metrics = self.iteration_context.setdefault("react_metrics", {})
        metrics["act_total"] = metrics.get("act_total", 0) + len(results)
        metrics["act_success"] = metrics.get("act_success", 0) + sum(
            1 for r in results if r.success
        )
        metrics["artifacts"] = metrics.get("artifacts", 0) + sum(
            1 for r in results if r.artifact
        )
```

**关键点**:
- Agent保留 `execute_tool_calls` 作为公开接口（向后兼容）
- 内部委托给 `ToolExecutor`（解耦执行细节）
- Agent负责补充业务级度量（ReAct循环、记忆写入）

**来源**: OpenAI Swarm Handoff Pattern, LangGraph Agent Architecture

---

## 六、多Agent工具分配策略

### 6.1 工具分配原则

**LangGraph Multi-Agent Best Practices**:

> 1. **Grouping tools by responsibility**: Agent更容易在专注的任务上成功
> 2. **Limiting tool count**: 工具太多会导致决策质量下降
> 3. **Supervisor coordination**: 用supervisor agent协调工具（Agent）调用顺序

**实践建议**:
- **Single Agent**: ≤10个工具（认知负担阈值）
- **Multi-Agent**: 按职责分组，每个Agent 3-7个工具
- **Supervisor**: 不直接调用业务工具，只负责Agent路由

```python
# ❌ 反模式：单个Agent拥有所有工具
class MegaAgent:
    tools = [
        "concept_generation", "script_writing",
        "image_generation", "video_generation",
        "audio_synthesis", "video_composition",
        "file_storage", "quality_check"
    ]  # 8个工具，决策混乱

# ✅ 正确：按职责分组到专门Agent
class ConceptPlannerAgent:
    tools = ["concept_generation", "content_analysis"]

class ImageGeneratorAgent:
    tools = ["image_generation", "style_extraction", "file_storage"]

class VideoGeneratorAgent:
    tools = ["video_generation", "scene_analysis", "file_storage"]

class OrchestratorAgent:
    # Supervisor只负责路由
    tools = []  # 或者定义为 agents = [ConceptPlanner, ImageGenerator, ...]
```

**来源**: LangGraph Multi-Agent Systems, Databricks Agent Design Patterns

---

### 6.2 动态工具选择（RAG-Style Tool Selection）

**场景**: Agent拥有100+工具时，如何避免LLM认知过载？

**解决方案**: 动态检索相关工具子集

```python
class DynamicToolAgent(BaseAgent):
    def __init__(self, all_tools: Dict[str, BaseTool]):
        self._all_tools = all_tools
        self._tool_index = self._build_semantic_index(all_tools)
        super().__init__(tools=[])  # 初始为空

    async def _plan_next_action(self, observation: Dict) -> Dict:
        """PLAN阶段：动态检索相关工具"""

        # 1. 根据观察结果检索相关工具
        query = self._build_tool_query(observation)
        relevant_tools = self._tool_index.search(query, top_k=5)

        # 2. 临时绑定工具到当前FC调用
        self.allocated_tools = {
            t.name: t for t in relevant_tools
        }
        fc_schema = self._build_function_call_schema()

        # 3. LLM只看到相关的5个工具
        plan = await self.llm_function_call(
            messages=self._build_plan_messages(observation),
            tools=fc_schema
        )

        return plan
```

**效果**:
- 减少token消耗（只传递5个工具schema vs 100个）
- 提高决策准确率（减少干扰项）
- 支持工具库扩展（新增工具不影响单次调用）

**来源**: LangGraph "How to handle large numbers of tools", MCP Dynamic Tool Discovery

---

## 七、错误处理与容错

### 7.1 工具调用错误分类

**错误类型**:
```python
class ToolErrorType(str, Enum):
    # 客户端错误（不应重试）
    VALIDATION_ERROR = "validation_error"      # 参数不合法
    PERMISSION_ERROR = "permission_error"      # 权限不足
    TOOL_NOT_FOUND = "tool_not_found"          # 工具不存在

    # 服务端错误（可重试）
    API_ERROR = "api_error"                    # 外部API失败
    TIMEOUT_ERROR = "timeout_error"            # 执行超时
    RATE_LIMIT_ERROR = "rate_limit_error"      # 速率限制

    # 业务错误（由LLM决定是否重试）
    BUSINESS_ERROR = "business_error"          # 业务逻辑失败
```

**错误处理策略**:
```python
class ToolExecutor:
    async def execute_tool_call_with_retry(
        self,
        call: Dict,
        context: ExecutionContext
    ) -> ExecutedToolCall:
        """带重试的工具执行"""

        max_retries = 3
        backoff_factor = 2

        for attempt in range(max_retries):
            try:
                result = await self._execute_single_call(call, context)

                if result.success:
                    return result

                # 根据错误类型决定是否重试
                if result.error_type in [
                    "validation_error",
                    "permission_error",
                    "tool_not_found"
                ]:
                    # 客户端错误：不重试
                    return result

                if result.error_type == "rate_limit_error":
                    # 速率限制：指数退避
                    await asyncio.sleep(backoff_factor ** attempt)
                    continue

                # 其他错误：短暂延迟后重试
                await asyncio.sleep(1 * backoff_factor ** attempt)

            except Exception as e:
                if attempt == max_retries - 1:
                    return self._build_error_record(
                        call, str(e), context,
                        error_type="execution_error"
                    )
                await asyncio.sleep(backoff_factor ** attempt)

        return result
```

**来源**: LangChain "How to handle tool errors", Claude Code Error Handling

---

### 7.2 LLM自主错误恢复

**让LLM参与错误恢复决策**:

```python
class ReActAgent:
    async def _reflect_on_results(
        self,
        action_result: Dict
    ) -> Dict:
        """REFLECT阶段：分析工具调用结果"""

        executed_calls = action_result.get("executed_calls", [])
        failures = [c for c in executed_calls if not c["success"]]

        if not failures:
            return {"task_complete": True}

        # 构建失败上下文
        failure_context = {
            "failed_calls": [
                {
                    "tool": f["tool"],
                    "error": f["error"],
                    "error_type": f["error_type"],
                    "args": f["args"]
                }
                for f in failures
            ],
            "successful_calls": len(executed_calls) - len(failures)
        }

        # 让LLM决定恢复策略
        messages = [
            {"role": "system", "content": self._render_reflect_prompt()},
            {"role": "user", "content": json.dumps(failure_context)}
        ]

        reflection = await self.llm.chat_completion(
            messages=messages,
            response_format={"type": "json_object"}
        )

        # LLM可能的决策：
        # - retry: 重试失败的调用（可能调整参数）
        # - skip: 跳过失败的任务
        # - alternative: 使用替代工具
        # - abort: 终止整个流程

        return json.loads(reflection["content"])
```

**来源**: Anthropic Building Effective Agents, LlamaIndex Agent Workflows

---

## 八、实施检查清单

### 8.1 架构合规性检查

- [ ] **工具分配即暴露**: 所有分配的工具都设置 `expose=True`
- [ ] **无运行时Schema拼接**: Agent不手动构造 `tools_override`
- [ ] **三层分离**: Agent/ToolExecutor/Tool职责清晰
- [ ] **依赖注入**: Agent通过构造器接收ToolExecutor
- [ ] **Fail-Fast**: 分配阶段验证工具可用性

### 8.2 安全性检查

- [ ] **最小权限**: 每个工具只暴露必要的动作
- [ ] **参数约束**: 敏感参数在工具实现层验证
- [ ] **上下文隔离**: 子Agent不访问父Agent完整上下文
- [ ] **审计日志**: 所有工具调用都有完整审计轨迹
- [ ] **权限策略**: 工具权限由中央策略管理，不硬编码

### 8.3 可观测性检查

- [ ] **标准化输出**: 所有工具返回 `ToolOutput`
- [ ] **执行度量**: 记录成功率、耗时、重试次数
- [ ] **产物快照**: 提取 `ArtifactSnapshot` 用于下游消费
- [ ] **错误分类**: 明确区分客户端/服务端/业务错误
- [ ] **链路追踪**: 支持跨Agent的调用链追踪

---

## 九、案例研究

### 9.1 Anthropic Claude Code

**设计特点**:
- 默认只读权限，操作需显式授权
- 工具分类：文件操作、命令执行、网络请求
- Permission系统：CLI flags + 配置文件
- 命令黑名单：阻止 `curl`、`wget` 等危险命令

**启示**:
- 默认安全，按需放宽
- 权限粒度：工具类别 > 单个工具 > 单个动作
- 用户可配置的权限策略

---

### 9.2 OpenAI Swarm

**设计特点**:
- 无状态架构（stateless between calls）
- Agent = instructions + tools + handoff logic
- 工具即Python函数（直接调用，无额外封装）
- Supervisor模式：Agent的工具是其他Agent

**启示**:
- 极简设计：只有Agent和Handoff两个抽象
- 工具轻量化：无需复杂的注册/发现机制
- Supervisor作为工具路由器

---

### 9.3 LangGraph Multi-Agent

**设计特点**:
- 动态工具选择：RAG-style检索相关工具
- 工具分组：按职责将工具分配给专门Agent
- Supervisor tool-calling：用LLM决定Agent调用顺序
- State injection：部分参数由框架注入，对LLM不可见

**启示**:
- 工具数量控制：单Agent ≤10个工具
- 动态检索：处理大型工具库的关键
- 参数注入：安全参数不交给LLM决策

---

## 十、参考文献

### 学术论文
1. **Progent**: Programmable Privilege Control for LLM Agents (AAAI 2025)
2. **Prompt Flow Integrity**: Prevent Privilege Escalation in LLM Agents (2025)
3. **Design Patterns for Securing LLM Agents against Prompt Injections** (2025)

### 工业实践
1. **Anthropic**: Writing Effective Tools for AI Agents (2025)
2. **Anthropic**: Building Effective Agents (2024)
3. **Anthropic**: Claude Code Best Practices (2025)
4. **LangChain**: LangGraph Multi-Agent Systems (2024)
5. **OpenAI**: Swarm Framework Documentation (2024)
6. **Microsoft**: Azure AI Agent Orchestration Patterns (2024)

### 框架文档
1. **LangChain**: How to Handle Tool Errors
2. **LangGraph**: How to Handle Large Numbers of Tools
3. **Pydantic AI**: Tool and Agent Design
4. **LlamaIndex**: Agent Workflows and Function Calling

### 博客与案例
1. **MCP Gateway & Registry**: Dynamic Tool Discovery (2025)
2. **InfoWorld**: 2-Agent Architecture - Separating Context from Execution (2024)
3. **AWS**: Strands Agents SDK Technical Deep Dive (2024)

---

## 十一、总结

### 核心原则回顾

1. **LLM-Driven First**: 分配给Agent的工具 = LLM可规划的工具
2. **三层分离**: Agent/ToolExecutor/Tool职责清晰
3. **安全即约束**: 通过实现层约束而非隐藏能力保障安全
4. **Fail-Fast**: 配置错误在分配阶段发现，而非执行阶段
5. **可观测性**: 完整的审计、度量、链路追踪

### 实施路径

```
Phase 1: 基础设施
├─ 实现ToolExecutor（工具执行引擎）
├─ 定义ExecutedToolCall/ArtifactSnapshot（标准化类型）
└─ 重构BaseAgent.execute_tool_calls（委托模式）

Phase 2: 权限系统
├─ 实现分配时严格校验（FC_STRICT_ALLOCATION）
├─ 工具层补充get_fc_visibility声明
└─ 添加参数级权限验证（工具实现层）

Phase 3: 可观测性
├─ 统一审计日志格式
├─ 添加执行度量（成功率/耗时/重试）
└─ 实现链路追踪（跨Agent调用）

Phase 4: 优化
├─ 动态工具选择（大型工具库）
├─ 并发执行优化
└─ 错误恢复策略
```

### 架构收益

- ✅ **一致性**: 所有Agent使用统一的工具执行流程
- ✅ **安全性**: 最小权限原则 + 参数约束 + 审计日志
- ✅ **可测试性**: ToolExecutor可独立测试，无需Agent上下文
- ✅ **可扩展性**: 新增工具/Agent无需修改现有代码
- ✅ **可观测性**: 完整的执行轨迹和度量数据

---

**文档版本**: 1.0
**最后更新**: 2025-01-16
**维护者**: MAS Architecture Team
