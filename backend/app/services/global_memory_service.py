"""Global Memory Service facade with injectable dependencies."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..agents.memory.long_term.stores import MemoryImportance, MemoryItem, MemoryType
from ..agents.memory.managers import (
    MemoryManagement,
    build_memory_management,
    get_default_memory_management,
)
from ..agents.memory.services.long_term import SimpleLongTermMemoryService


class GlobalMemoryService:
    """System-level facade that coordinates shared slots and long-term stores."""

    def __init__(
        self,
        management: MemoryManagement,
        *,
        long_term_service: Optional[SimpleLongTermMemoryService] = None,
    ) -> None:
        self.logger = logging.getLogger("global_memory_service")
        self._management = management
        # 底层 manager 仅供内部使用；对外只暴露受控 long_term 接口
        self._long_term_manager = management.long_term_manager
        self._long_term = long_term_service or SimpleLongTermMemoryService(self._long_term_manager)
        self.workflow_stats: Dict[str, Any] = {}
        self.logger.info("🧠 Global Memory Service initialised with injected management bundle")

    @property
    def long_term(self) -> SimpleLongTermMemoryService:
        """受控长记忆接口，屏蔽底层 LongTermMemoryManager。"""
        return self._long_term

    async def store_creative_guidance(
        self,
        workflow_id: str,
        concept_plan: Dict[str, Any],
        agent_name: str = "concept_planner"
    ) -> bool:
        """
        存储创意指导信息 - 供下游Agent使用
        
        Args:
            workflow_id: 工作流ID
            concept_plan: 概念规划数据
            agent_name: 存储Agent名称
            
        Returns:
            存储成功状态
        """
        try:
            # 存储整体创意指导
            overall_guidance = {
                "agent_role": "Creative Director",
                "workflow_id": workflow_id,
                "creative_vision": concept_plan.get("overview", ""),
                "visual_style_guidance": concept_plan.get("visual_style_guidance", {}),
                "narrative_flow_strategy": concept_plan.get("narrative_flow_strategy", {}),
                "production_guidance": concept_plan.get("production_guidance", {}),
                "agent_collaboration_guidance": concept_plan.get("agent_collaboration_guidance", {}),
                "scenes_overview": len(concept_plan.get("scenes", [])),
                "key_messages": concept_plan.get("key_messages", []),
                "timestamp": datetime.now().isoformat()
            }
            
            overall_memory_id = await self._long_term.store_memory(
                content=overall_guidance,
                memory_type=MemoryType.CONCEPTUAL,
                importance=MemoryImportance.HIGH,
                tags=["creative_direction", "visual_guidance", "team_coordination"],
                agent_id=agent_name,
                task_id=workflow_id,
                metadata={
                    "workflow_id": workflow_id,
                    "content_type": "creative_direction",
                    "agent_type": agent_name
                }
            )
            
            # 存储每个场景的具体指导
            scene_memory_ids = []
            scenes = concept_plan.get("scenes", [])
            
            for scene in scenes:
                scene_guidance = {
                    "agent_role": "Creative Director - Scene Design",
                    "scene_number": scene.get("scene_number"),
                    "workflow_id": workflow_id,
                    "creative_intent": scene.get("creative_intent", ""),
                    "visual_direction": scene.get("visual_direction", ""),
                    "narrative_direction": scene.get("narrative_direction", ""),
                    "mood_target": scene.get("mood_target", ""),
                    "visual_priorities": scene.get("visual_priorities", []),
                    "camera_strategy": scene.get("camera_strategy", ""),
                    "lighting_mood": scene.get("lighting_mood", ""),
                    "continuity_notes": scene.get("continuity_notes", ""),
                    "context": {
                        "duration": scene.get("final_duration", scene.get("duration", 0)),
                        "duration_reasoning": scene.get("duration_reasoning", ""),
                        "scene_type": scene.get("scene_type", ""),
                        "title": scene.get("title", ""),
                        "complexity_analysis": scene.get("complexity_analysis", {}),
                        "suggested_duration": scene.get("suggested_duration", 0)
                    },
                    "timestamp": datetime.now().isoformat()
                }
                
                scene_memory_id = await self._long_term.store_memory(
                    content=scene_guidance,
                    memory_type=MemoryType.EPISODIC,
                    importance=MemoryImportance.MEDIUM,
                    tags=["scene_design", "creative_guidance", f"scene_{scene.get('scene_number')}"],
                    agent_id=agent_name,
                    task_id=workflow_id,
                    metadata={
                        "workflow_id": workflow_id,
                        "scene_number": scene.get("scene_number"),
                        "content_type": "scene_guidance",
                        "agent_type": agent_name
                    }
                )
                scene_memory_ids.append(scene_memory_id)
            
            # 更新统计
            self.workflow_stats[workflow_id] = {
                "overall_memory_id": overall_memory_id,
                "scene_memory_ids": scene_memory_ids,
                "scenes_count": len(scenes),
                "stored_at": datetime.now().isoformat()
            }
            
            self.logger.info(f"✅ Creative guidance stored for workflow {workflow_id}: {len(scenes)} scenes")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to store creative guidance for workflow {workflow_id}: {e}")
            return False
    
    async def retrieve_creative_guidance(
        self,
        workflow_id: str,
        scene_number: Optional[int] = None,
        agent_name: str = None
    ) -> Dict[str, Any]:
        """
        检索创意指导信息
        
        Args:
            workflow_id: 工作流ID
            scene_number: 场景编号（可选，获取特定场景指导）
            agent_name: 请求Agent名称（用于日志）
            
        Returns:
            创意指导信息
        """
        try:
            guidance = {
                "overall_guidance": {},
                "scene_guidance": {},
                "has_guidance": False
            }
            
            # 检索整体创意指导
            overall_memories = await self._long_term.retrieve_memories(
                tags=["creative_direction", "visual_guidance"],
                memory_type=MemoryType.CONCEPTUAL,
                task_id=workflow_id,
                limit=1
            )
            
            if overall_memories:
                guidance["overall_guidance"] = overall_memories[0].content
                guidance["has_guidance"] = True
                self.logger.debug(f"📖 Retrieved overall guidance for workflow {workflow_id}")
            
            # 检索特定场景指导（如果指定了场景编号）
            if scene_number is not None:
                scene_memories = await self._long_term.retrieve_memories(
                    tags=["scene_design", f"scene_{scene_number}"],
                    memory_type=MemoryType.EPISODIC,
                    task_id=workflow_id,
                    limit=1
                )
                
                if scene_memories:
                    guidance["scene_guidance"] = scene_memories[0].content
                    guidance["has_guidance"] = True
                    self.logger.debug(f"📖 Retrieved scene {scene_number} guidance for workflow {workflow_id}")
            
            if not guidance["has_guidance"]:
                self.logger.warning(f"⚠️ No creative guidance found for workflow {workflow_id}, scene {scene_number}")
            
            return guidance
            
        except Exception as e:
            self.logger.error(f"❌ Failed to retrieve creative guidance for workflow {workflow_id}: {e}")
            return {"overall_guidance": {}, "scene_guidance": {}, "has_guidance": False}
    
    async def store_scene_references(
        self,
        workflow_id: str,
        scene_number: int,
        scene_references: Dict[str, Any],
        agent_name: str = "script_writer"
    ) -> bool:
        """
        存储ScriptWriter生成的场景参考数据
        
        Args:
            workflow_id: 工作流ID
            scene_number: 场景编号
            scene_references: 场景参考数据（包含首尾帧参考和内容发展）
            agent_name: 存储Agent名称
            
        Returns:
            存储成功状态
        """
        try:
            scene_ref_data = {
                "agent_role": "Script Writer - Scene References",
                "workflow_id": workflow_id,
                "scene_number": scene_number,
                "first_frame_scene_reference": scene_references.get("first_frame_scene_reference", {}),
                "last_frame_scene_reference": scene_references.get("last_frame_scene_reference", {}),
                "content_development_arc": scene_references.get("content_development_arc", {}),
                "script_text": scene_references.get("script_text", ""),
                "voice_over_text": scene_references.get("voice_over_text", ""),
                "timestamp": datetime.now().isoformat()
            }
            
            memory_id = await self._long_term.store_memory(
                content=scene_ref_data,
                memory_type=MemoryType.EPISODIC,
                importance=MemoryImportance.HIGH,
                tags=["scene_references", f"scene_{scene_number}", "script_writer", "mas_collaboration"],
                agent_id=agent_name,
                task_id=workflow_id,
                metadata={
                    "workflow_id": workflow_id,
                    "scene_number": scene_number,
                    "content_type": "scene_references",
                    "agent_type": agent_name
                }
            )
            
            self.logger.info(f"✅ Scene references stored for workflow {workflow_id}, scene {scene_number}")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to store scene references: {e}")
            return False
    
    async def retrieve_scene_references(
        self,
        workflow_id: str,
        scene_number: int,
        agent_name: str = None
    ) -> Dict[str, Any]:
        """
        检索ScriptWriter的场景参考数据
        
        Args:
            workflow_id: 工作流ID
            scene_number: 场景编号
            agent_name: 请求Agent名称（用于日志）
            
        Returns:
            场景参考数据
        """
        try:
            scene_ref_memories = await self._long_term.retrieve_memories(
                tags=["scene_references", f"scene_{scene_number}"],
                memory_type=MemoryType.EPISODIC,
                task_id=workflow_id,
                limit=1
            )
            
            if scene_ref_memories:
                self.logger.debug(f"📖 Retrieved scene references for workflow {workflow_id}, scene {scene_number}")
                return scene_ref_memories[0].content
            else:
                self.logger.debug(f"📭 No scene references found for workflow {workflow_id}, scene {scene_number}")
                return {}
                
        except Exception as e:
            self.logger.error(f"❌ Failed to retrieve scene references: {e}")
            return {}
    
    async def retrieve_motion_guidance(
        self,
        workflow_id: str,
        scene_number: int,
        agent_name: str = "video_generator"
    ) -> Dict[str, Any]:
        """
        检索动作指导信息（为VideoGenerator特化）
        
        Args:
            workflow_id: 工作流ID
            scene_number: 场景编号
            agent_name: 请求Agent名称
            
        Returns:
            动作指导信息
        """
        try:
            # 获取基础创意指导
            base_guidance = await self.retrieve_creative_guidance(workflow_id, scene_number, agent_name)
            
            # 扩展为动作指导格式
            motion_guidance = {
                "overall_guidance": base_guidance.get("overall_guidance", {}),
                "scene_guidance": base_guidance.get("scene_guidance", {}),
                "previous_scene": {},
                "next_scene": {},
                "has_guidance": base_guidance.get("has_guidance", False)
            }
            
            # 检索相邻场景信息用于动作衔接
            if scene_number > 1:
                prev_guidance = await self.retrieve_creative_guidance(workflow_id, scene_number - 1, agent_name)
                motion_guidance["previous_scene"] = prev_guidance.get("scene_guidance", {})
            
            # 尝试获取下一场景（假设存在）
            next_guidance = await self.retrieve_creative_guidance(workflow_id, scene_number + 1, agent_name)
            motion_guidance["next_scene"] = next_guidance.get("scene_guidance", {})
            
            return motion_guidance
            
        except Exception as e:
            self.logger.error(f"❌ Failed to retrieve motion guidance for workflow {workflow_id}, scene {scene_number}: {e}")
            return {"overall_guidance": {}, "scene_guidance": {}, "previous_scene": {}, "next_scene": {}, "has_guidance": False}
    
    async def get_workflow_memory_stats(self, workflow_id: str) -> Dict[str, Any]:
        """获取工作流记忆统计信息"""
        try:
            # 从memory manager获取统计
            memory_stats = await self._long_term.get_memory_stats()
            
            # 组合工作流特定统计
            workflow_specific = self.workflow_stats.get(workflow_id, {})
            
            return {
                "workflow_id": workflow_id,
                "workflow_specific": workflow_specific,
                "global_memory_stats": memory_stats,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"❌ Failed to get memory stats for workflow {workflow_id}: {e}")
            return {"error": str(e)}
    
    async def cleanup_workflow_memory(self, workflow_id: str) -> bool:
        """清理指定工作流的记忆（可选，用于资源管理）"""
        try:
            # 暂时不实现自动清理，保持记忆供调试使用
            self.logger.info(f"🧹 Memory cleanup requested for workflow {workflow_id} (not implemented)")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to cleanup memory for workflow {workflow_id}: {e}")
            return False


def create_global_memory_service(
    *,
    management: Optional[MemoryManagement] = None,
    slots_path: Optional[Path | str] = None,
    backend: Optional[str] = None,
) -> GlobalMemoryService:
    """Factory helper to build a service with explicit dependencies."""

    if management is None:
        if slots_path is not None or backend is not None:
            path_arg: Optional[Path]
            if isinstance(slots_path, Path):
                path_arg = slots_path
            elif slots_path is not None:
                path_arg = Path(slots_path)
            else:
                path_arg = None
            management = build_memory_management(
                slots_path=path_arg,
                storage_backend=backend,
            )
        else:
            management = get_default_memory_management()
    return GlobalMemoryService(management)


__all__ = ["GlobalMemoryService", "create_global_memory_service"]
