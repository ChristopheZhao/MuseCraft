"""
AI Client service for interacting with various AI APIs
"""
import asyncio
import aiohttp
import openai
import logging
from typing import Dict, Any, Optional, List
from ..core.config import settings


class AIClientError(Exception):
    """Base exception for AI client errors"""
    pass


class AIClient:
    """Unified client for various AI services"""
    
    def __init__(self):
        self.logger = logging.getLogger("ai_client")
        
        # Initialize GLM client (智谱AI) - 优先使用
        self.glm_client = None
        if settings.GLM_API_KEY:
            try:
                # 动态导入，避免依赖问题
                import zhipuai
                self.glm_client = zhipuai.ZhipuAI(api_key=settings.GLM_API_KEY)
                self.logger.info("GLM client initialized successfully")
            except ImportError:
                self.logger.warning("zhipuai package not installed, please run: pip install zhipuai")
            except Exception as e:
                self.logger.error(f"Failed to initialize GLM client: {e}")
        else:
            self.logger.warning("GLM_API_KEY not configured")
        
        # Initialize OpenAI client as fallback
        self.openai_client = None
        if settings.OPENAI_API_KEY:
            self.openai_client = openai.AsyncOpenAI(
                api_key=settings.OPENAI_API_KEY
            )
            self.logger.info("OpenAI client initialized as fallback")
        else:
            self.logger.warning("OpenAI API key not configured")
    
    async def generate_text(
        self,
        prompt: str,
        model: str = "glm-4-plus",
        max_tokens: int = 1000,
        temperature: float = 0.7,
        **kwargs
    ) -> Dict[str, Any]:
        """Generate text using GLM models (primary) or OpenAI models (fallback)"""
        
        # Try GLM first if available
        if self.glm_client:
            try:
                # 容错：允许调用方传入None/空字符串，自动回退至默认模型
                safe_model = model or settings.GLM_DEFAULT_MODEL or "glm-4-plus"
                self.logger.info(f"Using GLM model: {safe_model}")
                glm_model = safe_model if str(safe_model).startswith("glm-") else (settings.GLM_DEFAULT_MODEL or "glm-4-plus")
                
                response = self.glm_client.chat.completions.create(
                    model=glm_model,
                    messages=[
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=max_tokens,
                    temperature=temperature,
                    **kwargs
                )
                
                return {
                    "content": response.choices[0].message.content,
                    "usage": {
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens,
                        "total_tokens": response.usage.total_tokens
                    },
                    "model": response.model,
                    "provider": "glm"
                }
                
            except Exception as e:
                self.logger.warning(f"GLM text generation failed, falling back to OpenAI: {str(e)}")
        
        # Fallback to OpenAI
        if self.openai_client:
            try:
                self.logger.info("Using OpenAI as fallback")
                # Map GLM model to OpenAI model
                model_str = (model or "")
                openai_model = "gpt-3.5-turbo" if model_str.startswith("glm-") or not model_str else model_str
                
                response = await self.openai_client.chat.completions.create(
                    model=openai_model,
                    messages=[
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=max_tokens,
                    temperature=temperature,
                    **kwargs
                )
                
                return {
                    "content": response.choices[0].message.content,
                    "usage": {
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens,
                        "total_tokens": response.usage.total_tokens
                    },
                    "model": response.model,
                    "provider": "openai"
                }
                
            except Exception as e:
                self.logger.error(f"OpenAI text generation failed: {str(e)}")
                raise AIClientError(f"Text generation failed: {str(e)}") from e
        
        raise AIClientError("No AI client available (neither GLM nor OpenAI configured)")
    
    async def generate_image(
        self,
        prompt: str,
        model: str = "dall-e-3",
        size: str = "1024x1024",
        quality: str = "standard",
        **kwargs
    ) -> Dict[str, Any]:
        """Generate image using OpenAI DALL-E"""
        
        if not self.openai_client:
            raise AIClientError("OpenAI client not configured")
        
        try:
            response = await self.openai_client.images.generate(
                model=model,
                prompt=prompt,
                size=size,
                quality=quality,
                n=1,
                **kwargs
            )
            
            return {
                "image_url": response.data[0].url,
                "revised_prompt": getattr(response.data[0], 'revised_prompt', prompt),
                "model": model,
                "size": size,
                "quality": quality
            }
            
        except Exception as e:
            self.logger.error(f"OpenAI image generation failed: {str(e)}")
            raise AIClientError(f"Image generation failed: {str(e)}") from e
    
    async def generate_image_glm(
        self,
        prompt: str,
        size: str = "1024x1024",
        model: str = "cogview-4",
        **kwargs
    ) -> Dict[str, Any]:
        """Generate image using GLM CogView"""
        
        if not self.glm_client:
            raise AIClientError("GLM client not configured")
        
        try:
            response = self.glm_client.images.generations(
                model=model,
                prompt=prompt,
                size=size,
                **kwargs
            )
            
            return {
                "image_url": response.data[0].url,
                "revised_prompt": getattr(response.data[0], 'revised_prompt', prompt),
                "model": model,
                "size": size
            }
            
        except Exception as e:
            self.logger.error(f"GLM image generation failed: {str(e)}")
            raise AIClientError(f"GLM image generation failed: {str(e)}") from e
    
    async def generate_video_runway(
        self,
        prompt: str,
        image_url: Optional[str] = None,
        duration: int = 4,
        **kwargs
    ) -> Dict[str, Any]:
        """Generate video using Runway ML API"""
        
        if not settings.RUNWAY_API_KEY:
            raise AIClientError("Runway API key not configured")
        
        headers = {
            "Authorization": f"Bearer {settings.RUNWAY_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "textPrompt": prompt,
            "duration": duration,
            **kwargs
        }
        
        if image_url:
            payload["imageUrl"] = image_url
        
        try:
            async with aiohttp.ClientSession() as session:
                # Start generation
                async with session.post(
                    "https://api.runwayml.com/v1/video/generate",
                    headers=headers,
                    json=payload
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise AIClientError(f"Runway API error: {error_text}")
                    
                    generation_data = await response.json()
                    task_id = generation_data["id"]
                
                # Poll for completion
                return await self._poll_runway_generation(session, headers, task_id)
                
        except Exception as e:
            self.logger.error(f"Runway video generation failed: {str(e)}")
            raise AIClientError(f"Video generation failed: {str(e)}") from e
    
    async def _poll_runway_generation(
        self,
        session: aiohttp.ClientSession,
        headers: Dict[str, str],
        task_id: str,
        max_wait: int = 300  # 5 minutes
    ) -> Dict[str, Any]:
        """Poll Runway API for generation completion"""
        
        start_time = asyncio.get_event_loop().time()
        
        while True:
            async with session.get(
                f"https://api.runwayml.com/v1/video/generate/{task_id}",
                headers=headers
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise AIClientError(f"Runway polling error: {error_text}")
                
                result = await response.json()
                status = result.get("status")
                
                if status == "COMPLETED":
                    return {
                        "video_url": result["output"][0],
                        "task_id": task_id,
                        "duration": result.get("duration"),
                        "status": status
                    }
                elif status == "FAILED":
                    error_msg = result.get("error", "Unknown error")
                    raise AIClientError(f"Runway generation failed: {error_msg}")
                
                # Check timeout
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed > max_wait:
                    raise AIClientError("Runway generation timed out")
                
                # Wait before next poll
                await asyncio.sleep(5)
    
    async def generate_video_glm(
        self,
        prompt: str,
        image_url: Optional[str] = None,
        first_frame_image: Optional[str] = None,
        last_frame_image: Optional[str] = None,
        duration: int = 5,
        **kwargs
    ) -> Dict[str, Any]:
        """Generate video using GLM CogVideoX-3 API with first/last frame support"""
        
        if not settings.GLM_API_KEY:
            raise AIClientError("GLM API key not configured")
        
        # GLM CogVideoX uses zhipuai client
        try:
            # Import zhipuai client
            from zhipuai import ZhipuAI
            
            client = ZhipuAI(api_key=settings.GLM_API_KEY)

            configured_video_model = (getattr(settings, "COGVIDEOX3_MODEL", None) or "").strip()
            model_override = kwargs.get("model")
            target_model = model_override or configured_video_model
            if not target_model:
                raise AIClientError(
                    "GLM video model is not configured; set COGVIDEOX3_MODEL in env/config or pass model explicitly"
                )
            
            # Prepare request parameters - use CogVideoX-3 API format
            video_params = {
                "model": target_model,
                "prompt": prompt,
            }
            
            # Add image input - support multiple modes
            if first_frame_image and last_frame_image:
                # 首尾帧模式 (CogVideoX-3新功能) - image_url参数传入列表
                video_params["image_url"] = [first_frame_image, last_frame_image]
                self.logger.info(f"🎬 Using first/last frame mode: {first_frame_image} → {last_frame_image}")
            elif image_url:
                # 传统单图模式 (向下兼容)
                video_params["image_url"] = image_url
                self.logger.info(f"🎬 Using single image mode: {image_url}")
            else:
                # 纯文本模式
                self.logger.info(f"🎬 Using text-to-video mode")
            
            # Add official API parameters
            if "quality" in kwargs:
                video_params["quality"] = kwargs["quality"]
            if "with_audio" in kwargs:
                video_params["with_audio"] = kwargs["with_audio"]
            if "size" in kwargs:
                video_params["size"] = kwargs["size"]
            if "fps" in kwargs:
                video_params["fps"] = kwargs["fps"]
            
            self.logger.info(f"Generating video with GLM CogVideoX: {video_params}")
            
            # Call CogVideoX API to start generation
            response = client.videos.generations(
                **video_params
            )
            
            self.logger.info(f"GLM video generation started, task_id: {response.id}, status: {response.task_status}")
            
            # Poll for completion (GLM CogVideoX is async)
            return await self._poll_glm_video_generation(client, response.id, prompt, target_model)
                
        except Exception as e:
            self.logger.error(f"GLM video generation failed: {str(e)}")
            raise AIClientError(f"GLM video generation failed: {str(e)}") from e
    
    async def _poll_glm_video_generation(
        self,
        client,
        task_id: str,
        prompt: str,
        model: Optional[str] = None,
        max_wait: int = 600  # 10 minutes for video generation
    ) -> Dict[str, Any]:
        """Poll GLM CogVideoX API for video generation completion"""
        
        start_time = asyncio.get_event_loop().time()
        
        while True:
            try:
                # Check generation status
                result = client.videos.retrieve_videos_result(task_id)
                
                self.logger.info(f"GLM video generation status: {result.task_status}")
                
                if result.task_status == "SUCCESS":
                    # Generation completed successfully
                    if result.video_result and len(result.video_result) > 0:
                        video_data = result.video_result[0]
                        return {
                            "video_url": video_data.url,
                            "task_id": task_id,
                            "status": "completed",
                            "model": model,
                            "prompt": prompt,
                            "cover_image_url": getattr(video_data, 'cover_image_url', None)
                        }
                    else:
                        raise AIClientError("No video data in successful GLM response")
                        
                elif result.task_status == "FAIL":
                    error_msg = getattr(result, 'error', 'Unknown error')
                    raise AIClientError(f"GLM video generation failed: {error_msg}")
                
                # Check timeout
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed > max_wait:
                    raise AIClientError("GLM video generation timed out")
                
                # Wait before next poll (GLM recommends polling every 5-10 seconds)
                await asyncio.sleep(10)
                
            except Exception as e:
                if "GLM video generation" in str(e):
                    raise
                else:
                    self.logger.error(f"GLM polling error: {str(e)}")
                    raise AIClientError(f"GLM polling failed: {str(e)}") from e
    
    async def generate_image_stability(
        self,
        prompt: str,
        width: int = 1024,
        height: int = 1024,
        cfg_scale: float = 7.0,
        steps: int = 20,
        **kwargs
    ) -> Dict[str, Any]:
        """Generate image using Stability AI"""
        
        if not settings.STABILITY_API_KEY:
            raise AIClientError("Stability AI API key not configured")
        
        headers = {
            "Authorization": f"Bearer {settings.STABILITY_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "text_prompts": [
                {"text": prompt, "weight": 1.0}
            ],
            "width": width,
            "height": height,
            "cfg_scale": cfg_scale,
            "steps": steps,
            "samples": 1,
            **kwargs
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.stability.ai/v1/generation/stable-diffusion-xl-1024-v1-0/text-to-image",
                    headers=headers,
                    json=payload
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise AIClientError(f"Stability AI error: {error_text}")
                    
                    result = await response.json()
                    
                    return {
                        "image_base64": result["artifacts"][0]["base64"],
                        "seed": result["artifacts"][0]["seed"],
                        "finish_reason": result["artifacts"][0]["finishReason"],
                        "model": "stable-diffusion-xl-1024-v1-0"
                    }
                    
        except Exception as e:
            self.logger.error(f"Stability AI image generation failed: {str(e)}")
            raise AIClientError(f"Image generation failed: {str(e)}") from e
    
    async def enhance_prompt(
        self,
        original_prompt: str,
        context: str = "",
        style: str = "professional"
    ) -> str:
        """Enhance a prompt for better AI generation results"""
        
        enhancement_prompt = f"""
You are a prompt enhancement specialist. Improve the following prompt to get better results from AI image/video generation models.

Original prompt: {original_prompt}
Context: {context}
Desired style: {style}

Enhanced prompt should:
1. Be more descriptive and detailed
2. Include relevant visual elements, lighting, composition
3. Add style and quality modifiers
4. Remove ambiguous language
5. Be optimized for AI generation

Return only the enhanced prompt, no explanation.
"""
        
        try:
            response = await self.generate_text(
                prompt=enhancement_prompt,
                model="glm-4-plus",  # Use GLM-4-Plus as primary model
                max_tokens=200,
                temperature=0.3
            )
            
            return response["content"].strip()
            
        except Exception as e:
            self.logger.warning(f"Prompt enhancement failed: {str(e)}")
            # Return original prompt if enhancement fails
            return original_prompt
