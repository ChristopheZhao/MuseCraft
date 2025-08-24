"""
Video Generator Agent - Generates video clips from images and prompts
"""
import asyncio
import os
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from .base import BaseAgent, AgentError
from ..models import Task, AgentExecution, AgentType, Scene, Resource, ResourceType
from ..services.file_storage import FileStorageService
from ..services.ai_client import AIClient
from ..core.video_config_manager import get_video_config


class VideoGeneratorAgent(BaseAgent):
    """
    Video Generator Agent creates video clips from generated images and scene descriptions
    """
    
    def __init__(self):
        super().__init__(
            agent_type=AgentType.VIDEO_GENERATOR,
            agent_name="video_generator",
            timeout_seconds=900,  # 15 minutes for video generation
            max_retries=2
            # tools 将由工具分配系统自动设置
        )
        self.file_storage = FileStorageService()
        self.logger.info(f"VideoGeneratorAgent initialized with specialized tools: {self.get_tool_names()}")
    
    def get_tool_names(self):
        """获取已分配工具名称列表"""
        return [tool_name for tool_name in self._available_tools.keys()] if self._available_tools else []
    
    async def _execute_impl(
        self, 
        task: Task, 
        input_data: Dict[str, Any], 
        execution: AgentExecution,
        db: Session
    ) -> Dict[str, Any]:
        """Generate video clips for all scenes"""
        
        # Validate input
        self._validate_input(input_data, ["workflow_state_id"])
        
        workflow_state_id = input_data["workflow_state_id"]
        
        # 🧠 Phase 1.2 - 实现MAS记忆共享：VideoGenerator检索创意指导
        concept_plan = {}
        try:
            retrieved_guidance = await self.retrieve_creative_guidance(workflow_state_id)
            if retrieved_guidance:
                concept_plan = retrieved_guidance
                self.logger.info(f"🧠 VideoGenerator: 成功检索到创意指导，增强视频理解")
            else:
                self.logger.warning(f"⚠️ VideoGenerator: 未找到创意指导记忆")
        except Exception as e:
            self.logger.warning(f"⚠️ VideoGenerator: 记忆检索失败 - {e}")
        
        # 通过 workflow_manager 获取 WorkflowState
        from ..core.workflow_state import workflow_manager
        workflow_state = workflow_manager.get_workflow(workflow_state_id)
        if not workflow_state:
            raise AgentError(f"WorkflowState {workflow_state_id} not found")
        
        await self._update_progress(execution, 10, "Loading scenes and images", db)
        
        # Get scenes from WorkflowState
        scenes_data = workflow_state.scenes
        if not scenes_data:
            raise AgentError("No scenes found in workflow state")
        
        generated_videos = []
        total_scenes = len(scenes_data)
        
        # Generate video for each scene using Function Call
        for i, scene_data in enumerate(scenes_data):
            scene_progress = 10 + int((i / total_scenes) * 80)
            await self._update_progress(
                execution, 
                scene_progress, 
                f"Generating video for scene {scene_data.scene_number}",
                db
            )
            
            try:
                # Check if scene has image
                if not scene_data.image_path and not scene_data.image_url:
                    self.logger.warning(f"No image found for scene {scene_data.scene_number}, skipping video generation")
                    continue
                
                # Use Function Call to let LLM decide video generation strategy
                video_result = await self._llm_guided_video_generation(
                    scene_data, workflow_state_id, execution, input_data
                )
                
                # Update scene data in WorkflowState with video information
                workflow_state.update_scene(scene_data.scene_number,
                    video_prompt=video_result["prompt_used"],
                    video_url=video_result.get("video_url", ""),
                    video_path=video_result.get("video_path", ""),
                    video_generation_params=video_result.get("parameters", {})
                )
                
                # 🔗 存储场景视频的最后一帧到连续性内存（为后续场景做准备）
                await self._store_scene_final_frame(scene_data, video_result)
                
                generated_videos.append({
                    "scene_number": scene_data.scene_number,
                    "video_url": video_result.get("video_url"),
                    "video_path": video_result.get("video_path"),
                    "duration": video_result.get("duration", scene_data.duration),
                    "prompt_used": video_result["prompt_used"],
                    "generation_model": video_result["model"],
                    "generation_parameters": video_result.get("parameters", {})
                })
                
                self.logger.info(f"Generated video for scene {scene_data.scene_number}")
                
            except Exception as e:
                self.logger.error(f"Failed to generate video for scene {scene_data.scene_number}: {str(e)}")
                
                generated_videos.append({
                    "scene_number": scene_data.scene_number,
                    "video_url": None,
                    "duration": scene_data.duration,
                    "error": str(e),
                    "is_placeholder": True
                })
        
        await self._update_progress(execution, 95, "Finalizing video generation", db)
        
        # Generate summary statistics
        successful_generations = len([vid for vid in generated_videos if not vid.get("is_placeholder")])
        total_duration = sum(
            vid.get("duration", 0) or 0 for vid in generated_videos 
            if not vid.get("is_placeholder")
        )
        
        output_data = {
            "videos": generated_videos,
            "total_scenes": total_scenes,
            "successful_generations": successful_generations,
            "failed_generations": total_scenes - successful_generations,
            "total_duration": total_duration,
            "generation_summary": self._create_generation_summary(generated_videos),
            "technical_specs": self._get_technical_specifications(generated_videos),
            "workflow_state_id": workflow_state_id  # 传递给下一个Agent
        }
        
        await self._update_progress(execution, 100, "Video generation completed", db)
        
        return output_data
    
    async def _llm_guided_video_generation(
        self,
        scene_data,
        workflow_state_id: str,
        execution: AgentExecution,
        context_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        使用Function Call让LLM根据场景情况选择合适的工具和参数
        """
        
        # 检查场景连续性需求
        continuity_frame_path = await self._check_scene_continuity_requirements(scene_data)
        
        # 构建上下文信息
        context_messages = [
            {
                "role": "system",
                "content": """你是视频生成专家，负责根据场景内容和用户需求选择最合适的工具和参数。

可用工具说明：
- video_generation: 生成视频，需要prompt和duration参数
- scene_analysis: 分析场景复杂度和特征
- parameter_optimization: 优化生成参数

请根据场景内容智能选择工具调用顺序和参数。"""
            },
            {
                "role": "user",
                "content": f"""
场景数据：
场景号：{scene_data.scene_number}
脚本：{getattr(scene_data, 'script_text', '')}
视觉描述：{getattr(scene_data, 'visual_description', '')}
叙事描述：{getattr(scene_data, 'narrative_description', '')}
气氛：{getattr(scene_data, 'mood_and_atmosphere', '')}
时长：{scene_data.duration}秒
图像URL：{getattr(scene_data, 'image_url', '') or getattr(scene_data, 'image_path', '')}
连续性需求：{'是' if continuity_frame_path else '否'}

请分析这个场景并选择合适的工具来处理。
"""
            }
        ]
        
        try:
            # 使用Function Call让LLM选择工具
            llm_response = await self.llm_function_call(
                messages=context_messages,
                context_description=f"生成场景{scene_data.scene_number}的视频",
                temperature=0.3
            )
            
            if llm_response.get("success") and llm_response.get("tool_calls"):
                return await self._execute_llm_selected_tools(
                    llm_response["tool_calls"], scene_data, continuity_frame_path, workflow_state_id
                )
            else:
                # 如果LLM没有选择工具，使用默认策略
                self.logger.warning(f"LLM did not select tools for scene {scene_data.scene_number}, using default strategy")
                return await self._fallback_video_generation(scene_data, continuity_frame_path, workflow_state_id)
                
        except Exception as e:
            self.logger.error(f"Function call failed for scene {scene_data.scene_number}: {e}")
            return await self._fallback_video_generation(scene_data, continuity_frame_path, workflow_state_id)
    
    async def _call_tool_with_extended_timeout(
        self, 
        tool_name: str, 
        action: str, 
        parameters: Dict[str, Any], 
        timeout: int = 240
    ) -> Any:
        """调用工具并设置延长的超时时间（专门用于视频生成）"""
        
        if tool_name not in self._available_tools:
            raise AgentError(f"Tool {tool_name} not available for agent {self.agent_name}")
        
        tool = self._available_tools[tool_name]
        
        try:
            # 创建ToolInput并设置超时
            from .tools.base_tool import ToolInput
            tool_input = ToolInput(
                action=action, 
                parameters=parameters,
                timeout=timeout
            )
            
            self.logger.info(f"🔧 Calling {tool_name}:{action} with {timeout}s timeout")
            
            # 直接调用工具的execute方法
            raw_result = await tool.execute(tool_input)
            
            # 检查工具执行是否真正成功
            if hasattr(raw_result, 'success') and not raw_result.success:
                # 工具执行失败（包括超时）
                error_msg = getattr(raw_result, 'error', 'Tool execution failed')
                self.logger.error(f"Tool {tool_name} failed: {error_msg}")
                raise AgentError(f"Tool {tool_name} failed: {error_msg}")
            
            return raw_result
            
        except Exception as e:
            self.logger.error(f"Tool execution failed for {tool_name}.{action}: {e}")
            raise AgentError(f"Failed to execute {tool_name}: {str(e)}") from e
    
    async def _execute_llm_selected_tools(
        self, 
        tool_calls: List[Dict], 
        scene_data, 
        continuity_frame_path: Optional[str],
        workflow_state_id: str
    ) -> Dict[str, Any]:
        """执行LLM选择的工具调用"""
        
        results = []
        final_video_result = None
        
        for tool_call in tool_calls:
            function_name = tool_call["function"]["name"]
            function_args = tool_call["function"]["arguments"]
            
            self.logger.info(f"🤖 LLM选择调用工具: {function_name}")
            self.logger.info(f"📋 参数: {function_args}")
            
            try:
                # 解析工具名称和action
                if "_" in function_name:
                    tool_name, action = function_name.rsplit("_", 1)
                else:
                    tool_name = function_name
                    action = "execute"
                
                # 特殊处理video_generation
                if tool_name == "video" and action == "generation":
                    final_video_result = await self._execute_video_generation_with_params(
                        function_args, scene_data, continuity_frame_path, workflow_state_id
                    )
                    results.append({
                        "tool": function_name,
                        "args": function_args,
                        "result": final_video_result
                    })
                
                # 其他工具的标准执行
                else:
                    tool_result = await self.use_tool(tool_name, action, function_args)
                    results.append({
                        "tool": function_name,
                        "args": function_args,
                        "result": tool_result
                    })
                
            except Exception as e:
                self.logger.error(f"Failed to execute {function_name}: {e}")
                results.append({
                    "tool": function_name,
                    "args": function_args,
                    "error": str(e)
                })
        
        # 如果没有视频生成结果，使用fallback
        if not final_video_result:
            self.logger.warning(f"No video generation result from LLM tools, using fallback")
            final_video_result = await self._fallback_video_generation(
                scene_data, continuity_frame_path, workflow_state_id
            )
        
        return final_video_result
    
    async def _execute_video_generation_with_params(
        self,
        llm_params: Dict[str, Any],
        scene_data,
        continuity_frame_path: Optional[str],
        workflow_state_id: str
    ) -> Dict[str, Any]:
        """根据LLM决定的参数执行视频生成"""
        
        # 获取基本参数
        prompt = llm_params.get("prompt", "")
        
        # ✅ MAS设计原则：信任LLM Function Call的参数选择
        # LLM已经通过上下文了解场景规划时长，会智能选择duration参数
        duration = llm_params.get("duration", 5)  # LLM未指定时的fallback
        self.logger.info(f"🤖 LLM selected duration: {duration}s for scene {scene_data.scene_number}")
        
        # 如果没有prompt，生成一个
        if not prompt:
            prompt = await self._build_enhanced_video_prompt(scene_data, workflow_state_id)
        
        # 准备图像输入 - 优先使用连续性帧
        image_input = continuity_frame_path if continuity_frame_path else (
            scene_data.image_url or scene_data.image_path
        )
        
        if not image_input:
            raise AgentError(f"No image input available for scene {scene_data.scene_number}")
        
        # 使用video_generation工具
        try:
            result = await self.use_tool(
                "video_generation",
                "generate_video",
                {
                    "prompt": prompt,
                    "duration": duration,
                    "image_url": image_input,
                    "continuity_frame": continuity_frame_path
                }
            )
            
            # 处理工具返回结果
            if hasattr(result, 'result') and isinstance(result.result, dict):
                video_result = result.result
            else:
                video_result = result if isinstance(result, dict) else {}
            
            # 下载视频文件
            if video_result.get("video_url"):
                video_result["video_path"] = await self._save_video_from_result(
                    video_result, scene_data.scene_number
                )
            
            return video_result
            
        except Exception as e:
            self.logger.error(f"Video generation tool failed: {e}")
            raise AgentError(f"Failed to generate video: {str(e)}")
    
    async def _fallback_video_generation(
        self,
        scene_data,
        continuity_frame_path: Optional[str],
        workflow_state_id: str
    ) -> Dict[str, Any]:
        """默认的视频生成策略（当Function Call失败时使用）"""
        
        self.logger.info(f"Using fallback video generation for scene {scene_data.scene_number}")
        
        # 使用现有的方法生成视频
        return await self._generate_video_from_single_image_with_description(
            scene_data, workflow_state_id, None, {}, continuity_frame_path
        )
    
    async def _check_scene_continuity_requirements(self, scene_data) -> Optional[str]:
        """
        检查场景是否需要使用前一场景的最后一帧
        
        Returns:
            前一场景最后一帧的文件路径，如果不需要连续性则返回None
        """
        try:
            # 检查SceneData中的连续性标记（使用Script Writer设置的字段）
            if not scene_data.depends_on_scene:
                return None
                
            from ..core.scene_continuity_memory import get_scene_continuity_memory
            continuity_memory = get_scene_continuity_memory()
            
            # 从内存系统获取前一场景的最后一帧
            previous_frame_path = await continuity_memory.get_previous_scene_final_frame(
                scene_data.depends_on_scene
            )
            
            if previous_frame_path:
                self.logger.info(
                    f"🔗 Scene {scene_data.scene_number} requires continuity from Scene {scene_data.depends_on_scene}: {scene_data.continuity_reason}"
                )
                return previous_frame_path
            else:
                self.logger.warning(
                    f"⚠️  Scene {scene_data.scene_number} requires continuity from Scene {scene_data.depends_on_scene}, but previous frame not found"
                )
                return None
                
        except Exception as e:
            self.logger.error(f"Failed to check scene continuity: {e}")
            return None
    
    async def _store_scene_final_frame(self, scene_data, video_result: Dict[str, Any]) -> None:
        """
        提取并存储场景视频的最后一帧到连续性内存系统
        
        Args:
            scene_data: 场景数据
            video_result: 视频生成结果
        """
        try:
            video_path = video_result.get("video_path")
            video_url = video_result.get("video_url")
            
            if not video_path and not video_url:
                self.logger.warning(f"No video path/url for scene {scene_data.scene_number}, cannot extract final frame")
                return
                
            # 使用FFmpeg提取最后一帧
            final_frame_path = await self._extract_video_final_frame(
                video_path or video_url, scene_data.scene_number
            )
            
            if final_frame_path:
                # 处理连续性帧（转换为base64或上传到存储系统）
                final_frame_data = await self._upload_continuity_frame_to_storage(final_frame_path, scene_data.scene_number)
                
                if final_frame_data:
                    # 存储处理后的数据到连续性内存系统
                    from ..core.scene_continuity_memory import get_scene_continuity_memory
                    continuity_memory = get_scene_continuity_memory()
                    
                    await continuity_memory.store_scene_final_frame(
                        scene_data.scene_number, final_frame_data  # base64数据或URL
                    )
                    
                    data_type = "base64" if final_frame_data.startswith("data:") else "URL"
                    if data_type == "base64":
                        self.logger.info(
                            f"💾 Stored final frame (base64) for Scene {scene_data.scene_number}: {len(final_frame_data)} chars"
                        )
                    else:
                        self.logger.info(
                            f"💾 Stored final frame (URL) for Scene {scene_data.scene_number}: {final_frame_data}"
                        )
                else:
                    self.logger.warning(f"Failed to process final frame for scene {scene_data.scene_number}")
            else:
                self.logger.warning(f"Failed to extract final frame for scene {scene_data.scene_number}")
                
        except Exception as e:
            self.logger.error(f"Failed to store scene final frame: {e}")
            # 不抛出异常，不影响主要视频生成流程
    
    async def _convert_local_image_to_base64(self, image_path: str) -> Optional[str]:
        """
        将本地图片转换为base64格式，用于AI分析
        
        Args:
            image_path: 本地图片路径
            
        Returns:
            base64编码的图片数据
        """
        try:
            import base64
            from pathlib import Path
            
            if not Path(image_path).exists():
                self.logger.warning(f"Image file not found: {image_path}")
                return None
            
            with open(image_path, "rb") as image_file:
                image_data = image_file.read()
                base64_encoded = base64.b64encode(image_data).decode('utf-8')
                # 返回data URL格式，智谱AI支持
                return f"data:image/jpeg;base64,{base64_encoded}"
                
        except Exception as e:
            self.logger.error(f"Failed to convert image to base64: {e}")
            return None
    
    async def _upload_continuity_frame_to_storage(self, frame_path: str, scene_number: int) -> Optional[str]:
        """
        处理连续性帧存储（优先使用base64格式用于AI分析）
        
        Args:
            frame_path: 本地连续性帧路径
            scene_number: 场景号
            
        Returns:
            base64格式的图片数据或上传后的URL
        """
        try:
            # 首先尝试转换为base64格式（智谱AI支持）
            base64_data = await self._convert_local_image_to_base64(frame_path)
            if base64_data:
                self.logger.info(f"Converted continuity frame to base64 for scene {scene_number}")
                return base64_data
            
            # 如果base64转换失败，尝试文件存储工具上传（可选）
            try:
                result = await self.use_tool(
                    "file_storage_tool",
                    "upload_file",
                    {
                        "file_path": frame_path,
                        "destination_key": f"continuity_frames/scene_{scene_number}_final_frame.jpg",
                        "content_type": "image/jpeg",
                        "public": True,
                        "metadata": {
                            "type": "continuity_frame",
                            "scene_number": scene_number,
                            "purpose": "scene_continuity_analysis"
                        }
                    }
                )
                
                # 提取URL
                if hasattr(result, 'result') and isinstance(result.result, dict):
                    return result.result.get("url")
                elif isinstance(result, dict):
                    return result.get("url")
                    
            except Exception as upload_error:
                self.logger.warning(f"File storage upload failed: {upload_error}")
            
            return None
                
        except Exception as e:
            self.logger.error(f"Failed to process continuity frame: {e}")
            return None
    
    async def _extract_video_final_frame(self, video_source: str, scene_number: int) -> Optional[str]:
        """
        使用FFmpeg从视频中提取最后一帧
        
        Args:
            video_source: 视频文件路径或URL
            scene_number: 场景号
            
        Returns:
            最后一帧图片的文件路径
        """
        try:
            import subprocess
            import tempfile
            from pathlib import Path
            
            # 创建输出文件路径
            output_dir = Path("./storage/continuity_frames").resolve()
            output_dir.mkdir(parents=True, exist_ok=True)
            
            output_path = output_dir / f"scene_{scene_number}_final_frame.jpg"
            
            # FFmpeg命令：提取最后一帧
            # 正确的语法：输入参数必须在输入文件之前
            cmd = [
                "ffmpeg", 
                "-sseof", "-1",        # 从结尾前1秒开始（输入参数，必须在-i之前）
                "-i", video_source,    # 输入文件
                "-vframes", "1",       # 只提取1帧（输出参数）
                "-y",                  # 覆盖输出文件
                str(output_path)       # 输出文件
            ]
            
            # 执行FFmpeg命令
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                check=True
            )
            
            if output_path.exists():
                self.logger.info(f"✅ Extracted final frame: {output_path}")
                return str(output_path)
            else:
                self.logger.warning(f"FFmpeg completed but output file not found: {output_path}")
                return None
                
        except subprocess.CalledProcessError as e:
            self.logger.error(f"FFmpeg failed to extract final frame: {e.stderr}")
            return None
        except Exception as e:
            self.logger.error(f"Failed to extract final frame: {e}")
            return None
    
    async def _generate_scene_video_from_data(
        self, 
        scene_data,  # SceneData object from WorkflowState
        workflow_state_id: str,
        execution: AgentExecution,
        context_data: Dict[str, Any]  # 包含创意指导的上下文数据
    ) -> Dict[str, Any]:
        """根据场景的生成模式选择相应的视频生成策略"""
        
        # 🔗 STEP 1: 检查场景连续性需求
        continuity_frame_path = await self._check_scene_continuity_requirements(scene_data)
        if continuity_frame_path:
            # 不打印完整的base64数据
            if continuity_frame_path.startswith("data:image"):
                self.logger.info(
                    f"🎬 Scene {scene_data.scene_number} will use continuity frame (base64, {len(continuity_frame_path)} chars) from Scene {scene_data.depends_on_scene}"
                )
            else:
                self.logger.info(
                    f"🎬 Scene {scene_data.scene_number} will use continuity frame from Scene {scene_data.depends_on_scene}: {continuity_frame_path}"
                )
        
        generation_mode = getattr(scene_data, 'video_generation_mode', 'first_last_frame')
        
        if generation_mode == "single_image_with_description":
            # 新方案：单图 + 动作描述，支持连续性帧
            return await self._generate_video_from_single_image_with_description(
                scene_data, workflow_state_id, execution, context_data, continuity_frame_path
            )
        else:
            # 原方案：首尾帧模式（保留）
            return await self._generate_video_from_first_last_frames(
                scene_data, workflow_state_id, execution, context_data
            )

    async def _generate_video_from_single_image_with_description(
        self, scene_data, workflow_state_id, execution, context_data, continuity_frame_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """新方案：基于首帧图像 + 完整动作描述生成视频，支持场景连续性"""
        
        # 1. 获取首帧图像 - 优先使用连续性帧
        if continuity_frame_path:
            image_input = continuity_frame_path
            # 不打印完整的base64数据
            if continuity_frame_path.startswith("data:image"):
                self.logger.info(f"🔗 Using continuity frame (base64, {len(continuity_frame_path)} chars) for Scene {scene_data.scene_number}")
            else:
                self.logger.info(f"🔗 Using continuity frame for Scene {scene_data.scene_number}: {continuity_frame_path}")
        else:
            image_input = scene_data.first_frame_url or scene_data.image_url
            
        if not image_input:
            raise AgentError(f"No first frame image for scene {scene_data.scene_number}")
        
        # 2. 解读首帧图像的实际内容
        first_frame_description = await self._analyze_first_frame_image(image_input, scene_data)
        
        # 3. 构建完整的视频提示词（包含首帧实际内容）
        video_prompt = await self._build_enhanced_video_prompt(scene_data, workflow_state_id, first_frame_description)
        
        # 3. 调用CogVideoX API（单图模式）
        video_config = get_video_config()
        provider_config = video_config.get_current_provider_config()
        
        self.logger.info(f"🎬 Using single image mode for scene {scene_data.scene_number}")
        
        result = await self._call_tool_with_extended_timeout(
            "zhipu_client",
            "generate_video",
            {
                "prompt": video_prompt,
                "image_url": image_input,  # 单个URL
                "model": provider_config.model_name,
                "duration": provider_config.default_duration  # 使用配置的默认时长
            },
            timeout=240
        )
        
        # 提取ToolOutput结果
        if hasattr(result, 'result') and isinstance(result.result, dict):
            tool_result = result.result
        else:
            tool_result = result if isinstance(result, dict) else {}
            
        # 构建返回结果 - 确保prompt_used不被工具结果覆盖
        video_result = {
            **tool_result,
            "model": provider_config.model_name
        }
        # 强制设置正确的prompt_used，避免被tool_result覆盖
        video_result["prompt_used"] = video_prompt
        
        # 下载视频文件到本地
        if video_result.get("video_url"):
            self.logger.info(f"🎬 Downloading video for scene {scene_data.scene_number}: {video_result['video_url']}")
            video_result["video_path"] = await self._save_video_from_result(video_result, scene_data.scene_number)
            self.logger.info(f"🎬 Video saved to: {video_result['video_path']}")
        else:
            video_result["video_path"] = ""
            self.logger.warning(f"No video URL found for scene {scene_data.scene_number}")
        
        return video_result

    async def _generate_video_from_first_last_frames(
        self, scene_data, workflow_state_id, execution, context_data
    ) -> Dict[str, Any]:
        """原方案：基于首尾帧图像生成视频"""
        
        # 从上下文数据中提取动作指导（由Orchestrator提供）
        motion_guidance = self._extract_motion_guidance_from_context(context_data, scene_data.scene_number)
        
        # 解读首帧图像内容（如果有的话）
        first_frame_description = None
        image_for_analysis = scene_data.first_frame_url or scene_data.image_url or image_url or image_path
        if image_for_analysis:
            first_frame_description = await self._analyze_first_frame_image(image_for_analysis, scene_data)
        
        # Build enhanced video generation prompt with motion direction
        video_prompt = await self._build_video_prompt_with_motion_guidance(scene_data, motion_guidance, first_frame_description)
        
        # Get image URL/path for video generation
        image_url = scene_data.image_url
        image_path = scene_data.image_path
        if not image_url and not image_path:
            raise AgentError(f"No image available for scene {scene_data.scene_number}")
        
        # Determine video generation parameters
        generation_params = self._get_video_generation_parameters_from_data(scene_data)
        
        try:
            # 检查当前提供商是否支持首尾帧模式
            video_config = get_video_config()
            provider_config = video_config.get_current_provider_config()
        
            self.logger.info(f"🎬 scene_data.first_frame_url: {scene_data.first_frame_url}")
            self.logger.info(f"🎬 scene_data.last_frame_url: {scene_data.last_frame_url}")
        
            if (provider_config.supports_first_last_frame and 
                scene_data.first_frame_url and scene_data.last_frame_url):
                self.logger.info(f"🎬 Using {provider_config.provider_name} first/last frame mode for scene {scene_data.scene_number}")
                # 使用工具系统调用AI视频生成（首尾帧模式）
                result = await self._call_tool_with_extended_timeout(
                    "zhipu_client",  # TODO: 根据provider_config选择合适的工具
                    "generate_video",
                    {
                        "prompt": video_prompt,
                        "first_frame_image": scene_data.first_frame_url,
                        "last_frame_image": scene_data.last_frame_url,
                        "model": provider_config.model_name,
                        "duration": provider_config.default_duration  # 使用配置的默认时长
                    },
                    timeout=240
                )
            else:
                # 回退到传统单图模式
                image_input = image_url or image_path
                self.logger.info(f"🎬 Using {provider_config.provider_name} single image mode for scene {scene_data.scene_number}")
                # 使用工具系统调用AI视频生成（单图模式）
                result = await self._call_tool_with_extended_timeout(
                    "zhipu_client",  # TODO: 根据provider_config选择合适的工具
                    "generate_video",
                    {
                        "prompt": video_prompt,
                        "image_url": image_input,
                        "model": provider_config.model_name,
                        "duration": provider_config.default_duration  # 使用配置的默认时长
                    },
                    timeout=240
                )
            
            # Log successful tool execution
            self.logger.info(f"🔧 Tool zhipu_client:generate_video executed successfully")
            
            # Track API usage
            self._update_token_usage(execution, 0)  # Video generation doesn't use tokens
            
            # 提取工具输出的实际结果并处理None情况
            if result is None:
                tool_result = {}
                self.logger.error(f"Tool returned None for scene {scene_data.scene_number}")
            elif hasattr(result, 'result'):
                tool_result = result.result or {}
            else:
                tool_result = result or {}
            
            # 确保tool_result是字典类型
            if not isinstance(tool_result, dict):
                self.logger.error(f"Tool result is not a dict for scene {scene_data.scene_number}: {type(tool_result)}")
                tool_result = {}
            
            # 构建返回结果字典 - 确保prompt_used不被工具结果覆盖
            video_result = {
                **tool_result,  # 包含工具返回的所有数据
                "parameters": generation_params
            }
            # 强制设置正确的prompt_used，避免被tool_result覆盖
            video_result["prompt_used"] = video_prompt
            
            # Save video file if we have video data
            if (video_result.get("video_url") and video_result["video_url"]) or "video_data" in video_result:
                self.logger.info(f"🎬 Downloading video for scene {scene_data.scene_number}: {video_result.get('video_url', 'data')}")
                video_result["video_path"] = await self._save_video_from_result(video_result, scene_data.scene_number)
                self.logger.info(f"🎬 Video saved to: {video_result['video_path']}")
            else:
                video_result["video_path"] = ""
                if video_result.get("timeout"):
                    self.logger.warning(f"Scene {scene_data.scene_number} video generation timed out - video may be available later via video_id: {video_result.get('video_id')}")
                else:
                    self.logger.warning(f"No valid video URL for scene {scene_data.scene_number}, skipping file save")
            
            return video_result
            
        except Exception as e:
            self.logger.error(f"Video generation failed: {str(e)}")
            raise AgentError(f"Failed to generate video: {str(e)}") from e
    
    def _extract_motion_guidance_from_context(self, context_data: Dict[str, Any], scene_number: int) -> Dict[str, Any]:
        """从上下文数据中提取动作指导信息"""
        
        try:
            # 获取整体创意指导和叙事流动策略
            overall_guidance = context_data.get("creative_guidance", {})
            
            # 获取特定场景的指导
            scene_guidances = context_data.get("scene_guidances", {})
            scene_guidance = scene_guidances.get(f"scene_{scene_number}", {})
            
            # 获取相邻场景信息（用于动作衔接）
            previous_scene = scene_guidances.get(f"scene_{scene_number - 1}", {}) if scene_number > 1 else {}
            next_scene = scene_guidances.get(f"scene_{scene_number + 1}", {})
            
            motion_guidance = {
                "overall_guidance": overall_guidance,
                "scene_guidance": scene_guidance,
                "previous_scene": previous_scene,
                "next_scene": next_scene,
                "has_guidance": bool(overall_guidance or scene_guidance)
            }
            
            if motion_guidance["has_guidance"]:
                self.logger.info(f"🎬 Motion Director using creative guidance for scene {scene_number}")
            else:
                self.logger.debug(f"No specific motion guidance for scene {scene_number}, using base prompts")
            
            return motion_guidance
            
        except Exception as e:
            self.logger.error(f"Failed to extract motion guidance: {e}")
            return {"overall_guidance": {}, "scene_guidance": {}, "previous_scene": {}, "next_scene": {}, "has_guidance": False}
    
    async def _build_video_prompt_with_motion_guidance(
        self, 
        scene_data,
        motion_guidance: Dict[str, Any],
        first_frame_description: str = None
    ) -> str:
        """作为动作导演，基于创意总监和前后场景上下文构建视频生成提示词"""
        
        # 收集模板变量
        template_variables = {
            "visual_description": scene_data.visual_description or "",
            "narrative_description": scene_data.narrative_description,
            "script_text": scene_data.script_text,
            "mood_and_atmosphere": scene_data.mood_and_atmosphere,
            "overall_guidance": motion_guidance.get("overall_guidance", {}),
            "scene_guidance": motion_guidance.get("scene_guidance", {}),
        }
        
        # 处理场景衔接信息
        previous_scene = motion_guidance.get("previous_scene", {})
        next_scene = motion_guidance.get("next_scene", {})
        scene_guidance = motion_guidance.get("scene_guidance", {})
        
        template_variables.update({
            "previous_scene_mood": previous_scene.get("mood_target", ""),
            "next_scene_mood": next_scene.get("mood_target", ""),
            "current_scene_mood": scene_guidance.get("mood_target", ""),
        })
        
        # 添加API长度限制参数
        from ..core.video_config_manager import get_video_config
        video_config = get_video_config()
        provider_config = video_config.get_current_provider_config()
        template_variables["max_prompt_length"] = provider_config.prompt_max_length
        
        # 添加场景物理类型信息（从overall_guidance或scene_guidance中获取）
        overall_guidance = motion_guidance.get("overall_guidance", {})
        if isinstance(overall_guidance, dict):
            concept_plan = overall_guidance.get("concept_plan", {})
            if isinstance(concept_plan, dict) and "scene_physics_type" in concept_plan:
                template_variables["scene_physics_type"] = concept_plan["scene_physics_type"]
        
        # 添加首帧实际内容描述
        if first_frame_description:
            template_variables["first_frame_actual_content"] = first_frame_description
        
        # 使用模板系统渲染提示词
        motion_prompt_template = self.render_prompt("motion_guided_video_generation", **template_variables)
        
        # 通过LLM生成专业的动作提示词
        llm_result = await self.use_tool(
            "zhipu_client",
            "generate_text", 
            {
                "prompt": motion_prompt_template,
                "temperature": 0.7
            }
        )
        
        # DEBUG: 记录完整的LLM返回结果
        self.logger.info(f"🔍 DEBUG - LLM result type: {type(llm_result)}")
        self.logger.info(f"🔍 DEBUG - LLM result content: {str(llm_result)[:500]}...")
        
        # 处理ToolOutput对象 
        if hasattr(llm_result, 'result') and isinstance(llm_result.result, dict):
            enhanced_prompt = llm_result.result.get("content", "").strip()
            self.logger.info(f"🔍 DEBUG - Extracted from result.content: '{enhanced_prompt}'")
        elif hasattr(llm_result, 'content'):
            enhanced_prompt = llm_result.content.strip()
            self.logger.info(f"🔍 DEBUG - Extracted from content: '{enhanced_prompt}'")
        elif isinstance(llm_result, dict):
            enhanced_prompt = llm_result.get("content", "").strip()
            self.logger.info(f"🔍 DEBUG - Extracted from dict.content: '{enhanced_prompt}'")
        else:
            # 最后才转换为字符串，这里一般不应该执行
            self.logger.warning(f"Unexpected llm_result type: {type(llm_result)}, result: {llm_result}")
            enhanced_prompt = str(llm_result).strip()
        
        # 限制提示词长度以符合CogVideoX API要求
        if len(enhanced_prompt) > provider_config.prompt_max_length:
            enhanced_prompt = enhanced_prompt[:provider_config.prompt_max_length-3] + "..."
        
        self.logger.info(f"🎬 Generated motion-guided video prompt (length: {len(enhanced_prompt)}): {enhanced_prompt[:100]}...")
        return enhanced_prompt
    
    async def _build_video_prompt_from_data(self, scene_data) -> str:
        """Build prompt for video generation using SceneData"""
        
        # 收集模板变量
        template_variables = {
            "visual_description": scene_data.visual_description or "",
            "narrative_description": scene_data.narrative_description,
            "script_text": scene_data.script_text,
            "mood_and_atmosphere": scene_data.mood_and_atmosphere,
        }
        
        # 添加API长度限制参数
        from ..core.video_config_manager import get_video_config
        video_config = get_video_config()
        provider_config = video_config.get_current_provider_config()
        template_variables["max_prompt_length"] = provider_config.prompt_max_length
        
        # 使用模板系统渲染提示词
        video_prompt_template = self.render_prompt("basic_video_generation", **template_variables)
        
        # 通过LLM生成专业的视频提示词
        llm_result = await self.use_tool(
            "zhipu_client",
            "generate_text", 
            {
                "prompt": video_prompt_template,
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
            # 最后才转换为字符串，这里一般不应该执行
            self.logger.warning(f"Unexpected llm_result type in _build_video_prompt_from_data: {type(llm_result)}, result: {llm_result}")
            enhanced_prompt = str(llm_result).strip()
        
        # 限制提示词长度以符合CogVideoX API要求
        if len(enhanced_prompt) > provider_config.prompt_max_length:
            enhanced_prompt = enhanced_prompt[:provider_config.prompt_max_length-3] + "..."
        
        self.logger.info(f"🎬 Generated basic video prompt (length: {len(enhanced_prompt)}): {enhanced_prompt[:100]}...")
        return enhanced_prompt
    
    def _get_video_generation_parameters_from_data(self, scene_data) -> Dict[str, Any]:
        """Get video generation parameters based on scene data"""
        
        # 使用配置管理器获取当前提供商的参数
        video_config = get_video_config()
        provider_config = video_config.get_current_provider_config()
        
        return {
            "model": provider_config.model_name,
            "quality": "quality",      # 质量优先模式
            "with_audio": True,        # 包含音频
            "size": provider_config.resolution_options[0] if provider_config.resolution_options else "1920x1080",
            "fps": provider_config.frame_rate_options[0] if provider_config.frame_rate_options else 30
            # Image to Video模式：image_url在调用时单独传递
            # duration由provider_config.default_duration控制
        }
    
    async def _save_video_from_result(self, video_result: Dict[str, Any], scene_number: int) -> str:
        """Save video from generation result and return file path"""
        
        try:
            if "video_url" in video_result:
                # Download from URL (GLM CogVideoX)
                filename = f"scene_{scene_number}_video.mp4"
                file_path = await self.file_storage.download_and_save_video(
                    video_result["video_url"], filename
                )
            elif "video_data" in video_result:
                # Save from base64 or binary data
                filename = f"scene_{scene_number}_video.mp4"
                file_path = await self.file_storage.save_video_data(
                    video_result["video_data"], filename
                )
            else:
                raise ValueError("No video data found in generation result")
            
            return file_path
            
        except Exception as e:
            self.logger.error(f"Failed to save video for scene {scene_number}: {str(e)}")
            return ""
    
    async def _build_video_prompt(
        self, 
        scene: Scene, 
        scene_script: Dict[str, Any]
    ) -> str:
        """Build prompt for video generation"""
        
        # 收集模板变量
        template_variables = {
            "visual_description": scene.visual_description or "",
            "narrative_description": scene.narrative_description,
            "mood_and_atmosphere": scene.mood_and_atmosphere,
            "camera_movement": scene.camera_movement or "static",
        }
        
        # 处理脚本动作描述
        if scene_script and scene_script.get("action_descriptions"):
            template_variables["action_descriptions"] = scene_script["action_descriptions"][:2]  # 限制到2个动作
        
        # 添加API长度限制参数
        from ..core.video_config_manager import get_video_config
        video_config = get_video_config()
        provider_config = video_config.get_current_provider_config()
        template_variables["max_prompt_length"] = provider_config.prompt_max_length
        
        # 使用模板系统渲染提示词
        video_prompt_template = self.render_prompt("script_based_video_generation", **template_variables)
        
        # 通过LLM生成专业的视频提示词
        llm_result = await self.use_tool(
            "zhipu_client",
            "generate_text", 
            {
                "prompt": video_prompt_template,
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
            # 最后才转换为字符串，这里一般不应该执行
            self.logger.warning(f"Unexpected llm_result type in _build_video_prompt: {type(llm_result)}, result: {llm_result}")
            enhanced_prompt = str(llm_result).strip()
        
        # 限制提示词长度以符合CogVideoX API要求
        if len(enhanced_prompt) > provider_config.prompt_max_length:
            enhanced_prompt = enhanced_prompt[:provider_config.prompt_max_length-3] + "..."
        
        self.logger.info(f"🎬 Generated script-based video prompt (length: {len(enhanced_prompt)}): {enhanced_prompt[:100]}...")
        return enhanced_prompt
    
    def _find_scene_script(self, scene_id: int, scripts_data: Dict[str, Any]) -> Dict[str, Any]:
        """Find script data for a specific scene"""
        
        scripts = scripts_data.get("scripts", [])
        
        for script_result in scripts:
            if script_result["scene_id"] == scene_id:
                return script_result["script"]
        
        return {}
    
    def _get_video_generation_parameters(self, scene: Scene) -> Dict[str, Any]:
        """Get video generation parameters based on scene"""
        
        return {
            "motion": "medium",  # low, medium, high
            "seed": None,  # Random seed
            "watermark": False,
            "enhance": True,
            "upscale": False  # Keep original resolution for faster generation
        }
    
    async def _save_video_resource(
        self, 
        task: Task, 
        scene: Scene, 
        video_result: Dict[str, Any],
        db: Session
    ) -> Resource:
        """Save generated video and create resource record"""
        
        # Download video from URL
        video_url = video_result.get("video_url")
        if not video_url:
            raise AgentError("No video URL in generation result")
        
        filename = f"scene_{scene.scene_number}_{scene.id}.mp4"
        file_path = await self.file_storage.download_and_save_image(  # Reuse download method for video
            video_url, filename
        )
        
        # Get file info
        file_info = await self.file_storage.get_file_info(file_path)
        
        # Create resource record
        resource = Resource(
            task_id=task.id,
            scene_id=scene.id,
            filename=filename,
            original_filename=filename,
            file_path=file_path,
            resource_type=ResourceType.VIDEO,
            mime_type="video/mp4",
            file_size=file_info["size"],
            duration=int(video_result.get("duration", scene.duration)),
            generation_parameters=video_result.get("parameters", {}),
            generation_model=video_result.get("model"),
            generation_prompt=video_result.get("prompt_used"),
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
            filename=f"placeholder_scene_{scene.scene_number}.mp4",
            file_path="",
            resource_type=ResourceType.VIDEO,
            duration=int(scene.duration),
            processing_status="failed",
            is_generated=True,
            generation_parameters={"error": error_message}
        )
        
        db.add(resource)
        db.commit()
        db.refresh(resource)
        
        return resource
    
    def _create_generation_summary(self, generated_videos: List[Dict]) -> Dict[str, Any]:
        """Create summary of video generation results"""
        
        successful = [vid for vid in generated_videos if not vid.get("is_placeholder")]
        failed = [vid for vid in generated_videos if vid.get("is_placeholder")]
        
        total_duration = sum(vid.get("duration", 0) or 0 for vid in successful)
        
        return {
            "total_videos": len(generated_videos),
            "successful": len(successful),
            "failed": len(failed),
            "success_rate": len(successful) / len(generated_videos) if generated_videos else 0,
            "total_duration": total_duration,
            "average_duration": total_duration / len(successful) if successful else 0,
            "estimated_generation_time": "60-180 seconds per video clip"
        }
    
    def _get_technical_specifications(self, generated_videos: List[Dict]) -> Dict[str, Any]:
        """Get technical specifications of generated videos"""
        
        successful_videos = [vid for vid in generated_videos if not vid.get("is_placeholder")]
        
        if not successful_videos:
            return {"resolution": "unknown", "format": "mp4", "codec": "h264"}
        
        return {
            "resolution": "1024x576",  # Typical Runway output
            "format": "mp4",
            "codec": "h264",
            "frame_rate": 24,
            "bitrate": "variable",
            "total_clips": len(successful_videos),
            "quality": "standard"
        }

    async def _build_enhanced_video_prompt(self, scene_data, workflow_state_id, first_frame_description: str = None) -> str:
        """构建增强的视频生成提示词"""
        
        # 如果有完整描述，直接使用
        if hasattr(scene_data, 'complete_video_description') and scene_data.complete_video_description:
            return scene_data.complete_video_description
        
        # 否则收集信息并通过LLM生成
        from ..core.workflow_state import workflow_manager
        workflow_state = workflow_manager.get_workflow(workflow_state_id)
        
        context_info = self._collect_video_context_info(scene_data, workflow_state)
        
        # 添加首帧实际内容描述
        if first_frame_description:
            context_info["first_frame_actual_content"] = first_frame_description
        
        # 添加API长度限制参数
        from ..core.video_config_manager import get_video_config
        video_config = get_video_config()
        provider_config = video_config.get_current_provider_config()
        context_info["max_prompt_length"] = provider_config.prompt_max_length
        
        video_prompt_template = self.render_prompt("enhanced_video_generation", **context_info)
        
        # 通过LLM生成专业的视频提示词
        llm_result = await self.use_tool(
            "zhipu_client",
            "generate_text", 
            {
                "prompt": video_prompt_template,
                "temperature": 0.7
            }
        )
        
        # DEBUG: 记录完整的LLM返回结果
        self.logger.info(f"🔍 DEBUG - LLM result type in _build_enhanced_video_prompt: {type(llm_result)}")
        self.logger.info(f"🔍 DEBUG - LLM result content: {str(llm_result)[:500]}...")
        
        # 处理ToolOutput对象
        if hasattr(llm_result, 'result') and isinstance(llm_result.result, dict):
            enhanced_prompt = llm_result.result.get("content", "").strip()
            self.logger.info(f"🔍 DEBUG - Extracted from result.content: '{enhanced_prompt}'")
        elif hasattr(llm_result, 'content'):
            enhanced_prompt = llm_result.content.strip()
            self.logger.info(f"🔍 DEBUG - Extracted from content: '{enhanced_prompt}'")
        elif isinstance(llm_result, dict):
            enhanced_prompt = llm_result.get("content", "").strip()
            self.logger.info(f"🔍 DEBUG - Extracted from dict.content: '{enhanced_prompt}'")
        else:
            # 最后才转换为字符串，这里一般不应该执行
            self.logger.warning(f"Unexpected llm_result type in _build_enhanced_video_prompt: {type(llm_result)}, result: {llm_result}")
            enhanced_prompt = str(llm_result).strip()
        
        # 如果LLM生成的提示词为空，使用fallback
        if not enhanced_prompt:
            fallback_prompt = f"{scene_data.description or scene_data.title or 'Video scene'}, {scene_data.mood_and_atmosphere or 'cinematic style'}"
            self.logger.warning(f"⚠️ Empty enhanced_prompt, using fallback: '{fallback_prompt}'")
            enhanced_prompt = fallback_prompt
        
        # 限制提示词长度以符合CogVideoX API要求（1-512字符）
        if len(enhanced_prompt) > 512:
            enhanced_prompt = enhanced_prompt[:509] + "..."
        
        self.logger.info(f"🎬 Generated enhanced video prompt for scene {scene_data.scene_number} (length: {len(enhanced_prompt)}): {enhanced_prompt[:100]}...")
        return enhanced_prompt

    def _collect_video_context_info(self, scene_data, workflow_state) -> Dict[str, Any]:
        """收集实际可用的视频生成上下文信息"""
        
        context = {
            "image_prompt": scene_data.image_prompt or scene_data.description,
            "title": scene_data.title,
            "description": scene_data.description,  
            "duration": scene_data.duration,
            "user_prompt": workflow_state.user_prompt,
            "overall_duration": workflow_state.duration,
            "intelligent_style_design": workflow_state.intelligent_style_design,  # 🔧 修复: 使用智能风格设计
        }
        
        # 添加首帧图像的实际内容描述（如果ImageGenerator生成了的话）
        if hasattr(scene_data, 'first_frame_actual_content') and scene_data.first_frame_actual_content:
            context["first_frame_actual_content"] = scene_data.first_frame_actual_content
        elif hasattr(scene_data, 'image_description') and scene_data.image_description:
            context["first_frame_actual_content"] = scene_data.image_description
        else:
            # 回退到原始image_prompt作为首帧内容描述
            context["first_frame_actual_content"] = scene_data.image_prompt or scene_data.description
        
        # 添加ConceptPlanner判断的场景物理类型信息
        if hasattr(workflow_state, 'concept_plan') and workflow_state.concept_plan:
            concept_plan = workflow_state.concept_plan
            if isinstance(concept_plan, dict) and "scene_physics_type" in concept_plan:
                context["scene_physics_type"] = concept_plan["scene_physics_type"]
        
        # ConceptPlanner提供的信息（条件性添加）
        optional_fields = [
            'duration_reasoning', 'visual_description', 'narrative_description',
            'mood_and_atmosphere', 'camera_angle', 'lighting_style', 'art_style', 
            'character_descriptions', 'props_and_objects', 'color_palette'
        ]
        
        for field in optional_fields:
            value = getattr(scene_data, field, None)
            if value:
                context[field] = value
        
        # ScriptWriter提供的信息（条件性添加）
        script_fields = [
            'script_text', 'scene_design_elements', 'narrative_structure',
            'pacing_and_timing', 'content_development_arc'
        ]
        
        for field in script_fields:
            value = getattr(scene_data, field, None)
            if value:
                context[field] = value
        
        # 新方案：动作描述信息（ImageGenerator生成）
        action_description_fields = [
            'video_generation_mode', 'video_action_description',
            'initial_state_description', 'action_sequence_description', 
            'target_outcome_description', 'timing_structure_description',
            'complete_video_description'
        ]
        
        for field in action_description_fields:
            value = getattr(scene_data, field, None)
            if value:
                context[field] = value
        
        return context

    async def _analyze_first_frame_image(self, image_url: str, scene_data) -> str:
        """使用多模态LLM解读首帧图像的实际内容"""
        
        try:
            # 构建通用图像实体分析提示词
            analysis_prompt = f"""
作为视频制作助手，请分析这张图像中的关键视觉元素，为后续视频生成提供准确信息：

**实体识别与定位**：
1. **主要物体**：识别图中所有重要物体，描述其类型、数量、颜色、大小
2. **位置关系**：每个物体的具体位置（左、右、中、前、后、上、下）
3. **状态描述**：物体的当前状态（完整/破损、静止/运动、新/旧等）
4. **交互关系**：物体之间的距离、接触、重叠等空间关系

**环境信息**：
5. **背景环境**：场景类型、表面材质、光线条件
6. **空间布局**：整体构图和空间安排

**动作潜能**：
7. **可能动作**：基于当前布局，哪些动作是合理的？
8. **限制因素**：什么因素会影响后续动作的执行？

场景上下文："{scene_data.description}"

请提供结构化描述，重点关注物体的具体位置和状态，避免模糊表述。
"""

            # ✅ 使用工具系统调用智谱AI的GLM-4V进行图像分析
            try:
                # 通过工具系统调用图像分析
                result = await self.use_tool(
                    tool_name="zhipu_client",
                    action="analyze_image",
                    parameters={
                        "image_url": image_url,
                        "prompt": analysis_prompt,
                        "model": "glm-4v",
                        "temperature": 0.3,
                        "max_tokens": 800
                    }
                )
                
                # 处理ToolOutput格式
                if not result.success:
                    self.logger.error(f"GLM-4V image analysis failed: {result.error}")
                    return ""
                
                # 从ToolOutput中提取分析结果
                ai_result = result.result
                if not ai_result or "analysis" not in ai_result:
                    self.logger.error("Invalid response from image analysis tool")
                    return ""
                
                description = ai_result["analysis"].strip()
                
                # 清理可能的JSON格式响应，确保为纯文本
                description = self._clean_json_response_to_text(description)
                
            except Exception as e:
                self.logger.error(f"GLM-4V image analysis failed: {str(e)}")
                return ""
            
            # 检查结果
            if description:
                self.logger.info(f"🔍 First frame analysis for scene {scene_data.scene_number}: {description[:100]}...")
                return description
            else:
                self.logger.warning(f"Empty result from image analysis for scene {scene_data.scene_number}")
                return f"首帧图像显示{scene_data.description}的静态场景"
                
        except Exception as e:
            self.logger.error(f"Failed to analyze first frame for scene {scene_data.scene_number}: {str(e)}")
            # 回退到基本描述
            return f"首帧图像显示{scene_data.description}的静态场景"
    
    def _clean_json_response_to_text(self, response: str) -> str:
        """清理GLM-4V可能返回的JSON格式响应，如果JSON解析失败就直接用字符串"""
        try:
            # 首先清理代码块标记
            cleaned = response.replace('```json', '').replace('```', '').strip()
            
            # 检查是否是JSON格式并尝试解析
            if cleaned.startswith('{') and cleaned.endswith('}'):
                import json
                try:
                    # 尝试解析JSON并提取实际内容
                    json_data = json.loads(cleaned)
                    
                    if isinstance(json_data, dict):
                        # 常见的内容字段
                        content_fields = ['content', 'description', 'analysis', 'result', 'text', 'summary']
                        
                        for field in content_fields:
                            if field in json_data and isinstance(json_data[field], str):
                                text_content = json_data[field].strip()
                                if text_content:
                                    self.logger.info(f"🧹 Extracted text from JSON field '{field}'")
                                    return self._make_jinja2_safe(text_content)
                        
                        # 如果没有找到常见字段，组合所有字符串值
                        text_parts = []
                        for key, value in json_data.items():
                            if isinstance(value, str) and value.strip():
                                text_parts.append(value.strip())
                        
                        if text_parts:
                            combined_text = ' '.join(text_parts)
                            self.logger.info("🧹 Combined multiple JSON string fields")
                            return self._make_jinja2_safe(combined_text)
                
                except json.JSONDecodeError:
                    # JSON解析失败，直接用字符串
                    self.logger.info("🧹 JSON parsing failed, using string directly")
                    pass
            
            # JSON解析失败或不是JSON格式，直接处理为文本
            return self._make_jinja2_safe(cleaned)
            
        except Exception as e:
            self.logger.warning(f"Error cleaning response: {e}")
            # 发生错误时直接处理原始响应
            return self._make_jinja2_safe(response)
    
    def _make_jinja2_safe(self, text: str) -> str:
        """确保文本对Jinja2模板安全，简单转义关键字符"""
        if not text:
            return text
            
        try:
            # 简单转义可能破坏Jinja2模板的字符
            safe_text = text.replace('{{', '{ {').replace('}}', '} }')
            safe_text = safe_text.replace('{%', '{ %').replace('%}', '% }')
            safe_text = safe_text.replace('{#', '{ #').replace('#}', '# }')
            
            return safe_text.strip()
            
        except Exception as e:
            self.logger.warning(f"Error making text Jinja2-safe: {e}")
            # 最保守的处理：移除所有可能的问题字符
            import re
            safe_text = re.sub(r'[{}%#]', ' ', text)
            return safe_text.strip()
    
    async def _check_scene_continuity_requirements(self, scene_data) -> Optional[str]:
        """
        检查场景的连续性需求，如果需要连续性，则获取前一场景的最后一帧
        
        Args:
            scene_data: 当前场景数据
            
        Returns:
            连续性帧的路径/URL（base64或文件路径），如果不需要连续性返回None
        """
        try:
            # 只有第二个及以后的场景才可能需要连续性
            if scene_data.scene_number <= 1:
                return None
            
            # 检查场景是否设置了连续性策略
            if hasattr(scene_data, 'image_generation_strategy'):
                strategy = getattr(scene_data, 'image_generation_strategy', 'new')
                if strategy != 'continue_from_previous':
                    self.logger.info(f"Scene {scene_data.scene_number} 独立生成，不需要连续性")
                    return None
            else:
                # 如果没有设置策略，默认为独立生成
                self.logger.info(f"Scene {scene_data.scene_number} 无连续性策略，默认独立生成")
                return None
            
            # 需要连续性，获取前一场景的最后一帧
            previous_scene_number = scene_data.scene_number - 1
            
            # 从连续性内存系统获取前一场景的最后一帧
            from ..core.scene_continuity_memory import get_scene_continuity_memory
            continuity_memory = get_scene_continuity_memory()
            
            continuity_frame = await continuity_memory.get_scene_final_frame(previous_scene_number)
            
            if continuity_frame:
                # 判断数据类型并记录日志
                if continuity_frame.startswith("data:image"):
                    self.logger.info(
                        f"🔗 Scene {scene_data.scene_number} 将使用前一场景最后一帧 (base64, {len(continuity_frame)} chars)"
                    )
                else:
                    self.logger.info(
                        f"🔗 Scene {scene_data.scene_number} 将使用前一场景最后一帧: {continuity_frame}"
                    )
                return continuity_frame
            else:
                self.logger.warning(
                    f"⚠️ Scene {scene_data.scene_number} 需要连续性但未找到前一场景最后一帧，将使用独立生成"
                )
                return None
                
        except Exception as e:
            self.logger.error(f"检查场景连续性需求失败: {e}")
            return None