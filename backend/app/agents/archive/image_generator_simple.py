"""
Image Generator Agent - 简化版批量图像生成
使用BaseAgent接口，移除复杂ReAct实现
"""
import asyncio
import json
from typing import Dict, Any, List
from sqlalchemy.orm import Session

from .base import BaseAgent, AgentError
from ..models import Task, AgentExecution, AgentType
from ..core.workflow_state import WorkflowState, SceneData


class ImageGeneratorAgent(BaseAgent):
    """
    Image Generator Agent - 简化版批量图像生成
    使用BaseAgent接口实现批量处理逻辑
    """
    
    def __init__(self):
        super().__init__(
            agent_type=AgentType.IMAGE_GENERATOR,
            agent_name="image_generator",
            timeout_seconds=600,
            max_retries=2,
            tools=[
                "image_generation_tool"  # 只需要图像生成工具
            ]
        )

    async def execute(
        self,
        task: Task,
        input_data: Dict[str, Any],
        db: Session,
        execution_order: int = 0
    ) -> Dict[str, Any]:
        """批量图像生成执行"""
        try:
            from ..core.config import settings
            
            # 获取workflow_state
            workflow_state_id = input_data.get("workflow_state_id")
            from ..core.workflow_state import workflow_manager
            workflow_state = workflow_manager.get_workflow(workflow_state_id) if workflow_state_id else None
            
            if not workflow_state:
                return {
                    "success": False,
                    "error": "No workflow state available",
                    "workflow_state_updated": False,
                    "results": []
                }
            
            # 获取场景信息
            scenes = getattr(workflow_state, 'scenes', [])
            if not scenes:
                return {
                    "success": False, 
                    "error": "No scenes available for image generation",
                    "workflow_state_updated": False,
                    "results": []
                }
            
            # 获取创意指导
            context = input_data.get("context", {})
            creative_guidance = context.get("creative_guidance", {})
            
            # 批量生成图像
            return await self._batch_generate_images(scenes, creative_guidance, workflow_state)
            
        except Exception as e:
            self.logger.error(f"ImageGenerator execution failed: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "workflow_state_updated": False,
                "fallback_applied": True,
                "results": []
            }

    async def _batch_generate_images(
        self, 
        scenes: List[SceneData], 
        creative_guidance: Dict[str, Any],
        workflow_state: WorkflowState
    ) -> Dict[str, Any]:
        """批量生成场景图像"""
        
        # 筛选需要图像的场景
        scenes_needing_images = [
            scene for scene in scenes 
            if not scene.image_path and not scene.image_url
        ]
        
        if not scenes_needing_images:
            return {
                "success": True,
                "message": "所有场景图像已生成",
                "images_generated": 0,
                "workflow_state_updated": False
            }
        
        try:
            self.logger.info(f"开始批量生成{len(scenes_needing_images)}个场景图像")
            
            # 准备批量生成参数
            image_requests = []
            for scene in scenes_needing_images:
                # 使用场景的视觉描述或脚本
                visual_prompt = scene.narrative_description or scene.title
                
                # 从创意指导中获取场景具体指导
                scene_guidance = creative_guidance.get("scene_guidances", {}).get(str(scene.scene_number), {})
                if scene_guidance.get("visual_description"):
                    visual_prompt = scene_guidance["visual_description"]
                
                image_requests.append({
                    "scene_number": scene.scene_number,
                    "prompt": visual_prompt,
                    "style_guidance": creative_guidance.get("intelligent_style_design", {}),
                    "aspect_ratio": "16:9",  # 默认宽屏
                    "quality": "hd"
                })
            
            # Function Call: 批量图像生成
            generation_results = await self.use_tool(
                "image_generation_tool",
                "batch_generate_images",
                {
                    "image_requests": image_requests,
                    "generation_mode": "batch_optimized",
                    "style_consistency": True
                }
            )
            
            # 更新workflow_state
            generated_count = 0
            if generation_results and generation_results.get("success"):
                generated_images = generation_results.get("generated_images", {})
                
                for scene in scenes_needing_images:
                    scene_image = generated_images.get(str(scene.scene_number))
                    if scene_image and scene_image.get("image_path"):
                        workflow_state.update_scene(
                            scene.scene_number,
                            image_path=scene_image["image_path"],
                            image_url=scene_image.get("image_url", ""),
                            first_frame_path=scene_image["image_path"]  # 图像作为首帧
                        )
                        generated_count += 1
            
            self.logger.info(f"批量图像生成完成: {generated_count}/{len(scenes_needing_images)}")
            
            return {
                "success": True,
                "message": f"批量生成{generated_count}个场景图像",
                "images_generated": generated_count,
                "generation_results": generation_results,
                "workflow_state_updated": generated_count > 0,
                "total_scenes": len(scenes_needing_images)
            }
            
        except Exception as e:
            self.logger.error(f"批量图像生成失败: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "images_generated": 0,
                "workflow_state_updated": False
            }
"""
DEPRECATION NOTICE (archived)
Legacy simple example archived. Do not import in production.
"""
import warnings as _warnings
raise ImportError(
    "Archived legacy module 'image_generator_simple'. Do not import in production."
)
