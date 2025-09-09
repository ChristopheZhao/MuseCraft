"""
DEPRECATION NOTICE (archived)
Legacy experimental module archived. Do not import in new flows.
"""
import warnings as _warnings
raise ImportError(
    "Archived legacy module 'video_generator_old_loop'. Do not import in production."
)
import asyncio
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from .react_agent import ReActAgent
from ..models import Task, AgentExecution, AgentType, Scene
from ..core.video_config_manager import get_video_config


class VideoGeneratorAgent(ReActAgent):
    """
    视频生成Agent - 继承ReAct能力
    
    支持多场景动态依赖处理：
    - 智能分析场景间连续性需求
    - 动态调度并行vs串行执行
    - 处理连续性链的异常情况
    """
    
    def __init__(self):
        from ..core.config import settings
        super().__init__(
            agent_type=AgentType.VIDEO_GENERATOR,
            agent_name="video_generator",
            max_iterations=settings.VIDEO_GENERATOR_MAX_ITERATIONS,  # 从配置读取最大迭代次数
            timeout_seconds=900  # 15分钟超时
        )
        self.video_config = get_video_config()
        self.logger.info(f"VideoGeneratorAgent (ReAct) initialized with tools: {self.get_tool_names()}")
    
    def get_tool_names(self):
        """获取已分配工具名称列表"""
        return [tool_name for tool_name in self._available_tools.keys()] if self._available_tools else []
    
    # === ReAct循环实现 ===
    
    async def _observe_current_state(
        self, 
        input_data: Dict[str, Any], 
        context: Dict[str, Any], 
        iteration: int
    ) -> Dict[str, Any]:
        """
        观察当前多场景状态和依赖关系
        """
        workflow_state_id = input_data["workflow_state_id"]
        
        # 获取场景数据
        from ..core.workflow_state import workflow_manager
        workflow_state = workflow_manager.get_workflow(workflow_state_id)
        if not workflow_state:
            raise ValueError(f"WorkflowState {workflow_state_id} not found")
        
        scenes_data = workflow_state.scenes
        if not scenes_data:
            raise ValueError("No scenes found in workflow state")
        
        # 分析当前状态
        completed_scenes = context.get("cumulative_results", {}).get("completed_scenes", {})
        failed_scenes = context.get("cumulative_results", {}).get("failed_scenes", [])
        
        # 分析可执行场景和依赖关系
        executable_scenes = []
        pending_dependencies = []
        
        for scene in scenes_data:
            scene_status = self._analyze_scene_status(scene, completed_scenes, failed_scenes)
            
            if scene_status["executable"]:
                executable_scenes.append({
                    "scene": scene,
                    "continuity_needed": scene_status["continuity_needed"],
                    "dependency_scene": scene_status["dependency_scene"]
                })
            else:
                pending_dependencies.append({
                    "scene": scene,
                    "blocking_dependency": scene_status["blocking_dependency"],
                    "reason": scene_status["reason"]
                })
        
        await self.log_decision(
            f"Analyzed {len(scenes_data)} scenes: {len(executable_scenes)} executable, {len(pending_dependencies)} pending",
            f"Completed: {list(completed_scenes.keys())}, Failed: {failed_scenes}"
        )
        
        return {
            "scenes_total": len(scenes_data),
            "executable_scenes": executable_scenes,
            "pending_dependencies": pending_dependencies,
            "completed_scenes": completed_scenes,
            "failed_scenes": failed_scenes,
            "workflow_state_id": workflow_state_id,
            "iteration": iteration
        }
    
    async def _think_and_plan(
        self, 
        current_state: Dict[str, Any], 
        task: Task, 
        execution: AgentExecution,
        iteration: int
    ) -> Dict[str, Any]:
        """
        LLM规划多场景执行策略
        """
        executable_scenes = current_state["executable_scenes"]
        pending_dependencies = current_state["pending_dependencies"]
        completed_scenes = current_state["completed_scenes"]
        
        if not executable_scenes and not pending_dependencies:
            # 所有场景都已处理
            return {"strategy": "complete", "no_action_needed": True}
        
        if not executable_scenes:
            # 没有可执行场景，可能存在循环依赖或其他问题
            return {"strategy": "deadlock_analysis", "issue": "no_executable_scenes"}
        
        # 构建LLM规划提示
        system_prompt = """你是MuseCraft视频生成专家，负责规划多场景视频生成的执行策略。
        
你的职责：
1. 分析场景依赖关系，决定执行顺序
2. 判断哪些场景可以并行执行
3. 为需要连续性的场景选择合适的工具
4. 处理异常情况和依赖问题

请根据当前状态制定最优的执行计划。"""
        
        # 构建场景信息
        executable_info = []
        for item in executable_scenes:
            scene = item["scene"]
            executable_info.append({
                "scene_number": scene.scene_number,
                "title": getattr(scene, 'title', ''),
                "needs_continuity": item["continuity_needed"],
                "depends_on_scene": item.get("dependency_scene")
            })
        
        user_prompt = f"""
当前状态分析：

**可执行场景** ({len(executable_scenes)}个):
{executable_info}

**等待依赖场景** ({len(pending_dependencies)}个):
{[{"scene": p["scene"].scene_number, "waiting_for": p["blocking_dependency"]} for p in pending_dependencies]}

**已完成场景**: {list(completed_scenes.keys())}

**本次迭代**: {iteration + 1}/5

请规划下一步执行策略：
1. 选择本次要处理的场景（建议1-3个场景并行）
2. 为每个场景选择合适的工具和参数
3. 说明执行顺序和并行策略
"""
        
        try:
            planning_response = await self.llm_function_call(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                context_description="规划多场景视频生成策略",
                temperature=0.3
            )
            
            # 记录详细的规划内容
            self.logger.info(f"🎯 VideoAgent Plan Details:")
            self.logger.info(f"📋 LLM Response: {planning_response}")
            self.logger.info(f"🔧 Strategy: {planning_response.get('strategy', 'tool_calls')}")
            if planning_response.get('tool_calls'):
                self.logger.info(f"🛠️ Tool Calls: {len(planning_response['tool_calls'])}")
                for i, tool_call in enumerate(planning_response['tool_calls']):
                    self.logger.info(f"   {i+1}. {tool_call.get('function', {}).get('name')}: {tool_call.get('function', {}).get('arguments', {})}")
            else:
                self.logger.info(f"⚠️ No tool calls - LLM returned content only")
                if planning_response.get('content'):
                    self.logger.info(f"📝 LLM Content: {planning_response['content'][:200]}...")
            
            # 记录规划决策
            await self.log_decision(
                f"Planned execution for {len(executable_scenes)} scenes",
                f"LLM strategy: {planning_response.get('strategy', 'tool_calls')}"
            )
            
            return planning_response
            
        except Exception as e:
            self.logger.error(f"Planning failed: {e}")
            
            # fallback规划：简单的并行执行
            return {
                "strategy": "fallback_parallel",
                "scenes_to_execute": executable_scenes[:2],  # 最多并行处理2个场景
                "reason": f"LLM planning failed: {e}"
            }
    
    async def _execute_action(
        self, 
        action_plan: Dict[str, Any], 
        input_data: Dict[str, Any], 
        execution: AgentExecution,
        db: Session,
        iteration: int
    ) -> Dict[str, Any]:
        """
        执行规划的行动
        """
        strategy = action_plan.get("strategy", "tool_calls")
        
        if strategy == "complete":
            return {"execution_complete": True}
        
        if strategy == "deadlock_analysis":
            return await self._handle_deadlock_situation(action_plan, input_data)
        
        if strategy == "fallback_parallel":
            return await self._execute_fallback_parallel(action_plan, input_data, execution, db)
        
        # 标准的LLM工具调用执行
        if action_plan.get("tool_calls"):
            return await self._execute_llm_tool_calls(action_plan, input_data, execution, db)
        
        # 如果LLM没有使用工具，尝试解析其content中的执行指令
        if action_plan.get("content"):
            return await self._execute_content_based_plan(action_plan, input_data, execution, db)
        
        raise ValueError(f"Unknown execution strategy: {strategy}")
    
    async def _reflect_on_results(
        self, 
        action_result: Dict[str, Any], 
        current_state: Dict[str, Any], 
        task: Task,
        iteration: int
    ) -> Dict[str, Any]:
        """
        反思执行结果，决定是否继续迭代
        """
        if action_result.get("execution_complete"):
            return {
                "task_complete": True,
                "context_updates": {},
                "completion_reason": "all_scenes_processed"
            }
        
        # 更新完成和失败的场景
        new_completed = action_result.get("completed_scenes", {})
        new_failed = action_result.get("failed_scenes", [])
        
        # 分析总体进展
        total_scenes = current_state["scenes_total"]
        total_completed = len(current_state["completed_scenes"]) + len(new_completed)
        total_failed = len(current_state["failed_scenes"]) + len(new_failed)
        total_processed = total_completed + total_failed
        
        # 构建反思提示
        reflection_prompt = f"""
分析视频生成执行结果：

**本次执行结果**:
- 新完成场景: {list(new_completed.keys())}
- 新失败场景: {new_failed}
- 执行详情: {action_result.get("execution_summary", "")}

**整体进度**:
- 总场景数: {total_scenes}
- 已完成: {total_completed}/{total_scenes}
- 已失败: {total_failed}/{total_scenes} 
- 总处理: {total_processed}/{total_scenes}

**当前迭代**: {iteration + 1}/5

请判断：
1. 任务是否已完成？
2. 结果质量是否满足要求？
3. 是否需要继续迭代？
4. 如果需要停止，原因是什么？

直接返回判断结果，不需要解释。
"""
        
        try:
            reflection_response = await self.llm_function_call(
                messages=[{"role": "user", "content": reflection_prompt}],
                context_description="反思视频生成执行结果",
                temperature=0.2
            )
            
            # 解析反思结果
            task_complete = (
                reflection_response.get("task_complete", False) or
                total_processed >= total_scenes or
                reflection_response.get("content", "").find("任务完成") != -1
            )
            
            should_stop = reflection_response.get("should_stop", False)
            stop_reason = reflection_response.get("stop_reason", "")
            
            await self.log_decision(
                f"Reflection: complete={task_complete}, processed={total_processed}/{total_scenes}",
                f"LLM assessment: {reflection_response.get('content', '')[:100]}"
            )
            
            return {
                "task_complete": task_complete,
                "should_stop": should_stop,
                "stop_reason": stop_reason,
                "context_updates": {
                    "completed_scenes": {**current_state["completed_scenes"], **new_completed},
                    "failed_scenes": current_state["failed_scenes"] + new_failed
                },
                "progress_stats": {
                    "total_scenes": total_scenes,
                    "completed": total_completed,
                    "failed": total_failed,
                    "processed": total_processed
                }
            }
            
        except Exception as e:
            self.logger.error(f"Reflection failed: {e}")
            
            # Fallback反思逻辑
            task_complete = total_processed >= total_scenes
            
            return {
                "task_complete": task_complete,
                "should_stop": False,
                "context_updates": {
                    "completed_scenes": {**current_state["completed_scenes"], **new_completed},
                    "failed_scenes": current_state["failed_scenes"] + new_failed
                },
                "reflection_error": str(e)
            }
    
    # === 场景分析和执行的辅助方法 ===
    
    def _analyze_scene_status(
        self, 
        scene, 
        completed_scenes: Dict, 
        failed_scenes: List
    ) -> Dict[str, Any]:
        """
        分析单个场景的执行状态
        """
        scene_number = scene.scene_number
        
        # 检查是否已处理
        if scene_number in completed_scenes:
            return {"executable": False, "reason": "already_completed"}
        
        if scene_number in failed_scenes:
            return {"executable": False, "reason": "already_failed"}
        
        # 检查依赖关系
        depends_on = getattr(scene, 'depends_on_scene', None)
        continuity_needed = False
        
        if depends_on and isinstance(depends_on, int):
            # 需要连续性
            continuity_needed = True
            
            if depends_on in completed_scenes:
                # 依赖场景已完成，可以执行
                return {
                    "executable": True,
                    "continuity_needed": True,
                    "dependency_scene": depends_on
                }
            else:
                # 依赖场景未完成，需要等待
                return {
                    "executable": False,
                    "reason": "waiting_for_dependency",
                    "blocking_dependency": depends_on
                }
        else:
            # 独立场景，可以直接执行
            return {
                "executable": True,
                "continuity_needed": False,
                "dependency_scene": None
            }
    
    async def _execute_llm_tool_calls(
        self,
        action_plan: Dict[str, Any],
        input_data: Dict[str, Any],
        execution: AgentExecution,
        db: Session
    ) -> Dict[str, Any]:
        """
        执行LLM选择的工具调用
        """
        tool_calls = action_plan["tool_calls"]
        results = []
        completed_scenes = {}
        failed_scenes = []
        
        # 并行执行工具调用
        for tool_call in tool_calls:
            try:
                # 解析工具调用
                if isinstance(tool_call, dict) and "function" in tool_call:
                    function_name = tool_call["function"].get("name")
                    function_args = tool_call["function"].get("arguments", {})
                else:
                    function_name = tool_call.get("tool") or tool_call.get("name")
                    function_args = tool_call.get("args", {})
                
                self.logger.info(f"🤖 执行工具调用: {function_name}")
                
                # 解析工具名称和action
                if "_" in function_name:
                    tool_name, action = function_name.rsplit("_", 1)
                else:
                    tool_name = function_name
                    action = "execute"
                
                # 执行工具
                tool_result = await self.use_tool(tool_name, action, function_args)
                
                results.append({
                    "tool": function_name,
                    "args": function_args,
                    "result": tool_result,
                    "success": True
                })
                
                # 如果是视频生成工具，记录场景完成
                if self._is_video_generation_tool(tool_name, action):
                    scene_number = function_args.get("scene_number")
                    if scene_number:
                        completed_scenes[scene_number] = {
                            "video_result": getattr(tool_result, 'result', tool_result),
                            "tool_used": function_name
                        }
                
            except Exception as e:
                self.logger.error(f"工具调用失败 {function_name}: {e}")
                
                results.append({
                    "tool": function_name,
                    "args": function_args,
                    "error": str(e),
                    "success": False
                })
                
                # 记录失败的场景
                scene_number = function_args.get("scene_number")
                if scene_number:
                    failed_scenes.append(scene_number)
        
        return {
            "tool_results": results,
            "completed_scenes": completed_scenes,
            "failed_scenes": failed_scenes,
            "execution_summary": f"Executed {len(results)} tool calls, {len(completed_scenes)} scenes completed, {len(failed_scenes)} failed"
        }
    
    async def _execute_fallback_parallel(
        self,
        action_plan: Dict[str, Any],
        input_data: Dict[str, Any],
        execution: AgentExecution,
        db: Session
    ) -> Dict[str, Any]:
        """
        Fallback并行执行策略
        """
        scenes_to_execute = action_plan.get("scenes_to_execute", [])
        
        if not scenes_to_execute:
            return {"completed_scenes": {}, "failed_scenes": []}
        
        # 并行执行场景
        tasks = []
        for scene_item in scenes_to_execute:
            scene = scene_item["scene"]
            task = self._generate_scene_video(scene, scene_item, input_data)
            tasks.append(task)
        
        # 等待所有任务完成
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        completed_scenes = {}
        failed_scenes = []
        
        for i, result in enumerate(results):
            scene = scenes_to_execute[i]["scene"]
            scene_number = scene.scene_number
            
            if isinstance(result, Exception):
                self.logger.error(f"场景 {scene_number} 执行失败: {result}")
                failed_scenes.append(scene_number)
            else:
                self.logger.info(f"场景 {scene_number} 执行成功")
                completed_scenes[scene_number] = result
        
        return {
            "completed_scenes": completed_scenes,
            "failed_scenes": failed_scenes,
            "execution_summary": f"Fallback execution: {len(completed_scenes)} completed, {len(failed_scenes)} failed"
        }
    
    async def _generate_scene_video(
        self,
        scene,
        scene_item: Dict[str, Any],
        input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        生成单个场景的视频
        """
        try:
            # 处理连续性
            continuity_frame_url = None
            if scene_item["continuity_needed"]:
                dependency_scene = scene_item["dependency_scene"]
                continuity_frame_url = await self._get_continuity_frame_url(dependency_scene)
            
            # 调用视频生成工具
            generation_params = {
                "prompt": getattr(scene, 'video_prompt', '') or getattr(scene, 'script_text', ''),
                "duration": scene.duration,
                "image_url": continuity_frame_url or getattr(scene, 'image_url', ''),
                "scene_number": scene.scene_number
            }
            
            video_result = await self.use_tool("video_generation", "generate_video", generation_params)
            
            return {
                "scene_number": scene.scene_number,
                "video_result": getattr(video_result, 'result', video_result),
                "generation_params": generation_params
            }
            
        except Exception as e:
            raise Exception(f"Failed to generate video for scene {scene.scene_number}: {e}")
    
    async def _get_continuity_frame_url(self, dependency_scene_number: int) -> Optional[str]:
        """
        获取依赖场景的连续性帧URL
        """
        try:
            # 这里应该从已完成的场景结果中获取尾帧
            # 或者调用final_frame_tool提取
            completed_scenes = self.get_cumulative_results().get("completed_scenes", {})
            
            if dependency_scene_number in completed_scenes:
                scene_result = completed_scenes[dependency_scene_number]
                video_url = scene_result.get("video_result", {}).get("video_url")
                
                if video_url:
                    # 调用尾帧提取工具
                    frame_result = await self.use_tool(
                        "final_frame_tool", 
                        "extract_final_frame",
                        {"video_url": video_url}
                    )
                    
                    # 上传到OSS获取URL
                    if hasattr(frame_result, 'result'):
                        frame_data = frame_result.result
                        upload_result = await self.use_tool(
                            "oss_storage",
                            "upload",
                            {
                                "content": frame_data,
                                "remote_path": f"continuity_frames/scene_{dependency_scene_number}_final.jpg",
                                "content_type": "image/jpeg",
                                "public_read": True
                            }
                        )
                        
                        if hasattr(upload_result, 'result'):
                            return upload_result.result.get("url")
            
            return None
            
        except Exception as e:
            self.logger.error(f"Failed to get continuity frame for scene {dependency_scene_number}: {e}")
            return None
    
    def _is_video_generation_tool(self, tool_name: str, action: str) -> bool:
        """
        判断是否为视频生成工具
        """
        return (
            tool_name == "video_generation" and action == "generate_video"
        ) or (
            tool_name in ["video_generation_generate_video", "video_generate_video"]
        )
    
    async def _handle_deadlock_situation(
        self,
        action_plan: Dict[str, Any],
        input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        处理死锁情况（没有可执行场景）
        """
        self.logger.error("Detected deadlock situation: no executable scenes")
        
        return {
            "deadlock_detected": True,
            "completed_scenes": {},
            "failed_scenes": [],
            "execution_summary": "Deadlock detected - no scenes can be executed"
        }
    
    async def _execute_content_based_plan(
        self,
        action_plan: Dict[str, Any],
        input_data: Dict[str, Any],
        execution: AgentExecution,
        db: Session
    ) -> Dict[str, Any]:
        """
        基于LLM content内容执行计划
        """
        content = action_plan.get("content", "")
        
        # 简单的content解析 - 这里可以根据实际需求扩展
        if "完成" in content or "complete" in content.lower():
            return {"execution_complete": True}
        
        # 默认返回无操作结果
        return {
            "content_based_execution": True,
            "completed_scenes": {},
            "failed_scenes": [],
            "execution_summary": f"Content-based execution: {content[:100]}..."
        }
