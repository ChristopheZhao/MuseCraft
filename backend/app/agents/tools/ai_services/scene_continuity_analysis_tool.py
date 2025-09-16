"""
Scene Continuity Analysis Tool - 场景连续性分析工具
分析场景间的连续性需求，决定图像生成策略
"""

import json
from typing import Dict, Any, List
from ..base_tool import AsyncTool, ToolMetadata, ToolType, ToolError


class SceneContinuityAnalysisTool(AsyncTool):
    """
    场景连续性分析工具
    
    基于完整脚本和叙事结构分析场景间的连续性需求，
    决定每个场景应该独立生成图像还是使用前一场景的最后一帧
    """
    
    @classmethod
    def get_metadata(cls) -> ToolMetadata:
        return ToolMetadata(
            name="scene_continuity_analysis_tool",
            version="1.0.0",
            description="分析场景间连续性需求并制定图像生成策略",
            tool_type=ToolType.AI_SERVICE,
            author="system",
            tags=["scene", "continuity", "analysis", "strategy"],
            capabilities=[
                "scene_continuity_analysis",
                "image_generation_strategy",
                "narrative_flow_analysis",
                "visual_transition_planning"
            ]
        )
    
    def _initialize(self):
        """初始化工具"""
        pass
    
    def get_available_actions(self) -> List[str]:
        return ["analyze_all_scenes_continuity"]
    
    def get_action_schema(self, action: str) -> Dict[str, Any]:
        if action == "analyze_all_scenes_continuity":
            return {
                "type": "object",
                "properties": {
                    "scenes": {
                        "type": "array",
                        "description": "所有场景的完整信息",
                        "items": {
                            "type": "object",
                            "properties": {
                                "scene_number": {"type": "integer"},
                                "title": {"type": "string"},
                                "description": {"type": "string"},
                                "script_text": {"type": "string"},
                                "narrative_description": {"type": "string"},
                                "mood_and_atmosphere": {"type": "string"}
                            }
                        }
                    },
                    "overall_narrative": {"type": "string", "description": "整体叙事弧线"},
                    "narrative_flow": {"type": "string", "description": "叙事流程"},
                    "main_message": {"type": "string", "description": "主要信息"}
                },
                "required": ["scenes", "overall_narrative"]
            }
        return {}
    
    async def _execute_impl(self, tool_input) -> Dict[str, Any]:
        """执行工具 - 遵循新的接口约定"""
        action = tool_input.action
        parameters = tool_input.parameters
        if action == "analyze_all_scenes_continuity":
            return await self._analyze_all_scenes_continuity(parameters)
        else:
            raise ToolError(f"Unknown action: {action}", self.metadata.name)
    
    async def _analyze_all_scenes_continuity(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """分析所有场景的连续性需求"""
        
        try:
            scenes = params["scenes"]
            overall_narrative = params.get("overall_narrative", "")
            narrative_flow = params.get("narrative_flow", "")
            main_message = params.get("main_message", "")
            
            if not scenes or len(scenes) <= 1:
                # 单场景或无场景，无需连续性分析
                return {
                    "continuity_decisions": {},
                    "analysis_summary": "Single scene or no scenes, no continuity analysis needed"
                }
            
            # 首个场景直接设为 new，无需分析
            continuity_decisions = {}
            first_scene = scenes[0]
            first_scene_num = str(first_scene.get("scene_number", 1))
            continuity_decisions[first_scene_num] = {
                "strategy": "new",
                "reason": "首个场景，无前置场景可继续",
                "confidence": 1.0
            }
            
            # 如果只有一个场景，直接返回
            if len(scenes) == 1:
                return {
                    "continuity_decisions": continuity_decisions,
                    "analysis_summary": "Single scene, set to independent generation"
                }
            
            # 只分析第2个场景及之后的场景
            scenes_to_analyze = scenes[1:]
            
            # 构建分析提示词 - 只分析第2个场景及之后
            analysis_prompt = self._build_continuity_analysis_prompt(
                scenes_to_analyze, overall_narrative, narrative_flow, main_message, 
                include_first_scene_context=True, all_scenes=scenes
            )
            
            # 调用LLM进行分析（供应商无关）
            from ..tool_registry import get_tool_registry
            from ..base_tool import ToolInput as TI
            # 从 ai_config 中获取工具模型映射（可被参数覆盖）
            try:
                from ....core.ai_config import get_ai_config
                ai_cfg = get_ai_config()
                cfg_model = ai_cfg.get_model_for_tool("scene_continuity_analysis_tool")
                mcfg = ai_cfg.get_model_config(cfg_model) if cfg_model else None
                provider_name = ai_cfg.get_model_provider(cfg_model) if cfg_model else None
            except Exception:
                cfg_model = None
                mcfg = None
                provider_name = None
            req_model = cfg_model or None
            req_temp = 0.3 if not (mcfg and getattr(mcfg, 'temperature', None) is not None) else float(mcfg.temperature)

            prov_alias = {"zhipu": "zhipu_client", "openai": "openai_client", "kimi": "kimi_client"}
            provider_tool = prov_alias.get(provider_name or "zhipu", "zhipu_client")
            provider = get_tool_registry().get_tool(provider_tool)

            # Prefer strict JSON via json_completion
            result = await provider.execute(TI(action="json_completion", parameters={
                "prompt": analysis_prompt,
                "model": req_model,
                "temperature": req_temp,
                "max_tokens": 2000
            }))
            
            # 处理结果
            payload = getattr(result, 'result', result)
            response_content = "{}"
            if isinstance(payload, dict):
                if payload.get("json_result") is not None:
                    import json as _json
                    response_content = _json.dumps(payload.get("json_result"), ensure_ascii=False)
                else:
                    response_content = payload.get("content", payload.get("raw_content", "{}"))
            
            # 解析JSON响应
            try:
                analysis_result = json.loads(response_content.strip())
            except json.JSONDecodeError as e:
                # 尝试提取JSON内容
                import re
                json_match = re.search(r'```json\s*(\{.*?\})\s*```', response_content, re.DOTALL)
                if json_match:
                    analysis_result = json.loads(json_match.group(1))
                else:
                    raise ToolError(f"Failed to parse JSON response: {e}", self.metadata.name)
            
            # 验证和标准化结果 - 只处理第2个场景及之后
            llm_decisions = self._standardize_continuity_analysis(analysis_result, scenes_to_analyze)
            
            # 合并首个场景的预设结果和LLM分析结果
            final_decisions = continuity_decisions.copy()
            final_decisions.update(llm_decisions.get("continuity_decisions", {}))
            
            total_scenes = len(scenes)
            continuous_scenes = len([d for d in final_decisions.values() if d["strategy"] == "continue_from_previous"])
            
            return {
                "continuity_decisions": final_decisions,
                "analysis_summary": f"分析了 {total_scenes} 个场景，其中 {continuous_scenes} 个需要连续性处理。首个场景自动设为独立生成。",
                "total_scenes": total_scenes,
                "continuous_scenes": continuous_scenes
            }
            
        except Exception as e:
            self.logger.error(f"Scene continuity analysis failed: {e}")
            # 返回默认策略 - 首个场景 new，其余场景也设为 new
            default_decisions = {}
            for scene in params.get("scenes", []):
                scene_num = scene.get("scene_number", 1)
                if scene_num == 1:
                    default_decisions[str(scene_num)] = {
                        "strategy": "new",
                        "reason": "首个场景，无前置场景可继续",
                        "confidence": 1.0
                    }
                else:
                    default_decisions[str(scene_num)] = {
                        "strategy": "new",
                        "reason": f"Analysis failed, using default strategy: {str(e)}",
                        "confidence": 0.5
                    }
            
            return {
                "continuity_decisions": default_decisions,
                "analysis_summary": f"分析失败，使用默认策略（所有场景独立生成）: {str(e)}"
            }
    
    def _build_continuity_analysis_prompt(
        self, 
        scenes: List[Dict[str, Any]], 
        overall_narrative: str,
        narrative_flow: str,
        main_message: str,
        include_first_scene_context: bool = False,
        all_scenes: List[Dict[str, Any]] = None
    ) -> str:
        """构建连续性分析提示词"""
        # 注入 MAS 全局与通用连续性先验（分层系统指令合成，不暴露工具名/参数）
        sys_blocks: List[str] = []
        try:
            from ....core.prompt_manager import get_prompt_manager
            pm = get_prompt_manager()
            mas_sys = pm.render_template("mas_system", "system", variables={}, use_cache=True, auto_reload=False)
            cont_sys = pm.render_template("continuity_priors", "system", variables={}, use_cache=True, auto_reload=False)
            if mas_sys:
                sys_blocks.append(mas_sys.strip())
            if cont_sys:
                sys_blocks.append(cont_sys.strip())
        except Exception:
            pass

        # 如果包含首个场景上下文，则显示完整信息但说明不需要分析首个场景
        if include_first_scene_context and all_scenes:
            first_scene = all_scenes[0]
            first_scene_info = f"""
场景{first_scene.get('scene_number', 1)}：{first_scene.get('title', '')} [已确定为独立生成]
- 描述：{first_scene.get('description', '')}
- 脚本：{first_scene.get('script_text', '')}
- 叙事描述：{first_scene.get('narrative_description', '')}
- 情绪氛围：{first_scene.get('mood_and_atmosphere', '')}
"""
            
            scenes_info = [first_scene_info.strip()]
        else:
            scenes_info = []
        
        # 添加需要分析的场景信息
        for scene in scenes:
            scene_info = f"""
场景{scene.get('scene_number', 1)}：{scene.get('title', '')}
- 描述：{scene.get('description', '')}
- 脚本：{scene.get('script_text', '')}
- 叙事描述：{scene.get('narrative_description', '')}
- 情绪氛围：{scene.get('mood_and_atmosphere', '')}
"""
            scenes_info.append(scene_info.strip())
        
        context_note = "**注意：首个场景已自动设为独立生成（new），无需分析。**\n\n" if include_first_scene_context else ""
        
        # 动态构造 JSON 示例键，覆盖本次需要分析的所有场景编号，避免模型只返回部分（例如只到4号而漏掉5号）
        try:
            scene_keys_example = []
            for sc in scenes:
                try:
                    sid = int(sc.get('scene_number', 0) or 0)
                except Exception:
                    sid = 0
                if sid:
                    scene_keys_example.append(f'        "{sid}": {{\n            "strategy": "continue_from_previous" | "new",\n            "reason": "具体原因说明",\n            "confidence": 0.0-1.0\n        }}')
            example_body = (",\n".join(scene_keys_example)) if scene_keys_example else '        "2": {"strategy": "new", "reason": "", "confidence": 0.8}'
        except Exception:
            example_body = '        "2": {"strategy": "new", "reason": "", "confidence": 0.8}'

        prompt = f"""你是一个专业的视频制作顾问，需要分析场景间的逻辑关系，判断当前场景是否需要从上个场景的结尾画面状态开始，以保持实体状态和事件发展的视觉连贯性。

{context_note}**整体叙事信息：**
- 叙事弧线：{overall_narrative}
- 叙事流程：{narrative_flow}
- 核心信息：{main_message}

**场景详情：**
{chr(10).join(scenes_info)}

**分析任务：**
对于每个场景，判断其第一帧是否需要从上一个场景的最后一帧状态继续，还是独立生成新的画面内容。

**判断标准：**
1. **需要画面延续（continue_from_previous）**的情况：
   - 同一实体的状态演进或变化过程
   - 连续事件的发展和延续
   - 同一时空下的连续动作或反应
   - 视觉元素需要保持连贯性的情况

2. **无需画面延续（new）**的情况：
   - 场景切换（地点、时间、视角的显著变化）
   - 独立事件或情节的开始
   - 实体状态与前场景无直接关联
   - 叙事节奏需要重新开始的情况

**输出要求（严格）：**
- 返回JSON对象，只包含“本次需要分析的所有场景”的决策（即上文列出的场景，首个场景已另行设为 new 不在此列）。
- 逐个场景编号给出决策；缺一不可，不要省略任何编号。

```json
{{
    "continuity_decisions": {{
{example_body}
    }},
    "analysis_summary": "分析总结（不包含首个场景）"
}}
```

请严格按照JSON格式返回，分析要客观准确。"""

        # 将系统先验与具体任务提示合并为单一文本（工具层暂不支持多role消息）
        if sys_blocks:
            return "\n\n".join(sys_blocks + [prompt]).strip()
        return prompt
    
    def _standardize_continuity_analysis(
        self, 
        analysis_result: Dict[str, Any], 
        scenes: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """标准化连续性分析结果"""
        
        continuity_decisions = analysis_result.get("continuity_decisions", {})
        standardized_decisions = {}
        
        for scene in scenes:
            scene_number = scene.get("scene_number", 1)
            scene_key = str(scene_number)
            
            if scene_key in continuity_decisions:
                decision = continuity_decisions[scene_key]
                
                # 标准化策略值
                strategy = decision.get("strategy", "new")
                if strategy not in ["new", "continue_from_previous"]:
                    strategy = "new"
                
                # 标准化置信度
                confidence = float(decision.get("confidence", 0.8))
                confidence = max(0.0, min(1.0, confidence))
                
                standardized_decisions[scene_key] = {
                    "strategy": strategy,
                    "reason": decision.get("reason", ""),
                    "confidence": confidence
                }
            else:
                # 缺失的场景使用默认策略
                standardized_decisions[scene_key] = {
                    "strategy": "new",
                    "reason": "Missing analysis, using default strategy",
                    "confidence": 0.5
                }
        
        return {
            "continuity_decisions": standardized_decisions,
            "analysis_summary": analysis_result.get("analysis_summary", "Scene continuity analysis completed"),
            "total_scenes": len(scenes),
            "continuous_scenes": len([d for d in standardized_decisions.values() if d["strategy"] == "continue_from_previous"])
        }
