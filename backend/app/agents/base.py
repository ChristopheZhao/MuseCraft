"""
Base agent class for all video generation agents
"""
import asyncio
import time
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session

from ..models import Task, AgentExecution, AgentType, AgentStatus
from ..core.database import get_sync_db
from ..services.websocket import WebSocketManager

from .tools.tool_registry import get_tool_registry
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
        if tools:
            self._load_tools(tools)
        
        # 记忆管理器将通过依赖注入提供，Agent保持无状态
        self.memory_manager = None  # 临时解决方案，避免render_prompt报错
        
        # Initialize agent-specific prompt template manager
        # Each agent gets its own template manager with isolated templates
        self.template_manager = get_template_manager(agent_name=agent_name)
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
    
    async def render_prompt(
        self, 
        template_name: str, 
        variables: Dict[str, Any],
        store_in_memory: bool = True
    ) -> str:
        """Render a prompt template with variables"""
        try:
            rendered_prompt = self.template_manager.render_template(template_name, variables)
            
            # Store in memory if requested and memory_manager available
            if store_in_memory and self.memory_manager is not None:
                await self.memory_manager.store_memory(
                    content={
                        "template_name": template_name,
                        "variables": variables,
                        "rendered_prompt": rendered_prompt
                    },
                    tags=["prompt_rendering", template_name],
                    agent_id=self.agent_name,
                    metadata={"prompt_template": True}
                )
            
            return rendered_prompt
            
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