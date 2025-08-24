"""
MAS Communication Hub - Multi-Agent System 中心化通信架构
"""
import asyncio
import json
import uuid
from datetime import datetime
from typing import Dict, List, Any, Optional, Union, Callable
from dataclasses import dataclass, asdict
from enum import Enum
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class MessageType(Enum):
    """消息类型"""
    TASK_REQUEST = "task_request"
    TASK_RESPONSE = "task_response"
    AGENT_REGISTER = "agent_register"
    AGENT_DISCOVER = "agent_discover"
    STATUS_UPDATE = "status_update"
    PLAN_REQUEST = "plan_request"      # 🎯 强调planning
    PLAN_RESPONSE = "plan_response"    # 🎯 规划响应
    PLAN_EXECUTION = "plan_execution"  # 🎯 规划执行
    HANDOFF_REQUEST = "handoff_request"
    HANDOFF_COMPLETE = "handoff_complete"
    COORDINATION_SYNC = "coordination_sync"


class MessagePriority(Enum):
    """消息优先级"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4
    PLANNING = 5  # 🎯 规划消息最高优先级


@dataclass
class Message:
    """消息基础结构"""
    id: str
    type: MessageType
    priority: MessagePriority
    from_agent: str
    to_agent: Optional[str]  # None表示广播
    workflow_id: str
    payload: Dict[str, Any]
    timestamp: datetime
    timeout: Optional[int] = 30  # seconds
    retry_count: int = 0
    max_retries: int = 3
    correlation_id: Optional[str] = None  # 用于关联请求响应


@dataclass
class AgentCapability:
    """Agent能力描述"""
    agent_id: str
    agent_type: str
    capabilities: List[str]
    tools: List[str]
    status: str = "available"  # available, busy, offline
    load_factor: float = 0.0  # 0-1之间的负载因子
    last_heartbeat: Optional[datetime] = None
    planning_capable: bool = False  # 🎯 是否具备规划能力


class ICommunicationHub(ABC):
    """通信中心接口"""
    
    @abstractmethod
    async def register_agent(self, agent_capability: AgentCapability) -> bool:
        """注册Agent"""
        pass
    
    @abstractmethod
    async def discover_agents(
        self, 
        capabilities: List[str] = None,
        agent_type: str = None,
        planning_required: bool = False  # 🎯 是否需要规划能力
    ) -> List[AgentCapability]:
        """发现可用Agent"""
        pass
    
    @abstractmethod
    async def send_message(self, message: Message) -> bool:
        """发送消息"""
        pass
    
    @abstractmethod
    async def receive_messages(
        self, 
        agent_id: str,
        message_types: List[MessageType] = None
    ) -> List[Message]:
        """接收消息"""
        pass


class CentralCommunicationHub(ICommunicationHub):
    """
    中心化通信中心
    🎯 强化规划协调能力的多Agent通信架构
    """
    
    def __init__(self):
        # Agent注册表
        self._agents: Dict[str, AgentCapability] = {}
        
        # 消息队列 - 按优先级分层
        self._message_queues: Dict[str, List[Message]] = {}
        self._planning_queue: List[Message] = []  # 🎯 专门的规划消息队列
        
        # 消息路由和回调
        self._message_handlers: Dict[str, List[Callable]] = {}
        self._pending_responses: Dict[str, Message] = {}
        
        # 协调状态
        self._workflow_states: Dict[str, Dict[str, Any]] = {}
        self._planning_sessions: Dict[str, Dict[str, Any]] = {}  # 🎯 规划会话状态
        
        # 系统监控
        self._message_stats: Dict[str, int] = {}
        self._performance_metrics: Dict[str, Any] = {}
        
        self.logger = logging.getLogger("mas_communication")
        self.logger.info("🚀 CentralCommunicationHub initialized with enhanced planning capabilities")
    
    async def register_agent(self, agent_capability: AgentCapability) -> bool:
        """注册Agent到通信中心"""
        try:
            agent_id = agent_capability.agent_id
            
            # 注册Agent
            self._agents[agent_id] = agent_capability
            
            # 初始化消息队列
            if agent_id not in self._message_queues:
                self._message_queues[agent_id] = []
            
            # 更新心跳时间
            agent_capability.last_heartbeat = datetime.now()
            
            self.logger.info(f"✅ Agent registered: {agent_id} ({agent_capability.agent_type})")
            if agent_capability.planning_capable:
                self.logger.info(f"🎯 Planning-capable agent registered: {agent_id}")
            
            # 广播Agent注册消息
            register_msg = Message(
                id=str(uuid.uuid4()),
                type=MessageType.AGENT_REGISTER,
                priority=MessagePriority.NORMAL,
                from_agent="communication_hub",
                to_agent=None,  # 广播
                workflow_id="system",
                payload={
                    "agent_capability": asdict(agent_capability)
                },
                timestamp=datetime.now()
            )
            
            await self._broadcast_message(register_msg)
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Agent registration failed: {e}")
            return False
    
    async def discover_agents(
        self, 
        capabilities: List[str] = None,
        agent_type: str = None,
        planning_required: bool = False
    ) -> List[AgentCapability]:
        """发现符合条件的Agent"""
        try:
            matching_agents = []
            
            for agent_id, agent_cap in self._agents.items():
                # 状态过滤
                if agent_cap.status == "offline":
                    continue
                
                # 类型过滤
                if agent_type and agent_cap.agent_type != agent_type:
                    continue
                
                # 能力过滤
                if capabilities and not all(cap in agent_cap.capabilities for cap in capabilities):
                    continue
                
                # 🎯 规划能力过滤
                if planning_required and not agent_cap.planning_capable:
                    continue
                
                matching_agents.append(agent_cap)
            
            # 按负载因子排序，优先选择负载较低的Agent
            matching_agents.sort(key=lambda x: x.load_factor)
            
            self.logger.info(f"🔍 Discovered {len(matching_agents)} agents "
                           f"(capabilities={capabilities}, planning_required={planning_required})")
            
            return matching_agents
            
        except Exception as e:
            self.logger.error(f"❌ Agent discovery failed: {e}")
            return []
    
    async def send_message(self, message: Message) -> bool:
        """发送消息"""
        try:
            # 🎯 规划消息特殊处理
            if message.type in [MessageType.PLAN_REQUEST, MessageType.PLAN_RESPONSE, MessageType.PLAN_EXECUTION]:
                return await self._handle_planning_message(message)
            
            # 更新消息统计
            self._message_stats[message.type.value] = self._message_stats.get(message.type.value, 0) + 1
            
            if message.to_agent:
                # 点对点消息
                return await self._send_direct_message(message)
            else:
                # 广播消息
                return await self._broadcast_message(message)
            
        except Exception as e:
            self.logger.error(f"❌ Message send failed: {e}")
            return False
    
    async def receive_messages(
        self, 
        agent_id: str,
        message_types: List[MessageType] = None
    ) -> List[Message]:
        """接收消息"""
        try:
            if agent_id not in self._message_queues:
                return []
            
            messages = []
            queue = self._message_queues[agent_id]
            
            # 🎯 规划消息优先处理
            planning_messages = []
            regular_messages = []
            
            for msg in queue:
                if message_types and msg.type not in message_types:
                    regular_messages.append(msg)
                    continue
                
                if msg.priority == MessagePriority.PLANNING:
                    planning_messages.append(msg)
                else:
                    regular_messages.append(msg)
            
            # 先返回规划消息，再返回常规消息
            messages.extend(planning_messages)
            messages.extend(sorted(regular_messages, key=lambda x: x.priority.value, reverse=True))
            
            # 清空队列中已处理的消息
            self._message_queues[agent_id] = [
                msg for msg in queue 
                if msg not in messages
            ]
            
            return messages
            
        except Exception as e:
            self.logger.error(f"❌ Message receive failed for agent {agent_id}: {e}")
            return []
    
    async def _handle_planning_message(self, message: Message) -> bool:
        """🎯 专门处理规划相关消息"""
        try:
            workflow_id = message.workflow_id
            
            if message.type == MessageType.PLAN_REQUEST:
                # 规划请求 - 创建规划会话
                session_id = str(uuid.uuid4())
                self._planning_sessions[session_id] = {
                    "workflow_id": workflow_id,
                    "request_message": message,
                    "status": "planning",
                    "created_at": datetime.now(),
                    "plan_steps": [],
                    "execution_status": {}
                }
                
                # 查找具备规划能力的Agent
                planning_agents = await self.discover_agents(planning_required=True)
                if not planning_agents:
                    self.logger.error("🎯 No planning-capable agents available")
                    return False
                
                # 选择负载最低的规划Agent
                selected_agent = planning_agents[0]
                message.to_agent = selected_agent.agent_id
                message.priority = MessagePriority.PLANNING
                
                self.logger.info(f"🎯 Planning request routed to {selected_agent.agent_id}")
                
            elif message.type == MessageType.PLAN_RESPONSE:
                # 规划响应 - 更新规划会话
                plan_data = message.payload.get("plan", {})
                session_id = message.payload.get("session_id")
                
                if session_id in self._planning_sessions:
                    session = self._planning_sessions[session_id]
                    session["plan_steps"] = plan_data.get("steps", [])
                    session["status"] = "ready_for_execution"
                    session["plan_created_at"] = datetime.now()
                
                self.logger.info(f"🎯 Plan received for session {session_id}: "
                               f"{len(plan_data.get('steps', []))} steps")
                
            elif message.type == MessageType.PLAN_EXECUTION:
                # 规划执行状态更新
                session_id = message.payload.get("session_id")
                step_id = message.payload.get("step_id")
                status = message.payload.get("status")
                
                if session_id in self._planning_sessions:
                    session = self._planning_sessions[session_id]
                    session["execution_status"][step_id] = {
                        "status": status,
                        "updated_at": datetime.now(),
                        "agent_id": message.from_agent
                    }
                
                self.logger.info(f"🎯 Plan execution update - session: {session_id}, "
                               f"step: {step_id}, status: {status}")
            
            # 添加到规划队列
            self._planning_queue.append(message)
            
            # 发送到目标Agent
            if message.to_agent:
                return await self._send_direct_message(message)
            else:
                return await self._broadcast_message(message)
            
        except Exception as e:
            self.logger.error(f"❌ Planning message handling failed: {e}")
            return False
    
    async def _send_direct_message(self, message: Message) -> bool:
        """发送点对点消息"""
        try:
            target_agent = message.to_agent
            
            if target_agent not in self._agents:
                self.logger.warning(f"⚠️ Target agent not found: {target_agent}")
                return False
            
            if target_agent not in self._message_queues:
                self._message_queues[target_agent] = []
            
            # 根据优先级插入消息
            queue = self._message_queues[target_agent]
            if message.priority == MessagePriority.PLANNING:
                # 规划消息插入到队首
                queue.insert(0, message)
            else:
                # 按优先级插入
                inserted = False
                for i, existing_msg in enumerate(queue):
                    if message.priority.value > existing_msg.priority.value:
                        queue.insert(i, message)
                        inserted = True
                        break
                if not inserted:
                    queue.append(message)
            
            self.logger.debug(f"📨 Message sent to {target_agent}: {message.type.value}")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Direct message send failed: {e}")
            return False
    
    async def _broadcast_message(self, message: Message) -> bool:
        """广播消息到所有Agent"""
        try:
            success_count = 0
            total_count = len(self._agents)
            
            for agent_id in self._agents.keys():
                if agent_id == message.from_agent:
                    continue  # 不发送给自己
                
                broadcast_msg = Message(
                    id=str(uuid.uuid4()),
                    type=message.type,
                    priority=message.priority,
                    from_agent=message.from_agent,
                    to_agent=agent_id,
                    workflow_id=message.workflow_id,
                    payload=message.payload.copy(),
                    timestamp=datetime.now(),
                    correlation_id=message.id
                )
                
                if await self._send_direct_message(broadcast_msg):
                    success_count += 1
            
            self.logger.info(f"📡 Broadcast sent to {success_count}/{total_count} agents")
            return success_count > 0
            
        except Exception as e:
            self.logger.error(f"❌ Broadcast failed: {e}")
            return False
    
    async def get_workflow_coordination_status(self, workflow_id: str) -> Dict[str, Any]:
        """获取工作流协调状态"""
        try:
            # 收集该工作流相关的所有状态信息
            status = {
                "workflow_id": workflow_id,
                "active_agents": [],
                "message_queue_sizes": {},
                "planning_sessions": [],
                "coordination_health": "healthy"
            }
            
            # 查找活跃的Agent
            for agent_id, agent_cap in self._agents.items():
                if agent_cap.status == "available":
                    queue_size = len(self._message_queues.get(agent_id, []))
                    status["active_agents"].append({
                        "agent_id": agent_id,
                        "agent_type": agent_cap.agent_type,
                        "load_factor": agent_cap.load_factor,
                        "planning_capable": agent_cap.planning_capable
                    })
                    status["message_queue_sizes"][agent_id] = queue_size
            
            # 查找相关的规划会话
            for session_id, session in self._planning_sessions.items():
                if session["workflow_id"] == workflow_id:
                    status["planning_sessions"].append({
                        "session_id": session_id,
                        "status": session["status"],
                        "plan_steps_count": len(session.get("plan_steps", [])),
                        "execution_progress": len(session.get("execution_status", {}))
                    })
            
            # 系统健康检查
            total_queue_size = sum(status["message_queue_sizes"].values())
            if total_queue_size > 100:
                status["coordination_health"] = "overloaded"
            elif len(status["active_agents"]) == 0:
                status["coordination_health"] = "no_agents"
            
            return status
            
        except Exception as e:
            self.logger.error(f"❌ Coordination status check failed: {e}")
            return {"workflow_id": workflow_id, "error": str(e)}
    
    async def cleanup_inactive_agents(self, timeout_seconds: int = 300):
        """清理非活跃Agent"""
        try:
            current_time = datetime.now()
            inactive_agents = []
            
            for agent_id, agent_cap in self._agents.items():
                if agent_cap.last_heartbeat:
                    time_diff = (current_time - agent_cap.last_heartbeat).total_seconds()
                    if time_diff > timeout_seconds:
                        inactive_agents.append(agent_id)
            
            for agent_id in inactive_agents:
                self.logger.warning(f"⚠️ Removing inactive agent: {agent_id}")
                del self._agents[agent_id]
                
                # 清理消息队列
                if agent_id in self._message_queues:
                    del self._message_queues[agent_id]
            
            if inactive_agents:
                self.logger.info(f"🧹 Cleaned up {len(inactive_agents)} inactive agents")
            
        except Exception as e:
            self.logger.error(f"❌ Agent cleanup failed: {e}")
    
    def get_system_metrics(self) -> Dict[str, Any]:
        """获取系统指标"""
        try:
            total_messages = sum(self._message_stats.values())
            total_queue_size = sum(len(queue) for queue in self._message_queues.values())
            
            return {
                "registered_agents": len(self._agents),
                "active_agents": len([a for a in self._agents.values() if a.status == "available"]),
                "planning_agents": len([a for a in self._agents.values() if a.planning_capable]),
                "total_messages_processed": total_messages,
                "total_queue_size": total_queue_size,
                "planning_queue_size": len(self._planning_queue),
                "active_planning_sessions": len(self._planning_sessions),
                "message_stats": self._message_stats.copy(),
                "system_status": "healthy" if total_queue_size < 50 else "busy"
            }
            
        except Exception as e:
            self.logger.error(f"❌ System metrics collection failed: {e}")
            return {"error": str(e)}


# 全局通信中心实例
_communication_hub = None


def get_communication_hub() -> CentralCommunicationHub:
    """获取全局通信中心实例"""
    global _communication_hub
    if _communication_hub is None:
        _communication_hub = CentralCommunicationHub()
    return _communication_hub