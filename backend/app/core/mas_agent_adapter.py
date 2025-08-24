"""
MAS Agent Adapter - 将现有Agent集成到MAS通信架构中
"""
import asyncio
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import logging

from .mas_communication import (
    CentralCommunicationHub, 
    AgentCapability, 
    Message, 
    MessageType, 
    MessagePriority,
    get_communication_hub
)
from ..agents.base import BaseAgent, AgentType


class MASAgentAdapter:
    """
    MAS Agent 适配器
    将现有的BaseAgent适配到多Agent系统通信架构中
    """
    
    def __init__(self, base_agent: BaseAgent):
        self.base_agent = base_agent
        self.communication_hub = get_communication_hub()
        self.agent_id = f"{base_agent.agent_name}_{id(base_agent)}"
        self.is_registered = False
        self.logger = logging.getLogger(f"mas_adapter_{self.agent_id}")
        
        # Agent能力映射
        self.agent_capability = self._create_agent_capability()
    
    def _create_agent_capability(self) -> AgentCapability:
        """基于BaseAgent创建Agent能力描述"""
        
        # 映射Agent类型到能力
        capability_mapping = {
            AgentType.CONCEPT_PLANNER: {
                "capabilities": ["concept_generation", "scene_planning", "requirement_analysis"],
                "planning_capable": True  # 🎯 概念规划Agent具备规划能力
            },
            AgentType.SCRIPT_WRITER: {
                "capabilities": ["script_generation", "narrative_creation", "content_writing"],
                "planning_capable": False
            },
            AgentType.IMAGE_GENERATOR: {
                "capabilities": ["image_generation", "visual_creation", "prompt_processing"],
                "planning_capable": False
            },
            AgentType.VIDEO_GENERATOR: {
                "capabilities": ["video_generation", "motion_creation", "scene_animation"],
                "planning_capable": False
            },
            AgentType.VIDEO_COMPOSER: {
                "capabilities": ["video_composition", "timeline_assembly", "audio_sync"],
                "planning_capable": False
            },
            AgentType.QUALITY_CHECKER: {
                "capabilities": ["quality_analysis", "validation", "compliance_check"],
                "planning_capable": False
            }
        }
        
        agent_info = capability_mapping.get(self.base_agent.agent_type, {
            "capabilities": ["general"],
            "planning_capable": False
        })
        
        return AgentCapability(
            agent_id=self.agent_id,
            agent_type=self.base_agent.agent_type.value,
            capabilities=agent_info["capabilities"],
            tools=list(self.base_agent._available_tools.keys()) if hasattr(self.base_agent, '_available_tools') else [],
            status="available",
            load_factor=0.0,
            last_heartbeat=datetime.now(),
            planning_capable=agent_info["planning_capable"]
        )
    
    async def register_to_mas(self) -> bool:
        """将Agent注册到MAS通信系统"""
        try:
            success = await self.communication_hub.register_agent(self.agent_capability)
            if success:
                self.is_registered = True
                self.logger.info(f"✅ Agent {self.agent_id} registered to MAS")
                
                # 🎯 如果是规划能力Agent，记录规划能力
                if self.agent_capability.planning_capable:
                    self.logger.info(f"🎯 Planning-capable agent registered: {self.agent_id}")
            else:
                self.logger.error(f"❌ Failed to register agent {self.agent_id} to MAS")
            
            return success
            
        except Exception as e:
            self.logger.error(f"❌ MAS registration failed: {e}")
            return False
    
    async def discover_collaborators(
        self, 
        required_capabilities: List[str] = None,
        agent_type: str = None,
        need_planning: bool = False
    ) -> List[AgentCapability]:
        """发现协作Agent"""
        try:
            collaborators = await self.communication_hub.discover_agents(
                capabilities=required_capabilities,
                agent_type=agent_type,
                planning_required=need_planning
            )
            
            # 过滤掉自己
            collaborators = [
                agent for agent in collaborators 
                if agent.agent_id != self.agent_id
            ]
            
            self.logger.info(f"🔍 Discovered {len(collaborators)} collaborators "
                           f"(need_planning={need_planning})")
            
            return collaborators
            
        except Exception as e:
            self.logger.error(f"❌ Collaborator discovery failed: {e}")
            return []
    
    async def send_task_request(
        self, 
        target_agent_id: str,
        task_data: Dict[str, Any],
        workflow_id: str,
        is_planning_task: bool = False
    ) -> bool:
        """发送任务请求"""
        try:
            message_type = MessageType.PLAN_REQUEST if is_planning_task else MessageType.TASK_REQUEST
            priority = MessagePriority.PLANNING if is_planning_task else MessagePriority.NORMAL
            
            message = Message(
                id=f"task_req_{datetime.now().timestamp()}",
                type=message_type,
                priority=priority,
                from_agent=self.agent_id,
                to_agent=target_agent_id,
                workflow_id=workflow_id,
                payload=task_data,
                timestamp=datetime.now()
            )
            
            success = await self.communication_hub.send_message(message)
            
            if success:
                task_type = "planning" if is_planning_task else "regular"
                self.logger.info(f"📤 Sent {task_type} task request to {target_agent_id}")
            
            return success
            
        except Exception as e:
            self.logger.error(f"❌ Task request failed: {e}")
            return False
    
    async def send_task_response(
        self, 
        target_agent_id: str,
        response_data: Dict[str, Any],
        workflow_id: str,
        correlation_id: str = None,
        is_planning_response: bool = False
    ) -> bool:
        """发送任务响应"""
        try:
            message_type = MessageType.PLAN_RESPONSE if is_planning_response else MessageType.TASK_RESPONSE
            priority = MessagePriority.PLANNING if is_planning_response else MessagePriority.NORMAL
            
            message = Message(
                id=f"task_resp_{datetime.now().timestamp()}",
                type=message_type,
                priority=priority,
                from_agent=self.agent_id,
                to_agent=target_agent_id,
                workflow_id=workflow_id,
                payload=response_data,
                timestamp=datetime.now(),
                correlation_id=correlation_id
            )
            
            success = await self.communication_hub.send_message(message)
            
            if success:
                resp_type = "planning" if is_planning_response else "regular"
                self.logger.info(f"📤 Sent {resp_type} task response to {target_agent_id}")
            
            return success
            
        except Exception as e:
            self.logger.error(f"❌ Task response failed: {e}")
            return False
    
    async def receive_messages(
        self, 
        message_types: List[MessageType] = None
    ) -> List[Message]:
        """接收消息"""
        try:
            if not self.is_registered:
                return []
            
            messages = await self.communication_hub.receive_messages(
                agent_id=self.agent_id,
                message_types=message_types
            )
            
            if messages:
                planning_msgs = len([m for m in messages if m.priority == MessagePriority.PLANNING])
                if planning_msgs > 0:
                    self.logger.info(f"📨 Received {len(messages)} messages ({planning_msgs} planning)")
                else:
                    self.logger.debug(f"📨 Received {len(messages)} messages")
            
            return messages
            
        except Exception as e:
            self.logger.error(f"❌ Message receive failed: {e}")
            return []
    
    async def send_heartbeat(self):
        """发送心跳信号"""
        try:
            if self.is_registered:
                self.agent_capability.last_heartbeat = datetime.now()
                
                # 发送状态更新
                status_msg = Message(
                    id=f"heartbeat_{datetime.now().timestamp()}",
                    type=MessageType.STATUS_UPDATE,
                    priority=MessagePriority.LOW,
                    from_agent=self.agent_id,
                    to_agent=None,  # 广播
                    workflow_id="system",
                    payload={
                        "agent_status": {
                            "status": self.agent_capability.status,
                            "load_factor": self.agent_capability.load_factor,
                            "last_heartbeat": self.agent_capability.last_heartbeat.isoformat()
                        }
                    },
                    timestamp=datetime.now()
                )
                
                await self.communication_hub.send_message(status_msg)
                
        except Exception as e:
            self.logger.error(f"❌ Heartbeat failed: {e}")
    
    async def update_load_factor(self, load_factor: float):
        """更新负载因子"""
        try:
            self.agent_capability.load_factor = max(0.0, min(1.0, load_factor))
            await self.send_heartbeat()
            
        except Exception as e:
            self.logger.error(f"❌ Load factor update failed: {e}")
    
    async def request_planning_collaboration(
        self, 
        workflow_id: str,
        planning_request: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """🎯 请求规划协作"""
        try:
            # 发现规划能力Agent
            planning_agents = await self.discover_collaborators(need_planning=True)
            
            if not planning_agents:
                self.logger.warning("🎯 No planning-capable agents available")
                return None
            
            # 选择负载最低的规划Agent
            selected_agent = min(planning_agents, key=lambda x: x.load_factor)
            
            # 发送规划请求
            success = await self.send_task_request(
                target_agent_id=selected_agent.agent_id,
                task_data={
                    "planning_request": planning_request,
                    "requester_capabilities": self.agent_capability.capabilities,
                    "workflow_context": workflow_id
                },
                workflow_id=workflow_id,
                is_planning_task=True
            )
            
            if success:
                self.logger.info(f"🎯 Planning collaboration requested from {selected_agent.agent_id}")
                return {
                    "planning_agent": selected_agent.agent_id,
                    "request_sent": True
                }
            else:
                return None
                
        except Exception as e:
            self.logger.error(f"❌ Planning collaboration request failed: {e}")
            return None
    
    def get_mas_status(self) -> Dict[str, Any]:
        """获取MAS集成状态"""
        return {
            "agent_id": self.agent_id,
            "base_agent_type": self.base_agent.agent_type.value,
            "is_registered": self.is_registered,
            "capabilities": self.agent_capability.capabilities,
            "planning_capable": self.agent_capability.planning_capable,
            "current_status": self.agent_capability.status,
            "load_factor": self.agent_capability.load_factor,
            "tools": self.agent_capability.tools,
            "last_heartbeat": self.agent_capability.last_heartbeat.isoformat() if self.agent_capability.last_heartbeat else None
        }


class MASAgentRegistry:
    """
    MAS Agent 注册表 
    管理所有Agent适配器的生命周期
    """
    
    def __init__(self):
        self._adapters: Dict[str, MASAgentAdapter] = {}
        self.logger = logging.getLogger("mas_agent_registry")
    
    async def register_agent(self, base_agent: BaseAgent) -> MASAgentAdapter:
        """注册BaseAgent到MAS"""
        try:
            # 创建适配器
            adapter = MASAgentAdapter(base_agent)
            
            # 注册到MAS通信系统
            success = await adapter.register_to_mas()
            
            if success:
                self._adapters[adapter.agent_id] = adapter
                self.logger.info(f"✅ Agent {adapter.agent_id} registered to MAS registry")
                return adapter
            else:
                raise Exception("Failed to register to communication hub")
                
        except Exception as e:
            self.logger.error(f"❌ Agent registration failed: {e}")
            raise
    
    async def unregister_agent(self, agent_id: str):
        """注销Agent"""
        if agent_id in self._adapters:
            del self._adapters[agent_id]
            self.logger.info(f"✅ Agent {agent_id} unregistered from MAS")
    
    def get_adapter(self, agent_id: str) -> Optional[MASAgentAdapter]:
        """获取Agent适配器"""
        return self._adapters.get(agent_id)
    
    def get_all_adapters(self) -> List[MASAgentAdapter]:
        """获取所有适配器"""
        return list(self._adapters.values())
    
    async def broadcast_heartbeat(self):
        """广播所有Agent心跳"""
        for adapter in self._adapters.values():
            try:
                await adapter.send_heartbeat()
            except Exception as e:
                self.logger.warning(f"⚠️ Heartbeat failed for {adapter.agent_id}: {e}")
    
    def get_registry_status(self) -> Dict[str, Any]:
        """获取注册表状态"""
        return {
            "total_agents": len(self._adapters),
            "registered_agents": [
                adapter.get_mas_status() 
                for adapter in self._adapters.values()
            ],
            "planning_agents": [
                adapter.agent_id 
                for adapter in self._adapters.values() 
                if adapter.agent_capability.planning_capable
            ]
        }


# 全局Agent注册表
_agent_registry = None


def get_agent_registry() -> MASAgentRegistry:
    """获取全局Agent注册表"""
    global _agent_registry
    if _agent_registry is None:
        _agent_registry = MASAgentRegistry()
    return _agent_registry