"""
Base agent class for all video generation agents
"""
import asyncio
import time
import logging
import json
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session

from ..models import Task, AgentExecution, AgentType, AgentStatus
from ..core.database import get_sync_db
from ..services.websocket import WebSocketManager

from .tools.tool_registry import get_tool_registry
from .tools.agent_tool_allocation import get_agent_tools, validate_agent_tools
from .tools.ai_services.service_interfaces import get_llm_service
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
        prompt_templates: List[str] = None
    ):
        self.agent_type = agent_type
        self.agent_name = agent_name
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.logger = logging.getLogger(f"agent.{agent_name}")
        self.websocket_manager = WebSocketManager()
        
        # Initialize tool registry
        self.tool_registry = get_tool_registry()
        self._available_tools = {}
        
        # 工具分配：使用专门的工具列表或手动指定的工具
        if tools:
            # 手动指定工具列表（需要验证）
            validation = validate_agent_tools(agent_type, tools)
            if not validation["is_valid"]:
                self.logger.warning(f"Tool validation failed: {validation['recommendations']}")
                # 使用推荐的工具列表
                tools = validation["allowed_tools"]
            self._load_tools(tools)
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
        
        # Agent-specific initialization
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
        # Create agent execution record
        execution = AgentExecution(
            task_id=task.id,
            agent_type=self.agent_type,
            agent_name=self.agent_name,
            execution_order=execution_order,
            input_data=input_data,
            timeout_seconds=self.timeout_seconds,
            max_retries=self.max_retries
        )
        db.add(execution)
        db.commit()
        db.refresh(execution)
        
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
            
            # Complete execution
            execution.complete_execution(output_data)
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
        """Validate that required input keys are present"""
        missing_keys = [key for key in required_keys if key not in input_data]
        if missing_keys:
            raise AgentError(f"Missing required input keys: {missing_keys}")
    
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
        model: str = "glm-4-plus",
        temperature: float = 0.3,
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
            # 构建工具schema
            tools_schema = self._build_function_call_schema()
            
            if not tools_schema:
                self.logger.warning(f"No tools available for {self.agent_name}")
                return {
                    "success": False,
                    "error": "No tools available for function calling"
                }
            
            # 添加系统消息，描述Agent角色和可用工具
            system_message = {
                "role": "system",
                "content": f"""你是{self.agent_name}，专门负责{self.agent_type.value}相关任务。

可用工具: {', '.join(self.allocated_tools)}

{context_description}

请根据用户需求智能选择合适的工具和参数来完成任务。"""
            }
            
            # 构建完整消息列表
            complete_messages = [system_message] + messages
            
            # 调用LLM Function Call
            llm_service = get_llm_service()
            llm_response = await llm_service.function_call(
                messages=complete_messages,
                tools=tools_schema,
                tool_choice="auto",
                model=model,
                temperature=temperature,
                **kwargs
            )
            
            # 处理Function Call响应
            if llm_response.get("has_function_call") and llm_response.get("tool_calls"):
                # LLM选择了工具调用
                results = []
                
                for tool_call in llm_response["tool_calls"]:
                    function_name = tool_call["function"]["name"]
                    function_args = json.loads(tool_call["function"]["arguments"])
                    
                    self.logger.info(f"🤖 LLM选择工具: {function_name}")
                    
                    # 执行工具调用
                    try:
                        tool_result = await self._execute_function_call(function_name, function_args)
                        results.append({
                            "tool": function_name,
                            "args": function_args,
                            "result": tool_result,
                            "success": True
                        })
                    except Exception as e:
                        self.logger.error(f"Tool execution failed: {e}")
                        results.append({
                            "tool": function_name,
                            "args": function_args,
                            "error": str(e),
                            "success": False
                        })
                
                return {
                    "success": True,
                    "approach": "function_call",
                    "tool_calls": results,
                    "llm_response": llm_response
                }
            
            else:
                # LLM没有选择工具调用，返回文本响应
                return {
                    "success": True,
                    "approach": "text_response",
                    "content": llm_response.get("content", ""),
                    "llm_response": llm_response
                }
        
        except Exception as e:
            self.logger.error(f"Function call failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _build_function_call_schema(self) -> List[Dict[str, Any]]:
        """构建Function Call的工具schema"""
        tools_schema = []
        
        for tool_name in self.allocated_tools:
            try:
                tool = self._available_tools.get(tool_name)
                if tool is None:
                    continue
                
                # 获取工具的所有action
                actions = tool.get_available_actions()
                
                for action in actions:
                    action_schema = tool.get_action_schema(action)
                    if action_schema:
                        # 转换为标准Function Call格式
                        function_schema = {
                            "type": "function",
                            "function": {
                                "name": f"{tool_name}_{action}",
                                "description": f"{tool.get_metadata().description} - {action}",
                                "parameters": action_schema
                            }
                        }
                        tools_schema.append(function_schema)
                
            except Exception as e:
                self.logger.warning(f"Failed to build schema for tool {tool_name}: {e}")
        
        return tools_schema
    
    async def _execute_function_call(self, function_name: str, function_args: Dict[str, Any]) -> Any:
        """执行LLM选择的工具调用"""
        
        # 解析工具名称和action - 处理多个下划线的情况
        parts = function_name.split("_")
        if len(parts) < 2:
            raise ValueError(f"Invalid function name format: {function_name}")
        
        # 尝试不同的分割方式找到正确的工具
        for i in range(1, len(parts)):
            tool_name = "_".join(parts[:i])
            action = "_".join(parts[i:])
            
            if tool_name in self.allocated_tools:
                # 执行工具
                return await self.use_tool(tool_name, action, function_args)
        
        # 如果没有找到匹配的工具，抛出错误
        raise ValueError(f"No matching tool found for function: {function_name}. Available tools: {self.allocated_tools}")
    
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
        for tool_name in tool_names:
            try:
                tool = self.tool_registry.get_tool(tool_name)
                self._available_tools[tool_name] = tool
                self.logger.info(f"Loaded tool: {tool_name}")
            except Exception as e:
                self.logger.error(f"Failed to load tool {tool_name}: {e}")
    
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
            tool_input = ToolInput(action=action, parameters=parameters, timeout=timeout)
            result = await tool.execute(tool_input)
            
            # Log tool usage for debugging
            self.logger.info(f"🔧 Tool {tool_name}:{action} executed successfully")
            
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
        
        try:
            result = await self.use_tool(tool_name, "generate_text", parameters)
            if result.success:
                return result.result
            else:
                raise AgentError(f"文本生成失败: {result.error}")
        except Exception as e:
            # 如果工具不可用，回退到直接调用（兼容性）
            self.logger.warning(f"⚠️ 工具系统调用失败，回退到直接AI服务: {e}")
            return await self._fallback_generate_text(prompt, model, temperature, max_tokens, response_format)
    
    async def _fallback_generate_text(
        self,
        prompt: str,
        model: str = None,
        temperature: float = None,
        max_tokens: int = None,
        response_format: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """回退到直接AI服务调用（兼容性保证）"""
        try:
            from ..services.ai_client import AIClient
            ai_client = AIClient()
            return await ai_client.generate_text(
                prompt=prompt,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format
            )
        except Exception as e:
            raise AgentError(f"AI服务调用失败: {str(e)}")
    
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