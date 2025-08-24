"""
Image Generator Agent - Generates images for video scenes
"""
import asyncio
import base64
import os
from typing import Dict, Any, List
from sqlalchemy.orm import Session

from .base import BaseAgent, AgentError
from ..models import Task, AgentExecution, AgentType, Scene, Resource, ResourceType
from ..services.file_storage import FileStorageService
from ..core.config import settings


class ImageGeneratorAgent(BaseAgent):
    """
    Image Generator Agent creates visual assets for each scene using AI image generation
    """
    
    def __init__(self):
        super().__init__(
            agent_type=AgentType.IMAGE_GENERATOR,
            agent_name="image_generator",
            timeout_seconds=600,  # 10 minutes for multiple image generations
            max_retries=2,
            tools=["image_generation"]  # 🚀 MAS - 使用单一业务逻辑工具
        )
        self.file_storage = FileStorageService()
    
    async def _execute_impl(
        self, 
        task: Task, 
        input_data: Dict[str, Any], 
        execution: AgentExecution,
        db: Session
    ) -> Dict[str, Any]:
        """Generate images for all scenes"""
        
        # Validate input
        self._validate_input(input_data, ["concept_plan", "workflow_state_id"])
        
        concept_plan = input_data["concept_plan"]
        workflow_state_id = input_data["workflow_state_id"]
        
        # 🧠 Phase 1.2 - 实现MAS记忆共享：ImageGenerator检索创意指导
        try:
            retrieved_guidance = await self.retrieve_creative_guidance(workflow_state_id)
            if retrieved_guidance:
                # 使用检索到的创意指导增强概念计划
                self.logger.info(f"🧠 ImageGenerator: 成功检索到创意指导，增强视觉理解")
                concept_plan.update(retrieved_guidance)
            else:
                self.logger.warning(f"⚠️ ImageGenerator: 未找到创意指导记忆，使用原始概念计划")
        except Exception as e:
            self.logger.warning(f"⚠️ ImageGenerator: 记忆检索失败 - {e}")
        
        # 通过 workflow_manager 获取 WorkflowState
        from ..core.workflow_state import workflow_manager
        workflow_state = workflow_manager.get_workflow(workflow_state_id)
        if not workflow_state:
            raise AgentError(f"WorkflowState {workflow_state_id} not found")
        
        await self._update_progress(execution, 10, "Loading scenes", db)
        
        # Get scenes from WorkflowState instead of database
        scenes_data = workflow_state.scenes
        
        if not scenes_data:
            raise AgentError("No scenes found in workflow state")
        
        generated_images = []
        total_scenes = len(scenes_data)
        
        # Generate images for each scene
        for i, scene_data in enumerate(scenes_data):
            scene_progress = 10 + int((i / total_scenes) * 80)
            await self._update_progress(
                execution, 
                scene_progress, 
                f"Generating image for scene {scene_data.scene_number}",
                db
            )
            
            try:
                # 智能选择生成模式
                generation_mode = await self._select_generation_mode_intelligently(
                    scene_data, workflow_state
                )
                
                if generation_mode == "single_image_with_description":
                    # 新方案：首帧 + 动作描述
                    result = await self._generate_single_image_with_action_description(
                        scene_data, concept_plan, execution, workflow_state_id, input_data
                    )
                else:
                    # 原方案：首帧 + 尾帧（保留）
                    result = await self._generate_first_last_frame_images(
                        scene_data, concept_plan, execution, workflow_state_id, input_data
                    )
                
                # 更新WorkflowState
                self._update_scene_with_generation_result(
                    workflow_state, scene_data.scene_number, result, generation_mode
                )
                
                # 添加生成结果到返回数据
                result_summary = self._create_generation_result_summary(result, generation_mode)
                result_summary["scene_number"] = scene_data.scene_number
                generated_images.append(result_summary)
                
                # 根据是否跳过显示不同的日志
                if result.get("skipped"):
                    self.logger.info(f"Skipped image generation for scene {scene_data.scene_number} (continuity required)")
                else:
                    self.logger.info(f"Generated image for scene {scene_data.scene_number}")
                
            except Exception as e:
                self.logger.error(f"Failed to generate image for scene {scene_data.scene_number}: {str(e)}")
                
                generated_images.append({
                    "scene_number": scene_data.scene_number,
                    "image_url": None,
                    "error": str(e),
                    "is_placeholder": True
                })
        
        await self._update_progress(execution, 95, "Finalizing image generation", db)
        
        # Generate summary statistics
        successful_generations = len([img for img in generated_images if not img.get("is_placeholder")])
        
        output_data = {
            "images": generated_images,
            "total_scenes": total_scenes,
            "successful_generations": successful_generations,
            "failed_generations": total_scenes - successful_generations,
            "generation_summary": self._create_generation_summary(generated_images),
            "image_style_consistency": self._analyze_style_consistency(generated_images, concept_plan),
            "workflow_state_id": workflow_state_id  # 传递给下一个Agent
        }
        
        await self._update_progress(execution, 100, "Image generation completed", db)
        
        return output_data
    
    async def _generate_scene_image_from_data(
        self, 
        scene_data,  # SceneData object from WorkflowState
        workflow_state_id: str,
        execution: AgentExecution,
        context_data: Dict[str, Any],  # 包含创意指导的上下文数据
        frame_type: str = "single",  # "first", "last", or "single"
        frame_prompts: Dict[str, Any] = None  # Generated frame prompts
    ) -> Dict[str, Any]:
        """Generate image for a single scene using SceneData and memory guidance"""
        
        # 🧠 Phase 1.2 - 实现MAS记忆共享：ImageGenerator检索场景引用数据
        scene_references = {}
        try:
            scene_references = await self.retrieve_scene_references(
                workflow_state_id, 
                scene_data.scene_number
            )
            if scene_references:
                self.logger.info(f"🧠 ImageGenerator: 成功检索到场景{scene_data.scene_number}引用数据")
            else:
                self.logger.warning(f"⚠️ ImageGenerator: 未找到场景{scene_data.scene_number}引用数据")
        except Exception as e:
            self.logger.warning(f"⚠️ ImageGenerator: 场景引用检索失败 - {e}")
        
        # 从上下文数据中获取创意指导（由Orchestrator提供）+ 增强场景引用
        creative_guidance = self._extract_creative_guidance_from_context(context_data, scene_data.scene_number)
        if scene_references:
            creative_guidance.update(scene_references)
        
        # 初始化增强跳过标志
        skip_enhancement = False
        
        # ⚠️ 直接使用关联生成的提示词，不做任何增强
        if frame_type == "first" and frame_prompts:
            # 直接使用关联生成的首帧提示词
            base_prompt = frame_prompts["first_frame_prompt"].get("description", "")
        elif frame_type == "last" and frame_prompts:
            # 直接使用关联生成的尾帧提示词
            base_prompt = frame_prompts["last_frame_prompt"].get("description", "")
        elif frame_type == "first" and not frame_prompts:
            # 新方案fallback：直接生成专业的首帧提示词，无需二次增强
            base_prompt = await self._generate_single_frame_prompt_for_fallback(scene_data, creative_guidance)
            # 标记为已完成的专业提示词，跳过后续增强
            skip_enhancement = True
        elif frame_type == "last":
            # 新方案不再生成尾帧图像，抛出明确错误
            raise AgentError(f"单帧生成模式不支持生成尾帧图像。场景 {scene_data.scene_number} 应使用 'first' 帧类型")
        else:
            # 其他帧类型的后备处理（历史兼容）
            base_prompt = scene_data.visual_description or scene_data.description or f"Scene {scene_data.scene_number}: {scene_data.title}"
        
        # 关键日志：检查场景描述数据
        self.logger.info(f"🎨 Scene {scene_data.scene_number} {frame_type} frame: base_prompt='{base_prompt}'")
        
        # If base_prompt is still empty, use user prompt from workflow as fallback
        if not base_prompt or base_prompt.strip() == "":
            from ..core.workflow_state import workflow_manager  
            workflow = workflow_manager.get_workflow(workflow_state_id)
            if workflow and workflow.user_prompt:
                original_user_prompt = workflow.user_prompt
                base_prompt = f"{original_user_prompt} - Scene {scene_data.scene_number}"
                self.logger.warning(f"🚨 Scene {scene_data.scene_number}: Using fallback user_prompt='{original_user_prompt}'")
        
        # 判断是否需要增强
        needs_enhancement = self._should_enhance_prompt(base_prompt, frame_prompts, skip_enhancement)
        
        if needs_enhancement:
            # 回退策略：增强过短的提示词
            enhanced_prompt = await self._build_image_prompt_with_guidance(scene_data, creative_guidance, base_prompt)
            self.logger.warning(f"⚠️ Used fallback enhancement for short prompt: '{base_prompt[:50]}...'")
        else:
            # 直接使用已有提示词
            enhanced_prompt = base_prompt
            self.logger.info(f"✅ Using existing prompt for {frame_type} frame")
        
        # 记录最终的增强提示词
        self.logger.info(f"🎯 Scene {scene_data.scene_number} Final Enhanced Prompt: '{enhanced_prompt}'")
        
        # Determine image generation service and parameters
        image_service = self._select_image_service()
        generation_params = self._get_generation_parameters_with_guidance(scene_data, creative_guidance)
        
        try:
            if image_service == "glm":
                try:
                    # 使用AI配置管理器获取图像生成模型
                    from ..core.ai_config import get_ai_config
                    ai_config_manager = get_ai_config()
                    image_model = ai_config_manager.get_model_for_agent("image_generator")
                    
                    result = await self.use_tool(
                        tool_name="image_generation",
                        action="generate_image",
                        parameters={
                            "prompt": enhanced_prompt,
                            "model": generation_params.get("glm_model", image_model),
                            "size": generation_params.get("size", "1024x1024")
                        }
                    )
                    # 转换工具输出格式
                    tool_result = result.result if hasattr(result, 'result') else result
                    result = {
                        "image_url": tool_result.get("image_url", ""),
                        "model": tool_result.get("model", image_model),
                        "parameters": generation_params,
                        "revised_prompt": tool_result.get("revised_prompt", enhanced_prompt)
                    }
                except Exception as glm_error:
                    # 检查是否是余额不足错误
                    error_msg = str(glm_error)
                    if "余额不足" in error_msg or "1113" in error_msg or "429" in error_msg:
                        self.logger.warning(f"🚨 智谱AI CogView余额不足，自动降级到其他图像生务")
                        # 尝试降级到OpenAI
                        if settings.OPENAI_API_KEY:
                            self.logger.info("🔄 降级到OpenAI DALL-E服务")
                            image_service = "openai"
                        elif settings.STABILITY_API_KEY:
                            self.logger.info("🔄 降级到Stability AI服务")
                            image_service = "stability"
                        else:
                            raise AgentError("智谱AI余额不足且未配置其他图像生成服务") from glm_error
                    else:
                        raise glm_error
            
            # 如果降级了，需要重新执行对应的服务
            elif image_service == "openai":
                result = await self.use_tool(
                    tool_name="image_generation_client",
                    action="generate_image",
                    parameters={
                        "prompt": enhanced_prompt,
                        "provider": "openai",
                        "model": generation_params.get("model", "dall-e-3"),
                        "size": generation_params.get("size", "1024x1024"),
                        "quality": generation_params.get("quality", "standard")
                    }
                )
                # 转换工具输出格式
                tool_result = result.result if hasattr(result, 'result') else result
                result = {
                    "image_url": tool_result.get("image_url", ""),
                    "model": tool_result.get("model", "dall-e-3"),
                    "parameters": generation_params,
                    "revised_prompt": tool_result.get("revised_prompt", enhanced_prompt)
                }
            elif image_service == "stability":
                result = await self.use_tool(
                    tool_name="image_generation_client", 
                    action="generate_image",
                    parameters={
                        "prompt": enhanced_prompt,
                        "provider": "stability",
                        "width": generation_params.get("width", 1024),
                        "height": generation_params.get("height", 1024),
                        "cfg_scale": generation_params.get("cfg_scale", 7.0),
                        "steps": generation_params.get("steps", 20)
                    }
                )
                # 转换工具输出格式
                tool_result = result.result if hasattr(result, 'result') else result
                result = {
                    "image_base64": tool_result.get("image_base64", ""),
                    "model": tool_result.get("model", "stable-diffusion"),
                    "parameters": generation_params,
                    "seed": tool_result.get("seed"),
                    "finish_reason": tool_result.get("finish_reason")
                }
            else:
                raise AgentError(f"Unsupported image service: {image_service}")
            
            result["prompt_used"] = enhanced_prompt
            result["service"] = image_service
            
            # Save image file if we have image data
            if "image_url" in result or "image_base64" in result:
                result["image_path"] = await self._save_image_from_result(result, scene_data.scene_number, frame_type)
            
            return result
            
        except Exception as e:
            self.logger.error(f"Image generation failed: {str(e)}")
            raise AgentError(f"Failed to generate image: {str(e)}") from e
    
    def _extract_creative_guidance_from_context(self, context_data: Dict[str, Any], scene_number: int) -> Dict[str, Any]:
        """从上下文数据中提取创意指导信息"""
        
        try:
            # 获取整体创意指导
            overall_guidance = context_data.get("creative_guidance", {})
            
            # 获取特定场景的指导
            scene_guidances = context_data.get("scene_guidances", {})
            scene_guidance = scene_guidances.get(f"scene_{scene_number}", {})
            
            guidance = {
                "overall_guidance": overall_guidance,
                "scene_guidance": scene_guidance,
                "has_guidance": bool(overall_guidance or scene_guidance)
            }
            
            if guidance["has_guidance"]:
                self.logger.info(f"🎨 Visual Artist using creative guidance for scene {scene_number}")
            else:
                self.logger.debug(f"No specific creative guidance for scene {scene_number}, using base prompts")
            
            return guidance
            
        except Exception as e:
            self.logger.error(f"Failed to extract creative guidance: {e}")
            return {"overall_guidance": {}, "scene_guidance": {}, "has_guidance": False}
    
    def _should_enhance_prompt(self, base_prompt: str, frame_prompts: Dict, skip_enhancement: bool) -> bool:
        """简单回退策略：只有在提示词明显缺失时才增强"""
        
        # 已有专业生成的提示词，不需要增强
        if frame_prompts or skip_enhancement:
            return False
        
        # 只有在提示词为空或明显不完整时才增强
        if not base_prompt or not base_prompt.strip():
            return True
            
        # 其他情况都直接使用
        return False
    
    async def _build_image_prompt_with_guidance(
        self, 
        scene_data,
        creative_guidance: Dict[str, Any],
        base_prompt: str,
        frame_type: str = "main"
    ) -> str:
        """基于LLM动态生成专业级图像提示词增强"""
        
        # 使用LLM生成专业增强提示词 - 传递frame_type以避免混淆
        frame_type_for_enhancement = "first" if "first" in str(frame_type) else "last" if "last" in str(frame_type) else "main"
        enhanced_prompt = await self._generate_professional_image_prompt(
            base_prompt, scene_data, creative_guidance, frame_type_for_enhancement
        )
        
        return enhanced_prompt
    
    async def _generate_professional_image_prompt(
        self,
        base_prompt: str,
        scene_data,
        creative_guidance: Dict[str, Any],
        frame_type: str = "main"  # "first", "last", or "main"
    ) -> str:
        """使用LLM生成专业级图像提示词增强"""
        
        # 根据frame_type设置不同的指导
        frame_specific_instruction = ""
        if frame_type == "first":
            frame_specific_instruction = """
CRITICAL: This is the FIRST FRAME of a scene. Generate a prompt for the STARTING POSITION BEFORE any action occurs.
- The scene should show the PREPARATION state
- All objects should be in their INITIAL positions
- NO action or movement should be happening yet
- Example: "knife poised above fruit" NOT "knife cutting through fruit"
"""
        elif frame_type == "last":
            frame_specific_instruction = """
CRITICAL: This is the LAST FRAME of a scene. Generate a prompt for the ENDING POSITION AFTER action is complete.
- The scene should show the RESULT state
- All objects should be in their FINAL positions
- The action should be COMPLETED, not in progress
- Example: "fruit cut in half, knife resting beside" NOT "knife cutting through fruit"
"""
        
        # 使用新的提示词模板系统替换硬编码提示词
        prompt_generation_request = self.render_prompt(
            "professional_image_prompt_generation",
            frame_specific_instruction=frame_specific_instruction,
            base_prompt=base_prompt,
            scene_number=scene_data.scene_number,
            scene_title=getattr(scene_data, 'title', ''),
            scene_duration=getattr(scene_data, 'duration', 0),
            mood_and_atmosphere=getattr(scene_data, 'mood_and_atmosphere', ''),
            camera_angle=getattr(scene_data, 'camera_angle', ''),
            props_and_objects=getattr(scene_data, 'props_and_objects', []),
            character_descriptions=getattr(scene_data, 'character_descriptions', []),
            visual_description=getattr(scene_data, 'visual_description', ''),
            overall_concept=creative_guidance.get('overall_guidance', {}).get('concept', ''),
            visual_style_requirements=creative_guidance.get('overall_guidance', {}).get('visual_style', ''),
            target_mood=creative_guidance.get('overall_guidance', {}).get('mood_target', '')
        )
        
        try:
            # 使用AI配置管理器
            from ..core.ai_config import get_ai_config
            ai_config_manager = get_ai_config()
            model = ai_config_manager.get_model_for_agent("image_generator")
            model_config = ai_config_manager.get_model_config(model)
            
            # 调用AI服务
            from ..services.ai_client import AIClient
            ai_client = AIClient()
            
            response = await ai_client.generate_text(
                prompt=prompt_generation_request,
                model=model,
                max_tokens=model_config.max_tokens if model_config else 2000,
                temperature=0.7  # 保持一定创意性但不过度随机
            )
            
            enhanced_prompt = response["content"].strip()
            
            # 清理响应格式
            if enhanced_prompt.startswith('"') and enhanced_prompt.endswith('"'):
                enhanced_prompt = enhanced_prompt[1:-1]
            
            self.logger.info(f"🎆 LLM Enhanced Prompt for scene {scene_data.scene_number}: '{enhanced_prompt[:100]}...'")
            
            return enhanced_prompt
            
        except Exception as e:
            self.logger.error(f"Failed to generate LLM-enhanced prompt: {str(e)}")
            # Fallback: 使用硬编码增强逻辑
            return await self._fallback_prompt_enhancement(base_prompt, scene_data, frame_type)
    
    async def _fallback_prompt_enhancement(
        self,
        base_prompt: str, 
        scene_data,
        frame_type: str = "main"
    ) -> str:
        """备用的硬编码增强逻辑"""
        
        # 根据frame_type添加明确的状态指示
        enhancements = [base_prompt]
        
        if frame_type == "first":
            enhancements.append("in starting position before action")
        elif frame_type == "last":
            enhancements.append("in final position after action complete")
        
        # 添加气氛
        mood = getattr(scene_data, 'mood_and_atmosphere', '')
        if mood:
            enhancements.append(f"with {mood} atmosphere")
        
        # 添加基础质量修饰符
        quality_terms = [
            "professional photography",
            "high resolution", 
            "detailed",
            "sharp focus",
            "professional lighting"
        ]
        enhancements.extend(quality_terms)
        
        return ", ".join(enhancements)
    
    async def _build_image_prompt_with_guidance_legacy(
        self, 
        scene_data,
        creative_guidance: Dict[str, Any],
        base_prompt: str
    ) -> str:
        """保留原有的硬编码方法作为备用"""
        
        prompt_elements = []
        
        # 基础场景描述
        if base_prompt:
            prompt_elements.append(base_prompt)
        
        # 融入创意总监的整体视觉指导
        overall_guidance = creative_guidance.get("overall_guidance", {})
        if overall_guidance:
            visual_style_guidance = overall_guidance.get("visual_style_guidance", {})
            if visual_style_guidance:
                # 整体美学方向
                overall_aesthetic = visual_style_guidance.get("overall_aesthetic", "")
                if overall_aesthetic:
                    prompt_elements.append(f"Creative Director's vision: {overall_aesthetic}")
                
                # 色彩指导
                color_philosophy = visual_style_guidance.get("color_philosophy", "")
                color_palette = visual_style_guidance.get("color_palette", [])
                if color_philosophy:
                    prompt_elements.append(f"Color approach: {color_philosophy}")
                if color_palette:
                    prompt_elements.append(f"Color palette: {', '.join(color_palette)}")
                
                # 视觉一致性要求
                consistency_notes = visual_style_guidance.get("visual_consistency_notes", "")
                if consistency_notes:
                    prompt_elements.append(f"Visual consistency: {consistency_notes}")
        
        # 融入特定场景的创意指导
        scene_guidance = creative_guidance.get("scene_guidance", {})
        if scene_guidance:
            # 创意意图
            creative_intent = scene_guidance.get("creative_intent", "")
            if creative_intent:
                prompt_elements.append(f"Scene purpose: {creative_intent}")
            
            # 视觉指导
            visual_direction = scene_guidance.get("visual_direction", "")
            if visual_direction:
                prompt_elements.append(f"Visual direction: {visual_direction}")
            
            # 视觉优先级
            visual_priorities = scene_guidance.get("visual_priorities", [])
            if visual_priorities:
                prompt_elements.append(f"Visual priorities: {', '.join(visual_priorities)}")
            
            # 情绪目标
            mood_target = scene_guidance.get("mood_target", "")
            if mood_target:
                prompt_elements.append(f"Emotional target: {mood_target}")
            
            # 摄影策略
            camera_strategy = scene_guidance.get("camera_strategy", "")
            if camera_strategy:
                prompt_elements.append(f"Camera approach: {camera_strategy}")
            
            # 光照情绪
            lighting_mood = scene_guidance.get("lighting_mood", "")
            if lighting_mood:
                prompt_elements.append(f"Lighting: {lighting_mood}")
        
        # 添加场景数据中的其他信息（作为补充）
        if scene_data.mood_and_atmosphere and not scene_guidance.get("mood_target"):
            prompt_elements.append(f"Atmosphere: {scene_data.mood_and_atmosphere}")
        
        # 专业质量要求 - 根据视觉风格定制
        visual_style = creative_guidance.get("overall_guidance", {}).get("visual_style_guidance", {}).get("primary_style", "realistic")
        
        if visual_style == "cinematic":
            quality_modifiers = [
                "cinematic lighting", "film grain", "depth of field", "color grading", 
                "professional cinematography", "movie still quality"
            ]
        elif visual_style == "artistic":
            quality_modifiers = [
                "artistic composition", "creative lighting", "visual storytelling", 
                "fine art photography", "aesthetic appeal", "masterpiece quality"
            ]
        elif visual_style == "documentary":
            quality_modifiers = [
                "natural lighting", "authentic moment", "photojournalism style", 
                "real-world setting", "candid composition", "documentary photography"
            ]
        else:  # realistic or default
            quality_modifiers = [
                "professional photography", "high resolution", "detailed", 
                "realistic lighting", "sharp focus", "professional quality"
            ]
            
        prompt_elements.extend(quality_modifiers)
        
        enhanced_prompt = ", ".join(prompt_elements)
        
        # 智能长度控制 - 保持关键信息
        if len(enhanced_prompt) > 800:
            # 优先保留核心场景描述和质量修饰符
            core_parts = prompt_elements[:3] + quality_modifiers[-3:]
            enhanced_prompt = ", ".join(core_parts)
        
        return enhanced_prompt
    
    def _get_generation_parameters_with_guidance(self, scene_data, creative_guidance: Dict[str, Any]) -> Dict[str, Any]:
        """基于创意指导确定生成参数"""
        
        params = {
            "width": 1024,
            "height": 1024,
            "quality": "standard",
            "style": "natural"
        }
        
        # 从创意指导中提取技术要求
        overall_guidance = creative_guidance.get("overall_guidance", {})
        production_guidance = overall_guidance.get("production_guidance", {})
        if production_guidance:
            tech_requirements = production_guidance.get("technical_requirements", {})
            if tech_requirements.get("resolution"):
                resolution = tech_requirements["resolution"]
                if "1920x1080" in resolution:
                    params.update({"width": 1920, "height": 1080})
                elif "1024x1024" in resolution:
                    params.update({"width": 1024, "height": 1024})
        
        return params
    
    
    
    def _select_image_service(self) -> str:
        """Select which image generation service to use - 按优先级自动选择"""
        
        # Priority: GLM CogView > OpenAI > Stability AI
        if settings.GLM_API_KEY:
            self.logger.info("🎨 选择智谱AI CogView作为图像生成服务")
            return "glm"
        elif settings.OPENAI_API_KEY:
            self.logger.info("🎨 选择OpenAI DALL-E作为图像生成服务")
            return "openai"
        elif settings.STABILITY_API_KEY:
            self.logger.info("🎨 选择Stability AI作为图像生成服务")
            return "stability"
        else:
            raise AgentError("❌ 未配置任何图像生成服务API密钥，请至少配置以下之一：GLM_API_KEY, OPENAI_API_KEY, STABILITY_API_KEY")
    
    def _get_generation_parameters_from_data(
        self, 
        scene_data,  # SceneData object
        concept_plan: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Get image generation parameters based on scene and concept"""
        
        # Determine aspect ratio based on video requirements
        aspect_ratio = concept_plan.get("technical_requirements", {}).get("aspect_ratio", "16:9")
        
        if aspect_ratio == "16:9":
            size = "1792x1024"  # DALL-E 3 landscape
            width, height = 1792, 1024
        elif aspect_ratio == "9:16":
            size = "1024x1792"  # DALL-E 3 portrait
            width, height = 1024, 1792
        else:
            size = "1024x1024"  # Square
            width, height = 1024, 1024
        
        return {
            "model": "dall-e-3",
            "size": size,
            "width": width,
            "height": height,
            "quality": "hd",
            "cfg_scale": 7.0,
            "steps": 20
        }
    
    async def _save_image_resource(
        self, 
        task: Task, 
        scene: Scene, 
        image_result: Dict[str, Any],
        db: Session
    ) -> Resource:
        """Save generated image and create resource record"""
        
        # Download and save image
        if "image_url" in image_result:
            # Download from URL (OpenAI)
            filename = f"scene_{scene.scene_number}_{scene.id}.jpg"
            file_path = await self.file_storage.download_and_save_image(
                image_result["image_url"], filename
            )
        elif "image_base64" in image_result:
            # Save from base64 (Stability AI)
            filename = f"scene_{scene.scene_number}_{scene.id}.png"
            file_path = await self.file_storage.save_base64_image(
                image_result["image_base64"], filename
            )
        else:
            raise AgentError("No image data found in generation result")
        
        # Get file info
        file_info = await self.file_storage.get_file_info(file_path)
        
        # Create resource record
        resource = Resource(
            task_id=task.id,
            scene_id=scene.id,
            filename=filename,
            original_filename=filename,
            file_path=file_path,
            resource_type=ResourceType.IMAGE,
            mime_type=file_info["mime_type"],
            file_size=file_info["size"],
            width=file_info.get("width"),
            height=file_info.get("height"),
            generation_parameters=image_result.get("parameters", {}),
            generation_model=image_result.get("model"),
            generation_prompt=image_result.get("prompt_used"),
            generation_seed=image_result.get("seed"),
            processing_status="completed",
            is_generated=True
        )
        
        db.add(resource)
        db.commit()
        db.refresh(resource)
        
        return resource
    
    async def _create_placeholder_resource(
        self, 
        task: Task, 
        scene: Scene, 
        error_message: str,
        db: Session
    ) -> Resource:
        """Create placeholder resource for failed generation"""
        
        resource = Resource(
            task_id=task.id,
            scene_id=scene.id,
            filename=f"placeholder_scene_{scene.scene_number}.jpg",
            file_path="",
            resource_type=ResourceType.IMAGE,
            processing_status="failed",
            is_generated=True,
            generation_parameters={"error": error_message}
        )
        
        db.add(resource)
        db.commit()
        db.refresh(resource)
        
        return resource
    
    def _create_generation_summary(self, generated_images: List[Dict]) -> Dict[str, Any]:
        """Create summary of generation results"""
        
        successful = [img for img in generated_images if not img.get("is_placeholder")]
        failed = [img for img in generated_images if img.get("is_placeholder")]
        
        models_used = {}
        for img in successful:
            model = img.get("generation_model", "unknown")
            models_used[model] = models_used.get(model, 0) + 1
        
        return {
            "total_images": len(generated_images),
            "successful": len(successful),
            "failed": len(failed),
            "success_rate": len(successful) / len(generated_images) if generated_images else 0,
            "models_used": models_used,
            "average_generation_time": "estimated 10-30 seconds per image"
        }
    
    def _analyze_style_consistency(
        self, 
        generated_images: List[Dict], 
        concept_plan: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Analyze style consistency across generated images"""
        
        successful_images = [img for img in generated_images if not img.get("is_placeholder")]
        
        if not successful_images:
            return {"consistency_score": 0, "issues": ["No successful image generations"]}
        
        # Basic consistency analysis
        models_used = set(img.get("generation_model", "unknown") for img in successful_images)
        
        consistency_score = 0.8 if len(models_used) == 1 else 0.6  # Higher score for same model
        
        return {
            "consistency_score": consistency_score,
            "models_used": list(models_used),
            "style_notes": concept_plan.get("visual_style", ""),
            "recommendations": self._get_style_recommendations(successful_images)
        }
    
    def _get_style_recommendations(self, successful_images: List[Dict]) -> List[str]:
        """Get recommendations for improving style consistency"""
        
        recommendations = []
        
        if len(successful_images) < len(successful_images):
            recommendations.append("Consider regenerating failed images for consistency")
        
        recommendations.append("Review generated images for visual coherence")
        recommendations.append("Ensure color palette consistency across scenes")
        
        return recommendations
    
    async def analyze_and_generate_frames(self, scene_data, creative_guidance: Dict[str, Any]) -> Dict[str, Any]:
        """生成完整的首尾帧提示词, 返回结构化JSON数据"""
        
        # 使用提示词模板系统替代75行硬编码提示词
        frame_generation_prompt = self.render_prompt(
            "complete_frame_analysis",
            scene_duration=scene_data.duration,
            scene_description=scene_data.visual_description or scene_data.description
        )
        
        try:
            from ..core.ai_config import get_ai_config
            ai_config = get_ai_config()
            
            # 使用JSON格式调用
            result = await self.use_tool(
                tool_name="kimi_client",
                action="chat",
                parameters={
                    "messages": [{"role": "user", "content": frame_generation_prompt}],
                    "temperature": 0.3,
                    "response_format": {"type": "json_object"}  # 强制JSON格式输出
                }
            )
            
            # 解析JSON结果
            import json
            frame_data = json.loads(result.get("content", "{}"))
            
            # 验证必需字段
            if not frame_data.get("first_frame_image_prompt") or not frame_data.get("last_frame_image_prompt"):
                raise ValueError("Missing required frame prompt fields")
            
            self.logger.info(f"✅ Generated structured frame prompts for scene {scene_data.scene_number}")
            
            # 检查首尾帧差异度
            if self._should_check_frame_difference():
                difference_score = await self._calculate_frame_difference(
                    frame_data.get("first_frame_image_prompt", {}).get("description", ""),
                    frame_data.get("last_frame_image_prompt", {}).get("description", ""),
                    scene_data
                )
                
                frame_data["frame_difference_analysis"] = {
                    "difference_score": difference_score,
                    "sufficient_story_development": difference_score >= self._get_difference_threshold(),
                    "minimum_required_score": self._get_difference_threshold()
                }
                
                if difference_score < self._get_difference_threshold():
                    self.logger.warning(f"🎭 Scene {scene_data.scene_number}: Low frame difference ({difference_score:.2f}), may need more story development")
            
            return frame_data
            
        except Exception as e:
            self.logger.warning(f"Structured frame generation failed: {e}")
            # 降级到简单处理
            return await self._fallback_frame_generation(scene_data, creative_guidance)

    async def _fallback_frame_generation(self, scene_data, creative_guidance: Dict[str, Any]) -> Dict[str, Any]:
        """降级处理: 生成基础的首尾帧数据结构"""
        
        description = scene_data.visual_description or scene_data.description or ""
        
        return {
            "first_frame_image_prompt": {
                "description": f"Initial state: {description}. Scene {scene_data.scene_number} beginning.",
                "prohibited_words_check": True,
                "visual_elements": ["main subject", "environment", "lighting"],
                "composition": "establishing shot",
                "style_tags": ["photorealistic", "high quality"]
            },
            "last_frame_image_prompt": {
                "description": f"Final state: Action completed. Scene {scene_data.scene_number} conclusion.",
                "prohibited_words_check": True, 
                "visual_elements": ["transformed subject", "final environment", "result"],
                "composition": "conclusion shot",
                "style_tags": ["photorealistic", "high quality"]
            },
            "static_verification": {
                "first_frame_is_static": True,
                "last_frame_is_static": True,
                "difference_score": 0.6,
                "key_differences": ["Basic state change from initial to final"]
            }
        }

    async def _enhance_prompt_for_first_frame(self, base_prompt: str, scene_data, creative_guidance: Dict[str, Any]) -> str:
        """使用模板生成符合物理规律的首帧提示词"""
        
        # 从creative_guidance中获取ConceptPlanner判断的场景物理类型
        overall_guidance = creative_guidance.get("overall_guidance", {})
        concept_plan = overall_guidance.get("concept_plan", {}) if isinstance(overall_guidance, dict) else {}
        scene_physics_type = concept_plan.get("scene_physics_type", {})
        
        # 收集模板变量
        template_variables = {
            "scene_number": scene_data.scene_number,
            "description": scene_data.description or base_prompt,
            "visual_description": scene_data.visual_description or "",
            "narrative_description": scene_data.narrative_description,
            "script_text": getattr(scene_data, 'script_text', ''),
            "mood_and_atmosphere": scene_data.mood_and_atmosphere,
            "overall_guidance": overall_guidance,
            "scene_physics_type": scene_physics_type,  # ConceptPlanner的场景类型判断
        }
        
        # 使用模板系统渲染首帧提示词
        first_frame_template = await self.render_prompt("natural_first_frame_generation", template_variables)
        
        # 通过LLM生成符合物理规律的首帧提示词
        llm_result = await self.use_tool(
            "image_generation",
            "enhance_prompt", 
            {
                "prompt": first_frame_template,
                "target_style": "realistic",
                "focus": "quality"
            }
        )
        
        # 处理ToolOutput对象
        if hasattr(llm_result, 'result') and isinstance(llm_result.result, dict):
            enhanced_prompt = llm_result.result.get("enhanced_prompt", "").strip()
            if not enhanced_prompt:
                enhanced_prompt = llm_result.result.get("content", "").strip()
        elif hasattr(llm_result, 'content'):
            enhanced_prompt = llm_result.content.strip()
        elif isinstance(llm_result, dict):
            enhanced_prompt = llm_result.get("content", "").strip()
        else:
            enhanced_prompt = str(llm_result).strip()
        
        if not enhanced_prompt:
            self.logger.warning(f"LLM生成的首帧提示词为空，使用基础描述")
            enhanced_prompt = base_prompt
            
        self.logger.info(f"🎨 Generated physics-compliant first frame prompt for scene {scene_data.scene_number}")
        return enhanced_prompt
    
    def _enhance_prompt_for_last_frame(self, base_prompt: str, scene_data, creative_guidance: Dict[str, Any]) -> str:
        """增强尾帧提示词 - 基于ScriptWriter的情景参考进行专业视觉转换"""
        
        overall_guidance = creative_guidance.get("overall_guidance", {})
        scene_guidance = creative_guidance.get("scene_guidance", {})
        
        enhancements = []
        
        # 1. 获取ScriptWriter提供的尾帧情景参考 (直接从scene_data获取)
        last_frame_ref = getattr(scene_data, 'last_frame_scene_reference', {})
        if not last_frame_ref:
            # 降级：从creative_guidance中获取
            last_frame_ref = scene_guidance.get("last_frame_scene_reference", {})
        
        if last_frame_ref:
            # 将情景参考转换为视觉提示词
            situation = last_frame_ref.get("situation", "")
            if situation:
                enhancements.append(f"scene situation: {situation}")
            
            character_state = last_frame_ref.get("character_emotional_state", "") or last_frame_ref.get("character_state", "")
            if character_state:
                enhancements.append(f"character energy: {character_state}")
            
            visual_elements = last_frame_ref.get("key_visual_elements", []) or last_frame_ref.get("visual_elements", "")
            if visual_elements:
                if isinstance(visual_elements, list):
                    enhancements.append(f"key elements: {', '.join(visual_elements)}")
                else:
                    enhancements.append(f"visual focus: {visual_elements}")
            
            action_completion = last_frame_ref.get("action_completion", "")
            if action_completion:
                enhancements.append(f"action state: {action_completion}")
        
        # 2. 应用ConceptPlanner的视觉一致性要求
        visual_style_guidance = overall_guidance.get("visual_style_guidance", {})
        if visual_style_guidance:
            visual_consistency = visual_style_guidance.get("visual_consistency_notes", "")
            if visual_consistency:
                enhancements.append(f"visual consistency: {visual_consistency}")
        
        # 3. 遵循ConceptPlanner的过渡策略
        narrative_flow = overall_guidance.get("narrative_flow_strategy", {})
        if narrative_flow:
            mood_tone = narrative_flow.get("mood_and_tone", "")
            if mood_tone:
                enhancements.append(f"narrative mood: {mood_tone} - completion")
                
            transition_philosophy = narrative_flow.get("transition_philosophy", "")
            if transition_philosophy:
                enhancements.append(f"transition approach: {transition_philosophy}")
        
        # 4. 应用ImageGenerator的专业构图技能
        enhancements.extend([
            "scene completion composition",
            "emotional peak visualization",
            "professional photography style",
            "smooth transition preparation"
        ])
        
        return f"{base_prompt}, {', '.join(enhancements)}"
    
    async def _save_image_from_result(self, image_result: Dict[str, Any], scene_number: int, frame_type: str = "single") -> str:
        """Save image from generation result and return file path"""
        
        try:
            # 根据帧类型确定文件名
            if frame_type == "first":
                filename_suffix = "first_frame"
            elif frame_type == "last":
                filename_suffix = "last_frame"
            else:
                filename_suffix = "image"
            
            if "image_url" in image_result:
                # Download from URL (OpenAI, GLM)
                filename = f"scene_{scene_number}_{filename_suffix}.jpg"
                file_path = await self.file_storage.download_and_save_image(
                    image_result["image_url"], filename
                )
            elif "image_base64" in image_result:
                # Save from base64 (Stability AI)
                filename = f"scene_{scene_number}_{filename_suffix}.png"
                file_path = await self.file_storage.save_base64_image(
                    image_result["image_base64"], filename
                )
            else:
                raise ValueError("No image data found in generation result")
            
            return file_path
            
        except Exception as e:
            self.logger.error(f"Failed to save {frame_type} image for scene {scene_number}: {str(e)}")
            return ""
    
    def _should_check_frame_difference(self) -> bool:
        """检查是否应该进行首尾帧差异度检查"""
        return settings.ENABLE_FRAME_CONSISTENCY_CHECK
    
    def _get_difference_threshold(self) -> float:
        """获取首尾帧差异度阈值"""
        return settings.FRAME_DIFFERENCE_THRESHOLD
    
    async def _calculate_frame_difference(self, first_prompt: str, last_prompt: str, scene_data) -> float:
        """计算首尾帧提示词之间的差异度分数"""
        
        try:
            # 简单的词汇差异分析
            first_words = set(first_prompt.lower().split())
            last_words = set(last_prompt.lower().split())
            
            # 计算词汇重叠度
            intersection = first_words.intersection(last_words)
            union = first_words.union(last_words)
            
            if len(union) == 0:
                return 0.0
            
            overlap_ratio = len(intersection) / len(union)
            difference_score = 1.0 - overlap_ratio
            
            # 根据场景时长调整权重
            duration_factor = min(scene_data.duration / (settings.DEFAULT_SCENE_DURATION * 2), 1.0)  # 两倍默认时长为基准
            adjusted_score = difference_score * duration_factor
            
            # 检查关键差异词汇
            key_difference_words = [
                "before", "after", "initial", "final", "start", "end", "beginning", "completion",
                "intact", "broken", "whole", "split", "closed", "open", "full", "empty"
            ]
            
            difference_keywords_count = 0
            for word in key_difference_words:
                if word in first_prompt.lower() or word in last_prompt.lower():
                    difference_keywords_count += 1
            
            # 关键词加权
            keyword_bonus = min(difference_keywords_count * 0.1, 0.3)
            
            final_score = min(adjusted_score + keyword_bonus, 1.0)
            
            self.logger.debug(f"Frame difference calculation - Scene {scene_data.scene_number}: "
                            f"overlap={overlap_ratio:.2f}, diff={difference_score:.2f}, "
                            f"duration_factor={duration_factor:.2f}, keywords={difference_keywords_count}, "
                            f"final={final_score:.2f}")
            
            return final_score
            
        except Exception as e:
            self.logger.error(f"Failed to calculate frame difference: {e}")
            return 0.5  # 默认中等差异
    
    async def _build_enhanced_frame_prompt(
        self, 
        frame_prompt_data: Dict[str, Any], 
        scene_data, 
        creative_guidance: Dict[str, Any],
        frame_type: str
    ) -> str:
        """通过LLM智能构建增强的帧提示词 - 针对新生成的frame_prompts"""
        
        # 使用提示词模板系统替代硬编码整合提示词
        integration_prompt = self.render_prompt(
            "prompt_integration",
            core_description=frame_prompt_data.get('description', ''),
            detailed_objects=frame_prompt_data.get('detailed_elements', {}).get('objects', []),
            detailed_characters=frame_prompt_data.get('detailed_elements', {}).get('characters', []),
            detailed_environment=frame_prompt_data.get('detailed_elements', {}).get('environment', ''),
            composition_layout=frame_prompt_data.get('composition_layout', ''),
            lighting_and_mood=frame_prompt_data.get('lighting_and_mood', ''),
            result_changes=frame_prompt_data.get('result_changes', '') if frame_type == "last" else None,
            scene_number=scene_data.scene_number,
            frame_type=frame_type,
            scene_mood=getattr(scene_data, 'mood_and_atmosphere', ''),
            art_style=getattr(scene_data, 'art_style', 'realistic')
        )
        
        try:
            result = await self.use_tool(
                "image_generation", "enhance_prompt",
                {"prompt": integration_prompt, "target_style": "realistic", "focus": "quality"}
            )
            
            # 处理结果
            if hasattr(result, 'result') and isinstance(result.result, dict):
                enhanced_prompt = result.result.get("enhanced_prompt", "").strip()
                if not enhanced_prompt:
                    enhanced_prompt = result.result.get("content", "").strip()
            elif hasattr(result, 'content'):
                enhanced_prompt = result.content.strip()
            elif isinstance(result, dict):
                enhanced_prompt = result.get("enhanced_prompt", "").strip()
                if not enhanced_prompt:
                    enhanced_prompt = result.get("content", "").strip()
            else:
                enhanced_prompt = str(result).strip()
            
            # 验证结果有效性
            if not enhanced_prompt or len(enhanced_prompt) < 20:
                # 后备方案：使用核心描述
                return frame_prompt_data.get("description", "Static image description")
                
            return enhanced_prompt
            
        except Exception as e:
            self.logger.error(f"帧提示词整合失败: {e}")
            # 后备方案
            return frame_prompt_data.get("description", "Static image description")
    
    async def _generate_single_frame_prompt_for_fallback(
        self, 
        scene_data, 
        creative_guidance: Dict[str, Any]
    ) -> str:
        """为fallback情况生成专业的首帧提示词(符合新方案)"""
        
        # 从creative_guidance中提取全局信息
        overall_guidance = creative_guidance.get("overall_guidance", {})
        project_overview = overall_guidance.get("project_overview", {})
        
        # 获取项目全局信息
        total_duration = project_overview.get("total_duration", 30)
        video_style = project_overview.get("video_style", "professional") 
        user_prompt = project_overview.get("user_prompt", "")
        total_scenes = project_overview.get("total_scenes", 1)
        
        # 计算场景在整体中的位置和比重
        scene_percentage = (scene_data.duration / total_duration * 100) if total_duration > 0 else 0
        scene_position = "开场" if scene_data.scene_number == 1 else ("结尾" if scene_data.scene_number == total_scenes else "中段")
        
        # 获取场景上下文信息
        scene_context = overall_guidance.get("scene_context", {})
        narrative_flow = overall_guidance.get("narrative_flow_strategy", {})
        
        # 使用提示词模板系统替代75行硬编码提示词
        prompt_template = self.render_prompt(
            "professional_first_frame_design",
            scene_number=scene_data.scene_number,
            total_duration=total_duration,
            video_style=video_style,
            user_prompt=user_prompt,
            total_scenes=total_scenes,
            scene_title=scene_data.title,
            scene_duration=scene_data.duration,
            scene_percentage=f"{scene_percentage:.1f}",
            scene_description=scene_data.description,
            visual_description=getattr(scene_data, 'visual_description', ''),
            narrative_description=getattr(scene_data, 'narrative_description', ''),
            mood_and_atmosphere=getattr(scene_data, 'mood_and_atmosphere', ''),
            art_style=getattr(scene_data, 'art_style', 'realistic'),
            lighting_style=getattr(scene_data, 'lighting_style', 'natural'),
            scene_position=scene_position,
            narrative_flow=narrative_flow,
            creative_guidance=creative_guidance
        )
        
        try:
            from ..core.ai_config import get_ai_config
            ai_config_manager = get_ai_config()
            model = ai_config_manager.get_model_for_agent("image_generator")
            
            result = await self.use_tool(
                "image_generation", "enhance_prompt",
                {"prompt": prompt_template, "target_style": "realistic", "focus": "quality"}
            )
            
            # 提取生成的内容
            content = ""
            if hasattr(result, 'result') and isinstance(result.result, dict):
                # ToolOutput对象，从result.result中获取enhanced_prompt
                content = result.result.get("enhanced_prompt", "")
                if not content:
                    content = result.result.get("content", "")
            elif hasattr(result, 'content'):
                content = result.content or ""
            elif isinstance(result, dict):
                content = result.get("enhanced_prompt", "")
                if not content:
                    content = result.get("content", "")
            
            content = content.strip()
            
            # 如果内容为空，使用后备方案
            if not content:
                self.logger.warning(f"LLM生成的首帧提示词为空，使用后备描述")
                return scene_data.visual_description or scene_data.description or f"Scene {scene_data.scene_number}: {scene_data.title}"
            
            return content
                
        except Exception as e:
            self.logger.error(f"首帧提示词生成失败: {e}")
            # 使用基础描述作为后备
            return scene_data.visual_description or scene_data.description or f"Scene {scene_data.scene_number}: {scene_data.title}"

    
    
    async def _generate_correlated_frame_prompts(
        self, 
        scene_data,  # SceneData from WorkflowState
        concept_plan: Dict[str, Any],
        execution: AgentExecution
    ) -> Dict[str, Any]:
        """
        [LEGACY/COMPATIBILITY] 生成关联的首尾帧提示词
        
        ⚠️ 此方法仅用于向下兼容旧的首尾帧方案
        新的技术方案使用 single_image_with_description (仅首帧)
        """
        
        # 获取ScriptWriter提供的场景设计元素
        scene_design = getattr(scene_data, 'scene_design_elements', {})
        narrative_structure = getattr(scene_data, 'narrative_structure', {})
        
        # 使用提示词模板系统替代112行硬编码提示词
        prompt = self.render_prompt(
            "correlated_frame_generation",
            scene_number=scene_data.scene_number,
            scene_title=scene_data.title,
            scene_duration=scene_data.duration,
            narrative_description=scene_data.narrative_description,
            scene_design=scene_design,
            narrative_structure=narrative_structure,
            concept_overview=concept_plan.get('overview', ''),
            visual_style=concept_plan.get('visual_style', ''),
            mood_and_tone=concept_plan.get('mood_and_tone', '')
        )
        
        try:
            # 使用AI配置管理器
            from ..core.ai_config import get_ai_config
            ai_config_manager = get_ai_config()
            model = ai_config_manager.get_model_for_agent("image_generator")
            model_config = ai_config_manager.get_model_config(model)
            
            # 调用AI服务
            from ..services.ai_client import AIClient
            ai_client = AIClient()
            
            response = await ai_client.generate_text(
                prompt=prompt,
                model=model,
                max_tokens=model_config.max_tokens if model_config else 2000,
                temperature=model_config.temperature if model_config else 0.7
            )
            
            # 更新token使用情况
            self._update_token_usage(
                execution, 
                response.get("usage", {}).get("total_tokens", 0)
            )
            
            # 解析响应
            import json
            content = response["content"].strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
            
            correlated_prompts = json.loads(content)
            
            self.logger.info(f"🔗 Generated CORRELATED frame prompts for scene {scene_data.scene_number} ({scene_data.duration}s)")
            return correlated_prompts
            
        except Exception as e:
            self.logger.error(f"Failed to generate correlated frame prompts for scene {scene_data.scene_number}: {str(e)}")
            # 降级到分离生成
            self.logger.info(f"Falling back to separate frame generation for scene {scene_data.scene_number}")
            return await self._generate_frame_prompts_from_scene_design(scene_data, concept_plan, execution)
    
    async def _generate_frame_prompts_from_scene_design(
        self, 
        scene_data,  # SceneData from WorkflowState
        concept_plan: Dict[str, Any],
        execution: AgentExecution
    ) -> Dict[str, Any]:
        """
        [LEGACY/COMPATIBILITY] 基于ScriptWriter的场景设计生成首尾帧提示词
        
        ⚠️ 此方法仅用于向下兼容旧的首尾帧方案
        新的技术方案使用 single_image_with_description (仅首帧)
        """
        
        # 获取ScriptWriter提供的场景设计元素
        scene_design = getattr(scene_data, 'scene_design_elements', {})
        narrative_structure = getattr(scene_data, 'narrative_structure', {})
        
        # 使用提示词模板系统替代85行硬编码提示词
        prompt = self.render_prompt(
            "scene_design_frame_generation",
            scene_number=scene_data.scene_number,
            scene_title=scene_data.title,
            scene_duration=scene_data.duration,
            narrative_description=scene_data.narrative_description,
            scene_design=scene_design,
            narrative_structure=narrative_structure,
            concept_overview=concept_plan.get('overview', ''),
            visual_style=concept_plan.get('visual_style', ''),
            mood_and_tone=concept_plan.get('mood_and_tone', '')
        )
        
        try:
            # 使用AI配置管理器
            from ..core.ai_config import get_ai_config
            ai_config_manager = get_ai_config()
            model = ai_config_manager.get_model_for_agent("image_generator")
            model_config = ai_config_manager.get_model_config(model)
            
            # 调用AI服务
            from ..services.ai_client import AIClient
            ai_client = AIClient()
            
            response = await ai_client.generate_text(
                prompt=prompt,
                model=model,
                max_tokens=model_config.max_tokens if model_config else 2000,
                temperature=model_config.temperature if model_config else 0.7
            )
            
            # 更新token使用情况
            self._update_token_usage(
                execution, 
                response.get("usage", {}).get("total_tokens", 0)
            )
            
            # 解析响应
            import json
            content = response["content"].strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
            
            frame_prompts = json.loads(content)
            
            self.logger.info(f"Generated frame prompts for scene {scene_data.scene_number}")
            return frame_prompts
            
        except Exception as e:
            self.logger.error(f"Failed to generate frame prompts for scene {scene_data.scene_number}: {str(e)}")
            # 返回fallback提示词
            return self._generate_fallback_frame_prompts(scene_data)
    
    def _generate_fallback_frame_prompts(self, scene_data) -> Dict[str, Any]:
        """生成fallback首尾帧提示词"""
        
        base_description = scene_data.narrative_description or scene_data.description or f"Scene {scene_data.scene_number}"
        
        # 提取关键元素进行一致性描述
        props = getattr(scene_data, 'props_and_objects', []) or []
        characters = getattr(scene_data, 'character_descriptions', []) or []
        
        # 构建一致的元素描述
        consistent_objects = []
        if props:
            for prop in props:
                if isinstance(prop, str):
                    # 为每个道具添加具体特征描述
                    if 'knife' in prop.lower():
                        consistent_objects.append("sharp stainless steel kitchen knife with black handle")
                    elif 'apple' in prop.lower():
                        consistent_objects.append("fresh green Granny Smith apple")
                    elif 'car' in prop.lower():
                        consistent_objects.append("white sports car")
                    else:
                        consistent_objects.append(f"specific {prop} with defined characteristics")
        
        consistent_characters = []
        if characters:
            for char in characters:
                if isinstance(char, str):
                    consistent_characters.append(f"{char} with specific clothing and appearance details")
        
        return {
            "first_frame_prompt": {
                "description": f"Static opening moment: {base_description} - scene beginning with all elements in starting positions",
                "detailed_elements": {
                    "objects": consistent_objects,
                    "characters": consistent_characters,
                    "environment": f"detailed {scene_data.mood_and_atmosphere or 'neutral'} environment"
                },
                "composition_layout": "balanced composition with clear element positioning",
                "lighting_and_mood": scene_data.mood_and_atmosphere or "neutral lighting"
            },
            "last_frame_prompt": {
                "description": f"Static closing moment: {base_description} - scene completion with same elements in final positions",
                "detailed_elements": {
                    "objects": consistent_objects,  # 相同的对象描述
                    "characters": consistent_characters,  # 相同的角色描述
                    "environment": f"same detailed {scene_data.mood_and_atmosphere or 'neutral'} environment with completion changes"
                },
                "composition_layout": "final positioning maintaining composition balance",
                "lighting_and_mood": scene_data.mood_and_atmosphere or "neutral lighting",
                "result_changes": "visible scene action results while keeping element characteristics identical"
            },
            "element_consistency_map": {
                "identical_characteristics": consistent_objects + consistent_characters,
                "evolving_states": ["position changes", "scene completion effects"]
            }
        }
    
    async def _select_generation_mode_intelligently(
        self, scene_data, workflow_state
    ) -> str:
        """直接返回新的生成模式"""
        
        # 直接使用新方案：单图 + 动作描述
        self.logger.info(f"🎯 Scene {scene_data.scene_number}: Using single_image_with_description mode")
        return "single_image_with_description"
    
    async def _generate_single_image_with_action_description(
        self, scene_data, concept_plan, execution, workflow_state_id, input_data
    ) -> Dict[str, Any]:
        """新方案: 生成首帧图像 + 完整的视频动作描述
        
        ⚠️ 架构修正：Image Generator 只负责生成图像，不处理连续性逻辑
        连续性处理由 Video Generator 负责，因为它可以访问前一场景的视频
        """
        
        # 📝 读取Script Writer设置的连续性策略
        strategy = getattr(scene_data, 'image_generation_strategy', 'new')
        depends_on_scene = getattr(scene_data, 'depends_on_scene', None)
        continuity_reason = getattr(scene_data, 'continuity_reason', '')
        
        self.logger.info(f"📋 Scene {scene_data.scene_number}: Script Writer strategy = {strategy}")
        
        # 🚫 跨组件资源优化：需要连续性的场景跳过图像生成
        if strategy == "continue_from_previous" and depends_on_scene:
            self.logger.info(
                f"🔗 Scene {scene_data.scene_number}: Skipping image generation, will use continuity from Scene {depends_on_scene} in Video Generator\n"
                f"   Reason: {continuity_reason}"
            )
            
            # 返回跳过标记，但保持接口兼容性
            return {
                "generation_mode": "single_image_with_description",
                "continuity_strategy": strategy,
                "depends_on_scene": depends_on_scene,
                "skipped": True,
                "skip_reason": "continuity_required",
                "first_frame_result": {
                    "skipped": True,
                    "message": f"Image generation skipped for Scene {scene_data.scene_number}, will use continuity from Scene {depends_on_scene}",
                    "image_url": None,
                    "image_path": None
                },
                "action_description": {
                    "action_description": f"Scene {scene_data.scene_number} will continue from Scene {depends_on_scene}",
                    "generation_method": "skipped_for_continuity",
                    "continuity_strategy": strategy
                },
                "primary_image": None  # 无主要图像，由Video Generator处理
            }
        
        # 🎨 只为独立场景生成图像
        self.logger.info(f"🎨 Scene {scene_data.scene_number}: Generating new image (independent scene)")
        first_frame_result = await self._generate_scene_image_from_data(
            scene_data, workflow_state_id, execution, input_data, "first", frame_prompts=None
        )
        
        # 🎬 生成视频动作描述
        action_description_result = await self._generate_video_action_description(
            scene_data, concept_plan, first_frame_result
        )
        
        return {
            "generation_mode": "single_image_with_description",
            "continuity_strategy": strategy,  # 记录策略但不执行
            "depends_on_scene": depends_on_scene,
            "first_frame_result": first_frame_result,
            "action_description": action_description_result,
            "primary_image": first_frame_result  # 主要图像信息
        }
    
    async def _generate_first_last_frame_images(
        self, scene_data, concept_plan, execution, workflow_state_id, input_data
    ) -> Dict[str, Any]:
        """
        [LEGACY/COMPATIBILITY] 原方案: 生成首帧 + 尾帧图像
        
        ⚠️ 此方法仅用于向下兼容，当前主流方案是 single_image_with_description
        """
        
        # First, generate CORRELATED frame prompts based on scene design and duration
        frame_prompts = await self._generate_correlated_frame_prompts(
            scene_data, concept_plan, execution
        )
        
        # Generate first frame and last frame for smooth transitions
        first_frame_result = await self._generate_scene_image_from_data(
            scene_data, workflow_state_id, execution, input_data, "first", frame_prompts=frame_prompts
        )
        last_frame_result = await self._generate_scene_image_from_data(
            scene_data, workflow_state_id, execution, input_data, "last", frame_prompts=frame_prompts
        )
        
        return {
            "generation_mode": "first_last_frame",
            "first_frame_result": first_frame_result,
            "last_frame_result": last_frame_result,
            "primary_image": first_frame_result  # 主要图像信息
        }
    
    async def _generate_video_action_description(
        self, scene_data, concept_plan, first_frame_result
    ) -> Dict[str, Any]:
        """生成完整的视频动作描述"""
        
        # 简化：不在ImageGenerator中生成详细视频描述，留给VideoGenerator
        simple_description = f"从首帧开始的{scene_data.duration}秒动态变化：{scene_data.narrative_description or scene_data.description}"
        
        self.logger.info(f"🎬 Generated simple action description for scene {scene_data.scene_number}")
        
        return {
            "action_description": simple_description,
            "first_frame_prompt": first_frame_result.get("prompt_used", ""),
            "generation_method": "simplified",
            "continuity_strategy": "new_image"  # Image Generator 始终生成新图像
        }
    
    
    def _update_scene_with_generation_result(
        self, workflow_state, scene_number, result, generation_mode
    ):
        """根据生成模式更新场景数据"""
        
        if generation_mode == "single_image_with_description":
            # 新方案更新
            first_frame_result = result["first_frame_result"]
            action_description = result["action_description"]
            
            workflow_state.update_scene(scene_number,
                # 基础图像信息
                image_prompt=first_frame_result["prompt_used"],
                image_url=first_frame_result.get("image_url", ""),
                image_path=first_frame_result.get("image_path", ""),
                first_frame_url=first_frame_result.get("image_url", ""),
                first_frame_path=first_frame_result.get("image_path", ""),
                image_generation_params=first_frame_result.get("parameters", {}),
                
                # 视频生成相关
                video_generation_mode=generation_mode,
                video_action_description=action_description.get("action_description", ""),
                
                # 新增：连续性策略信息
                scene_continuity_strategy=result.get("generation_strategy", {}).get("strategy", "new_image"),
                scene_continuity_reasoning=result.get("generation_strategy", {}).get("reasoning", "")
            )
        else:
            # 原方案更新逻辑
            first_frame_result = result["first_frame_result"]
            last_frame_result = result["last_frame_result"]
            
            workflow_state.update_scene(scene_number,
                # 保持向下兼容
                image_prompt=first_frame_result["prompt_used"],
                image_url=first_frame_result.get("image_url", ""),
                image_path=first_frame_result.get("image_path", ""),
                image_generation_params=first_frame_result.get("parameters", {}),
                # 新增首尾帧信息
                first_frame_url=first_frame_result.get("image_url", ""),
                first_frame_path=first_frame_result.get("image_path", ""),
                last_frame_url=last_frame_result.get("image_url", ""),
                last_frame_path=last_frame_result.get("image_path", ""),
                
                # 视频生成相关
                video_generation_mode=generation_mode
            )
    
    def _create_generation_result_summary(self, result, generation_mode) -> Dict[str, Any]:
        """创建生成结果摘要"""
        
        primary_image = result["primary_image"]
        
        summary = {
            "generation_mode": generation_mode,
            "first_frame_url": primary_image.get("image_url"),
            "first_frame_path": primary_image.get("image_path"),
            "prompt_used": primary_image["prompt_used"],
            "generation_model": primary_image["model"],
            "generation_parameters": primary_image.get("parameters", {})
        }
        
        if generation_mode == "first_last_frame" and "last_frame_result" in result:
            last_frame_result = result["last_frame_result"]
            summary.update({
                "last_frame_url": last_frame_result.get("image_url"),
                "last_frame_path": last_frame_result.get("image_path")
            })
        elif generation_mode == "single_image_with_description" and "action_description" in result:
            action_description = result["action_description"]
            summary.update({
                "video_description": action_description.get("action_description", "")
            })
        
        return summary
    
    async def _determine_image_generation_strategy(
        self, scene_data, workflow_state_id, concept_plan
    ) -> Dict[str, Any]:
        """
        🔗 读取Script Writer设置的连续性策略
        不再重新分析，直接使用ScriptWriter阶段确定的策略
        """
        
        # 读取Script Writer设置的连续性策略
        strategy = getattr(scene_data, 'image_generation_strategy', 'new')
        depends_on_scene = getattr(scene_data, 'depends_on_scene', None)
        continuity_reason = getattr(scene_data, 'continuity_reason', '')
        continuity_confidence = getattr(scene_data, 'continuity_confidence', 0.8)
        
        # Image Generator 始终返回 new_image 策略（连续性由 Video Generator 处理）
        return {
            "strategy": "new_image", 
            "reasoning": "Image Generator always generates new images, continuity handled by Video Generator",
            "confidence_score": 1.0,
            "source_scene": None,
            "original_strategy": strategy,  # 保留原始策略信息
            "original_depends_on_scene": depends_on_scene
        }
    
    async def _get_previous_scene_data(self, workflow_state_id: str, current_scene_number: int):
        """获取前一场景数据"""
        
        if current_scene_number <= 1:
            return None
            
        try:
            from ..core.workflow_state import workflow_manager
            workflow_state = workflow_manager.get_workflow(workflow_state_id)
            
            if not workflow_state:
                return None
            
            # 查找前一个场景
            previous_scene_number = current_scene_number - 1
            for scene in workflow_state.scenes:
                if scene.scene_number == previous_scene_number:
                    return scene
                    
            return None
            
        except Exception as e:
            self.logger.error(f"Failed to get previous scene data: {e}")
            return None
    
    async def _analyze_scene_continuity_with_llm(
        self, current_scene, previous_scene, concept_plan, workflow_state_id
    ) -> Dict[str, Any]:
        """使用LLM分析场景连续性"""
        
        # 获取工作流上下文
        from ..core.workflow_state import workflow_manager
        workflow_state = workflow_manager.get_workflow(workflow_state_id)
        
        # 构建分析提示词
        analysis_prompt = self.render_prompt(
            "scene_generation_strategy_analysis",
            current_scene_number=current_scene.scene_number,
            current_scene_title=current_scene.title,
            current_scene_description=current_scene.description,
            current_scene_narrative=getattr(current_scene, 'narrative_description', ''),
            current_scene_initial_state=getattr(current_scene, 'initial_state_description', ''),
            
            previous_scene_number=previous_scene.scene_number,
            previous_scene_title=previous_scene.title,
            previous_scene_description=previous_scene.description,
            previous_scene_narrative=getattr(previous_scene, 'narrative_description', ''),
            previous_scene_final_state=getattr(previous_scene, 'target_outcome_description', ''),
            
            user_prompt=workflow_state.user_prompt if workflow_state else '',
            intelligent_style_design=workflow_state.intelligent_style_design if workflow_state else {},  # 🔧 修复: 使用智能风格设计
            overall_concept=concept_plan.get('overview', ''),
            project_duration=workflow_state.duration if workflow_state else 30
        )
        
        try:
            # 使用AI服务分析
            from ..core.ai_config import get_ai_config
            ai_config_manager = get_ai_config()
            model = ai_config_manager.get_model_for_agent("image_generator")
            
            result = await self.use_tool(
                "image_generation", "enhance_prompt",
                {
                    "prompt": analysis_prompt, 
                    "target_style": "realistic",
                    "focus": "continuity"
                }
            )
            
            # 解析结果 - 正确处理ToolOutput对象
            import json
            
            # 获取内容
            if hasattr(result, 'result') and isinstance(result.result, dict):
                content = result.result.get("content", "")
            elif hasattr(result, 'content'):
                content = result.content
            elif isinstance(result, dict):
                content = result.get("content", "")
            else:
                content = str(result)
            
            self.logger.info(f"📝 Raw LLM response content: '{content[:200]}...' (length: {len(content)})")
            
            # 智谱AI 使用 response_format 参数时返回干净的JSON，直接解析
            # 但也处理可能的 ```json``` 包装格式作为降级
            try:
                analysis_data = json.loads(content.strip())
            except json.JSONDecodeError:
                # 降级：尝试提取 ```json``` 包装的JSON
                if "```json" in content and "```" in content:
                    import re
                    json_match = re.search(r'```json\s*({.*?})\s*```', content, re.DOTALL)
                    if json_match:
                        json_str = json_match.group(1)
                        analysis_data = json.loads(json_str)
                    else:
                        raise ValueError("Cannot extract JSON from markdown code block")
                else:
                    raise ValueError(f"Unable to parse JSON from content: {content[:100]}")
            
            # 验证必需字段
            if "strategy" not in analysis_data:
                raise ValueError("Missing 'strategy' field in LLM response")
            
            # 标准化结果
            standardized_result = {
                "strategy": analysis_data.get("strategy", "new_image"),
                "reasoning": analysis_data.get("reasoning", "LLM analysis completed"),
                "confidence_score": analysis_data.get("confidence_score", 0.8),
                "analysis_dimensions": analysis_data.get("analysis_dimensions", {}),
                "continuity_requirements": analysis_data.get("continuity_requirements", {})
            }
            
            self.logger.info(f"✨ Scene Continuity Analysis Result:")
            self.logger.info(f"   📋 Strategy: {standardized_result['strategy']}")
            self.logger.info(f"   🎯 Confidence: {standardized_result['confidence_score']}")
            self.logger.info(f"   💭 Reasoning: {standardized_result['reasoning'][:100]}...")
            
            # 如果需要连续性，标记到内存系统
            if standardized_result['strategy'] == 'continue_from_previous':
                await self._mark_scene_continuity(
                    current_scene, previous_scene, standardized_result, workflow_state_id
                )
            
            return standardized_result
            
        except Exception as e:
            self.logger.error(f"LLM scene continuity analysis failed: {e}")
            # 更详细的错误信息
            if 'result' in locals():
                self.logger.error(f"Raw result type: {type(result)}")
                if hasattr(result, 'result'):
                    self.logger.error(f"Raw result.result: {result.result}")
            raise
    
    async def _mark_scene_continuity(
        self, current_scene, previous_scene, analysis_result, workflow_state_id
    ):
        """标记场景连续性到内存系统和SceneData"""
        try:
            # 导入内存管理器
            from ..core.scene_continuity_memory import get_scene_continuity_memory
            continuity_memory = get_scene_continuity_memory()
            
            # 标记到内存系统
            await continuity_memory.mark_scene_continuity(
                current_scene_number=current_scene.scene_number,
                previous_scene_number=previous_scene.scene_number,
                reason=analysis_result['reasoning'],
                confidence=analysis_result['confidence_score']
            )
            
            # 更新当前场景的连续性字段
            current_scene.requires_continuity_from = previous_scene.scene_number
            current_scene.continuity_reason = analysis_result['reasoning'] 
            current_scene.continuity_confidence = analysis_result['confidence_score']
            
            self.logger.info(
                f"🔗 Scene {current_scene.scene_number} marked for continuity "
                f"from Scene {previous_scene.scene_number}"
            )
            
        except Exception as e:
            self.logger.error(f"Failed to mark scene continuity: {e}")
            # 不抛出异常，继续后续处理
    
    async def _extract_previous_scene_final_frame(
        self, scene_data, workflow_state_id, generation_strategy
    ) -> Dict[str, Any]:
        """
        ⚠️ [DEPRECATED] 此方法已废弃
        Image Generator 不再处理连续性逻辑，该功能已移至 Video Generator
        """
        
        self.logger.error(f"DEPRECATED: _extract_previous_scene_final_frame called for Scene {scene_data.scene_number}")
        self.logger.error("This method should not be called - continuity logic moved to Video Generator")
        
        # 返回错误标记，表明此方法不应被调用
        return {
            "error": "Method deprecated - continuity handled by Video Generator",
            "image_url": "",
            "image_path": "",
            "prompt_used": f"ERROR: Frame extraction in wrong agent - Scene {scene_data.scene_number}",
            "model": "deprecated_method",
            "parameters": {"error": "continuity_logic_moved_to_video_generator"},
            "source": "deprecated_image_generator_method"
        }
    
    async def _extract_final_frame_with_ffmpeg(self, video_path: str, scene_number: int) -> str:
        """
        ⚠️ [DEPRECATED] 此方法已废弃
        FFmpeg 视频帧提取已移至 Video Generator
        """
        
        try:
            import subprocess
            import os
            
            # 生成输出文件名
            output_filename = f"scene_{scene_number}_extracted_frame.jpg"
            output_path = self.file_storage.get_output_path(output_filename)
            
            # FFmpeg命令：提取最后一帧
            ffmpeg_cmd = [
                "ffmpeg", "-y",  # -y 覆盖输出
                "-sseof", "-1",  # 从结束前1秒开始
                "-i", video_path,  # 输入视频
                "-frames:v", "1",  # 只提取一帧
                "-q:v", "2",  # 高质量
                output_path
            ]
            
            self.logger.info(f"🎥 Extracting final frame: {' '.join(ffmpeg_cmd)}")
            
            # 执行FFmpeg命令
            process = subprocess.run(
                ffmpeg_cmd,
                capture_output=True,
                text=True,
                timeout=30  # 30秒超时
            )
            
            if process.returncode != 0:
                error_msg = process.stderr if process.stderr else "Unknown FFmpeg error"
                self.logger.error(f"FFmpeg frame extraction failed: {error_msg}")
                return ""
            
            # 验证输出文件
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                self.logger.info(f"✅ Final frame extracted successfully: {output_path}")
                return output_path
            else:
                self.logger.error(f"Final frame extraction failed: output file not created or empty")
                return ""
                
        except subprocess.TimeoutExpired:
            self.logger.error("FFmpeg frame extraction timed out")
            return ""
        except Exception as e:
            self.logger.error(f"FFmpeg frame extraction error: {e}")
            return ""