"""
DEPRECATION NOTICE (archived)
This old agent is archived. Do not import in new flows.
"""
import warnings as _warnings
raise ImportError(
    "Archived legacy module 'video_generator_old'. Do not import in production."
)
import asyncio
import os
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from .base import BaseAgent, AgentError
from ..models import Task, AgentExecution, AgentType, Scene, Resource, ResourceType
from ..services.ai_client import AIClient
from ..core.video_config_manager import get_video_config
from ..core.config import settings


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
        
        # 🧠 使用LLM智能分析场景连续性需求（符合MAS设计原则）
        continuity_analysis = await self._llm_analyze_scene_continuity(scene_data, workflow_state_id)
        
        # 使用模板管理器构建上下文信息
        system_prompt = self.render_prompt(
            "llm_guided_video_generation_system",
            **{}
        )
        
        user_prompt = self.render_prompt(
            "llm_guided_video_generation_user",
            **{
                "scene_number": scene_data.scene_number,
                "script_text": getattr(scene_data, 'script_text', ''),
                "visual_description": getattr(scene_data, 'visual_description', ''),
                "narrative_description": getattr(scene_data, 'narrative_description', ''),
                "mood_and_atmosphere": getattr(scene_data, 'mood_and_atmosphere', ''),
                "duration": scene_data.duration,
                "image_info": getattr(scene_data, 'image_url', '') or getattr(scene_data, 'image_path', ''),
                "continuity_analysis": continuity_analysis
            }
        )
        
        context_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        # 注入当前视频服务能力（例如仅支持的时长选项），供 LLM 决策参考
        try:
            from ..core.video_config_manager import get_video_config
            provider_config = get_video_config().get_current_provider_config()
            caps = provider_config.duration_capabilities or []
            if caps:
                caps_msg = f"当前视频生成服务仅支持以下时长(秒): {caps}. 请选择其一，不要给出列表外的数值。"
                context_messages.insert(1, {"role": "system", "content": caps_msg})
        except Exception:
            pass
        
        try:
            # 使用Function Call让LLM选择工具
            llm_response = await self.llm_function_call(
                messages=context_messages,
                context_description=f"生成场景{scene_data.scene_number}的视频",
                temperature=0.3
            )
            
            if llm_response.get("success") and llm_response.get("tool_calls"):
                return await self._execute_llm_selected_tools(
                    llm_response["tool_calls"], scene_data, continuity_analysis, workflow_state_id
                )
            else:
                # 如果LLM没有选择工具，使用默认策略
                self.logger.warning(f"LLM did not select tools for scene {scene_data.scene_number}, using default strategy")
                return await self._fallback_video_generation(scene_data, continuity_analysis, workflow_state_id)
                
        except Exception as e:
            self.logger.error(f"Function call failed for scene {scene_data.scene_number}: {e}")
            return await self._fallback_video_generation(scene_data, continuity_analysis, workflow_state_id)
    
    async def _llm_analyze_scene_continuity(
        self, scene_data, workflow_state_id: str
    ) -> Dict[str, Any]:
        """
        🧠 使用LLM智能分析场景连续性需求（符合MAS设计原则）
        
        ✅ 遵循CLAUDE.md原则：Agent → LLM Function Call → Dynamic Tool Selection → Intelligent Parameters
        """
        
        # 0) 显式脚本/规划标注：有 depends_on_scene 时视为强约束，直接决策，不走 LLM / fallback
        try:
            depends_on = getattr(scene_data, 'depends_on_scene', None)
            if isinstance(depends_on, int) and depends_on > 0:
                prev_frame = await self._try_get_previous_scene_frame(scene_data)
                reason = getattr(scene_data, 'continuity_reason', '脚本/规划显式标注需要连续性')
                self.logger.info(
                    f"🧷 Scene {scene_data.scene_number}: 显式连续性标注 → 依赖场景 {depends_on}, 跳过 LLM 与 fallback"
                )
                return {
                    "needs_continuity": True,
                    "llm_reasoning": reason,
                    "continuity_frame_path": prev_frame,
                    "decision_type": "explicit_script",
                }
        except Exception:
            pass

        # 🔍 构建连续性分析的上下文
        continuity_context = await self._build_continuity_analysis_context(scene_data, workflow_state_id)
        
        context_messages = [
            {
                "role": "system", 
                "content": """你是MuseCraft视频创作平台的连续性分析专家。你的职责是分析场景间的视觉连续性需求并提供智能决策。提示仅包含事实与约束，不包含任何能力或参数信息。你可以直接给出文本结论，或以结构化方式表达可执行的外部操作。请勿输出解释性头衔或代码块。

决策原则：
1. 分析场景间的叙事关联性
2. 考虑视觉元素的一致性需求  
3. 评估角色/物体的位置连续性
4. 判断时间和空间的逻辑关系
5. 优化用户观看体验

输出：直接返回中文结论，或返回结构化的可执行调用（不在文本中描述函数或参数）。"""
            },
            {
                "role": "user",
                "content": f"""请分析场景{scene_data.scene_number}的连续性需求：

**当前场景信息：**
- 场景号: {scene_data.scene_number}
- 标题: {getattr(scene_data, 'title', '')}  
- 脚本: {getattr(scene_data, 'script_text', '')}
- 视觉描述: {getattr(scene_data, 'visual_description', '')}
- 叙事描述: {getattr(scene_data, 'narrative_description', '')}
- 气氛: {getattr(scene_data, 'mood_and_atmosphere', '')}

**Script Writer建议：**
- 连续性策略: {getattr(scene_data, 'image_generation_strategy', 'new')}
- 依赖场景: {getattr(scene_data, 'depends_on_scene', None)}
- 连续性原因: {getattr(scene_data, 'continuity_reason', '')}

**上下文信息：**
{continuity_context}

请智能分析并决策该场景的连续性处理方案。"""
            }
        ]
        
        try:
            llm_response = await self.llm_function_call(
                messages=context_messages,
                context_description=f"分析场景{scene_data.scene_number}的连续性需求",
                temperature=0.2  # 较低温度确保一致性决策
            )
            
            if llm_response.get("has_function_call") and llm_response.get("tool_calls"):
                # LLM选择了连续性分析工具
                return await self._process_continuity_analysis_result(llm_response, scene_data)
            else:
                # LLM没有选择工具：仅在无显式标注的前提下使用智能 fallback（兜底）
                self.logger.info(f"🔄 Scene {scene_data.scene_number}: LLM未选择连续性工具，使用智能fallback")
                return await self._intelligent_continuity_fallback(scene_data, workflow_state_id)
                
        except Exception as e:
            self.logger.error(f"LLM continuity analysis failed for scene {scene_data.scene_number}: {e}")
            return await self._intelligent_continuity_fallback(scene_data, workflow_state_id)
    
    async def _build_continuity_analysis_context(
        self, scene_data, workflow_state_id: str  
    ) -> str:
        """构建连续性分析的上下文信息"""
        
        context_parts = []
        
        # 🧠 从全局记忆获取前序场景信息
        try:
            if scene_data.scene_number > 1:
                previous_scene_memories = await self.retrieve_scene_references(
                    workflow_state_id, scene_data.scene_number - 1
                )
                if previous_scene_memories:
                    context_parts.append(f"前一场景记忆信息: {previous_scene_memories}")
        except Exception as e:
            self.logger.warning(f"获取前序场景记忆失败: {e}")
        
        # 🔗 从连续性内存获取相关信息
        try:
            from ..core.scene_continuity_memory import get_scene_continuity_memory
            continuity_memory = get_scene_continuity_memory()
            
            # 检查是否有连续性映射
            if scene_data.scene_number in continuity_memory._continuity_mappings:
                mapping = continuity_memory._continuity_mappings[scene_data.scene_number]
                context_parts.append(
                    f"已记录的连续性需求: 场景{scene_data.scene_number} -> 场景{mapping.previous_scene} "
                    f"(原因: {mapping.reason}, 置信度: {mapping.confidence})"
                )
        except Exception as e:
            self.logger.warning(f"获取连续性记忆失败: {e}")
            
        return " | ".join(context_parts) if context_parts else "无额外上下文信息"
    
    async def _process_continuity_analysis_result(
        self, llm_response: Dict[str, Any], scene_data
    ) -> Dict[str, Any]:
        """处理LLM的连续性分析结果"""
        
        results = []
        
        for tool_call in llm_response["tool_calls"]:
            # 兼容BaseAgent已执行后的结果格式和原始FC格式
            if isinstance(tool_call, dict) and "function" in tool_call:
                function_name = tool_call["function"].get("name")
                function_args = tool_call["function"].get("arguments", {})
            else:
                function_name = tool_call.get("tool") or tool_call.get("name")
                function_args = tool_call.get("args", {})
            
            self.logger.info(f"🧠 LLM连续性决策: {function_name}")
            
            if function_name == "analyze_scene_continuity_need":
                # LLM决定需要连续性分析
                result = await self._handle_continuity_need_analysis(scene_data, function_args)
                
            elif function_name == "retrieve_previous_scene_frame":
                # LLM决定获取前一场景尾帧
                result = await self._handle_previous_frame_retrieval(scene_data, function_args)
                
            elif function_name == "skip_continuity_for_independent_scene":
                # LLM决定跳过连续性（独立场景）
                result = await self._handle_independent_scene_decision(scene_data, function_args)
            else:
                self.logger.warning(f"⚠️ Unknown continuity function: {function_name}")
                continue
                
            results.append(result)
        
        # 返回主要结果
        return results[0] if results else await self._intelligent_continuity_fallback(scene_data, None)
    
    async def _handle_continuity_need_analysis(
        self, scene_data, function_args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """处理LLM决定的连续性需求分析"""
        
        analysis_reason = function_args.get("reason", "LLM决策需要连续性分析")
        confidence = function_args.get("confidence", 0.8)
        
        # 尝试获取前一场景的尾帧
        previous_frame = await self._try_get_previous_scene_frame(scene_data)
        
        return {
            "needs_continuity": True,
            "llm_reasoning": analysis_reason,
            "confidence": confidence,
            "continuity_frame_path": previous_frame,
            "decision_type": "llm_continuity_analysis"
        }
    
    async def _handle_previous_frame_retrieval(
        self, scene_data, function_args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """处理LLM决定的前景尾帧获取"""
        
        target_scene = function_args.get("target_scene", scene_data.scene_number - 1)
        reason = function_args.get("reason", "LLM决策获取前景尾帧")
        
        previous_frame = await self._try_get_scene_final_frame(target_scene)
        
        return {
            "needs_continuity": bool(previous_frame),
            "llm_reasoning": reason,
            "continuity_frame_path": previous_frame,
            "target_scene": target_scene,
            "decision_type": "llm_frame_retrieval"
        }
    
    async def _handle_independent_scene_decision(
        self, scene_data, function_args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """处理LLM决定的独立场景标记"""
        
        reason = function_args.get("reason", "LLM决策：独立场景无需连续性")
        
        self.logger.info(f"🎬 Scene {scene_data.scene_number}: {reason}")
        
        return {
            "needs_continuity": False, 
            "llm_reasoning": reason,
            "continuity_frame_path": None,
            "decision_type": "llm_independent_scene"
        }
    
    async def _try_get_previous_scene_frame(self, scene_data) -> Optional[str]:
        """尝试获取用于连续性的上一参考场景的尾帧。

        优先使用 Script/Planner 标注的 depends_on_scene；若无，则回退为上一顺序场景（scene_number-1）。
        """
        # 明确标注的依赖场景（可非相邻）
        depends_on = getattr(scene_data, 'depends_on_scene', None)
        if isinstance(depends_on, int) and depends_on > 0:
            return await self._try_get_scene_final_frame(depends_on)

        # 无标注则使用上一顺序场景
        if scene_data.scene_number <= 1:
            return None
        return await self._try_get_scene_final_frame(scene_data.scene_number - 1)
    
    async def _try_get_scene_final_frame(self, scene_number: int) -> Optional[str]:
        """尝试获取指定场景的尾帧"""
        try:
            # 优先通过工具获取（从连续性内存读取），便于统一治理与埋点
            tool_result = await self.use_tool(
                "final_frame_tool",
                "get_final_frame_from_memory",
                {"scene_number": scene_number}
            )
            payload = getattr(tool_result, 'result', tool_result)
            val = None
            if isinstance(payload, dict):
                fmt = payload.get("format")
                if fmt == "data_url":
                    val = payload.get("data_url")
                elif fmt == "url":
                    val = payload.get("url")
                elif fmt == "path":
                    val = payload.get("path")

            if val:
                self.logger.info(
                    f"✅ 成功通过工具获取场景{scene_number}的尾帧（{('base64' if str(val).startswith('data:image') else 'url/path')}）"
                )
                return val

            self.logger.info(f"ℹ️ 工具未命中场景{scene_number}尾帧数据")
            return None
        except Exception as e:
            self.logger.error(f"获取场景{scene_number}尾帧失败: {e}")
            return None
    
    async def _intelligent_continuity_fallback(
        self, scene_data, workflow_state_id: Optional[str]
    ) -> Dict[str, Any]:
        """智能连续性fallback决策（当LLM分析失败时）"""

        # 基于场景特征的智能判断
        has_script_continuity_hint = getattr(scene_data, 'depends_on_scene', None) is not None
        is_first_scene = scene_data.scene_number <= 1

        needs_continuity = False
        reason = "独立场景，无连续性需求"
        if is_first_scene:
            reason = "首场景无需连续性"
            needs_continuity = False
        elif has_script_continuity_hint:
            reason = "基于Script Writer建议启用连续性"
            needs_continuity = True
        else:
            # 追加启发：对比概念规划的场景要素（主角/环境）
            try:
                if workflow_state_id:
                    from ..core.workflow_state import workflow_manager
                    wf = workflow_manager.get_workflow(workflow_state_id)
                    cp = (wf.concept_plan or {}) if wf else {}
                    scenes = cp.get("scenes", []) if isinstance(cp, dict) else []
                    cur = next((s for s in scenes if s.get("scene_number") == scene_data.scene_number), None)
                    prev = next((s for s in scenes if s.get("scene_number") == scene_data.scene_number - 1), None)
                    if cur and prev:
                        cur_ce = (cur.get("content_elements") or {})
                        prev_ce = (prev.get("content_elements") or {})
                        cur_chars = set(cur_ce.get("characters_present", []) or [])
                        prev_chars = set(prev_ce.get("characters_present", []) or [])
                        same_char = bool(cur_chars.intersection(prev_chars))
                        same_env = (cur_ce.get("environment") == prev_ce.get("environment") and cur_ce.get("environment"))
                        if same_char or same_env:
                            needs_continuity = True
                            reason = "基于概念规划：主角/环境连续"
            except Exception:
                pass
        
        continuity_frame = None
        if needs_continuity:
            continuity_frame = await self._try_get_previous_scene_frame(scene_data)
            
        self.logger.info(f"🔄 Scene {scene_data.scene_number} fallback决策: {reason}")
        
        return {
            "needs_continuity": needs_continuity,
            "llm_reasoning": reason,
            "continuity_frame_path": continuity_frame,
            "decision_type": "intelligent_fallback"
        }

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
        continuity_analysis: Dict[str, Any],
        workflow_state_id: str
    ) -> Dict[str, Any]:
        """执行LLM选择的工具调用"""
        
        results = []
        final_video_result = None
        
        for tool_call in tool_calls:
            # 兼容BaseAgent已执行后的结果格式和原始FC格式
            if isinstance(tool_call, dict) and "function" in tool_call:
                function_name = tool_call["function"].get("name")
                function_args = tool_call["function"].get("arguments", {})
                pre_executed_result = None
            else:
                function_name = tool_call.get("tool") or tool_call.get("name")
                function_args = tool_call.get("args", {})
                pre_executed_result = tool_call.get("result")
            
            self.logger.info(f"🤖 LLM选择调用工具: {function_name}")
            self.logger.info(f"📋 参数: {function_args}")
            
            try:
                # 解析工具名称和action
                if "_" in function_name:
                    tool_name, action = function_name.rsplit("_", 1)
                else:
                    tool_name = function_name
                    action = "execute"
                
                # 标准执行：按 FC 结果直接路由工具
                if pre_executed_result is not None:
                    tool_result = pre_executed_result
                else:
                    tool_result = await self.use_tool(tool_name, action, function_args)
                results.append({
                    "tool": function_name,
                    "args": function_args,
                    "result": tool_result
                })

                # 若为视频生成工具，抽取视频结果作为最终输出（同时保留结果集）
                is_video_gen = (
                    (tool_name == "video_generation" and action == "generate_video") or
                    (function_name in ("video_generation_generate_video", "video_generate_video"))
                )
                if is_video_gen and not final_video_result:
                    payload = getattr(tool_result, 'result', tool_result)
                    video_result = payload if isinstance(payload, dict) else {}
                    # 下载文件到本地（可选）
                    if video_result.get("video_url"):
                        try:
                            video_result["video_path"] = await self._save_video_from_result(video_result, scene_data.scene_number)
                        except Exception as se:
                            self.logger.warning(f"Failed to save video locally: {se}")
                    final_video_result = video_result
                
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
                scene_data, continuity_analysis, workflow_state_id
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
        
        # 获取基本参数（直接透传给工具，由工具Schema进行严格校验）
        prompt = llm_params.get("prompt")
        
        # 如果没有prompt，可按需生成（保持最小入侵；工具仍可校验为空的场景）
        if not prompt:
            try:
                prompt = await self._build_enhanced_video_prompt(scene_data, workflow_state_id)
            except Exception:
                prompt = None
        
        # 准备图像输入 - 优先使用连续性帧
        image_input = continuity_frame_path if continuity_frame_path else (
            scene_data.image_url or scene_data.image_path
        )
        
        if not image_input:
            raise AgentError(f"No image input available for scene {scene_data.scene_number}")
        
        # 若为本地路径或data URL，则按需上传到OSS以获取可用HTTP URL（Zhipu需要URL）
        image_url_for_provider = await self._ensure_image_url(image_input, scene_data.scene_number)
        
        # 使用video_generation工具（参数尽量原样透传；仅对image_url做提供商要求的规范化）
        try:
            tool_params = {
                "prompt": prompt,
                "duration": llm_params.get("duration"),
                "model": llm_params.get("model"),
                "first_frame_image": llm_params.get("first_frame_image"),
                "last_frame_image": llm_params.get("last_frame_image"),
                # 仅规范化 image_url，满足视频服务对URL的要求
                "image_url": image_url_for_provider,
                "continuity_frame": continuity_frame_path,
            }
            result = await self.use_tool("video_generation", "generate_video", tool_params)
            
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

    def _normalize_duration(self, desired: int) -> int:
        """将期望时长映射到提供商支持的时长（如 [5,10]）。"""
        try:
            video_config = get_video_config()
            provider_config = video_config.get_current_provider_config()
            caps = list(provider_config.duration_capabilities or [])
            if not caps:
                return desired
            # 取最接近的可用时长
            best = min(caps, key=lambda x: abs(int(x) - int(desired)))
            return int(best)
        except Exception:
            return desired

    async def _ensure_image_url(self, image_input: str, scene_number: int) -> str:
        """确保传入Zhipu的视频生成的是HTTP(S) URL。

        - 若已是http/https，直接返回。
        - 若是data URL，解码后上传至OSS获取公开URL；失败则异常（不返回 file://）。
        - 若是本地路径，上传至OSS获取公开URL；失败则异常。
        """
        try:
            if isinstance(image_input, str) and (image_input.startswith("http://") or image_input.startswith("https://")):
                return image_input
            
            remote_path = f"images/scene_{scene_number}_first_frame.jpg"
            if isinstance(image_input, str) and image_input.startswith("data:image"):
                header, b64 = image_input.split(",", 1)
                import base64
                # 直接传content（字符串），工具内部会编码
                content_bytes = base64.b64decode(b64)
                res = await self.use_tool(
                    "oss_storage",
                    "upload",
                    {
                        "content": content_bytes,
                        "remote_path": remote_path,
                        "content_type": "image/jpeg",
                        "public_read": True,
                        "metadata": {"scene_number": scene_number, "source": "video_generation"}
                    }
                )
            else:
                res = await self.use_tool(
                    "oss_storage",
                    "upload",
                    {
                        "local_path": image_input,
                        "remote_path": remote_path,
                        "content_type": "image/jpeg",
                        "public_read": True,
                        "metadata": {"scene_number": scene_number, "source": "video_generation"}
                    }
                )
            payload = getattr(res, 'result', res)
            if isinstance(payload, dict) and payload.get("url"):
                return payload["url"]
            raise AgentError("Failed to obtain image URL from OSS upload result")
        except Exception as e:
            self.logger.error(f"确保 image_url 失败: {e}")
            raise AgentError(f"Unable to ensure image URL for provider: {e}")
    
    async def _fallback_video_generation(
        self,
        scene_data,
        continuity_analysis: Dict[str, Any],
        workflow_state_id: str
    ) -> Dict[str, Any]:
        """默认的视频生成策略（当Function Call失败时使用）"""
        
        self.logger.info(f"Using fallback video generation for scene {scene_data.scene_number}")
        
        # 使用现有的方法生成视频
        continuity_frame_path = continuity_analysis.get("continuity_frame_path")
        
        self.logger.info(f"🔄 Scene {scene_data.scene_number} fallback视频生成:")
        self.logger.info(f"  - 连续性需求: {continuity_analysis.get('needs_continuity', False)}")
        self.logger.info(f"  - LLM推理: {continuity_analysis.get('llm_reasoning', '无')}")
        self.logger.info(f"  - 决策类型: {continuity_analysis.get('decision_type', 'unknown')}")
        
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
                        scene_data.scene_number, final_frame_data  # path/url（不再写回base64）
                    )
                    # 标准化日志输出
                    if isinstance(final_frame_data, str) and final_frame_data.startswith("data:"):
                        self.logger.info(
                            f"💾 Stored final frame (data_url) for Scene {scene_data.scene_number}: {len(final_frame_data)} chars"
                        )
                    elif isinstance(final_frame_data, str) and (final_frame_data.startswith("http://") or final_frame_data.startswith("https://")):
                        self.logger.info(
                            f"💾 Stored final frame (url) for Scene {scene_data.scene_number}: {final_frame_data}"
                        )
                    else:
                        self.logger.info(
                            f"💾 Stored final frame (path) for Scene {scene_data.scene_number}: {final_frame_data}"
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
        连续性帧存储策略（FC 友好版）：
        - 不再将图片以 base64 形式存入内存；
        - 直接返回本地文件路径，由后续 FC 工具链（例如 oss_storage.upload）在需要 URL 时自行处理；
        - 保持最小副作用，避免在此处做上云。
        """
        try:
            if not frame_path:
                return None
            # 仅返回路径，不做任何上传或转码，便于 FC 链路使用轻量引用（scene_number + path）。
            return frame_path
        except Exception as e:
            self.logger.error(f"Failed to handle continuity frame path: {e}")
            return None
    
    async def _extract_video_final_frame(self, video_source: str, scene_number: int) -> Optional[str]:
        """
        使用工具（FFmpegTool）从视频中提取最后一帧

        Args:
            video_source: 视频文件路径或URL
            scene_number: 场景号

        Returns:
            最后一帧图片的文件路径
        """
        try:
            params = {
                "output_format": "jpg",
                "output_filename": f"scene_{scene_number}_final_frame.jpg",
                "time_tolerance": 0.1,
            }
            if isinstance(video_source, str) and (video_source.startswith("http://") or video_source.startswith("https://")):
                params["video_url"] = video_source
            else:
                params["video_path"] = video_source

            result = await self.use_tool("ffmpeg_tool", "extract_last_frame", params)
            payload = getattr(result, 'result', result)
            if isinstance(payload, dict):
                out_path = payload.get("image_path")
                if out_path:
                    self.logger.info(f"✅ Extracted final frame via tool: {out_path}")
                    return out_path
            self.logger.warning("FFmpegTool did not return image_path for last frame")
            return None
        except Exception as e:
            self.logger.error(f"Failed to extract final frame via tool: {e}")
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
            "video_generation",
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
                    "video_generation",
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
                    "video_generation",
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
            self.logger.info(f"🔧 Tool video_generation:generate_video executed successfully")
            
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
        
        # 通过FC让LLM自主决定是否需要工具（中文约束已在llm_function_call内）
        fc = await self.llm_function_call(
            messages=[{"role": "user", "content": motion_prompt_template}],
            context_description=f"为场景{scene_data.scene_number}生成中文视频动作提示词，如无需工具可直接在content返回",
        )
        
        # 注意：FC 已记录摘要日志，此处无需再打印大段内容
        
        # 处理FC结果：优先content路径（文本），若工具路径则从工具结果中提取content
        if fc.get("approach") == "text_response":
            enhanced_prompt = (fc.get("content") or "").strip()
        elif fc.get("approach") == "function_call" and fc.get("tool_calls"):
            first = fc["tool_calls"][0]
            r = first.get("result", {}) or {}
            if isinstance(r, dict):
                enhanced_prompt = (r.get("content") or r.get("prompt") or "").strip()
            else:
                enhanced_prompt = str(r).strip()
        else:
            enhanced_prompt = ""
        
        # 长度控制：优先用 LLM 压缩到限制内，而不是直接截断
        if len(enhanced_prompt) > provider_config.prompt_max_length:
            enhanced_prompt = await self._fit_prompt_to_limit(
                enhanced_prompt, provider_config.prompt_max_length
            )
        
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
        
        # 通过FC让LLM自主决定是否需要工具（中文约束已在llm_function_call内）
        fc = await self.llm_function_call(
            messages=[{"role": "user", "content": video_prompt_template}],
            context_description=f"为当前场景生成中文视频提示词，如无需工具可直接在content返回",
        )

        # 处理FC结果：优先content路径（文本），若工具路径则从工具结果中提取content
        if fc.get("approach") == "text_response":
            enhanced_prompt = (fc.get("content") or "").strip()
        elif fc.get("approach") == "function_call" and fc.get("tool_calls"):
            first = fc["tool_calls"][0]
            r = first.get("result", {}) or {}
            if isinstance(r, dict):
                enhanced_prompt = (r.get("content") or r.get("prompt") or "").strip()
            else:
                enhanced_prompt = str(r).strip()
        else:
            enhanced_prompt = ""
        
        # 长度控制：优先用 LLM 压缩到限制内，而不是直接截断
        if len(enhanced_prompt) > provider_config.prompt_max_length:
            enhanced_prompt = await self._fit_prompt_to_limit(
                enhanced_prompt, provider_config.prompt_max_length
            )
        
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
            if "video_url" in video_result and video_result["video_url"]:
                # 通过文件存储工具从URL持久化（工具内部处理下载与保存）
                filename = f"scene_{scene_number}_video.mp4"
                upload = await self.use_tool(
                    "file_storage_tool",
                    "upload_from_url",
                    {
                        "url": video_result["video_url"],
                        "destination_key": f"videos/{filename}",
                        "metadata": {"scene_number": scene_number, "source": "video_generation"}
                    }
                )
                payload = getattr(upload, 'result', upload)
                file_path = payload.get("local_path") if isinstance(payload, dict) else ""
            elif "video_data" in video_result and video_result["video_data"]:
                # 通过文件存储工具保存base64/二进制数据
                filename = f"scene_{scene_number}_video.mp4"
                upload = await self.use_tool(
                    "file_storage_tool",
                    "upload_base64",
                    {
                        "base64_data": video_result["video_data"],
                        "filename": filename,
                        "content_type": "video/mp4"
                    }
                )
                payload = getattr(upload, 'result', upload)
                file_path = payload.get("local_path") if isinstance(payload, dict) else ""
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
        
        # 通过FC让LLM自主决定是否需要工具（中文约束已在llm_function_call内）
        fc = await self.llm_function_call(
            messages=[{"role": "user", "content": video_prompt_template}],
            context_description=f"为当前场景生成中文视频提示词，如无需工具可直接在content返回",
        )

        if fc.get("approach") == "text_response":
            enhanced_prompt = (fc.get("content") or "").strip()
        elif fc.get("approach") == "function_call" and fc.get("tool_calls"):
            first = fc["tool_calls"][0]
            r = first.get("result", {}) or {}
            if isinstance(r, dict):
                enhanced_prompt = (r.get("content") or r.get("prompt") or "").strip()
            else:
                enhanced_prompt = str(r).strip()
        else:
            enhanced_prompt = ""
        
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
        # 使用文件存储工具从URL持久化
        upload = await self.use_tool(
            "file_storage_tool",
            "upload_from_url",
            {
                "url": video_url,
                "destination_key": f"videos/{filename}",
                "metadata": {"scene_id": scene.id, "task_id": task.id, "source": "video_generation"}
            }
        )
        payload = getattr(upload, 'result', upload)
        file_path = payload.get("local_path") if isinstance(payload, dict) else ""
        if not file_path:
            raise AgentError("Failed to persist video via storage tool")

        # Get file info via工具
        info = await self.use_tool(
            "file_storage_tool",
            "get_file_info",
            {"file_path": file_path}
        )
        file_info = getattr(info, 'result', info) if isinstance(info, dict) or hasattr(info, 'result') else {}
        
        # Create resource record
        resource = Resource(
            task_id=task.id,
            scene_id=scene.id,
            filename=filename,
            original_filename=filename,
            file_path=file_path,
            resource_type=ResourceType.VIDEO,
            mime_type="video/mp4",
            file_size=(file_info.get("size") if isinstance(file_info, dict) else None) or 0,
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

        # 通过FC让LLM自主决定是否需要工具（中文约束已在llm_function_call内）
        fc = await self.llm_function_call(
            messages=[{"role": "user", "content": video_prompt_template}],
            context_description=f"为场景{scene_data.scene_number}生成中文视频提示词（增强版），如无需工具可直接在content返回",
        )

        # 处理FC结果：优先content路径（文本），若工具路径则从工具结果中提取content
        if fc.get("approach") == "text_response":
            enhanced_prompt = (fc.get("content") or "").strip()
        elif fc.get("approach") == "function_call" and fc.get("tool_calls"):
            first = fc["tool_calls"][0]
            r = first.get("result", {}) or {}
            if isinstance(r, dict):
                enhanced_prompt = (r.get("content") or r.get("prompt") or "").strip()
            else:
                enhanced_prompt = str(r).strip()
        else:
            enhanced_prompt = ""
        
        # 如果LLM生成的提示词为空，使用fallback
        if not enhanced_prompt:
            fallback_prompt = f"{scene_data.description or scene_data.title or 'Video scene'}, {scene_data.mood_and_atmosphere or 'cinematic style'}"
            self.logger.warning(f"⚠️ Empty enhanced_prompt, using fallback: '{fallback_prompt}'")
            enhanced_prompt = fallback_prompt
        
        # 限制提示词长度：使用 LLM 压缩到当前提供商限制，而非直接截断
        from ..core.video_config_manager import get_video_config
        video_config = get_video_config()
        provider_config = video_config.get_current_provider_config()
        max_len = getattr(provider_config, 'prompt_max_length', 512)
        if len(enhanced_prompt) > max_len:
            enhanced_prompt = await self._fit_prompt_to_limit(enhanced_prompt, max_len)
        
        self.logger.info(f"🎬 Generated enhanced video prompt for scene {scene_data.scene_number} (length: {len(enhanced_prompt)}): {enhanced_prompt[:100]}...")
        return enhanced_prompt

    async def _fit_prompt_to_limit(self, text: str, max_len: int) -> str:
        """使用 LLM 将文本压缩到不超过 max_len（优先保持关键信息），失败则抛错，不做静默截断。"""
        try:
            instruction = (
                f"请将以下文本压缩到不超过{max_len}个字符，保留关键信息与风格关键词。"
                "只返回压缩后的文本，不要解释、标题或代码块。"
            )
            messages = [
                {"role": "system", "content": instruction},
                {"role": "user", "content": text},
            ]
            fc = await self.llm_function_call(
                messages=messages,
                context_description=f"压缩视频提示词至≤{max_len}字符",
            )
            if fc.get("approach") == "text_response":
                compressed = (fc.get("content") or "").strip()
            elif fc.get("approach") == "function_call" and fc.get("tool_calls"):
                first = fc["tool_calls"][0]
                r = first.get("result", {}) or {}
                compressed = (r.get("content") or r.get("text") or r.get("prompt") or "").strip() if isinstance(r, dict) else str(r).strip()
            else:
                compressed = ""

            if not compressed:
                raise AgentError("LLM未返回有效的压缩结果")
            if len(compressed) > max_len:
                raise AgentError(f"LLM压缩结果仍超过长度限制（{len(compressed)}/{max_len}）")
            return compressed
        except Exception as e:
            self.logger.error(f"提示词压缩失败: {e}")
            # 遵循你的策略：过长不做静默截断，直接报错以便定位根因
            raise

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

            # ✅ 使用业务级图像工具进行视觉特征提取（注册名：image_generation）
            try:
                result = await self.use_tool(
                    tool_name="image_generation",
                    action="extract_visual_features",
                    parameters={
                        "image_url": image_url
                    }
                )
                payload = getattr(result, 'result', result)
                description = ""
                if isinstance(payload, dict) and payload.get("success"):
                    vf = payload.get("visual_features")
                    if isinstance(vf, dict):
                        # 简单串联为可读文本
                        parts = []
                        for k, v in vf.items():
                            try:
                                parts.append(f"{k}: {v}")
                            except Exception:
                                continue
                        description = "；".join(parts)
                    elif isinstance(vf, str):
                        description = vf
                if not description:
                    self.logger.warning("Image feature extraction returned empty; fallback to scene description")
                    description = f"首帧图像显示{scene_data.description}的静态场景"
            except Exception as e:
                self.logger.error(f"Image feature extraction failed: {str(e)}")
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
