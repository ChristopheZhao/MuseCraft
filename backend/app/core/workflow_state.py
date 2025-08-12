"""
工作流状态管理器 - Agent执行过程中的内存状态管理
将数据存储和Agent任务解耦，统一在最后进行数据验证和持久化
"""

import json
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from enum import Enum


class WorkflowStatus(Enum):
    INITIALIZING = "initializing"
    CONCEPT_PLANNING = "concept_planning"
    SCRIPT_WRITING = "script_writing"
    IMAGE_GENERATING = "image_generating"
    VIDEO_GENERATING = "video_generating"
    AUDIO_GENERATING = "audio_generating"
    VIDEO_COMPOSING = "video_composing"
    QUALITY_CHECKING = "quality_checking"
    PERSISTING_DATA = "persisting_data"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class SceneData:
    """场景数据结构"""
    scene_number: int
    scene_type: str = "main_content"
    title: str = ""
    description: str = ""
    duration: float = 5.0
    start_time: float = 0.0
    end_time: float = 5.0
    duration_reasoning: str = ""  # 动态时长计算理由
    
    # 概念相关
    visual_description: str = ""
    narrative_description: str = ""
    mood_and_atmosphere: str = ""
    camera_angle: str = "medium shot"
    lighting_style: str = "natural"
    art_style: str = "realistic"
    character_descriptions: List[str] = field(default_factory=list)
    props_and_objects: List[str] = field(default_factory=list)
    color_palette: List[str] = field(default_factory=list)
    
    # 脚本相关
    script_text: str = ""
    voice_over_text: str = ""
    background_music_style: str = ""
    sound_effects: List[str] = field(default_factory=list)
    
    # MAS协作：ScriptWriter为ImageGenerator提供的场景设计
    scene_design_elements: Dict[str, Any] = field(default_factory=dict)  # 新增：场景设计元素
    narrative_structure: Dict[str, Any] = field(default_factory=dict)     # 新增：叙事结构
    audio_design: Dict[str, Any] = field(default_factory=dict)           # 新增：音频设计
    pacing_and_timing: Dict[str, Any] = field(default_factory=dict)      # 新增：节奏时序
    content_development_arc: Dict[str, Any] = field(default_factory=dict) # 保留：内容发展弧线
    
    # 向下兼容：保留旧字段（废弃但保留）
    first_frame_scene_reference: Dict[str, Any] = field(default_factory=dict)  # 废弃
    last_frame_scene_reference: Dict[str, Any] = field(default_factory=dict)   # 废弃
    
    # 图像相关
    image_prompt: str = ""
    image_url: str = ""
    image_path: str = ""
    image_generation_params: Dict[str, Any] = field(default_factory=dict)
    
    # 首尾帧图像 (CogVideoX-3新功能)
    first_frame_url: str = ""
    first_frame_path: str = ""
    last_frame_url: str = ""
    last_frame_path: str = ""
    
    # 视频相关
    video_prompt: str = ""
    video_url: str = ""
    video_path: str = ""
    video_generation_params: Dict[str, Any] = field(default_factory=dict)
    
    # 新增：视频生成模式相关
    video_generation_mode: str = "single_image_with_description"  # 默认新方案
    video_action_description: Dict[str, Any] = field(default_factory=dict)
    
    # 动作描述详细结构（由ImageGenerator生成）
    initial_state_description: str = ""
    action_sequence_description: str = ""
    target_outcome_description: str = ""
    timing_structure_description: str = ""
    complete_video_description: str = ""  # 完整描述，直接用于CogVideoX
    
    # 质量相关
    quality_score: float = 0.0
    quality_issues: List[str] = field(default_factory=list)
    quality_suggestions: List[str] = field(default_factory=list)


@dataclass
class WorkflowState:
    """工作流状态管理"""
    
    # 基本信息
    task_id: str
    user_prompt: str
    video_style: str = "professional"
    duration: int = 30
    aspect_ratio: str = "16:9"
    
    # 状态管理
    status: WorkflowStatus = WorkflowStatus.INITIALIZING
    current_step: str = ""
    progress_percentage: int = 0
    
    # 时间戳
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # 概念规划结果
    concept_plan: Dict[str, Any] = field(default_factory=dict)
    
    # 场景数据
    scenes: List[SceneData] = field(default_factory=list)
    
    # 整体结果
    overall_narrative: str = ""
    estimated_word_count: int = 0
    estimated_reading_time: float = 0.0
    script_themes: List[str] = field(default_factory=list)
    voice_over_instructions: str = ""
    
    # 最终输出
    final_video_path: str = ""
    final_video_url: str = ""
    video_metadata: Dict[str, Any] = field(default_factory=dict)
    composition_timeline: List[Dict[str, Any]] = field(default_factory=list)
    
    # 背景音乐
    background_music_url: str = ""
    background_music_path: str = ""
    background_music_title: str = ""
    background_music_duration: float = 0.0
    background_music_style: str = ""
    background_music_generation_params: Dict[str, Any] = field(default_factory=dict)
    
    # 错误和日志
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    agent_logs: List[Dict[str, Any]] = field(default_factory=list)
    
    # 性能指标
    tokens_used: int = 0
    api_calls_made: int = 0
    estimated_cost: float = 0.0
    processing_time: float = 0.0
    
    def add_scene(self, scene_data: SceneData):
        """添加场景数据"""
        self.scenes.append(scene_data)
    
    def get_scene(self, scene_number: int) -> Optional[SceneData]:
        """获取指定场景"""
        for scene in self.scenes:
            if scene.scene_number == scene_number:
                return scene
        return None
    
    def update_scene(self, scene_number: int, **kwargs):
        """更新场景数据"""
        scene = self.get_scene(scene_number)
        if scene:
            for key, value in kwargs.items():
                if hasattr(scene, key):
                    setattr(scene, key, value)
    
    def set_status(self, status: WorkflowStatus, current_step: str = "", progress: int = 0):
        """更新工作流状态"""
        self.status = status
        self.current_step = current_step
        self.progress_percentage = progress
        
        if status == WorkflowStatus.CONCEPT_PLANNING and not self.started_at:
            self.started_at = datetime.now()
        elif status == WorkflowStatus.COMPLETED:
            self.completed_at = datetime.now()
            if self.started_at:
                self.processing_time = (self.completed_at - self.started_at).total_seconds()
    
    def add_error(self, error: str):
        """添加错误信息"""
        self.errors.append(f"{datetime.now().isoformat()}: {error}")
        if self.status != WorkflowStatus.FAILED:
            self.status = WorkflowStatus.FAILED
    
    def add_warning(self, warning: str):
        """添加警告信息"""
        self.warnings.append(f"{datetime.now().isoformat()}: {warning}")
    
    def log_agent_action(self, agent_name: str, action: str, result: Any, duration: float = 0.0):
        """记录Agent行动"""
        self.agent_logs.append({
            "timestamp": datetime.now().isoformat(),
            "agent": agent_name,
            "action": action,
            "result_type": type(result).__name__,
            "duration": duration,
            "success": True
        })
    
    def log_agent_error(self, agent_name: str, action: str, error: str, duration: float = 0.0):
        """记录Agent错误"""
        self.agent_logs.append({
            "timestamp": datetime.now().isoformat(),
            "agent": agent_name,
            "action": action,
            "error": error,
            "duration": duration,
            "success": False
        })
    
    def update_background_music(
        self, 
        music_url: str = "", 
        music_path: str = "",
        music_title: str = "",
        music_duration: float = 0.0,
        music_style: str = "",
        music_generation_params: Dict[str, Any] = None
    ):
        """更新背景音乐信息"""
        if music_url:
            self.background_music_url = music_url
        if music_path:
            self.background_music_path = music_path
        if music_title:
            self.background_music_title = music_title
        if music_duration > 0:
            self.background_music_duration = music_duration
        if music_style:
            self.background_music_style = music_style
        if music_generation_params:
            self.background_music_generation_params.update(music_generation_params)
    
    def update_tokens(self, tokens: int):
        """更新token使用量"""
        self.tokens_used += tokens
        self.api_calls_made += 1
    
    def is_completed(self) -> bool:
        """检查是否完成"""
        return self.status == WorkflowStatus.COMPLETED
    
    def is_failed(self) -> bool:
        """检查是否失败"""
        return self.status == WorkflowStatus.FAILED
    
    def get_summary(self) -> Dict[str, Any]:
        """获取状态摘要"""
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "current_step": self.current_step,
            "progress_percentage": self.progress_percentage,
            "scenes_count": len(self.scenes),
            "errors_count": len(self.errors),
            "warnings_count": len(self.warnings),
            "tokens_used": self.tokens_used,
            "api_calls_made": self.api_calls_made,
            "estimated_cost": self.estimated_cost,
            "processing_time": self.processing_time,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于序列化）"""
        return {
            "task_id": self.task_id,
            "user_prompt": self.user_prompt,
            "video_style": self.video_style,
            "duration": self.duration,
            "aspect_ratio": self.aspect_ratio,
            "status": self.status.value,
            "current_step": self.current_step,
            "progress_percentage": self.progress_percentage,
            "concept_plan": self.concept_plan,
            "scenes": [scene.__dict__ for scene in self.scenes],
            "overall_narrative": self.overall_narrative,
            "final_video_path": self.final_video_path,
            "final_video_url": self.final_video_url,
            "errors": self.errors,
            "warnings": self.warnings,
            "tokens_used": self.tokens_used,
            "api_calls_made": self.api_calls_made,
            "estimated_cost": self.estimated_cost,
            "processing_time": self.processing_time,
        }


class WorkflowStateManager:
    """工作流状态管理器"""
    
    def __init__(self):
        self._states: Dict[str, WorkflowState] = {}
    
    def create_workflow(self, user_prompt: str, video_style: str = "professional", 
                       duration: int = 30, aspect_ratio: str = "16:9") -> WorkflowState:
        """创建新的工作流状态"""
        task_id = str(uuid.uuid4())
        workflow_state = WorkflowState(
            task_id=task_id,
            user_prompt=user_prompt,
            video_style=video_style,
            duration=duration,
            aspect_ratio=aspect_ratio
        )
        self._states[task_id] = workflow_state
        return workflow_state
    
    def get_workflow(self, task_id: str) -> Optional[WorkflowState]:
        """获取工作流状态"""
        return self._states.get(task_id)
    
    def update_workflow(self, task_id: str, **kwargs) -> bool:
        """更新工作流状态"""
        workflow = self.get_workflow(task_id)
        if workflow:
            for key, value in kwargs.items():
                if hasattr(workflow, key):
                    setattr(workflow, key, value)
            return True
        return False
    
    def remove_workflow(self, task_id: str) -> bool:
        """移除工作流状态"""
        if task_id in self._states:
            del self._states[task_id]
            return True
        return False
    
    def list_workflows(self) -> List[Dict[str, Any]]:
        """列出所有工作流状态摘要"""
        return [workflow.get_summary() for workflow in self._states.values()]
    
    def get_active_workflows(self) -> List[WorkflowState]:
        """获取活跃的工作流"""
        return [
            workflow for workflow in self._states.values()
            if not workflow.is_completed() and not workflow.is_failed()
        ]


# 全局状态管理器实例
workflow_manager = WorkflowStateManager()