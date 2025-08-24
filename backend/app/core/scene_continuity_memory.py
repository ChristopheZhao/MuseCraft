"""
Scene Continuity Memory System - 解耦的场景连续性内存管理
"""
import asyncio
import json
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from pathlib import Path
import logging

from .workflow_state import SceneData


@dataclass
class ContinuityMapping:
    """连续性映射信息"""
    current_scene: int
    previous_scene: int
    reason: str
    confidence: float
    created_at: str
    

class SceneContinuityMemory:
    """
    场景连续性内存管理器 - 负责存储和管理场景间的连续性信息
    
    功能：
    1. 记录哪些场景需要使用前一场景的最后一帧
    2. 存储场景最后一帧的文件路径
    3. 提供解耦的查询接口
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._continuity_mappings: Dict[int, ContinuityMapping] = {}
        self._scene_final_frames: Dict[int, str] = {}
        
    async def mark_scene_continuity(
        self, 
        current_scene_number: int, 
        previous_scene_number: int,
        reason: str,
        confidence: float = 0.8
    ) -> None:
        """
        标记场景连续性需求
        
        Args:
            current_scene_number: 当前场景号
            previous_scene_number: 需要连续的前一场景号  
            reason: 连续性原因
            confidence: 连续性置信度
        """
        from datetime import datetime
        
        mapping = ContinuityMapping(
            current_scene=current_scene_number,
            previous_scene=previous_scene_number,
            reason=reason,
            confidence=confidence,
            created_at=datetime.now().isoformat()
        )
        
        self._continuity_mappings[current_scene_number] = mapping
        
        self.logger.info(
            f"🔗 Scene Continuity Marked: Scene {current_scene_number} "
            f"continues from Scene {previous_scene_number} "
            f"(reason: {reason}, confidence: {confidence})"
        )
    
    async def store_scene_final_frame(self, scene_number: int, frame_data: str) -> None:
        """
        存储场景的最后一帧数据（可能是文件路径、URL或base64数据）
        
        Args:
            scene_number: 场景号
            frame_data: 最后一帧的数据（文件路径、URL或base64编码）
        """
        self._scene_final_frames[scene_number] = frame_data
        
        # 确定数据类型并格式化日志显示
        if frame_data.startswith("data:image"):
            data_type = "base64"
            # 只显示数据类型，不打印完整base64内容
            display_info = f"base64 image data ({len(frame_data)} chars)"
        elif frame_data.startswith("http"):
            data_type = "URL"
            display_info = frame_data
        else:
            data_type = "file_path"
            display_info = frame_data
        
        self.logger.info(
            f"💾 Scene Final Frame Stored ({data_type}): Scene {scene_number} → {display_info}"
        )
    
    async def requires_continuity_from(self, scene_number: int) -> Optional[ContinuityMapping]:
        """
        检查指定场景是否需要从前一场景继续
        
        Args:
            scene_number: 要检查的场景号
            
        Returns:
            如果需要连续性，返回ContinuityMapping，否则返回None
        """
        return self._continuity_mappings.get(scene_number)
    
    async def get_previous_scene_final_frame(self, scene_number: int) -> Optional[str]:
        """
        获取前一场景的最后一帧路径
        
        Args:
            scene_number: 前一场景号
            
        Returns:
            最后一帧的文件路径，如果不存在返回None
        """
        frame_data = self._scene_final_frames.get(scene_number)
        
        if not frame_data:
            return None
            
        # 检查数据类型: Base64 vs 文件路径
        if frame_data.startswith("data:image"):
            # Base64 数据 - 直接返回，不检查文件存在性
            self.logger.info(f"Retrieved base64 frame data for scene {scene_number} ({len(frame_data)} chars)")
            return frame_data
        elif frame_data.startswith("http"):
            # URL 数据 - 直接返回
            self.logger.info(f"Retrieved URL frame data for scene {scene_number}: {frame_data[:50]}...")
            return frame_data
        else:
            # 文件路径 - 检查存在性
            try:
                if Path(frame_data).exists():
                    self.logger.info(f"Retrieved file path for scene {scene_number}: {frame_data}")
                    return frame_data
                else:
                    self.logger.warning(f"Scene {scene_number} final frame file missing: {frame_data}")
                    return None
            except OSError as e:
                # 处理 "File name too long" 等文件系统错误
                self.logger.error(f"Invalid file path for scene {scene_number}: {e}")
                return None
    
    async def get_scene_continuity_info(self, scene_number: int) -> Dict[str, Any]:
        """
        获取场景的完整连续性信息
        
        Args:
            scene_number: 场景号
            
        Returns:
            包含连续性信息的字典
        """
        continuity = await self.requires_continuity_from(scene_number)
        
        if not continuity:
            return {
                "requires_continuity": False,
                "from_scene": None,
                "reason": "",
                "previous_frame_available": False
            }
        
        previous_frame = await self.get_previous_scene_final_frame(continuity.previous_scene)
        
        return {
            "requires_continuity": True,
            "from_scene": continuity.previous_scene,
            "reason": continuity.reason,
            "confidence": continuity.confidence,
            "previous_frame_available": previous_frame is not None,
            "previous_frame_path": previous_frame,
            "created_at": continuity.created_at
        }
    
    async def list_continuity_chains(self) -> List[Dict[str, Any]]:
        """
        列出所有连续性链条
        
        Returns:
            连续性链条列表
        """
        chains = []
        for scene_num, mapping in self._continuity_mappings.items():
            info = await self.get_scene_continuity_info(scene_num)
            chains.append({
                "scene": scene_num,
                "continues_from": mapping.previous_scene,
                "reason": mapping.reason,
                "confidence": mapping.confidence,
                "frame_available": info["previous_frame_available"]
            })
        
        return sorted(chains, key=lambda x: x["scene"])
    
    async def clear_scene_continuity(self, scene_number: int) -> None:
        """
        清除指定场景的连续性标记
        
        Args:
            scene_number: 场景号
        """
        if scene_number in self._continuity_mappings:
            del self._continuity_mappings[scene_number]
            self.logger.info(f"🗑️  Cleared continuity mapping for Scene {scene_number}")
    
    async def clear_all(self) -> None:
        """清除所有连续性信息"""
        self._continuity_mappings.clear()
        self._scene_final_frames.clear()
        self.logger.info("🗑️  Cleared all scene continuity data")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取连续性统计信息"""
        return {
            "total_continuity_mappings": len(self._continuity_mappings),
            "total_stored_frames": len(self._scene_final_frames),
            "scenes_with_continuity": list(self._continuity_mappings.keys()),
            "scenes_with_frames": list(self._scene_final_frames.keys())
        }


# 全局单例实例
_scene_continuity_memory = None

def get_scene_continuity_memory() -> SceneContinuityMemory:
    """获取全局场景连续性内存实例"""
    global _scene_continuity_memory
    if _scene_continuity_memory is None:
        _scene_continuity_memory = SceneContinuityMemory()
    return _scene_continuity_memory