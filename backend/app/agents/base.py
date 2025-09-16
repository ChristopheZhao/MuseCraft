"""
Base agent class for all video generation agents
"""
import asyncio
import time
import logging
import json
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
import re
from sqlalchemy.orm import Session

from ..models import Task, AgentExecution, AgentType, AgentStatus
from ..core.config import settings
from ..core.database import get_sync_db
from ..services.websocket import WebSocketManager, websocket_manager

from .tools.tool_registry import get_tool_registry
from .tools.agent_tool_allocation import get_agent_tools, validate_agent_tools
from .prompts.template_manager import get_template_manager


class AgentError(Exception):
    """Base exception for agent errors"""
    pass


class AgentTimeoutError(AgentError):
    """Raised when agent execution times out"""
    pass


class BaseAgent(ABC):
    """Base class for all agents in the video generation workflow"""
    
    def __init__(
        self,
        agent_type: AgentType,
        agent_name: str,
        timeout_seconds: int = 300,
        max_retries: int = 3,
        tools: List[str] = None,
        prompt_templates: List[str] = None,
        llms: Dict[str, Any] = None
    ):
        self.agent_type = agent_type
        self.agent_name = agent_name
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.logger = logging.getLogger(f"agent.{agent_name}")
        # Use global singleton WebSocket manager so broadcasts reach connected clients
        self.websocket_manager = websocket_manager
        
        # Initialize tool registry
        self.tool_registry = get_tool_registry()
        self._available_tools = {}
        
        # 工具分配：使用专门的工具列表或手动指定的工具
        if tools is not None:
            # 手动指定工具列表：空列表意味着显式不加载任何工具
            if tools:
                validation = validate_agent_tools(agent_type, tools)
                if not validation["is_valid"]:
                    self.logger.warning(f"Tool validation failed: {validation['recommendations']}")
                    # 使用推荐的工具列表
                    tools = validation["allowed_tools"]
                self._load_tools(tools)
            else:
                self.logger.info(f"🔧 No tools explicitly requested for {agent_name}; FC将以纯文本为主")
        else:
            # 使用Agent类型的专门工具列表
            agent_tools = get_agent_tools(agent_type)
            self._load_tools(agent_tools)
            self.logger.info(f"🔧 Loaded {len(agent_tools)} specialized tools for {agent_type.value}")
            
        self.allocated_tools = list(self._available_tools.keys())
        
        # 记忆管理器 - 🧠 ACTIVATED! 实现真正的MAS记忆共享
        from ..services.global_memory_service import global_memory_service
        self.memory_manager = global_memory_service.memory_manager
        self.memory_service = global_memory_service
        
        self.logger.info(f"🧠 {self.agent_name} memory system activated")
        
        # 统一提示词管理器 - 支持YAML配置和模板渲染
        from ..core.prompt_manager import get_prompt_manager
        self.prompt_manager = get_prompt_manager()
        self._prompt_templates = prompt_templates or []
        # 注入的 LLM 实例集合：{default, observe, plan, act}
        self._llms = llms or {}
        
        # FC执行轨迹（用于在后续FC上下文中注入“已产出事实”，避免无谓重复）
        # 结构：[{"tool": str, "args": dict, "success": bool, "result": Any, "error": str, "ts": float}]
        self._fc_exec_trace: List[Dict[str, Any]] = []

        # Agent-specific initialization
        # Inject default thinking mode and token tiers from configuration
        try:
            from ..core.ai_config import get_ai_config
            from ..core.config import settings
            ai_cfg = get_ai_config()
            self.default_thinking_mode = ai_cfg.get_thinking_mode_for_agent(self.agent_name)  # "thinking" | "standard"
            self.max_tokens_standard = settings.LLM_MAX_TOKENS_STANDARD
            self.max_tokens_thinking = settings.LLM_MAX_TOKENS_THINKING
            self.logger.info(
                f"LLM policy for {self.agent_name}: thinking_default={self.default_thinking_mode}, "
                f"tiers={{standard:{self.max_tokens_standard}, thinking:{self.max_tokens_thinking}}}"
            )
        except Exception as e:
            # Fallback defaults if config not available
            self.default_thinking_mode = "standard"
            self.max_tokens_standard = 4096
            self.max_tokens_thinking = 20000
            self.logger.warning(f"Failed to load LLM policy config: {e} (using defaults)")

        self._initialize_agent()
    
    async def execute(
        self, 
        task: Task, 
        input_data: Dict[str, Any], 
        db: Session,
        execution_order: int = 0
    ) -> Dict[str, Any]:
        """
        Execute the agent with the given task and input data
        
        Args:
            task: The task to execute
            input_data: Input data for the agent
            db: Database session
            execution_order: Order of execution in the workflow
            
        Returns:
            Dict containing the agent's output data
        """
        # Reset FC执行轨迹（避免跨任务泄露）
        try:
            self._fc_exec_trace = []
        except Exception:
            self._fc_exec_trace = []

        # Create agent execution record
        def _to_jsonable(obj):
            # Recursively convert objects to JSON-serializable structures
            from pydantic import BaseModel as _PydanticBaseModel  # type: ignore
            if obj is None:
                return None
            if isinstance(obj, (str, int, float, bool)):
                return obj
            if isinstance(obj, dict):
                return {k: _to_jsonable(v) for k, v in obj.items()}
            if isinstance(obj, (list, tuple, set)):
                return [_to_jsonable(v) for v in obj]
            # Pydantic BaseModel (e.g., ToolOutput)
            if isinstance(obj, _PydanticBaseModel):
                try:
                    return _to_jsonable(obj.model_dump())
                except Exception:
                    try:
                        return _to_jsonable(obj.dict())
                    except Exception:
                        return str(obj)
            # Fallback to __dict__ or string
            return getattr(obj, "__dict__", str(obj))

        sanitized_input = _to_jsonable(input_data)
        execution = AgentExecution(
            task_id=task.id,
            agent_type=self.agent_type,
            agent_name=self.agent_name,
            execution_order=execution_order,
            input_data=sanitized_input,
            timeout_seconds=self.timeout_seconds,
            max_retries=self.max_retries
        )
        db.add(execution)
        db.commit()
        db.refresh(execution)
        
        # 将当前任务挂到实例上，便于进度上报和子类访问
        # 注意：同一实例串行执行多个任务时会被覆盖，这是预期行为
        self._current_task = task

        try:
            # Start execution
            execution.start_execution()
            db.commit()
            
            # Send WebSocket update
            await self._send_progress_update(task, execution, "started")
            
            self.logger.info(f"Starting {self.agent_name} for task {task.task_id}")
            
            # Execute with timeout
            output_data = await asyncio.wait_for(
                self._execute_impl(task, input_data, execution, db),
                timeout=self.timeout_seconds
            )
            sanitized_output = _to_jsonable(output_data)
            
            # Complete execution
            execution.complete_execution(sanitized_output)
            db.commit()
            
            # Send WebSocket update
            await self._send_progress_update(task, execution, "completed")
            
            self.logger.info(f"Completed {self.agent_name} for task {task.task_id}")
            
            return output_data
            
        except asyncio.TimeoutError:
            error_msg = f"Agent {self.agent_name} timed out after {self.timeout_seconds} seconds"
            execution.fail_execution(error_msg, "timeout")
            db.commit()
            
            await self._send_progress_update(task, execution, "failed")
            
            self.logger.error(error_msg)
            raise AgentTimeoutError(error_msg)
            
        except Exception as e:
            error_msg = f"Agent {self.agent_name} failed: {str(e)}"
            execution.fail_execution(error_msg, type(e).__name__)
            db.commit()
            
            await self._send_progress_update(task, execution, "failed")
            
            self.logger.error(error_msg, exc_info=True)
            raise AgentError(error_msg) from e
        finally:
            # 避免跨任务残留引用
            try:
                del self._current_task
            except Exception:
                pass
    
    @abstractmethod
    async def _execute_impl(
        self, 
        task: Task, 
        input_data: Dict[str, Any], 
        execution: AgentExecution,
        db: Session
    ) -> Dict[str, Any]:
        """
        Internal implementation of agent execution
        
        Args:
            task: The task to execute
            input_data: Input data for the agent
            execution: Agent execution record
            db: Database session
            
        Returns:
            Dict containing the agent's output data
        """
        pass
    
    async def _send_progress_update(
        self, 
        task: Task, 
        execution: AgentExecution, 
        status: str
    ):
        """Send progress update via WebSocket"""
        try:
            message = {
                "type": "agent_progress",
                "task_id": str(task.task_id),
                "agent_type": execution.agent_type.value,
                "agent_name": execution.agent_name,
                "status": status,
                "progress": execution.progress_percentage,
                "current_step": execution.current_substep,
                "timestamp": int(time.time())
            }
            
            await self.websocket_manager.broadcast_to_task(
                str(task.task_id), 
                message
            )
        except Exception as e:
            self.logger.warning(f"Failed to send WebSocket update: {e}")
    
    async def _update_progress(
        self, 
        execution: AgentExecution, 
        percentage: int, 
        substep: str = None,
        db: Session = None
    ):
        """Update execution progress"""
        execution.update_progress(percentage, substep)
        if db:
            db.commit()
        
        # Send WebSocket update
        if hasattr(self, '_current_task'):
            await self._send_progress_update(
                self._current_task, 
                execution, 
                "progress"
            )
    
    def _validate_input(self, input_data: Dict[str, Any], required_keys: List[str]):
        """Validate that required input keys are present and non-empty"""
        missing_keys = [key for key in required_keys if key not in input_data]
        if missing_keys:
            raise AgentError(f"Missing required input keys: {missing_keys}")
        
        # 检查关键字段是否为空
        empty_keys = []
        for key in required_keys:
            value = input_data.get(key)
            if key == "user_prompt" and (not value or str(value).strip() == ""):
                empty_keys.append(key)
        
        if empty_keys:
            raise AgentError(f"Required input fields cannot be empty: {empty_keys}. Cannot continue with empty prompt.")
    
    def _get_model_parameters(self, execution: AgentExecution) -> Dict[str, Any]:
        """Get model parameters for AI service calls"""
        return execution.model_parameters or {}
    
    def _update_token_usage(self, execution: AgentExecution, tokens_used: int):
        """Update token usage for cost tracking"""
        execution.tokens_used = (execution.tokens_used or 0) + tokens_used
        execution.api_calls_made += 1
        execution.estimate_cost()
    
    # === Function Call支持 ===
    
    async def llm_function_call(
        self,
        messages: List[Dict[str, Any]],
        context_description: str = "",
        model: str = None,
        temperature: float = 0.2,
        tools_override: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        使用LLM的Function Call能力让AI选择合适的工具和参数
        
        Args:
            messages: 对话消息列表
            context_description: 上下文描述，帮助LLM理解任务
            model: LLM模型名称
            temperature: 生成温度
            
        Returns:
            包含工具调用结果的字典
        """
        try:
            # 构建工具schema（允许调用方在特定回合传入覆盖，例如首轮 plan-only 传空列表）
            if tools_override is not None:
                tools_schema = list(tools_override)
                # 使用统一方法从覆盖schema重建路由映射，并做严格校验
                self._rebuild_fc_map_from_schema(tools_schema, strict=True)
            else:
                tools_schema = self._build_function_call_schema()
            
            if not tools_schema:
                # 无工具可用时，也允许走FC文本路径（tools=[]），由模型直接在content返回
                self.logger.info(f"No tools available for {self.agent_name}; proceeding with text-only FC")
                tools_schema = []
            else:
                # 调试：显示可用的工具函数
                func_names = [t["function"]["name"] for t in tools_schema if t.get("function", {}).get("name")]
                self.logger.info(f"🔧 FC可用函数: {func_names[:3]}{'...' if len(func_names) > 3 else ''} (总数: {len(func_names)})")
            
            # 构建完整消息列表（零侵入：完全透传调用方 messages）
            complete_messages = list(messages or [])
            
            # 注入思维链与token档位（仅在未显式传入时），依据Agent默认策略
            thinking_cfg = kwargs.get("thinking")
            if thinking_cfg is None:
                default_enabled = (self.default_thinking_mode == "thinking")
                kwargs["thinking"] = {"type": "enabled"} if default_enabled else {"type": "disabled"}

            if kwargs.get("max_tokens") is None:
                # 依据最终thinking选择档位
                t_cfg = kwargs.get("thinking")
                t_enabled = False
                if isinstance(t_cfg, dict):
                    t_enabled = (t_cfg.get("type") == "enabled")
                elif isinstance(t_cfg, bool):
                    t_enabled = t_cfg
                kwargs["max_tokens"] = self.max_tokens_thinking if t_enabled else self.max_tokens_standard

            # 调用注入的 LLM（plan/act 优先其后 default）
            llm_service = self._resolve_llm_for_role('plan')
            try:
                llm_response = await llm_service.function_call(
                    messages=complete_messages,
                    tools=tools_schema,
                    tool_choice="auto",
                    model=model,
                    temperature=temperature,
                    **kwargs
                )
            except Exception as e:
                # 当无工具可用且供应商FC失败时，通常降级到普通对话接口，避免上游中断；
                # 但若明显是超时类错误，则直接上抛，让调用方（如ConceptPlanner）执行配置化的备用模型策略。
                if not tools_schema:
                    err_str = str(e).lower()
                    is_timeout_like = (
                        isinstance(e, asyncio.TimeoutError)
                        or "timeout" in err_str
                        or "timed out" in err_str
                        or "request timeout" in err_str
                    )
                    if is_timeout_like:
                        # 交由上层处理（例如根据 ai_config 切换 fallback 模型），避免重复等待同一供应商
                        raise
                    try:
                        self.logger.error(f"Function call failed without tools; falling back to chat_completion: {e}")
                    except Exception:
                        pass
                    # 使用同一服务的 chat_completion 作为降级路径（非超时错误）
                    chat_res = await llm_service.chat_completion(
                        messages=complete_messages,
                        model=model,
                        temperature=temperature,
                        max_tokens=kwargs.get("max_tokens")
                    )
                    # 组装与FC近似的响应结构
                    llm_response = {
                        "content": chat_res.get("content"),
                        "reasoning_content": chat_res.get("reasoning_content"),
                        "model": chat_res.get("model"),
                        "usage": chat_res.get("usage", {}),
                        "finish_reason": chat_res.get("finish_reason"),
                        "provider": chat_res.get("provider"),
                        "has_function_call": False,
                    }
                else:
                    raise
            # 观测：记录finish_reason、tool_calls数量、content长度（中文环境，避免打印长文本）
            try:
                fr = llm_response.get("finish_reason")
                tcs = len(llm_response.get("tool_calls", []) or []) if isinstance(llm_response.get("tool_calls"), list) else 0
                clen = len((llm_response.get("content") or ""))
                model = llm_response.get("model")
                provider = llm_response.get("provider")
                mp = f", model={model}, provider={provider}" if (model or provider) else ""
                self.logger.info(f"FC返回: finish_reason={fr}, tool_calls={tcs}, content_len={clen}{mp}")
            except Exception:
                pass

            # 极简“length截断一次受控重试”：
            # - 仅当 finish_reason=length 且无工具调用且 content 为空时触发
            # - 仅重试一次：放大 max_tokens（x2），封顶按当前思维档位上限（standard/thinking）
            # - 不新增配置项；作为协议层小保险，避免将“被截断”误判为空结果
            # 单轮一次 FC：不做长度放大重试
            
            # 处理Function Call响应（仅返回计划，不执行）
            if llm_response.get("has_function_call") and llm_response.get("tool_calls"):
                # 调试：打印本轮计划的工具调用名称与参数预览（不执行）
                try:
                    call_summaries = []
                    for tc in llm_response["tool_calls"][:5]:  # 只预览前5个
                        fn = tc.get("function", {}).get("name")
                        raw = tc.get("function", {}).get("arguments")
                        arg_preview = raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False)
                        if isinstance(arg_preview, str):
                            # DEBUG 等级下不截断；否则使用配置化的预览长度
                            arg_preview = arg_preview.replace("\n", " ")
                            if not self.logger.isEnabledFor(logging.DEBUG):
                                try:
                                    max_len = int(getattr(settings, 'CONTENT_PREVIEW_CHARS', 300))
                                except Exception:
                                    max_len = 300
                                arg_preview = arg_preview[:max_len]
                        call_summaries.append(f"{fn}({arg_preview})")
                    self.logger.info(f"📝 FC计划: {len(llm_response['tool_calls'])} calls -> " + ", ".join(call_summaries))
                    # 将计划数量与函数名写入迭代上下文（若可用），仅作为可观测状态
                    try:
                        if hasattr(self, 'iteration_context') and isinstance(self.iteration_context, dict):
                            planned_fns = [tc.get("function", {}).get("name") for tc in llm_response.get("tool_calls", []) if isinstance(tc, dict)]
                            rm = dict(self.iteration_context.get('react_metrics', {}))
                            rm.update({
                                'planned_calls': len(planned_fns),
                                'planned_functions': planned_fns[:10],
                            })
                            self.iteration_context['react_metrics'] = rm
                    except Exception:
                        pass
                except Exception:
                    pass
                return {
                    "success": True,
                    "approach": "function_call_plan",
                    "tool_calls": llm_response["tool_calls"],
                    "llm_response": llm_response
                }
            
            else:
                # 无tool_calls路径：可能直接给出文本，也可能空（需重试/兜底）
                content = (llm_response.get("content") or "").strip()
                if content:
                    # 仅返回确定性摘要，不驱动任何外部执行
                    content_preview = re.sub(r"\s+", " ", content).strip()[: settings.CONTENT_PREVIEW_CHARS]
                    meta = {
                        "finish_reason": llm_response.get("finish_reason"),
                        "content_len": len(content),
                        "content_preview": content_preview,
                    }
                    return {
                        "success": True,
                        "approach": "text_response",
                        "content": content,
                        "meta": meta,
                        "llm_response": llm_response,
                    }
                # 不再在Base层追加二次提示或注入系统信息，直接返回空文本结果
                return {
                    "success": True,
                    "approach": "text_response",
                    "content": "",
                    "meta": {"finish_reason": llm_response.get("finish_reason"), "content_len": 0, "content_preview": ""},
                    "llm_response": llm_response,
                }
        
        except Exception as e:
            # 统一记录一次错误
            try:
                self.logger.error(f"Function call failed: {e}")
            except Exception:
                pass
            # 文本FC（tools=[]）且为“超时类错误”时，上抛给调用方以执行配置化的备用模型策略
            try:
                err_str = str(e).lower()
                is_timeout_like = (
                    isinstance(e, asyncio.TimeoutError)
                    or "timeout" in err_str
                    or "timed out" in err_str
                    or "request timeout" in err_str
                )
                if is_timeout_like:
                    # 若前面构建了 tools_schema 且为空，认为是 text-only FC
                    try:
                        if not tools_schema:
                            raise
                    except NameError:
                        # 未定义 tools_schema 时，不影响默认返回
                        pass
            except Exception:
                # 继续按默认失败返回
                pass
            return {
                "success": False,
                "error": str(e)
            }
    
    def _build_function_call_schema(self) -> List[Dict[str, Any]]:
        """
        构建 Function Call 的工具 schema（最小化，不含任何策略裁剪）。
        - 不嵌入具体工具实现逻辑，仅通过工具公开的 metadata/actions 构建 Schema。
        - 路由映射的构建统一委托给 _rebuild_fc_map_from_schema，避免分叉。
        """
        tools_schema: List[Dict[str, Any]] = []

        for tool_name in self.allocated_tools:
            try:
                tool = self._available_tools.get(tool_name)
                if tool is None:
                    continue
                # FC 可见性过滤：仅对暴露的动作构建schema
                try:
                    vis = tool.get_fc_visibility() if hasattr(tool, 'get_fc_visibility') else {"expose": True}
                except Exception:
                    vis = {"expose": True}
                if not vis or not vis.get("expose", True):
                    continue
                allowed = vis.get("allowed_actions")
                actions = tool.get_available_actions() or []
                if isinstance(allowed, list) and allowed:
                    actions = [a for a in actions if a in allowed]

                # 1) 多动作工具：按“tool.action”注册
                for action in actions:
                    try:
                        action_schema = tool.get_action_schema(action)
                    except Exception:
                        action_schema = None
                    if not action_schema:
                        continue
                    func_name = f"{tool_name}.{action}"
                    function_schema = {
                        "type": "function",
                        "function": {
                            "name": func_name,
                            "description": f"{tool.get_metadata().description} - {action}",
                            "parameters": action_schema
                        }
                    }
                    tools_schema.append(function_schema)

                # 2) 无动作工具：支持工具级直接注册（仅当工具声明支持且策略允许）
                if not actions and hasattr(tool, 'supports_tool_level_call') and callable(getattr(tool, 'supports_tool_level_call')):
                    try:
                        if tool.supports_tool_level_call():
                            tool_level_schema = tool.get_tool_level_schema() if hasattr(tool, 'get_tool_level_schema') else {}
                            if isinstance(tool_level_schema, dict) and tool_level_schema:
                                func_name = f"{tool_name}"
                                function_schema = {
                                    "type": "function",
                                    "function": {
                                        "name": func_name,
                                        "description": tool.get_metadata().description,
                                        "parameters": tool_level_schema
                                    }
                                }
                                tools_schema.append(function_schema)
                    except Exception:
                        pass

            except Exception as e:
                self.logger.warning(f"FC schema build failed for {tool_name}: {e}")

        # 统一从 schema 重建一次路由表，防止局部变更遗漏
        try:
            self._rebuild_fc_map_from_schema(tools_schema, strict=False)
        except Exception as _e:
            # 非严格模式下，映射失败不应阻断；仅记录
            self.logger.debug(f"FC map rebuild (non-strict) skipped: {_e}")

        if not tools_schema:
            self.logger.info("No function-callable tools/actions available for this agent.")
        return tools_schema

    def _rebuild_fc_map_from_schema(self, tools_schema: List[Dict[str, Any]], strict: bool = False) -> None:
        """
        根据给 LLM 的函数 schema 重建 `_fc_function_map`，保持“规划与执行”一致。
        - 仅解析函数名（tool.action），不引入具体工具实现；通过工具公开的 actions 做存在性校验。
        - strict=True 时，若发现未分配工具或不存在的动作，抛出 AgentError 以便快速诊断。
        """
        self._fc_function_map = {}
        invalids: List[str] = []
        for t in (tools_schema or []):
            try:
                fn = (t or {}).get("function", {}).get("name")
                if not fn or not isinstance(fn, str):
                    continue
                tool_name, action = (fn.split(".", 1) + [None])[:2] if "." in fn else (fn, None)
                # 仅为当前Agent已加载的工具建立映射
                if tool_name not in getattr(self, "_available_tools", {}):
                    invalids.append(f"{fn} (tool not allocated)")
                    continue
                # 若声明了动作，则校验其在工具 actions 列表中
                if action:
                    tool_obj = self._available_tools.get(tool_name)
                    try:
                        actions = tool_obj.get_available_actions() or []
                    except Exception:
                        actions = []
                    if action not in actions:
                        invalids.append(f"{fn} (action not available)")
                        continue
                # 注册映射
                self._fc_function_map[fn] = (tool_name, action)
            except Exception:
                continue
        if strict and invalids:
            raise AgentError(f"Invalid tools_override entries: {', '.join(invalids)}")

    # === FC进展注入（通用，不暴露工具名/参数名）===
    def _build_progress_facts_block(self, limit: int = None) -> Optional[str]:
        """
        从最近的工具调用执行轨迹中提取“事实片段”，作为下轮FC的上下文补充。
        - 保持中立：不出现工具名、动作名或参数名；仅呈现产出事实（文本片段/链接/文件路径等）。
        - 目的：让模型看到已获得的素材，避免反复生成相同内容，从而实现真正的 ReAct 重规划。
        """
        try:
            # 追加一行简要进度摘要（已完成/待办），帮助强模型把握收敛，而不需要重放全部轨迹
            header_lines: List[str] = []
            try:
                ws = dict(self.iteration_context.get("working_state", {}) or {})
                ctx = dict(ws.get("context", {}) or {})
                scenes = ctx.get("scenes_to_generate") or []
                completed = ws.get("completed_scenes") or []
                failed = ws.get("failed_scenes") or []
                completed_ids = set([s.get('scene_number') for s in (completed if isinstance(completed, list) else completed.values()) if isinstance(s, dict) and s.get('scene_number') is not None]) if completed else set()
                failed_ids = set([s.get('scene_number') for s in failed if isinstance(s, dict) and s.get('scene_number') is not None])
                all_ids = set([s.get('scene_number') for s in scenes if isinstance(s, dict) and s.get('scene_number') is not None])
                pending_ids = [str(x) for x in sorted(list(all_ids - completed_ids - failed_ids))]
                header_lines.append("进度摘要：")
                header_lines.append(f"- 已完成：{','.join([str(x) for x in sorted(list(completed_ids))]) if completed_ids else '无'}")
                header_lines.append(f"- 待办：{','.join(pending_ids) if pending_ids else '无'}")
            except Exception:
                pass
            if not isinstance(self._fc_exec_trace, list) or not self._fc_exec_trace:
                return "\n".join(header_lines) if header_lines else None
            # 开关与上限从配置读取
            enabled = True
            try:
                enabled = bool(getattr(settings, 'REACT_FC_PROGRESS_INJECTION', True))
            except Exception:
                enabled = True
            if not enabled:
                return "\n".join(header_lines) if header_lines else None

            max_items = None
            try:
                max_items = int(getattr(settings, 'REACT_FC_MAX_PROGRESS_ITEMS', 8))
            except Exception:
                max_items = 8
            if limit is None:
                limit = max_items

            # 选取最近的若干成功结果
            items = [r for r in self._fc_exec_trace if r.get('success')]
            if not items:
                # 若无成功项，回显最近失败的简要，以便模型调整策略
                items = self._fc_exec_trace[-min(len(self._fc_exec_trace), limit or 8):]
            else:
                items = items[-min(len(items), limit or 8):]

            lines: List[str] = []
            if header_lines:
                lines.extend(header_lines)
            lines.append("最近产出要点（不含工具细节）：")
            for r in items:
                # 统一提取“标识/文本/链接/路径”四类中立字段
                ident = None
                text_preview = None
                link = None
                fpath = None

                payload = r.get('result')
                if hasattr(payload, 'result'):
                    payload = getattr(payload, 'result')
                if isinstance(payload, dict):
                    # 标识：常见为 scene_number / id / index
                    for k in ['scene_number', 'scene', 'id', 'index', 'identifier']:
                        if k in payload and payload[k] not in (None, ""):
                            ident = payload[k]
                            break
                    # 文本片段：优先 text/script/prompt/description 字段
                    for k in ['prompt_text', 'script_text', 'text', 'description', 'content']:
                        v = payload.get(k)
                        if isinstance(v, str) and len(v.strip()) >= 10:
                            text_preview = v.strip().replace('\n', ' ')[:200]
                            break
                    # 链接与路径
                    for k in ['image_url', 'video_url', 'url', 'link']:
                        v = payload.get(k)
                        if isinstance(v, str) and v.startswith(('http://','https://')):
                            link = v
                            break
                    for k in ['file_path', 'path', 'output_path']:
                        v = payload.get(k)
                        if isinstance(v, str) and len(v) > 3:
                            fpath = v
                            break
                elif isinstance(payload, str) and len(payload.strip()) >= 10:
                    text_preview = payload.strip().replace('\n', ' ')[:200]

                parts = []
                if ident is not None:
                    parts.append(f"标识={ident}")
                if text_preview:
                    parts.append(f"文本片段：{text_preview}")
                # 优先展示本地路径，避免同时展示远程链接造成干扰
                if fpath:
                    parts.append(f"路径：{fpath}")
                elif link:
                    parts.append(f"链接：{link}")
                if not parts:
                    # 兜底：只提示已完成一项产出
                    parts.append("已有可用产出")
                lines.append("- " + "；".join(parts))

            return "\n".join(lines)
        except Exception:
            return None

    # === LLM依赖注入访问器 ===
    def _resolve_llm_for_role(self, role: str):
        if role in self._llms and self._llms[role] is not None:
            return self._llms[role]
        if 'default' in self._llms and self._llms['default'] is not None:
            return self._llms['default']
        raise AgentError(f"LLM not injected for agent {self.agent_name} (role={role})")

    def get_llm(self, role: str = None):
        """Public accessor for injected llm handles."""
        r = role or 'default'
        return self._resolve_llm_for_role(r)
    
    async def _execute_function_call(self, function_name: str, function_args: Dict[str, Any]) -> Any:
        """执行LLM选择的工具调用"""
        # 仅通过映射进行稳定路由（不再做字符串猜测）
        if hasattr(self, "_fc_function_map") and function_name in getattr(self, "_fc_function_map", {}):
            tool_name, action = self._fc_function_map[function_name]
            return await self.use_tool(tool_name, action, function_args)
        raise ValueError(
            f"No matching tool for function '{function_name}'. Registered: {list(getattr(self, '_fc_function_map', {}).keys())}"
        )

    # === LLM依赖注入访问器 ===
    def _resolve_llm_for_role(self, role: str):
        if role in self._llms and self._llms[role] is not None:
            return self._llms[role]
        if 'default' in self._llms and self._llms['default'] is not None:
            return self._llms['default']
        raise AgentError(f"LLM not injected for agent {self.agent_name} (role={role})")

    def get_llm(self, role: str = None):
        """Public accessor for injected llm handles."""
        r = role or 'default'
        return self._resolve_llm_for_role(r)
    
    async def _execute_function_call(self, function_name: str, function_args: Dict[str, Any]) -> Any:
        """执行LLM选择的工具调用"""
        # 优先使用扁平映射进行稳定路由
        if hasattr(self, "_fc_function_map") and function_name in getattr(self, "_fc_function_map", {}):
            tool_name, action = self._fc_function_map[function_name]
            return await self.use_tool(tool_name, action, function_args)

        # 兼容旧格式：解析“tool_action”风格名称
        parts = function_name.split("_")
        if len(parts) >= 2:
            for i in range(1, len(parts)):
                tool_name = "_".join(parts[:i])
                action = "_".join(parts[i:])
                if tool_name in self.allocated_tools:
                    return await self.use_tool(tool_name, action, function_args)

        # 找不到匹配，给出明确错误
        raise ValueError(
            f"No matching tool for function '{function_name}'. Registered: {list(getattr(self, '_fc_function_map', {}).keys())}"
        )

    async def execute_tool_calls(self, tool_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """统一执行一组 tool_calls（与 FC 返回格式兼容）。
        每条元素期望形如 {"function": {"name": str, "arguments": str|dict}}。
        返回标准结果列表：[{tool, args, result?, success, error?, error_type?}]
        """
        try:
            self.logger.info("🤖 选择工具：开始执行规划的工具调用")
        except Exception:
            pass
        results: List[Dict[str, Any]] = []
        funcs_used: List[str] = []
        # 本轮规范化结果快照（通用字段，供应商无关）
        last_round_results: List[Dict[str, Any]] = []
        # 本轮度量（不改变行为，仅可观测）
        round_metrics = {
            'total': 0,
            'success': 0,
            'fail': 0,
            'plan_total': 0,
            'plan_success': 0,
            'act_total': 0,
            'act_success': 0,
            'artifacts': 0,
        }
        for idx, tool_call in enumerate(tool_calls):
            try:
                fn = tool_call["function"]["name"]
                funcs_used.append(fn)
                raw_args = tool_call["function"].get("arguments", {})
                args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})

                # 解析 tool 与 action（优先映射，其次点分隔用于日志展示）
                tool_name, action_name = None, None
                try:
                    if hasattr(self, "_fc_function_map") and fn in getattr(self, "_fc_function_map", {}):
                        tool_name, action_name = self._fc_function_map[fn]
                    elif "." in fn:
                        tool_name, action_name = fn.split(".", 1)
                    else:
                        tool_name, action_name = fn, None
                except Exception:
                    tool_name, action_name = fn, None

                scene = args.get("scene_number") if isinstance(args, dict) else None
                try:
                    args_preview = raw_args if isinstance(raw_args, str) else json.dumps(args, ensure_ascii=False)
                    if isinstance(args_preview, str):
                        # DEBUG 等级下不截断；否则使用配置化的预览长度
                        args_preview = args_preview.replace("\n", " ")
                        if not self.logger.isEnabledFor(logging.DEBUG):
                            try:
                                max_len = int(getattr(settings, 'CONTENT_PREVIEW_CHARS', 300))
                            except Exception:
                                max_len = 300
                            args_preview = args_preview[:max_len]
                except Exception:
                    args_preview = "{}"

                # 快速前置校验：函数是否已暴露/可执行（避免进入执行期才报错）
                try:
                    if fn not in getattr(self, "_fc_function_map", {}):
                        # 允许以“tool.action”形式直达（不做下划线拆分以保持中立）
                        if "." in fn:
                            _tn, _an = fn.split(".", 1)
                            valid_tool = _tn in self._available_tools
                            valid_action = False
                            if valid_tool:
                                try:
                                    valid_action = _an in (self._available_tools[_tn].get_available_actions() or [])
                                except Exception:
                                    valid_action = False
                            if not (valid_tool and valid_action):
                                results.append({
                                    "tool": fn,
                                    "args": args,
                                    "success": False,
                                    "error": "function not exposed or action unavailable",
                                    "error_type": "invalid_tool_call",
                                })
                                # 记录到度量
                                round_metrics['total'] += 1
                                round_metrics['fail'] += 1
                                continue
                        else:
                            # 既非映射也非 tool.action，直接判定为无效
                            results.append({
                                "tool": fn,
                                "args": args,
                                "success": False,
                                "error": "unknown function format (expected tool.action)",
                                "error_type": "invalid_tool_call",
                            })
                            round_metrics['total'] += 1
                            round_metrics['fail'] += 1
                            continue
                except Exception:
                    # 校验失败不阻断，交给执行期处理
                    pass

                call_id = f"{int(time.time()*1000)}-{idx}"
                try:
                    self.logger.info(
                        f"TOOL_START call_id={call_id} fn={fn} tool={tool_name} action={action_name} scene={scene} args={args_preview}"
                    )
                except Exception:
                    pass

                _call_ts = time.time()
                tool_result = await self._execute_function_call(fn, args)
                _dur = time.time() - _call_ts
                # 兼容 ToolOutput / dict
                is_success = True
                error_text = None
                error_type = None
                if hasattr(tool_result, 'success'):
                    is_success = bool(getattr(tool_result, 'success'))
                    if not is_success:
                        error_text = getattr(tool_result, 'error', None)
                        meta = getattr(tool_result, 'metadata', {}) or {}
                        error_type = meta.get('error_type')
                # 分段度量统计
                round_metrics['total'] += 1
                # 判定阶段（plan/act）
                stage = 'act'
                try:
                    if hasattr(self, "_fc_function_map") and fn in getattr(self, "_fc_function_map", {}):
                        tname, aname = self._fc_function_map[fn]
                        tool_obj = self._available_tools.get(tname)
                        if tool_obj and hasattr(tool_obj, 'get_action_stage') and callable(getattr(tool_obj, 'get_action_stage')):
                            stage = tool_obj.get_action_stage(aname) or 'act'
                except Exception:
                    stage = 'act'
                record = {"tool": fn, "args": args, "success": is_success}
                if is_success:
                    record["result"] = tool_result
                    results.append(record)
                    round_metrics['success'] += 1
                else:
                    record["error"] = error_text or "tool execution failed"
                    record["error_type"] = error_type
                    results.append(record)
                    round_metrics['fail'] += 1
                # 写入FC执行轨迹（用于后续FC上下文注入）
                try:
                    from time import time as _now
                    trace_item = {
                        "tool": fn,
                        "args": args,
                        "success": is_success,
                        "result": tool_result if is_success else None,
                        "error": error_text,
                        "error_type": error_type,
                        "ts": _now(),
                    }
                    self._fc_exec_trace.append(trace_item)
                except Exception:
                    pass
                # 结束日志 + 可选自动持久化产物
                try:
                    artifact = None
                    payload = tool_result.result if hasattr(tool_result, 'result') else tool_result
                    if isinstance(payload, dict):
                        # 优先使用本地持久化路径作为“产物”可观测标识
                        artifact = payload.get('file_path') or payload.get('image_url') or payload.get('video_url')
                        # 自动持久化：根据配置与可用工具，将 image_url/video_url 落盘并回写 file_path（保持中立，无供应商/工具名暴露）
                        try:
                            from ..core.config import settings as _cfg
                            auto_persist = bool(getattr(_cfg, 'REACT_AUTO_PERSIST_ARTIFACTS', False))
                        except Exception:
                            auto_persist = False
                        # 幂等保护：若 payload 已有 file_path，则跳过上传
                        already_persisted = isinstance(payload.get('file_path'), str) and len(payload.get('file_path')) > 0
                        if auto_persist and (not already_persisted) and artifact and isinstance(artifact, str) and artifact.startswith(("http://", "https://")):
                            try:
                                if 'file_storage_tool' in self._available_tools:
                                    # 目标文件名推断（尽量基于场景号）
                                    scene_num = args.get('scene_number') if isinstance(args, dict) else None
                                    is_video = bool(payload.get('video_url'))
                                    prefix = 'videos' if is_video else 'images'
                                    fname = f"scene_{scene_num}_{'video.mp4' if is_video else 'image.jpg'}" if scene_num is not None else f"artifact_{int(time.time()*1000)}.bin"
                                    dest_key = f"{prefix}/{fname}"
                                    store_res = await self.use_tool(
                                        tool_name='file_storage_tool',
                                        action='upload_from_url',
                                        parameters={
                                            'url': artifact,
                                            'destination_key': dest_key,
                                            'metadata': {
                                                'scene_number': scene_num,
                                                'source': 'react_autopersist'
                                            }
                                        }
                                    )
                                    persisted = store_res.result if hasattr(store_res, 'result') else store_res
                                    if isinstance(persisted, dict) and persisted.get('file_path'):
                                        # 将持久化路径写回payload，便于统一快照与后续上下文
                                        payload['file_path'] = persisted['file_path']
                            except Exception:
                                pass
                        if payload.get('file_path') or artifact:
                            round_metrics['artifacts'] += 1
                    if stage == 'plan':
                        round_metrics['plan_total'] += 1
                        if is_success:
                            round_metrics['plan_success'] += 1
                    else:
                        round_metrics['act_total'] += 1
                        if is_success:
                            round_metrics['act_success'] += 1
                    # 规范化结果快照（供应商无关字段）
                    try:
                        snap: Dict[str, Any] = {
                            'scene_number': args.get('scene_number') if isinstance(args, dict) else None,
                            'success': is_success,
                            'stage': stage,
                            'duration_sec': round(_dur, 2),
                        }
                        if isinstance(payload, dict):
                            # 文本片段（优先 prompt_text，其次 prompt/text/description）
                            txt = payload.get('prompt_text') or payload.get('prompt') or payload.get('text') or payload.get('description')
                            if isinstance(txt, str) and txt.strip():
                                snap['prompt_text'] = txt.strip()
                            # 产物位置
                            if payload.get('image_url'):
                                snap['image_url'] = payload.get('image_url')
                            if payload.get('video_url'):
                                snap['video_url'] = payload.get('video_url')
                            # 音频产物位置（用于音频代理等场景）
                            if payload.get('audio_url'):
                                snap['audio_url'] = payload.get('audio_url')
                            if payload.get('file_path'):
                                snap['file_path'] = payload.get('file_path')
                        last_round_results.append(snap)
                    except Exception:
                        pass
                    self.logger.info(
                        f"TOOL_END call_id={call_id} fn={fn} tool={tool_name} action={action_name} scene={scene} success={is_success} dur={_dur:.2f}s"
                        + (f" artifact={artifact}" if artifact else "")
                        + (f" error={error_text}" if (not is_success and error_text) else "")
                    )
                except Exception:
                    pass
            except Exception as e:
                try:
                    _dur = time.time() - _call_ts if '_call_ts' in locals() else 0.0
                    self.logger.error(
                        f"TOOL_END call_id={call_id} fn={fn} tool={tool_name} action={action_name} scene={scene} success=false dur={_dur:.2f}s error={str(e)}"
                    )
                except Exception:
                    self.logger.error(f"Tool execution failed: {e}")
                results.append({"tool": tool_call.get("function", {}).get("name"), "args": tool_call.get("function", {}).get("arguments"), "error": str(e), "success": False})
        # 更新 ReAct 级别的重复调用守卫（若存在迭代上下文）
        try:
            if hasattr(self, 'iteration_context') and isinstance(self.iteration_context, dict):
                guard = dict(self.iteration_context.get('fc_repeat_guard', {}))
                last_funcs = set(guard.get('last_functions', []))
                current_funcs = set(funcs_used)
                if current_funcs and current_funcs == last_funcs:
                    guard['repeat_times'] = int(guard.get('repeat_times', 0)) + 1
                else:
                    guard['repeat_times'] = 0
                guard['last_functions'] = list(current_funcs)
                self.iteration_context['fc_repeat_guard'] = guard
                # 写入本轮度量（仅可观测状态）
                rm = dict(self.iteration_context.get('react_metrics', {}))
                rm.update(round_metrics)
                rm['executed_functions'] = funcs_used[:10]
                self.iteration_context['react_metrics'] = rm
                # 写入本轮规范化结果快照
                self.iteration_context['last_round_results'] = last_round_results
        except Exception:
            pass
        return results
    
    def get_tool_names(self) -> List[str]:
        """获取当前Agent加载的工具名称列表"""
        return list(self._available_tools.keys())
    
    def get_tool_capabilities_summary(self) -> str:
        """获取工具能力摘要，供LLM理解"""
        capabilities = []
        
        for tool_name in self.allocated_tools:
            tool = self._available_tools.get(tool_name)
            if tool:
                metadata = tool.get_metadata()
                actions = tool.get_available_actions()
                capabilities.append(f"- {tool_name}: {metadata.description} (actions: {', '.join(actions)})")
        
        return "\n".join(capabilities) if capabilities else "No tools available"
    
    
    def get_system_instructions(self) -> Dict[str, Any]:
        """获取Agent的系统指令"""
        return self.prompt_manager.get_system_instruction(self.agent_name)
    
    async def _handle_retry(
        self, 
        task: Task, 
        execution: AgentExecution, 
        error: Exception,
        db: Session
    ) -> bool:
        """
        Handle retry logic for failed executions
        
        Returns:
            True if retry should be attempted, False otherwise
        """
        if not execution.can_retry:
            self.logger.error(
                f"Max retries ({execution.max_retries}) exceeded for {self.agent_name}"
            )
            return False
        
        self.logger.warning(
            f"Retrying {self.agent_name} (attempt {execution.retry_count + 1})"
        )
        
        # Wait before retry with exponential backoff
        wait_time = min(60, 2 ** execution.retry_count)
        await asyncio.sleep(wait_time)
        
        return True
    
    def _initialize_agent(self):
        """Agent-specific initialization - override in subclasses"""
        pass
    
    def _load_tools(self, tool_names: List[str]):
        """Load specified tools from registry"""
        load_errors: List[str] = []
        schema_warnings: List[str] = []
        for tool_name in tool_names:
            try:
                tool = self.tool_registry.get_tool(tool_name)
                self._available_tools[tool_name] = tool
                # 轻量校验：至少存在一个可用的action schema
                try:
                    actions = tool.get_available_actions() or []
                    has_schema = False
                    for act in actions:
                        sch = tool.get_action_schema(act) or {}
                        if isinstance(sch, dict) and sch:
                            has_schema = True
                            break
                    if not has_schema:
                        schema_warnings.append(tool_name)
                except Exception as se:
                    schema_warnings.append(f"{tool_name} (schema error: {se}")
                self.logger.info(f"Loaded tool: {tool_name}")
            except Exception as e:
                err = f"{tool_name}: {e}"
                self.logger.error(f"Failed to load tool {err}")
                load_errors.append(err)

        # Fail fast: 任何分配但未成功加载的工具直接报错，保障可验证性
        if load_errors:
            raise AgentError(
                f"Tool allocation failed for {self.agent_name}: {', '.join(load_errors)}"
            )
        # 非致命：若工具缺少可用schema，记录警告，FC时将无法暴露该工具动作
        if schema_warnings:
            self.logger.warning(
                f"Tools missing valid action schema (will not be exposed to FC): {', '.join(schema_warnings)}"
            )
    
    async def use_tool(
        self, 
        tool_name: str, 
        action: str, 
        parameters: Dict[str, Any],
        timeout: int = None
    ) -> Any:
        """Use a tool (stateless execution)"""
        if tool_name not in self._available_tools:
            raise AgentError(f"Tool {tool_name} not available for agent {self.agent_name}")
        
        tool = self._available_tools[tool_name]
        
        try:
            # Execute tool
            from .tools.base_tool import ToolInput
            # Inject context for timeout resolver: allow agent-level control without hardcoding
            context = {
                "agent_tool_timeout": None,  # reserved for per-agent tool defaults
                "agent_timeout_seconds": self.timeout_seconds,
            }
            # action 允许为 None（无动作工具），约定下发 "__call__" 作为工具级调用占位符
            tool_input = ToolInput(action=(action if action is not None else "__call__"), parameters=parameters, context=context, timeout=timeout)
            result = await tool.execute(tool_input)

            # Log based on success
            try:
                if hasattr(result, 'success') and not result.success:
                    self.logger.warning(
                        f"🔧 Tool {tool_name}:{action} returned failure: {getattr(result, 'error', 'unknown error')}"
                    )
                else:
                    self.logger.info(f"🔧 Tool {tool_name}:{action} executed successfully")
            except Exception:
                # Fallback log if structure unexpected
                self.logger.info(f"🔧 Tool {tool_name}:{action} executed (log parsing skipped)")

            return result

        except Exception as e:
            self.logger.error(f"Tool execution failed for {tool_name}.{action}: {e}")
            raise AgentError(f"Tool execution failed: {str(e)}")
    
    # 🚀 Phase 1.3 - 工具系统解耦：统一AI服务接口
    async def generate_text(
        self,
        prompt: str,
        model: str = None,
        temperature: float = None,
        max_tokens: int = None,
        response_format: Dict[str, Any] = None,
        tool_name: str = "text_generation_tool"
    ) -> Dict[str, Any]:
        """
        统一的文本生成接口 - 通过工具系统调用AI服务
        替代直接使用AIClient的调用方式
        """
        parameters = {
            "prompt": prompt,
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": response_format
        }
        # 移除None值
        parameters = {k: v for k, v in parameters.items() if v is not None}
        
        result = await self.use_tool(tool_name, "generate_text", parameters)
        if result.success:
            return result.result
        raise AgentError(f"文本生成失败: {result.error}")
    
    # 直连AI回退已禁用：一切文本生成需通过工具/服务接口执行
    
    def register_default_tools(self):
        """注册默认工具集"""
        default_tools = [
            "text_generation_tool",
            "ai_service_tool"
        ]
        
        for tool_name in default_tools:
            if tool_name not in self._available_tools:
                try:
                    tool = self.tool_registry.get_tool(tool_name)
                    self._available_tools[tool_name] = tool
                    self.logger.info(f"🔧 已注册默认工具: {tool_name}")
                except Exception as e:
                    self.logger.warning(f"⚠️ 默认工具注册失败 {tool_name}: {e}")
    
    async def ensure_ai_tools_available(self):
        """确保AI工具可用"""
        ai_tools = ["text_generation_tool", "ai_service_tool"]
        
        for tool_name in ai_tools:
            if tool_name not in self._available_tools:
                self.register_default_tools()
                break
    
    def render_prompt(
        self, 
        template_name: str, 
        **variables
    ) -> str:
        """
        渲染Agent专用提示词模板 - 使用新的统一提示词管理系统
        
        Args:
            template_name: 模板名称
            **variables: 模板变量
            
        Returns:
            渲染后的提示词文本
        """
        try:
            return self.prompt_manager.render_template(
                config_name=self.agent_name,
                template_name=template_name,
                variables=variables,
                auto_reload=False  # 生产环境关闭自动重载
            )
        except Exception as e:
            self.logger.error(f"Prompt rendering failed for {template_name}: {e}")
            raise AgentError(f"Prompt rendering failed: {str(e)}")
    
    async def store_memory(
        self,
        content: Any,
        tags: List[str] = None,
        importance: str = "medium",
        metadata: Dict[str, Any] = None
    ) -> str:
        """Store information in agent memory"""
        from .memory.base_memory import MemoryImportance, MemoryType
        
        importance_map = {
            "minimal": MemoryImportance.MINIMAL,
            "low": MemoryImportance.LOW,
            "medium": MemoryImportance.MEDIUM,
            "high": MemoryImportance.HIGH,
            "critical": MemoryImportance.CRITICAL
        }
        
        if self.memory_manager is None:
            return "memory_disabled"
        
        memory_id = await self.memory_manager.store_memory(
            content=content,
            memory_type=MemoryType.SHORT_TERM,
            importance=importance_map.get(importance, MemoryImportance.MEDIUM),
            tags=tags or [],
            agent_id=self.agent_name,
            metadata=metadata or {}
        )
        
        return memory_id
    
    async def retrieve_memories(
        self,
        query: str = None,
        tags: List[str] = None,
        limit: int = 10
    ) -> List[Any]:
        """Retrieve relevant memories"""
        if self.memory_manager is None:
            return []
        
        memories = await self.memory_manager.search_memories(
            query=query,
            tags=tags,
            agent_id=self.agent_name,
            limit=limit
        )
        
        return [memory.content for memory in memories]
    
    def get_available_tools(self) -> List[str]:
        """Get list of available tool names"""
        return list(self._available_tools.keys())
    
    def get_tool_capabilities(self, tool_name: str) -> List[str]:
        """Get capabilities of a specific tool"""
        if tool_name not in self._available_tools:
            return []
        
        tool = self._available_tools[tool_name]
        return tool.get_available_actions()
    
    def get_prompt_templates(self) -> List[str]:
        """Get list of available prompt templates"""
        return self._prompt_templates
    
    async def get_memory_stats(self) -> Dict[str, Any]:
        """Get memory usage statistics"""
        if self.memory_manager is None:
            return {"status": "disabled"}
        
        return await self.memory_manager.get_memory_stats()
    
    # 🚀 MAS记忆共享机制 - Phase 1.2新增
    async def store_creative_guidance(
        self, 
        workflow_id: str, 
        concept_plan: Dict[str, Any]
    ) -> bool:
        """存储创意指导供其他Agent使用"""
        return await self.memory_service.store_creative_guidance(
            workflow_id, concept_plan, self.agent_name
        )
    
    async def retrieve_creative_guidance(
        self, 
        workflow_id: str, 
        scene_number: Optional[int] = None
    ) -> Dict[str, Any]:
        """检索创意指导信息"""
        return await self.memory_service.retrieve_creative_guidance(
            workflow_id, scene_number, self.agent_name
        )
    
    async def store_scene_references(
        self, 
        workflow_id: str, 
        scene_number: int, 
        scene_references: Dict[str, Any]
    ) -> bool:
        """存储场景参考数据供其他Agent使用"""
        return await self.memory_service.store_scene_references(
            workflow_id, scene_number, scene_references, self.agent_name
        )
    
    async def retrieve_scene_references(
        self, 
        workflow_id: str, 
        scene_number: int
    ) -> Dict[str, Any]:
        """检索场景参考数据"""
        return await self.memory_service.retrieve_scene_references(
            workflow_id, scene_number, self.agent_name
        )
    
    async def _cleanup_resources(self):
        """Cleanup agent resources"""
        try:
            # Close memory manager
            if self.memory_manager is not None and hasattr(self.memory_manager, 'close'):
                await self.memory_manager.close()
            
            # Cleanup tools
            for tool in self._available_tools.values():
                if hasattr(tool, 'cleanup'):
                    await tool.cleanup()
                    
        except Exception as e:
            self.logger.warning(f"Error during resource cleanup: {e}")
    
    async def __aenter__(self):
        """Async context manager entry"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self._cleanup_resources()
