"""
数据持久化服务 - 统一的数据验证和存储服务
将工作流执行期间的内存状态最终持久化到数据库

采用混合方案：
1. 快速解决当前数据库中断问题
2. 为未来MAS架构预留接口设计
"""

import json
from datetime import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, DataError

from ..core.workflow_state import WorkflowState, SceneData, WorkflowStatus
from ..models import Task, Scene, Resource, AgentType, ResourceType, SceneType, TaskType, TaskStatus
from ..core.config import settings
from ..agents.memory.long_term.snapshots import export_shared_wm_snapshot
from ..services.memory_provider import MemoryServices


class DataValidationError(Exception):
    """数据验证错误"""
    pass


class DataPersistenceService:
    """
    数据持久化服务
    
    设计原则：
    1. 快速解决当前问题：统一数据验证和持久化
    2. MAS兼容性：支持Agent间状态共享和通信
    """
    
    def __init__(self, memory_services: MemoryServices):
        self.logger = self._get_logger()
        if memory_services is None:
            raise ValueError("memory_services is required for DataPersistenceService")
        self._memory_services = memory_services

    def _get_logger(self):
        import logging
        return logging.getLogger(__name__)

    def _resolve_voice_resource_type(self) -> ResourceType:
        """Return a resource type supported by the current DB enum definition."""
        try:
            enum_values = getattr(Resource.__table__.c.resource_type.type, "enums", [])
        except Exception:
            enum_values = []

        if ResourceType.VOICE_OVER.value in enum_values:
            return ResourceType.VOICE_OVER

        # 向后兼容未添加 voice_over 的数据库枚举
        return ResourceType.AUDIO

    async def persist_workflow_results(self, workflow_state: WorkflowState, db: Session) -> Dict[str, Any]:
        """
        将工作流状态持久化到数据库
        
        Args:
            workflow_state: 工作流状态对象
            db: 数据库会话
            
        Returns:
            持久化结果摘要
        """
        
        self.logger.info(f"🗄️ 开始持久化工作流 {workflow_state.task_id} 的数据")
        
        try:
            # 1. 数据验证和清理
            validated_state = await self._validate_and_clean_data(workflow_state)
            
            # 2. 持久化任务
            task = await self._persist_task(validated_state, db)
            
            # 3. 持久化场景
            scene_results = await self._persist_scenes(task, validated_state, db)
            
            # 4. 持久化资源
            resource_results = await self._persist_resources(task, validated_state, db)
            
            # 5. 最终状态
            await self._finalize_task_status(task, validated_state, db)
            
            # 6. 提交事务
            db.commit()
            
            summary = {
                "task_id": task.id,
                "external_task_id": validated_state.task_id,
                "status": "success",
                "scenes_persisted": len(scene_results),
                "resources_persisted": len(resource_results),
                "agent_logs_persisted": 0,
                "warnings": validated_state.warnings,
                "persistence_time": datetime.now().isoformat()
            }
            
            self.logger.info(f"✅ 工作流 {workflow_state.task_id} 数据持久化成功")
            return summary
            
        except Exception as e:
            self.logger.error(f"❌ 工作流 {workflow_state.task_id} 数据持久化失败: {str(e)}")
            db.rollback()
            
            workflow_state.add_error(f"数据持久化失败: {str(e)}")
            
            return {
                "task_id": workflow_state.task_id,
                "status": "failed", 
                "error": str(e),
                "persistence_time": datetime.now().isoformat()
            }

    async def persist_from_mas_wm(self, task_id: str, db: Session) -> Dict[str, Any]:
        """Persist results by reading snapshot from MAS WorkingMemory (facts/scene_outputs)."""
        self.logger.info(f"🗄️ 开始基于 MAS WM 持久化任务 {task_id} 的数据")
        try:
            snapshot = export_shared_wm_snapshot(
                task_id,
                memory_services=self._memory_services,
                short_term_service=getattr(self._memory_services, "short_term", None),
            )
            task = await self._persist_task_from_snapshot(snapshot, db)
            scene_results = await self._persist_scenes_from_snapshot(task, snapshot, db)
            resource_results = await self._persist_resources_from_snapshot(task, snapshot, db)
            resource_results += await self._persist_task_level_resources_from_snapshot(task, snapshot, db)
            db.commit()
            return {
                "task_id": task.id,
                "external_task_id": task_id,
                "status": "success",
                "scenes_persisted": len(scene_results),
                "resources_persisted": len(resource_results),
                "persistence_time": datetime.now().isoformat(),
            }
        except Exception as e:
            db.rollback()
            self.logger.error(f"❌ 基于 MAS WM 的数据持久化失败: {e}")
            return {
                "task_id": task_id,
                "status": "failed",
                "error": str(e),
                "persistence_time": datetime.now().isoformat(),
            }

    async def _persist_task_from_snapshot(
        self,
        snapshot: Dict[str, Any],
        db: Session,
    ) -> Task:
        ext_id = str(snapshot.get("task_id") or "")
        facts = snapshot.get("facts") or {}
        concept_plan = facts.get("concept_plan", {}) if isinstance(facts, dict) else {}
        voice_plan = facts.get("voice_plan", {}) if isinstance(facts, dict) else {}
        intelligent_style_design = {}
        content_elements = {}
        if isinstance(concept_plan, dict):
            intelligent_style_design = concept_plan.get("intelligent_style_design", {}) or {}
            content_elements = concept_plan.get("content_elements", {}) or {}
        # upsert task by external task_id
        task = db.query(Task).filter(Task.task_id == ext_id).first()
        if not task:
            task = Task(
                task_id=ext_id,
                title="Short Video Task",
                description="",
                task_type=TaskType.VIDEO_GENERATION,
                status=TaskStatus.PERSISTING,
                progress_percentage=90,
                current_step="Persisting data",
                input_parameters={
                    "intelligent_style_design": intelligent_style_design,
                    "voice_plan": voice_plan,
                    "content_elements": content_elements,
                },
            )
            db.add(task)
            db.flush()
        # output metadata
        if hasattr(task, "output_metadata"):
            task.output_metadata = {
                "concept_plan": concept_plan,
                "intelligent_style_design": intelligent_style_design,
                "voice_plan": voice_plan,
                "content_elements": content_elements,
            }
        db.flush()
        return task

    async def _persist_scenes_from_snapshot(self, task: Task, snapshot: Dict[str, Any], db: Session) -> List[Dict[str, Any]]:
        scenes = snapshot.get("scenes") or []
        results: List[Dict[str, Any]] = []
        self.logger.info(f"🎬 基于 MAS WM 持久化 {len(scenes)} 个场景")
        for sd in scenes:
            if not isinstance(sd, dict):
                continue
            sn = sd.get("scene_number")
            if sn is None:
                continue
            existing = db.query(Scene).filter(Scene.task_id == task.id, Scene.scene_number == sn).first()
            if existing:
                scene = existing
                status = "updated"
            else:
                scene = Scene(task_id=task.id, scene_number=sn)
                db.add(scene)
                status = "created"
            self._update_scene_from_snapshot_dict(scene, sd)
            db.flush()
            results.append({"scene_id": scene.id, "scene_number": scene.scene_number, "status": status})
        return results

    async def _persist_resources_from_snapshot(self, task: Task, snapshot: Dict[str, Any], db: Session) -> List[Dict[str, Any]]:
        scenes = snapshot.get("scenes") or []
        results: List[Dict[str, Any]] = []
        for sd in scenes:
            if not isinstance(sd, dict):
                continue
            sn = sd.get("scene_number")
            if sn is None:
                continue
            scene = db.query(Scene).filter(Scene.task_id == task.id, Scene.scene_number == sn).first()
            if not scene:
                continue
            # video resource
            vu = (sd.get("video_url") or "") if isinstance(sd.get("video_url"), str) else ""
            vp = (sd.get("video_path") or "") if isinstance(sd.get("video_path"), str) else ""
            if vu or vp:
                try:
                    res = Resource(
                        task_id=task.id,
                        scene_id=scene.id,
                        filename=f"scene_{sn}_video.{(vp or 'mp4').split('.')[-1]}",
                        file_path=vp or "",
                        file_url=vu or None,
                        resource_type=ResourceType.VIDEO,
                        generation_parameters=sd.get("video_generation_params", {}),
                        processing_status="completed" if (vp or vu) else "pending",
                        is_generated=True,
                    )
                    db.add(res)
                    results.append({"type": "video", "scene": sn, "status": "created"})
                except Exception as e:
                    self.logger.error(f"❌ 视频资源持久化失败: {e}")
            # voice resource
            vu2 = (sd.get("voice_over_audio_url") or "") if isinstance(sd.get("voice_over_audio_url"), str) else ""
            vp2 = (sd.get("voice_over_audio_path") or "") if isinstance(sd.get("voice_over_audio_path"), str) else ""
            if vu2 or vp2:
                try:
                    res = Resource(
                        task_id=task.id,
                        scene_id=scene.id,
                        filename=f"scene_{sn}_voice.{(vp2 or 'wav').split('.')[-1]}",
                        file_path=vp2 or "",
                        file_url=vu2 or None,
                        resource_type=self._resolve_voice_resource_type(),
                        generation_parameters=sd.get("voice_over_audio_metadata", {}),
                        processing_status="completed" if (vp2 or vu2) else "pending",
                        is_generated=True,
                    )
                    db.add(res)
                    results.append({"type": "voice_over", "scene": sn, "status": "created"})
                except Exception as e:
                    self.logger.error(f"❌ 配音资源持久化失败: {e}")
        return results

    async def _persist_task_level_resources_from_snapshot(self, task: Task, snapshot: Dict[str, Any], db: Session) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        final_video = snapshot.get("final_video") or {}
        if isinstance(final_video, dict):
            path = final_video.get("path") or ""
            url = final_video.get("url") or ""
            if path or url:
                try:
                    res = Resource(
                        task_id=task.id,
                        scene_id=None,
                        filename=(path or url).split("/")[-1] or "final_video.mp4",
                        file_path=path or "",
                        file_url=url or None,
                        resource_type=ResourceType.VIDEO,
                        processing_status="completed" if (path or url) else "pending",
                        is_generated=True,
                        is_final_output=True,
                        generation_parameters={"mix": final_video.get("mix")},
                        storage_provider=(final_video.get("storage") or {}).get("provider", "local"),
                    )
                    db.add(res)
                    results.append({"type": "final_video", "status": "created"})
                except Exception as e:
                    self.logger.error(f"❌ Final video persistence failed: {e}")
        return results

    def _update_scene_from_snapshot_dict(self, scene: Scene, d: Dict[str, Any]) -> None:
        # type-safe mapping with defaults
        def _s(key: str) -> str:
            v = d.get(key)
            return v if isinstance(v, str) else (str(v) if v is not None else "")
        def _f(key: str, default: float = 0.0) -> float:
            try:
                return float(d.get(key, default) or default)
            except Exception:
                return default

        scene.scene_type = SceneType.MAIN_CONTENT
        scene.title = _s("title")
        scene.description = _s("description")
        scene.duration = _f("duration", 0.0)
        scene.start_time = _f("start_time", 0.0)
        scene.end_time = _f("end_time", scene.start_time + scene.duration)

        scene.visual_description = _s("visual_description")
        scene.narrative_description = _s("narrative_description")
        scene.mood_and_atmosphere = _s("mood_and_atmosphere")
        scene.camera_angle = _s("camera_angle")
        scene.lighting_style = _s("lighting_style")
        scene.art_style = _s("art_style")

        scene.script_text = _s("script_text")
        scene.voice_over_text = _s("voice_over_text")
    
    async def _validate_and_clean_data(self, workflow_state: WorkflowState) -> WorkflowState:
        """验证和清理工作流数据 - 防止数据库字段长度错误"""
        
        self.logger.info("🔍 验证和清理工作流数据...")
        
        # 清理主要字段
        workflow_state.user_prompt = self._safe_truncate(workflow_state.user_prompt, 1000)
        workflow_state.style_preference = self._safe_truncate(workflow_state.style_preference, 200)  # 🔧 修复: 使用style_preference替换video_style
        workflow_state.aspect_ratio = self._safe_truncate(workflow_state.aspect_ratio, 10)
        workflow_state.current_step = self._safe_truncate(workflow_state.current_step, 90)  # 修复为合适的长度
        workflow_state.overall_narrative = self._safe_truncate(workflow_state.overall_narrative, 2000)
        workflow_state.voice_over_instructions = self._safe_truncate(workflow_state.voice_over_instructions, 1000)
        workflow_state.final_video_path = self._safe_truncate(workflow_state.final_video_path, 500)
        workflow_state.final_video_url = self._safe_truncate(workflow_state.final_video_url, 500)
        
        # 清理场景数据
        for scene in workflow_state.scenes:
            self._clean_scene_data(scene)
        
        # 基本验证
        if not workflow_state.user_prompt.strip():
            raise DataValidationError("用户提示词不能为空")
        
        # 创建默认场景（如果没有）
        if not workflow_state.scenes:
            workflow_state.add_warning("没有场景数据，创建默认场景")
            default_scene = SceneData(
                scene_number=1,
                title="默认场景",
                description=workflow_state.user_prompt[:200],
                duration=float(workflow_state.duration)
            )
            workflow_state.add_scene(default_scene)
        
        # 数值范围验证
        workflow_state.duration = max(5, min(workflow_state.duration, 300))
        workflow_state.progress_percentage = max(0, min(workflow_state.progress_percentage, 100))
        
        self.logger.info(f"✅ 数据验证完成，场景数: {len(workflow_state.scenes)}")
        return workflow_state
    
    def _clean_scene_data(self, scene: SceneData):
        """清理场景数据字段长度"""
        
        # 字符串字段清理
        scene.title = self._safe_truncate(scene.title, 200)
        scene.description = self._safe_truncate(scene.description, 1000)
        scene.visual_description = self._safe_truncate(scene.visual_description, 1000)
        scene.narrative_description = self._safe_truncate(scene.narrative_description, 1000)
        scene.mood_and_atmosphere = self._safe_truncate(scene.mood_and_atmosphere, 200)
        scene.camera_angle = self._safe_truncate(scene.camera_angle, 100)
        scene.lighting_style = self._safe_truncate(scene.lighting_style, 100)
        scene.art_style = self._safe_truncate(scene.art_style, 100)
        scene.script_text = self._safe_truncate(scene.script_text, 2000)
        scene.voice_over_text = self._safe_truncate(scene.voice_over_text, 2000)
        scene.background_music_style = self._safe_truncate(scene.background_music_style, 100)  # 关键修复
        scene.voice_over_audio_path = self._safe_truncate(scene.voice_over_audio_path, 500)
        scene.voice_over_audio_url = self._safe_truncate(scene.voice_over_audio_url, 500)
        scene.image_prompt = self._safe_truncate(scene.image_prompt, 1000)
        scene.image_url = self._safe_truncate(scene.image_url, 500)
        scene.image_path = self._safe_truncate(scene.image_path, 500)
        scene.video_prompt = self._safe_truncate(scene.video_prompt, 1000)
        scene.video_url = self._safe_truncate(scene.video_url, 500)
        scene.video_path = self._safe_truncate(scene.video_path, 500)
        
        # 列表字段清理
        scene.character_descriptions = self._safe_truncate_list(scene.character_descriptions, 10, 200)
        scene.props_and_objects = self._safe_truncate_list(scene.props_and_objects, 20, 100)
        scene.color_palette = self._safe_truncate_list(scene.color_palette, 10, 50)
        scene.sound_effects = self._safe_truncate_list(scene.sound_effects, 15, 100)
        scene.quality_issues = self._safe_truncate_list(scene.quality_issues, 20, 200)
        scene.quality_suggestions = self._safe_truncate_list(scene.quality_suggestions, 10, 200)
        if isinstance(scene.voice_over_audio_metadata, dict) and len(scene.voice_over_audio_metadata) > 50:
            scene.voice_over_audio_metadata = dict(list(scene.voice_over_audio_metadata.items())[:50])
        
        # 数值验证
        scene.duration = max(1.0, min(scene.duration, 60.0))
        scene.start_time = max(0.0, scene.start_time)
        scene.end_time = max(scene.start_time + 1.0, scene.end_time)
        scene.quality_score = max(0.0, min(scene.quality_score, 10.0))
    
    def _safe_truncate(self, value: str, max_length: int) -> str:
        """安全截断字符串"""
        if not value:
            return ""
        
        value = str(value)
        if len(value) <= max_length:
            return value
        
        return value[:max_length-3] + "..."
    
    def _safe_truncate_list(self, value: List[str], max_items: int, max_item_length: int) -> List[str]:
        """安全截断列表"""
        if not value:
            return []
        
        truncated_list = value[:max_items]
        return [self._safe_truncate(item, max_item_length) for item in truncated_list]
    
    def _map_workflow_to_task_status(self, workflow_status: WorkflowStatus) -> TaskStatus:
        """映射 WorkflowStatus 到 TaskStatus"""
        mapping = {
            WorkflowStatus.INITIALIZING: TaskStatus.PENDING,
            WorkflowStatus.CONCEPT_PLANNING: TaskStatus.IN_PROGRESS,
            WorkflowStatus.SCRIPT_WRITING: TaskStatus.IN_PROGRESS,
            WorkflowStatus.IMAGE_GENERATING: TaskStatus.IN_PROGRESS,
            WorkflowStatus.VIDEO_GENERATING: TaskStatus.IN_PROGRESS,
            WorkflowStatus.VIDEO_COMPOSING: TaskStatus.IN_PROGRESS,
            WorkflowStatus.QUALITY_CHECKING: TaskStatus.IN_PROGRESS,
            WorkflowStatus.PERSISTING_DATA: TaskStatus.IN_PROGRESS,
            WorkflowStatus.COMPLETED: TaskStatus.COMPLETED,
            WorkflowStatus.FAILED: TaskStatus.FAILED
        }
        
        return mapping.get(workflow_status, TaskStatus.IN_PROGRESS)
    
    async def _persist_task(self, workflow_state: WorkflowState, db: Session) -> Task:
        """持久化任务数据"""
        
        self.logger.info(f"💾 持久化任务: {workflow_state.task_id}")
        
        # 查找现有任务（使用task_id字段）
        existing_task = db.query(Task).filter(Task.task_id == workflow_state.task_id).first()
        
        # 映射 WorkflowStatus 到 TaskStatus
        task_status = self._map_workflow_to_task_status(workflow_state.status)
        
        if existing_task:
            task = existing_task
            task.status = task_status
            task.progress_percentage = workflow_state.progress_percentage
            task.current_step = workflow_state.current_step
        else:
            # 创建新任务 - 使用 Task 模型的正确字段
            task = Task(
                task_id=workflow_state.task_id,
                title=workflow_state.user_prompt[:255],  # Task 需要 title 字段
                description=workflow_state.user_prompt,
                task_type=TaskType.VIDEO_GENERATION,  # 固定为视频生成任务
                status=task_status,
                progress_percentage=workflow_state.progress_percentage,
                current_step=workflow_state.current_step,
                input_parameters={
                    "user_prompt": workflow_state.user_prompt,
                    "style_preference": workflow_state.style_preference,  # 🔧 修复: 使用style_preference替换video_style
                    "intelligent_style_design": workflow_state.intelligent_style_design,  # 新增: 智能风格设计
                    "duration": workflow_state.duration,
                    "aspect_ratio": workflow_state.aspect_ratio
                },
                created_at=workflow_state.created_at
            )
            db.add(task)
        
        # 更新任务的输出元数据 - 使用 Task 模型支持的字段
        if hasattr(task, 'output_metadata'):
            task.output_metadata = {
                "concept_plan": workflow_state.concept_plan,
                "overall_narrative": workflow_state.overall_narrative,
                "estimated_word_count": workflow_state.estimated_word_count,
                "estimated_reading_time": workflow_state.estimated_reading_time,
                "script_themes": workflow_state.script_themes,
                "voice_over_instructions": workflow_state.voice_over_instructions,
                "voice_over_assets": workflow_state.voice_over_assets,
                "voice_settings": workflow_state.voice_settings,
                "final_video_path": workflow_state.final_video_path,
                "final_video_url": workflow_state.final_video_url,
                "video_metadata": workflow_state.video_metadata,
                "tokens_used": workflow_state.tokens_used,
                "api_calls_made": workflow_state.api_calls_made,
                "estimated_cost": workflow_state.estimated_cost,
                "processing_time": workflow_state.processing_time
            }
        
        db.flush()
        return task
    
    async def _persist_scenes(self, task: Task, workflow_state: WorkflowState, db: Session) -> List[Dict[str, Any]]:
        """持久化场景数据"""
        
        self.logger.info(f"🎬 持久化 {len(workflow_state.scenes)} 个场景")
        
        scene_results = []
        
        for scene_data in workflow_state.scenes:
            try:
                # 查找现有场景
                existing_scene = db.query(Scene).filter(
                    Scene.task_id == task.id,
                    Scene.scene_number == scene_data.scene_number
                ).first()
                
                if existing_scene:
                    scene = existing_scene
                    status = "updated"
                else:
                    scene = Scene(task_id=task.id, scene_number=scene_data.scene_number)
                    db.add(scene)
                    status = "created"
                
                # 更新场景数据
                self._update_scene_from_data(scene, scene_data)
                db.flush()
                
                scene_results.append({
                    "scene_id": scene.id,
                    "scene_number": scene.scene_number,
                    "status": status
                })
                
            except Exception as e:
                self.logger.error(f"❌ 场景 {scene_data.scene_number} 持久化失败: {str(e)}")
                scene_results.append({
                    "scene_number": scene_data.scene_number,
                    "status": "failed",
                    "error": str(e)
                })
        
        return scene_results
    
    def _update_scene_from_data(self, scene: Scene, scene_data: SceneData):
        """从SceneData更新Scene模型"""
        
        # 基本属性 - 安全的scene_type转换
        try:
            if scene_data.scene_type:
                # 尝试直接转换为SceneType enum
                if hasattr(SceneType, scene_data.scene_type.upper()):
                    scene.scene_type = SceneType(scene_data.scene_type)
                else:
                    # 如果不是有效的enum值，使用智能映射
                    scene.scene_type = self._safe_map_scene_type(scene_data.scene_type)
            else:
                scene.scene_type = SceneType.MAIN_CONTENT
        except (ValueError, AttributeError) as e:
            # 如果转换失败，记录警告并使用默认值
            self.logger.warning(f"无效的scene_type值 '{scene_data.scene_type}'，使用默认值 'main_content': {str(e)}")
            scene.scene_type = SceneType.MAIN_CONTENT
        scene.title = scene_data.title
        scene.description = scene_data.description
        scene.duration = scene_data.duration
        scene.start_time = scene_data.start_time
        scene.end_time = scene_data.end_time
        
        # 概念相关
        scene.visual_description = scene_data.visual_description
        scene.narrative_description = scene_data.narrative_description
        scene.mood_and_atmosphere = scene_data.mood_and_atmosphere
        scene.camera_angle = scene_data.camera_angle
        scene.lighting_style = scene_data.lighting_style
        scene.art_style = scene_data.art_style
        scene.character_descriptions = scene_data.character_descriptions
        scene.props_and_objects = scene_data.props_and_objects
        scene.color_palette = scene_data.color_palette
        
        # 脚本相关
        scene.script_text = scene_data.script_text
        scene.voice_over_text = scene_data.voice_over_text
        scene.background_music_style = scene_data.background_music_style  # 已经清理过长度
        scene.sound_effects = scene_data.sound_effects
        
        # 生成参数
        scene.image_generation_params = scene_data.image_generation_params
        scene.video_generation_params = scene_data.video_generation_params
        
        # 质量相关
        scene.quality_score = scene_data.quality_score
        scene.quality_issues = scene_data.quality_issues
        scene.quality_suggestions = scene_data.quality_suggestions
    
    def _safe_map_scene_type(self, scene_type_str: str) -> SceneType:
        """安全的scene_type映射，处理中英文场景类型"""
        if not scene_type_str:
            return SceneType.MAIN_CONTENT
        
        scene_type_lower = scene_type_str.lower().strip()
        
        # English mappings
        english_mapping = {
            "intro": SceneType.INTRO,
            "introduction": SceneType.INTRO,
            "opening": SceneType.INTRO,
            "main_content": SceneType.MAIN_CONTENT,
            "main": SceneType.MAIN_CONTENT,
            "content": SceneType.MAIN_CONTENT,
            "body": SceneType.MAIN_CONTENT,
            "transition": SceneType.TRANSITION,
            "bridge": SceneType.TRANSITION,
            "outro": SceneType.OUTRO,
            "conclusion": SceneType.OUTRO,
            "ending": SceneType.OUTRO,
            "background": SceneType.BACKGROUND
        }
        
        # Chinese mappings for common scenario types
        chinese_mapping = {
            # 开始/起始/引入相关
            "修炼起始": SceneType.INTRO,
            "开始": SceneType.INTRO,
            "起始": SceneType.INTRO,
            "引入": SceneType.INTRO,
            "初始": SceneType.INTRO,
            "开场": SceneType.INTRO,
            # 主要内容/发展/过程
            "能量爆发": SceneType.MAIN_CONTENT,
            "主要内容": SceneType.MAIN_CONTENT,
            "发展": SceneType.MAIN_CONTENT,
            "过程": SceneType.MAIN_CONTENT,
            "进行": SceneType.MAIN_CONTENT,
            "演进": SceneType.MAIN_CONTENT,
            "修炼过程": SceneType.MAIN_CONTENT,
            # 突破/成功/结论/高潮
            "突破成功": SceneType.OUTRO,
            "突破": SceneType.OUTRO,
            "成功": SceneType.OUTRO,
            "完成": SceneType.OUTRO,
            "结束": SceneType.OUTRO,
            "结论": SceneType.OUTRO,
            "收尾": SceneType.OUTRO,
            # 过渡
            "过渡": SceneType.TRANSITION,
            "转场": SceneType.TRANSITION,
            "衔接": SceneType.TRANSITION,
            # 背景
            "背景": SceneType.BACKGROUND,
            "环境": SceneType.BACKGROUND
        }
        
        # Try English mapping first
        if scene_type_lower in english_mapping:
            return english_mapping[scene_type_lower]
        
        # Try Chinese mapping
        if scene_type_str in chinese_mapping:
            return chinese_mapping[scene_type_str]
        
        # Default fallback
        return SceneType.MAIN_CONTENT
    
    async def _persist_resources(self, task: Task, workflow_state: WorkflowState, db: Session) -> List[Dict[str, Any]]:
        """持久化资源文件记录"""
        
        resource_results = []
        
        for scene_data in workflow_state.scenes:
            scene = db.query(Scene).filter(
                Scene.task_id == task.id,
                Scene.scene_number == scene_data.scene_number
            ).first()
            
            if not scene:
                continue
            
            # 图像资源：仅记录引用/元数据，URL 优先，路径为备选
            if scene_data.image_path or scene_data.image_url:
                try:
                    image_resource = Resource(
                        task_id=task.id,
                        scene_id=scene.id,
                        filename=f"scene_{scene_data.scene_number}_image.jpg",
                        file_path=scene_data.image_path or "",
                        file_url=scene_data.image_url or None,
                        resource_type=ResourceType.IMAGE,
                        generation_prompt=scene_data.image_prompt,
                        generation_parameters=scene_data.image_generation_params,
                        processing_status="completed" if (scene_data.image_path or scene_data.image_url) else "pending",
                        is_generated=True
                    )
                    db.add(image_resource)
                    resource_results.append({"type": "image", "scene": scene_data.scene_number, "status": "created"})
                except Exception as e:
                    self.logger.error(f"❌ 图像资源持久化失败: {str(e)}")
            
            # 视频资源：仅记录引用/元数据
            if scene_data.video_path or scene_data.video_url:
                try:
                    video_resource = Resource(
                        task_id=task.id,
                        scene_id=scene.id,
                        filename=f"scene_{scene_data.scene_number}_video.mp4",
                        file_path=scene_data.video_path or "",
                        file_url=scene_data.video_url or None,
                        resource_type=ResourceType.VIDEO,
                        generation_prompt=scene_data.video_prompt,
                        generation_parameters=scene_data.video_generation_params,
                        processing_status="completed" if (scene_data.video_path or scene_data.video_url) else "pending",
                        is_generated=True
                    )
                    db.add(video_resource)
                    resource_results.append({"type": "video", "scene": scene_data.scene_number, "status": "created"})
                except Exception as e:
                    self.logger.error(f"❌ 视频资源持久化失败: {str(e)}")

            # 配音资源：仅记录引用/元数据
            if scene_data.voice_over_audio_path or scene_data.voice_over_audio_url:
                try:
                    voice_metadata = dict(scene_data.voice_over_audio_metadata or {})
                    voice_metadata.setdefault("audio_role", "voice_over")

                    voice_resource = Resource(
                        task_id=task.id,
                        scene_id=scene.id,
                        filename=f"scene_{scene_data.scene_number}_voice.{(scene_data.voice_over_audio_path or 'tmp.wav').split('.')[-1]}",
                        file_path=scene_data.voice_over_audio_path or "",
                        file_url=scene_data.voice_over_audio_url or None,
                        resource_type=self._resolve_voice_resource_type(),
                        generation_parameters=voice_metadata,
                        processing_status="completed" if (scene_data.voice_over_audio_path or scene_data.voice_over_audio_url) else "pending",
                        is_generated=True
                    )
                    db.add(voice_resource)
                    resource_results.append({"type": "voice_over", "scene": scene_data.scene_number, "status": "created"})
                except Exception as e:
                    self.logger.error(f"❌ 配音资源持久化失败: {str(e)}")

        return resource_results
    
    async def _persist_agent_logs(self, task: Task, workflow_state: WorkflowState, db: Session) -> List[Dict[str, Any]]:
        """已弃用：AgentExecution 审计由事件监听器负责，此处不再落库。"""
        self.logger.info("Skip agent_logs persistence (handled by event audit sink)")
        return []
    
    def _map_agent_name_to_type(self, agent_name: str) -> AgentType:
        """Agent名称到类型映射"""
        mapping = {
            "concept_planner": AgentType.CONCEPT_PLANNER,
            "script_writer": AgentType.SCRIPT_WRITER,
            "image_generator": AgentType.IMAGE_GENERATOR,
            "video_generator": AgentType.VIDEO_GENERATOR,
            "video_composer": AgentType.VIDEO_COMPOSER,
            "voice_synthesizer": AgentType.VOICE_SYNTHESIZER,
            "quality_checker": AgentType.QUALITY_CHECKER
        }
        return mapping.get(agent_name, AgentType.CONCEPT_PLANNER)
    
    async def _finalize_task_status(self, task: Task, workflow_state: WorkflowState, db: Session):
        """最终确定任务状态"""
        
        if workflow_state.errors:
            task.status = WorkflowStatus.FAILED.value
            task.error_message = "; ".join(workflow_state.errors[:3])
        elif workflow_state.is_completed():
            task.status = WorkflowStatus.COMPLETED.value
            task.completed_at = datetime.now()
        else:
            task.status = WorkflowStatus.PERSISTING_DATA.value
        
        task.updated_at = datetime.now()
        self.logger.info(f"📊 任务最终状态: {task.status}")
    
    # MAS架构预留接口
    async def get_agent_shared_state(self, task_id: str, agent_name: str) -> Dict[str, Any]:
        """获取Agent间共享状态 - 为MAS架构预留"""
        # TODO: 实现Agent间状态共享
        return {}
    
    async def update_agent_shared_state(self, task_id: str, agent_name: str, state_update: Dict[str, Any]):
        """更新Agent间共享状态 - 为MAS架构预留"""
        # TODO: 实现Agent间状态更新
        pass


# 全局服务实例（需通过 configure_data_persistence 显式设置）
data_persistence_service: Optional[DataPersistenceService] = None


def configure_data_persistence(memory_services: MemoryServices) -> None:
    global data_persistence_service
    data_persistence_service = DataPersistenceService(memory_services)
