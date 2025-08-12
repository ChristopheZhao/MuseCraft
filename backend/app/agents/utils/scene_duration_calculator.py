"""
Scene Duration Calculator - 基于场景概念的动态时长计算
"""

from typing import Dict, Any, List
from enum import Enum
from ...core.config import settings


class SceneComplexity(Enum):
    """场景复杂度级别"""
    SIMPLE = "simple"          # 简单场景：单一元素，静态
    MODERATE = "moderate"      # 中等场景：多个元素，轻微动作
    COMPLEX = "complex"        # 复杂场景：多个角色，动态交互
    VERY_COMPLEX = "very_complex"  # 非常复杂：群体场景，高动态


class ContentDensity(Enum):
    """内容密度级别"""
    LOW = "low"              # 低密度：简单信息传递
    MEDIUM = "medium"        # 中等密度：标准叙事内容
    HIGH = "high"            # 高密度：多重信息或情感
    VERY_HIGH = "very_high"  # 极高密度：复杂概念或强烈情感


class SceneDurationCalculator:
    """
    基于场景概念计算动态时长
    
    核心原则：
    1. 场景时长应该基于内容需求，而非硬编码
    2. 考虑视觉复杂度、叙事需求、情感发展
    3. 保持整体视频节奏的平衡
    """
    
    # 基础时长映射（秒）
    BASE_DURATION_MAP = {
        SceneComplexity.SIMPLE: 3.0,
        SceneComplexity.MODERATE: 5.0,
        SceneComplexity.COMPLEX: 8.0,
        SceneComplexity.VERY_COMPLEX: 10.0
    }
    
    # 内容密度调整系数
    DENSITY_MULTIPLIER = {
        ContentDensity.LOW: 0.8,
        ContentDensity.MEDIUM: 1.0,
        ContentDensity.HIGH: 1.2,
        ContentDensity.VERY_HIGH: 1.5
    }
    
    # 场景类型时长调整
    SCENE_TYPE_ADJUSTMENT = {
        "intro": 0.9,         # 开场稍短，快速吸引
        "main_content": 1.1,  # 主要内容稍长，充分展现
        "transition": 0.7,    # 过渡场景较短
        "outro": 0.85,        # 结尾适中，留下印象
        "climax": 1.3         # 高潮场景需要时间发展
    }
    
    @classmethod
    def calculate_scene_duration(
        cls,
        scene_data: Dict[str, Any],
        total_video_duration: float,
        scene_count: int
    ) -> float:
        """
        计算单个场景的建议时长
        
        Args:
            scene_data: 场景数据，包含类型、描述、元素等
            total_video_duration: 视频总时长
            scene_count: 总场景数
            
        Returns:
            float: 建议的场景时长（秒）
        """
        # 1. 分析场景复杂度
        complexity = cls._analyze_scene_complexity(scene_data)
        
        # 2. 分析内容密度
        density = cls._analyze_content_density(scene_data)
        
        # 3. 获取基础时长
        base_duration = cls.BASE_DURATION_MAP[complexity]
        
        # 4. 应用内容密度调整
        duration = base_duration * cls.DENSITY_MULTIPLIER[density]
        
        # 5. 应用场景类型调整
        scene_type = scene_data.get("scene_type", "main_content")
        type_adjustment = cls.SCENE_TYPE_ADJUSTMENT.get(scene_type, 1.0)
        duration *= type_adjustment
        
        # 6. 考虑总时长约束
        average_duration = total_video_duration / scene_count
        if duration > average_duration * 2:
            # 防止单个场景过长
            duration = average_duration * 1.8
        elif duration < average_duration * 0.3:
            # 防止单个场景过短
            duration = average_duration * 0.4
        
        # 7. 最终时长范围限制
        min_duration = settings.MIN_SCENE_DURATION  # 最短时长
        max_duration = min(settings.MAX_SCENE_DURATION, total_video_duration * 0.4)  # 最长时长或总时长的40%
        
        return max(min_duration, min(duration, max_duration))
    
    @classmethod
    def _analyze_scene_complexity(cls, scene_data: Dict[str, Any]) -> SceneComplexity:
        """分析场景视觉复杂度"""
        
        complexity_score = 0
        
        # 检查角色数量
        characters = scene_data.get("characters", []) or scene_data.get("character_descriptions", [])
        if len(characters) == 0:
            complexity_score += 0
        elif len(characters) == 1:
            complexity_score += 1
        elif len(characters) <= 3:
            complexity_score += 2
        else:
            complexity_score += 3
        
        # 检查道具和对象
        props = scene_data.get("props", []) or scene_data.get("props_and_objects", [])
        if len(props) <= 2:
            complexity_score += 0
        elif len(props) <= 5:
            complexity_score += 1
        else:
            complexity_score += 2
        
        # 检查动作描述
        action_descriptions = scene_data.get("action_descriptions", [])
        visual_description = scene_data.get("visual_description", "")
        
        # 动作关键词
        action_keywords = ["moving", "running", "jumping", "dancing", "fighting", 
                          "playing", "splashing", "throwing", "catching", "动态",
                          "奔跑", "跳跃", "舞蹈", "游戏", "互动"]
        
        action_count = sum(1 for keyword in action_keywords 
                          if keyword in visual_description.lower())
        
        if action_count == 0:
            complexity_score += 0
        elif action_count <= 2:
            complexity_score += 1
        else:
            complexity_score += 2
        
        # 根据总分确定复杂度
        if complexity_score <= 2:
            return SceneComplexity.SIMPLE
        elif complexity_score <= 4:
            return SceneComplexity.MODERATE
        elif complexity_score <= 6:
            return SceneComplexity.COMPLEX
        else:
            return SceneComplexity.VERY_COMPLEX
    
    @classmethod
    def _analyze_content_density(cls, scene_data: Dict[str, Any]) -> ContentDensity:
        """分析内容密度"""
        
        density_score = 0
        
        # 检查叙事描述长度
        narrative = scene_data.get("narrative_description", "")
        if len(narrative) < 50:
            density_score += 0
        elif len(narrative) < 150:
            density_score += 1
        elif len(narrative) < 300:
            density_score += 2
        else:
            density_score += 3
        
        # 检查情感强度
        emotional_keywords = ["emotional", "intense", "dramatic", "touching",
                            "exciting", "thrilling", "heartwarming", "powerful",
                            "感人", "激动", "温馨", "震撼", "深情"]
        
        mood_target = scene_data.get("mood_target", "")
        emotional_tone = scene_data.get("emotional_tone", "")
        
        emotional_count = sum(1 for keyword in emotional_keywords
                            if keyword in mood_target.lower() or 
                               keyword in emotional_tone.lower())
        
        if emotional_count >= 2:
            density_score += 2
        elif emotional_count >= 1:
            density_score += 1
        
        # 检查关键信息数量
        key_messages = scene_data.get("visual_priorities", [])
        if len(key_messages) >= 4:
            density_score += 2
        elif len(key_messages) >= 2:
            density_score += 1
        
        # 根据总分确定密度
        if density_score <= 1:
            return ContentDensity.LOW
        elif density_score <= 3:
            return ContentDensity.MEDIUM
        elif density_score <= 5:
            return ContentDensity.HIGH
        else:
            return ContentDensity.VERY_HIGH
    
    @classmethod
    def optimize_scene_durations(
        cls,
        scenes: List[Dict[str, Any]],
        total_duration: float
    ) -> List[Dict[str, Any]]:
        """
        优化所有场景的时长分配
        
        Args:
            scenes: 场景列表
            total_duration: 视频总时长
            
        Returns:
            List[Dict]: 包含优化后时长的场景列表
        """
        # 1. 计算每个场景的初始建议时长
        for scene in scenes:
            suggested_duration = cls.calculate_scene_duration(
                scene, total_duration, len(scenes)
            )
            scene["suggested_duration"] = suggested_duration
            scene["duration_reasoning"] = cls._get_duration_reasoning(
                scene, suggested_duration
            )
        
        # 2. 检查总时长
        total_suggested = sum(scene["suggested_duration"] for scene in scenes)
        
        # 3. 如果需要，按比例调整
        if abs(total_suggested - total_duration) > 1.0:
            adjustment_ratio = total_duration / total_suggested
            for scene in scenes:
                scene["suggested_duration"] *= adjustment_ratio
                scene["duration_adjusted"] = True
        
        # 4. 确保时长为合理值（0.5秒的倍数）
        for scene in scenes:
            scene["final_duration"] = round(scene["suggested_duration"] * 2) / 2
        
        return scenes
    
    @classmethod
    def _get_duration_reasoning(
        cls,
        scene_data: Dict[str, Any],
        duration: float
    ) -> str:
        """生成时长决策的解释"""
        
        complexity = cls._analyze_scene_complexity(scene_data)
        density = cls._analyze_content_density(scene_data)
        scene_type = scene_data.get("scene_type", "main_content")
        
        reasoning = f"场景时长{duration:.1f}秒基于: "
        reasoning += f"视觉复杂度[{complexity.value}], "
        reasoning += f"内容密度[{density.value}], "
        reasoning += f"场景类型[{scene_type}]"
        
        return reasoning