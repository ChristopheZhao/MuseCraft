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
            tools=["zhipu_client", "openai_client", "image_generation_client"]  # 注册所需的AI工具
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
        
        # 从上下文数据中获取创意指导（由Orchestrator提供）
        creative_guidance = self._extract_creative_guidance_from_context(context_data, scene_data.scene_number)
        
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
                        tool_name="zhipu_client",
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
        
        prompt_generation_request = f"""
You are a professional AI image generation prompt engineer with expertise in CogView-4 and similar models. Your task is to enhance a basic scene description into a detailed, professional prompt that will generate high-quality STATIC images.

{frame_specific_instruction}

Base Scene Description: {base_prompt}

Scene Context:
- Scene Number: {scene_data.scene_number}
- Title: {getattr(scene_data, 'title', '')}
- Duration: {getattr(scene_data, 'duration', 0)} seconds
- Mood/Atmosphere: {getattr(scene_data, 'mood_and_atmosphere', '')}
- Camera Angle: {getattr(scene_data, 'camera_angle', '')}
- Props/Objects: {getattr(scene_data, 'props_and_objects', [])}
- Character Descriptions: {getattr(scene_data, 'character_descriptions', [])}
- Visual Description: {getattr(scene_data, 'visual_description', '')}

Creative Context:
- Overall Video Concept: {creative_guidance.get('overall_guidance', {}).get('concept', '')}
- Visual Style Requirements: {creative_guidance.get('overall_guidance', {}).get('visual_style', '')}
- Target Mood: {creative_guidance.get('overall_guidance', {}).get('mood_target', '')}

Professional Image Generation Requirements:
1. STATELESS DESIGN: Each prompt must be completely self-contained for stateless APIs
2. SPECIFIC VISUAL DETAILS: Include exact colors, materials, textures, lighting
3. COMPOSITION CONTROL: Specify camera angles, framing, depth of field
4. TECHNICAL QUALITY: Add professional photography/cinematography terms
5. CONSISTENCY ELEMENTS: Ensure repeatable visual characteristics
6. COGVIEW-4 OPTIMIZATION: Use terms known to work well with AI image generation

Generate an enhanced prompt following this structure:
[CORE_SCENE] + [SPECIFIC_DETAILS] + [COMPOSITION] + [LIGHTING_MOOD] + [TECHNICAL_QUALITY] + [STYLE_MODIFIERS]

Example Enhancement Patterns:
- Instead of "apple" → "fresh red Gala apple with natural skin texture"
- Instead of "car" → "sleek white BMW M3 sedan with metallic paint finish"
- Instead of "person" → "young professional wearing navy blue business suit"
- Instead of "kitchen" → "modern kitchen with white marble countertops and stainless steel appliances"

Return ONLY the enhanced prompt text, no explanations or additional formatting.
"""
        
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
        """生成完整的首尾帧提示词，返回结构化JSON数据"""
        
        frame_generation_prompt = f"""
        你是专业的静态图像设计师，为视频生成创建首尾帧图像提示词。

        ## 关键要求
        ⚠️ **理解动态定格**: 首尾帧是动态视频中的定格瞬间，可以包含运动状态，但不描述运动过程
        ✅ **只允许**: 描述某个瞬间的画面状态（可以是动态中的定格）

        ## 场景信息
        场景时长：{scene_data.duration}秒
        场景描述：{scene_data.visual_description or scene_data.description}

        ## 动态定格描述原则

        ### 首帧 - 起始瞬间定格
        - 可描述动态状态：is running, is cutting, is flying (正在进行的动作瞬间)
        - 描述位置和姿态：leaning forward, positioned above, tilted at angle
        - 描述状态和外观：intact apple, sharp blade, focused expression
        - 禁用过程描述：从A变为B, 逐渐改变, 开始转向, 即将完成

        ### 尾帧 - 结束瞬间定格  
        - 可描述动态结果：already cut, currently separated, now visible
        - 描述最终位置：scattered pieces, blade resting beside, juice droplets suspended
        - 描述完成状态：revealed interior, divided halves, completed action
        - 禁用过程描述：切割过程中, 正在分离, 变化进行时

        ## 严格的验证检查

        ### 允许的动态定格描述
        ✅ **瞬间状态**：
        - 正在进行的动作：is cutting (刀正在切的瞬间)
        - 运动中的姿态：car speeding on track (赛车疾驰的瞬间)
        - 动态结果状态：apple split in half (苹果已分离的瞬间)

        ❌ **禁止的过程描述**：
        - 变化过程：changing from A to B, gradually becoming
        - 时间序列：then, next, followed by, after that
        - 趋势描述：about to, going to, starting to, beginning to

        ### 差异度要求
        首尾帧必须有明显的视觉差异：
        - 动态进展：从准备动作到动作完成的不同瞬间
        - 状态变化：从完整到分离，从静止到运动中
        - 位置变化：元素在不同时刻的不同位置
        - 视觉对比：足以支撑{scene_data.duration}秒的视频内容发展

        ## 输出格式

        请严格按照以下JSON格式输出：
        {{
            "first_frame_image_prompt": {{
                "description": "完整的首帧静态画面描述",
                "prohibited_words_check": true,
                "visual_elements": ["静态元素1", "静态元素2", "静态元素3"],
                "composition": "构图描述（景别、角度）",
                "style_tags": ["photorealistic", "studio lighting", "high detail"]
            }},
            "last_frame_image_prompt": {{
                "description": "完整的尾帧静态画面描述",
                "prohibited_words_check": true,
                "visual_elements": ["变化后的元素1", "新元素2", "修改的元素3"],
                "composition": "构图变化（如果有）",
                "style_tags": ["与首帧保持一致的风格"]
            }},
            "static_verification": {{
                "first_frame_is_static": true,
                "last_frame_is_static": true,
                "difference_score": 0.8,
                "key_differences": [
                    "具体差异1：从X状态到Y状态",
                    "具体差异2：元素A消失，元素B出现"
                ]
            }}
        }}

        请按照动态定格原则生成提示词。
        """
        
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
        """降级处理：生成基础的首尾帧数据结构"""
        
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
            "zhipu_client",
            "generate_text", 
            {
                "prompt": first_frame_template,
                "temperature": 0.7
            }
        )
        
        # 处理ToolOutput对象
        if hasattr(llm_result, 'result') and isinstance(llm_result.result, dict):
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
        
        # 构建LLM整合提示词
        integration_prompt = f"""
作为专业的AI图像提示词工程师，请将以下结构化的帧描述信息智能整合为一个流畅、完整的图像生成提示词：

核心描述：{frame_prompt_data.get('description', '')}

详细元素：
- 物体：{frame_prompt_data.get('detailed_elements', {}).get('objects', [])}
- 角色：{frame_prompt_data.get('detailed_elements', {}).get('characters', [])}
- 环境：{frame_prompt_data.get('detailed_elements', {}).get('environment', '')}

构图布局：{frame_prompt_data.get('composition_layout', '')}
光影氛围：{frame_prompt_data.get('lighting_and_mood', '')}
{f'场景变化：{frame_prompt_data.get("result_changes", "")}' if frame_type == "last" and frame_prompt_data.get('result_changes') else ''}

场景背景：
- 场景编号：{scene_data.scene_number}
- 帧类型：{frame_type}
- 整体氛围：{getattr(scene_data, 'mood_and_atmosphere', '')}
- 艺术风格：{getattr(scene_data, 'art_style', 'realistic')}

要求：
1. 将结构化信息自然融合成流畅的描述
2. 突出关键视觉元素
3. 保持专业的图像生成语言
4. 确保描述清晰、具体
5. 适合AI图像生成使用

请直接返回整合后的完整提示词：
"""
        
        try:
            result = await self.use_tool(
                "zhipu_client", "generate_text",
                {"prompt": integration_prompt, "temperature": 0.6}
            )
            
            # 处理结果
            if hasattr(result, 'content'):
                enhanced_prompt = result.content.strip()
            elif isinstance(result, dict):
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
        """为fallback情况生成专业的首帧提示词（符合新方案）"""
        
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
        
        # 构建专业的首帧提示词生成请求
        prompt_template = f"""
你是一位专业的视频导演和视觉设计师，需要为场景 {scene_data.scene_number} 设计首帧图像。首帧是视频的开场画面，为整个场景的发展奠定基础。

## 全局项目信息
项目总时长：{total_duration}秒
项目风格：{video_style}
用户原始需求：{user_prompt}
总场景数：{total_scenes}个

## 当前场景信息 (场景 {scene_data.scene_number}/{total_scenes} - {scene_position}场景)
标题：{scene_data.title}
时长：{scene_data.duration}秒 (占总时长的 {scene_percentage:.1f}%)
场景描述：{scene_data.description}
视觉描述：{getattr(scene_data, 'visual_description', '')}
叙事描述：{getattr(scene_data, 'narrative_description', '')}
氛围风格：{getattr(scene_data, 'mood_and_atmosphere', '')}
艺术风格：{getattr(scene_data, 'art_style', 'realistic')}
光影风格：{getattr(scene_data, 'lighting_style', 'natural')}

## 叙事流动策略
整体节奏：{narrative_flow.get('pacing_strategy', '标准节奏')}
情绪基调：{narrative_flow.get('mood_and_tone', '中性基调')}
过渡理念：{narrative_flow.get('transition_philosophy', '自然过渡')}

## 场景定位分析
场景在项目中的作用：{scene_position}场景 ({scene_percentage:.1f}%占比)
{f'承接功能：需要与前序场景自然衔接' if scene_data.scene_number > 1 else '开场功能：需要吸引注意力并建立背景'}
{f'发展功能：需要为后续场景做好铺垫' if scene_data.scene_number < total_scenes else '收尾功能：需要完成整体叙事闭环'}

## 创意总监完整指导
{creative_guidance}

## 专业首帧设计原则

### 1. 叙事功能精准定位
- **静态起点状态**：只展现动作开始前的完全静态状态，所有元素处于准备位置
- **准备状态设计**：画面要显示即将发生动作的准备阶段，但不展现动作本身
- **节奏协调**：作为{scene_position}场景，需要与整体{total_duration}秒节奏保持协调

### 2. 专业构图策略
- **焦点引导**：主体位置安排要引导观众视线，为动态发展做准备
- **空间预留**：为关键动作和变化预留足够的视觉发展空间
- **层次构建**：前中后景的安排要服务于叙事需求

### 3. 技术标准匹配
- **CogVideoX单图模式优化**：确保首帧适合作为视频生成的起始图像
- **动态潜能体现**：虽是静止画面，但要蕴含动态发展的视觉暗示
- **质量标准**：达到专业{video_style}风格的制作水准

### 4. 整体项目融合
- **风格统一**：与{video_style}项目风格完美契合
- **色彩协调**：考虑与其他场景的视觉连续性
- **品质保证**：符合{total_duration}秒短视频的专业标准

## 输出任务
基于以上分析，生成一个**CogView-4优化的首帧图像生成提示词**，要求：

1. **自然语言描述**：使用流畅的自然语言，而非标签式枚举
2. **详细具体**：包含主体特征、环境细节、光影氛围、构图安排
3. **首帧特性**：只描述动作开始前的初始状态，不包含任何动作过程或结果

**首帧状态要求**：
- 主体元素：必须是完整、未改变的原始形态，不包含任何本场景将要发生的变化特征
- 环境设置：展现适合动作发生的基础环境，但环境本身未被动作影响
- 相关道具：处于静置或常规位置，不暗示即将使用
- 整体氛围：静态、稳定，不含动态元素

**输出要求**：
直接描述符合上述状态的画面，无需解释或推理为什么这样设计。专注于视觉呈现，避免任何动作逻辑的体现。

请按以下格式生成完整的自然语言描述：
"在[环境背景描述]中，[主体元素的原始完整状态]。[相关元素的初始位置和状态]。[光影和氛围描述]，[构图和视觉细节]，呈现出[整体风格和质感]的专业画面效果。"

直接返回完整的提示词描述： 
"""
        
        try:
            from ..core.ai_config import get_ai_config
            ai_config_manager = get_ai_config()
            model = ai_config_manager.get_model_for_agent("image_generator")
            
            result = await self.use_tool(
                "zhipu_client", "generate_text",
                {"prompt": prompt_template, "temperature": 0.7}
            )
            
            # 提取生成的内容
            content = ""
            if hasattr(result, 'result') and isinstance(result.result, dict):
                # ToolOutput对象，从result.result中获取content
                content = result.result.get("content", "")
            elif hasattr(result, 'content'):
                content = result.content or ""
            elif isinstance(result, dict):
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

    
    
    async def _get_technical_specifications(
        self, 
        scene_data, 
        creative_guidance: Dict[str, Any], 
        frame_type: str
    ) -> List[str]:
        """通过LLM智能生成技术规格和质量控制参数"""
        
        # 收集上下文信息
        visual_style_guidance = creative_guidance.get("overall_guidance", {}).get("visual_style_guidance", {})
        
        context = {
            "scene_type": getattr(scene_data, 'scene_type', ''),
            "frame_type": frame_type,
            "visual_description": getattr(scene_data, 'visual_description', ''),
            "mood_and_atmosphere": getattr(scene_data, 'mood_and_atmosphere', ''),
            "art_style": getattr(scene_data, 'art_style', 'realistic'),
            "lighting_style": getattr(scene_data, 'lighting_style', 'natural'),
            "primary_style": visual_style_guidance.get("primary_style", ""),
            "scene_setting": creative_guidance.get("overall_guidance", {}).get("scene_setting", "")
        }
        
        # 通过LLM生成技术规格
        try:
            prompt = f"""
作为专业的图像技术总监，基于以下场景信息，为AI图像生成提供专业的技术规格建议：

场景信息：
- 场景类型：{context['scene_type']}
- 帧类型：{context['frame_type']}
- 视觉描述：{context['visual_description']}
- 氛围风格：{context['mood_and_atmosphere']}
- 艺术风格：{context['art_style']}
- 光影风格：{context['lighting_style']}
- 主体风格：{context['primary_style']}

请提供4-6个精准的技术质量参数，用于优化CogView-4的生成效果。
要求：
1. 基于场景特点选择最合适的质量参数
2. 避免通用词汇，提供具体的技术指导
3. 考虑AI生成的特点和局限性

请以简洁的短语列表形式返回，一行一个参数：
"""
            
            result = await self.use_tool(
                "zhipu_client", "generate_text",
                {"prompt": prompt, "temperature": 0.5}
            )
            
            # 处理结果
            if hasattr(result, 'content'):
                specs_text = result.content.strip()
            elif isinstance(result, dict):
                specs_text = result.get("content", "").strip()
            else:
                specs_text = str(result).strip()
            
            # 解析为列表
            specs = [spec.strip() for spec in specs_text.split('\n') if spec.strip()]
            
            # 确保最少有基础质量参数
            if not specs:
                specs = ['high resolution', 'sharp focus', 'professional quality']
                
            return specs[:6]  # 限制最多6个
            
        except Exception as e:
            self.logger.error(f"技术规格生成失败: {e}")
            # 返回基础规格作为后备
            return ['high resolution', 'sharp focus', 'professional quality']
    
    async def _generate_correlated_frame_prompts(
        self, 
        scene_data,  # SceneData from WorkflowState
        concept_plan: Dict[str, Any],
        execution: AgentExecution
    ) -> Dict[str, Any]:
        """生成关联的首尾帧提示词 - 在同一个模板中考虑场景关联和duration推理"""
        
        # 获取ScriptWriter提供的场景设计元素
        scene_design = getattr(scene_data, 'scene_design_elements', {})
        narrative_structure = getattr(scene_data, 'narrative_structure', {})
        
        # 构建关联的首尾帧生成请求 - 通过先验知识注入
        prompt = f"""
You are a professional visual sequence designer with deep expertise in AI image generation, specifically CogView-4 and similar stateless APIs. Your task is to create CORRELATED first and last frame prompts that maintain perfect consistency.

PRIOR KNOWLEDGE for High-Quality Image Generation:
- Stateless APIs like CogView-4 have no memory between calls, so each prompt must be completely self-contained
- Specific details prevent variation: "red apple" can vary, but "fresh Gala apple with red-yellow gradient skin" is consistent
- Professional photography terms improve quality: "shallow depth of field", "studio lighting", "50mm lens"
- Temporal indicators must be static: use "positioned above" not "moving towards", "resting beside" not "falling"
- Consistency requires identical phrasing: if first frame has "Wüsthof chef's knife", last frame must use exact same phrase

IMPORTANT: Generate BOTH frames in ONE request using your expertise to ensure perfect visual consistency.

Scene Information:
- Scene Number: {scene_data.scene_number}
- Title: {scene_data.title}
- Duration: {scene_data.duration} seconds
- Narrative Description: {scene_data.narrative_description}

Scene Design Elements from Script Writer:
- Key Subjects: {scene_design.get('key_subjects', [])}
- Scene Setting: {scene_design.get('scene_setting', '')}
- Visual Style Notes: {scene_design.get('visual_style_notes', '')}
- Composition Requirements: {scene_design.get('composition_requirements', '')}
- Continuity Elements: {scene_design.get('continuity_elements', [])}

Narrative Structure:
- Opening State: {narrative_structure.get('opening_state', '')}
- Main Action: {narrative_structure.get('main_action', '')}
- Closing State: {narrative_structure.get('closing_state', '')}
- Story Function: {narrative_structure.get('story_function', '')}

Video Context:
- Overall Concept: {concept_plan.get('overview', '')}
- Visual Style: {concept_plan.get('visual_style', '')}
- Mood and Tone: {concept_plan.get('mood_and_tone', '')}

DURATION-AWARE PROGRESSION ANALYSIS:
- Short Duration (1-3s): Minimal change, subtle progression
- Medium Duration (4-7s): Moderate change, clear progression  
- Long Duration (8+s): Significant change, dramatic progression

For this {scene_data.duration}-second scene, design the appropriate level of visual change.

Generate CORRELATED frame descriptions in JSON format:

{{
    "visual_progression_analysis": {{
        "duration_category": "short/medium/long based on {scene_data.duration} seconds",
        "change_intensity": "minimal/moderate/significant change level",
        "progression_type": "describe the type of visual progression (positional, transformational, environmental)",
        "key_continuity_elements": ["elements that must remain identical"],
        "evolving_elements": ["elements that change between frames"]
    }},
    "first_frame_prompt": {{
        "description": "[COMPLETE PROFESSIONAL PROMPT] Generate a comprehensive, production-ready prompt that includes: (1) Main subject with exact colors, materials, textures (e.g., 'fresh green Granny Smith apple with waxy skin'); (2) Precise positioning and composition (e.g., 'centered on polished oak cutting board'); (3) Professional lighting setup (e.g., 'soft natural light from 45-degree angle'); (4) Camera specifications (e.g., 'medium shot, shallow depth of field'); (5) Technical quality (e.g., 'high resolution, sharp focus, professional photography'); (6) Environmental context. This must be the INITIAL STATE before any action occurs.",
        "detailed_elements": {{
            "consistent_objects": ["objects with EXACT color/material/characteristics that MUST remain identical"],
            "consistent_characters": ["characters with EXACT clothing/appearance that MUST remain identical"],
            "consistent_environment": "environment description with EXACT materials/colors/lighting",
            "starting_positions": "precise spatial arrangement of all elements at scene start"
        }},
        "composition_and_technical": {{
            "camera_angle": "specific camera perspective and framing",
            "lighting_setup": "detailed lighting conditions and mood",
            "depth_and_focus": "depth of field and focus specifications"
        }}
    }},
    "last_frame_prompt": {{
        "description": "[COMPLETE PROFESSIONAL PROMPT] Generate a comprehensive, production-ready prompt with IDENTICAL subjects as first frame but showing RESULT state. Include: (1) SAME subjects with EXACT SAME colors/materials but in final state (e.g., 'same green Granny Smith apple now cut in half'); (2) SAME environment and lighting; (3) Visible changes from action (e.g., 'juice droplets on board'); (4) SAME camera angle and technical specifications; (5) All continuity elements must use IDENTICAL descriptions. This must be the FINAL STATE after action is complete.",
        "detailed_elements": {{
            "consistent_objects": ["SAME objects with IDENTICAL color/material/characteristics as first frame"],
            "consistent_characters": ["SAME characters with IDENTICAL clothing/appearance as first frame"],
            "consistent_environment": "SAME environment with identical materials/colors but showing changes",
            "final_positions": "precise spatial arrangement showing progression from first frame"
        }},
        "progression_changes": {{
            "position_changes": "how elements moved/repositioned during scene",
            "state_changes": "what transformations occurred (cut fruit, opened door, etc.)",
            "environmental_effects": "visible results of the scene action"
        }},
        "composition_and_technical": {{
            "camera_angle": "same or logically evolved camera perspective",
            "lighting_setup": "same or naturally evolved lighting conditions",
            "depth_and_focus": "same or appropriately adjusted focus"
        }}
    }},
    "consistency_verification": {{
        "identical_descriptions": ["exact phrases that appear in BOTH frame descriptions"],
        "progression_logic": "explanation of how the frames connect logically",
        "duration_appropriateness": "why this level of change fits the {scene_data.duration}s duration"
    }}
}}

BEST PRACTICES from Professional Image Generation Experience:

Example of GOOD correlated prompts:
First: "Fresh Gala apple with red-yellow gradient skin positioned on bamboo cutting board, Wüsthof chef's knife with black handle poised 2 inches above apple center, soft studio lighting from left, 50mm lens, shallow depth of field"
Last: "Same Gala apple now cleanly halved showing white flesh and brown seeds on same bamboo cutting board, same Wüsthof chef's knife resting beside apple halves, same soft studio lighting, same 50mm lens perspective"

Example of BAD prompts (lacking consistency):
First: "Apple on board with knife"
Last: "Cut fruit with blade nearby"

Key insights from thousands of generations:
- Specificity creates consistency: exact brands, materials, measurements
- Static descriptions prevent motion blur: "positioned at" vs "moving to"
- Identical phrasing maintains continuity: copy exact descriptions
- Professional terms enhance quality: proper photography vocabulary
- Complete information enables independence: full scene in each prompt

Return only the JSON object, no additional text.
"""
        
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
        """基于ScriptWriter的场景设计生成首尾帧提示词"""
        
        # 获取ScriptWriter提供的场景设计元素
        scene_design = getattr(scene_data, 'scene_design_elements', {})
        narrative_structure = getattr(scene_data, 'narrative_structure', {})
        
        # 构建首尾帧提示词生成的AI请求
        prompt = f"""
You are a professional visual prompt generator for AI image generation. Based on the scene design from the Script Writer, create detailed static frame descriptions for video generation.

Scene Information:
- Scene Number: {scene_data.scene_number}
- Title: {scene_data.title}
- Duration: {scene_data.duration} seconds
- Narrative Description: {scene_data.narrative_description}

Scene Design Elements from Script Writer:
- Key Subjects: {scene_design.get('key_subjects', [])}
- Scene Setting: {scene_design.get('scene_setting', '')}
- Visual Style Notes: {scene_design.get('visual_style_notes', '')}
- Composition Requirements: {scene_design.get('composition_requirements', '')}
- Continuity Elements: {scene_design.get('continuity_elements', [])}

Narrative Structure:
- Opening State: {narrative_structure.get('opening_state', '')}
- Main Action: {narrative_structure.get('main_action', '')}
- Closing State: {narrative_structure.get('closing_state', '')}
- Story Function: {narrative_structure.get('story_function', '')}

Video Context:
- Overall Concept: {concept_plan.get('overview', '')}
- Visual Style: {concept_plan.get('visual_style', '')}
- Mood and Tone: {concept_plan.get('mood_and_tone', '')}

IMPORTANT: CogView-4 API is STATELESS - each prompt must fully describe all visual elements independently. 
For elements that appear in both frames, use IDENTICAL descriptive language to ensure visual consistency.

Example Consistency Requirements:
- If first frame has "red Ferrari sports car", last frame must also specify "red Ferrari sports car"
- If first frame has "person wearing blue denim jacket", last frame must specify "person wearing blue denim jacket"
- If first frame has "green Granny Smith apple", last frame must specify "green Granny Smith apple (now cut in half)"
- If first frame has "stainless steel kitchen knife", last frame must specify "stainless steel kitchen knife"

Please generate detailed static frame descriptions in JSON format:

{{
    "first_frame_prompt": {{
        "description": "Complete self-contained static image description with EXACT characteristics of all elements",
        "detailed_elements": {{
            "objects": ["specific object with exact colors, materials, and characteristics"],
            "characters": ["character with specific clothing, appearance details"],
            "environment": "detailed setting with specific materials, colors, lighting"
        }},
        "composition_layout": "Precise spatial arrangement of all elements",
        "lighting_and_mood": "Specific lighting style and atmospheric details"
    }},
    "last_frame_prompt": {{
        "description": "Complete self-contained static image description maintaining IDENTICAL characteristics for continuing elements",
        "detailed_elements": {{
            "objects": ["same objects with identical colors/materials but showing result changes"],
            "characters": ["same character with identical clothing/appearance in final position"],
            "environment": "same environment with identical materials/colors plus visible changes"
        }},
        "composition_layout": "Precise spatial arrangement showing final positions",
        "lighting_and_mood": "Lighting description (identical or logically evolved)",
        "result_changes": "Specific visible changes while maintaining element consistency"
    }},
        "element_consistency_map": {{
        "identical_characteristics": ["list of exact descriptions that must be identical in both frames"],
        "evolving_states": ["list of what changes between frames while keeping core characteristics"]
    }}
}}

CRITICAL Guidelines for Stateless Image Generation API:
1. Create STATIC SNAPSHOT descriptions - NO motion or action words
2. Each frame prompt must be COMPLETELY SELF-CONTAINED with full element descriptions
3. SPECIFY EXACT VISUAL CHARACTERISTICS for consistent elements:
   - Colors: "green apple" (not just "apple") 
   - Objects: "white GTR sports car" (not just "car")
   - Materials: "wooden cutting board" (not just "cutting board")
   - People: "person wearing blue shirt" (not just "person")
4. For CONTINUITY ELEMENTS that appear in both frames, use IDENTICAL descriptions:
   - First frame: "sharp silver kitchen knife with black handle"
   - Last frame: "sharp silver kitchen knife with black handle" (same exact description)
5. Only describe RESULT CHANGES, keep object characteristics identical:
   - First frame: "whole green apple on wooden cutting board"
   - Last frame: "green apple cut in half on wooden cutting board" (apple stays green, board stays wooden)
6. Use precise positional language: "character stands beside table" NOT "character approaches table"
7. Each prompt must work independently - API has no memory of previous generations
8. Environmental changes should be visible but core element properties stay consistent

Return only the JSON object, no additional text.
"""
        
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
        """新方案：生成首帧图像 + 完整的视频动作描述"""
        
        # 1. 生成首帧图像（复用现有逻辑）
        first_frame_result = await self._generate_scene_image_from_data(
            scene_data, workflow_state_id, execution, input_data, "first", frame_prompts=None
        )
        
        # 2. 生成视频动作描述
        action_description_result = await self._generate_video_action_description(
            scene_data, concept_plan, first_frame_result
        )
        
        return {
            "generation_mode": "single_image_with_description",
            "first_frame_result": first_frame_result,
            "action_description": action_description_result,
            "primary_image": first_frame_result  # 主要图像信息
        }
    
    async def _generate_first_last_frame_images(
        self, scene_data, concept_plan, execution, workflow_state_id, input_data
    ) -> Dict[str, Any]:
        """原方案：生成首帧 + 尾帧图像"""
        
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
            "generation_method": "simplified"
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
                video_action_description=action_description.get("action_description", "")
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