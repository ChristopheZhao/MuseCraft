"""
场景分析工具 - 分析场景内容特征
"""

from typing import Dict, Any, List
import logging

from ..base_tool import AsyncTool, ToolMetadata, ToolType, ToolInput, ToolError, ToolValidationError


class SceneAnalysisTool(AsyncTool):
    """
    场景分析工具
    
    职责：
    - 分析场景的复杂度
    - 评估动作密度和节奏
    - 提供场景特征信息
    - 不做参数决策，只提供分析结果
    """
    
    @classmethod
    def get_metadata(cls) -> ToolMetadata:
        return ToolMetadata(
            name="scene_analysis",
            version="1.0.0", 
            description="分析场景内容的复杂度、动作密度、视觉特征等信息",
            tool_type=ToolType.ANALYSIS,
            author="system",
            tags=["scene", "analysis", "content"],
            capabilities=[
                "complexity_analysis",
                "motion_density_assessment",
                "visual_feature_extraction",
                "narrative_pacing_analysis"
            ],
            limitations=[]
        )
    
    def _initialize(self):
        """初始化场景分析工具"""
        # 场景分析工具不依赖外部服务，总是可用的
        self._functional = True
    
    def get_available_actions(self) -> List[str]:
        return [
            "analyze_scene_complexity",
            "assess_motion_density", 
            "extract_visual_features",
            "analyze_narrative_pacing"
        ]
    
    def get_action_schema(self, action: str) -> Dict[str, Any]:
        base_scene_properties = {
            "script_text": {"type": "string", "description": "场景脚本文本"},
            "visual_description": {"type": "string", "description": "视觉描述"},
            "narrative_description": {"type": "string", "description": "叙事描述"},
            "mood_and_atmosphere": {"type": "string", "description": "氛围描述"}
        }
        
        schemas = {
            "analyze_scene_complexity": {
                "type": "object",
                "properties": {
                    "scene_data": {
                        "type": "object",
                        "properties": base_scene_properties,
                        "description": "场景数据"
                    }
                },
                "required": ["scene_data"],
                "description": "分析场景的整体复杂度级别"
            },
            "assess_motion_density": {
                "type": "object", 
                "properties": {
                    "scene_data": {
                        "type": "object",
                        "properties": base_scene_properties,
                        "description": "场景数据"
                    }
                },
                "required": ["scene_data"],
                "description": "评估场景中的动作密度和运动强度"
            },
            "extract_visual_features": {
                "type": "object",
                "properties": {
                    "scene_data": {
                        "type": "object", 
                        "properties": base_scene_properties,
                        "description": "场景数据"
                    }
                },
                "required": ["scene_data"],
                "description": "提取场景的关键视觉特征"
            },
            "analyze_narrative_pacing": {
                "type": "object",
                "properties": {
                    "scene_data": {
                        "type": "object",
                        "properties": base_scene_properties,
                        "description": "场景数据"
                    },
                    "scene_position": {
                        "type": "string",
                        "enum": ["opening", "development", "climax", "resolution"],
                        "description": "场景在整体叙事中的位置"
                    }
                },
                "required": ["scene_data"],
                "description": "分析场景在叙事节奏中的作用"
            }
        }
        
        return schemas.get(action, {})
    
    async def _execute_impl(self, tool_input: ToolInput) -> Any:
        """执行场景分析"""
        action = tool_input.action
        params = tool_input.parameters
        
        if action == "analyze_scene_complexity":
            return await self._analyze_complexity(params)
        elif action == "assess_motion_density":
            return await self._assess_motion_density(params)
        elif action == "extract_visual_features":
            return await self._extract_visual_features(params)
        elif action == "analyze_narrative_pacing":
            return await self._analyze_narrative_pacing(params)
        else:
            raise ToolValidationError(f"Unknown action: {action}", self.metadata.name)
    
    async def _analyze_complexity(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """分析场景复杂度"""
        scene_data = params["scene_data"]
        
        # 基于关键词和内容长度的启发式分析
        complexity_indicators = {
            "high": ["打斗", "追逐", "爆炸", "战斗", "复杂", "多人", "变化", "转换", "动作"],
            "medium": ["对话", "移动", "展示", "交流", "互动", "过渡"],
            "low": ["静态", "独白", "思考", "观察", "简单", "单一"]
        }
        
        text_content = f"{scene_data.get('script_text', '')} {scene_data.get('visual_description', '')} {scene_data.get('narrative_description', '')}"
        text_length = len(text_content)
        
        # 计算复杂度分数
        complexity_score = 0
        matched_indicators = []
        
        for level, keywords in complexity_indicators.items():
            matches = [kw for kw in keywords if kw in text_content]
            if matches:
                matched_indicators.extend([(level, kw) for kw in matches])
                if level == "high":
                    complexity_score += len(matches) * 3
                elif level == "medium":
                    complexity_score += len(matches) * 2
                else:
                    complexity_score += len(matches) * 1
        
        # 基于文本长度调整
        if text_length > 200:
            complexity_score += 2
        elif text_length > 100:
            complexity_score += 1
        
        # 确定复杂度级别
        if complexity_score >= 8:
            complexity_level = "high"
        elif complexity_score >= 4:
            complexity_level = "medium"
        else:
            complexity_level = "low"
        
        return {
            "complexity_level": complexity_level,
            "complexity_score": complexity_score,
            "matched_indicators": matched_indicators,
            "text_length": text_length,
            "analysis_reasoning": f"基于{len(matched_indicators)}个复杂度指标和{text_length}字符的内容长度"
        }
    
    async def _assess_motion_density(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """评估动作密度"""
        scene_data = params["scene_data"]
        
        motion_keywords = {
            "high_motion": ["跑", "跳", "飞", "冲", "追", "逃", "打", "踢", "旋转", "翻滚"],
            "medium_motion": ["走", "移动", "转身", "抬头", "低头", "伸手", "坐下", "站起"],
            "low_motion": ["站立", "坐着", "静止", "凝视", "思考", "观察", "说话"]
        }
        
        text_content = f"{scene_data.get('script_text', '')} {scene_data.get('visual_description', '')}"
        
        motion_score = 0
        detected_motions = []
        
        for motion_type, keywords in motion_keywords.items():
            matches = [kw for kw in keywords if kw in text_content]
            if matches:
                detected_motions.extend([(motion_type, kw) for kw in matches])
                if motion_type == "high_motion":
                    motion_score += len(matches) * 3
                elif motion_type == "medium_motion":
                    motion_score += len(matches) * 2
                else:
                    motion_score += len(matches) * 1
        
        # 确定动作密度
        if motion_score >= 6:
            motion_density = "high"
        elif motion_score >= 3:
            motion_density = "medium"
        else:
            motion_density = "low"
        
        return {
            "motion_density": motion_density,
            "motion_score": motion_score,
            "detected_motions": detected_motions,
            "assessment_reasoning": f"检测到{len(detected_motions)}个动作指标"
        }
    
    async def _extract_visual_features(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """提取视觉特征"""
        scene_data = params["scene_data"]
        
        visual_elements = {
            "lighting": ["明亮", "昏暗", "阳光", "月光", "灯光", "阴影"],
            "environment": ["室内", "室外", "森林", "城市", "海边", "山上", "房间"],
            "colors": ["红色", "蓝色", "绿色", "金色", "黑色", "白色", "彩色"],
            "atmosphere": ["温馨", "紧张", "神秘", "浪漫", "危险", "平静"]
        }
        
        visual_content = f"{scene_data.get('visual_description', '')} {scene_data.get('mood_and_atmosphere', '')}"
        
        extracted_features = {}
        for feature_type, keywords in visual_elements.items():
            matches = [kw for kw in keywords if kw in visual_content]
            if matches:
                extracted_features[feature_type] = matches
        
        return {
            "visual_features": extracted_features,
            "feature_count": sum(len(features) for features in extracted_features.values()),
            "dominant_elements": max(extracted_features.items(), key=lambda x: len(x[1])) if extracted_features else None
        }
    
    async def _analyze_narrative_pacing(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """分析叙事节奏"""
        scene_data = params["scene_data"]
        scene_position = params.get("scene_position", "development")
        
        pacing_indicators = {
            "fast": ["快速", "紧急", "立即", "迅速", "急", "冲"],
            "medium": ["逐渐", "慢慢", "然后", "接着", "随后"],
            "slow": ["缓慢", "静静", "悠悠", "轻轻", "慢慢地"]
        }
        
        text_content = f"{scene_data.get('script_text', '')} {scene_data.get('narrative_description', '')}"
        
        pacing_score = 0
        pacing_clues = []
        
        for pace_type, keywords in pacing_indicators.items():
            matches = [kw for kw in keywords if kw in text_content]
            if matches:
                pacing_clues.extend([(pace_type, kw) for kw in matches])
                if pace_type == "fast":
                    pacing_score += len(matches) * 2
                elif pace_type == "medium":
                    pacing_score += len(matches) * 1
                else:
                    pacing_score -= len(matches) * 1
        
        # 根据场景位置调整节奏期望
        position_adjustments = {
            "opening": 1,  # 开场倾向于中等节奏
            "development": 0,  # 发展阶段保持原节奏
            "climax": 2,  # 高潮阶段倾向于快节奏
            "resolution": -1  # 结尾倾向于慢节奏
        }
        
        adjusted_score = pacing_score + position_adjustments.get(scene_position, 0)
        
        if adjusted_score >= 3:
            narrative_pacing = "fast"
        elif adjusted_score >= 0:
            narrative_pacing = "medium"
        else:
            narrative_pacing = "slow"
        
        return {
            "narrative_pacing": narrative_pacing,
            "pacing_score": pacing_score,
            "adjusted_score": adjusted_score,
            "scene_position": scene_position,
            "pacing_clues": pacing_clues,
            "recommended_duration_hint": self._get_duration_hint(narrative_pacing, scene_position)
        }
    
    def _get_duration_hint(self, pacing: str, position: str) -> str:
        """根据节奏提供时长建议"""
        if pacing == "fast" or position == "climax":
            return "建议使用较长时长(8-10秒)以充分展现动作"
        elif pacing == "slow" or position == "resolution":
            return "建议使用较短时长(5-6秒)保持简洁"
        else:
            return "建议使用中等时长(6-8秒)平衡展现"
    
    def _validate_action_parameters(self, action: str, parameters: Dict[str, Any]):
        """验证操作参数"""
        if not parameters.get("scene_data"):
            raise ToolValidationError(f"scene_data is required for {action}")