"""
Quality Control System
- Content safety and moderation
- Consistency validation across generated content
- Quality scoring and assessment
- Automated content filtering
- Human review workflow integration
"""
import asyncio
import logging
import re
import hashlib
from typing import Dict, Any, List, Optional, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import json
import aiohttp
from sqlalchemy.orm import Session

from ..models import Task, Scene, Resource, AgentType
from .enhanced_ai_client import enhanced_ai_client, AIServiceProvider
from ..core.config import settings


class ContentSafetyLevel(str, Enum):
    SAFE = "safe"
    MODERATE = "moderate"
    UNSAFE = "unsafe"
    REVIEW_REQUIRED = "review_required"


class QualityLevel(str, Enum):
    EXCELLENT = "excellent"      # 9-10
    GOOD = "good"               # 7-8
    ACCEPTABLE = "acceptable"    # 5-6
    POOR = "poor"               # 3-4
    UNACCEPTABLE = "unacceptable"  # 1-2


class ContentType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"


@dataclass
class SafetyCheck:
    """Content safety check result"""
    content_type: ContentType
    safety_level: ContentSafetyLevel
    confidence: float
    issues: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    flagged_content: List[str] = field(default_factory=list)


@dataclass
class QualityAssessment:
    """Content quality assessment result"""
    content_type: ContentType
    quality_level: QualityLevel
    quality_score: float  # 1-10 scale
    assessment_criteria: Dict[str, float] = field(default_factory=dict)
    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)


@dataclass
class ConsistencyCheck:
    """Content consistency check result"""
    consistency_score: float  # 0-1 scale
    issues: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    reference_elements: Dict[str, Any] = field(default_factory=dict)


@dataclass
class QualityControlResult:
    """Comprehensive quality control result"""
    overall_score: float
    safety_check: Optional[SafetyCheck] = None
    quality_assessment: Optional[QualityAssessment] = None
    consistency_check: Optional[ConsistencyCheck] = None
    requires_human_review: bool = False
    approved: bool = False
    timestamp: datetime = field(default_factory=datetime.now)


class QualityControlService:
    """Comprehensive quality control and content moderation service"""
    
    def __init__(self):
        self.logger = logging.getLogger("quality_control")
        
        # Content safety filters and patterns
        self.safety_patterns = self._initialize_safety_patterns()
        
        # Quality assessment criteria
        self.quality_criteria = self._initialize_quality_criteria()
        
        # Consistency validation rules
        self.consistency_rules = self._initialize_consistency_rules()
        
        # Content moderation API endpoints (if available)
        self.moderation_apis = {
            "openai": "https://api.openai.com/v1/moderations",
            # Add other moderation services as needed
        }
        
        # Human review thresholds
        self.review_thresholds = {
            "safety_confidence": 0.7,
            "quality_score": 5.0,
            "consistency_score": 0.6
        }
    
    def _initialize_safety_patterns(self) -> Dict[str, List[str]]:
        """Initialize content safety patterns and keywords"""
        return {
            "violence": [
                r"\b(kill|murder|violence|blood|gore|weapon|gun|knife|bomb)\b",
                r"\b(fight|attack|assault|harm|hurt|damage)\b"
            ],
            "hate_speech": [
                r"\b(hate|racist|discrimination|offensive|slur)\b",
                # Add more patterns as needed
            ],
            "adult_content": [
                r"\b(sexual|explicit|nude|nsfw|adult)\b",
                r"\b(pornographic|erotic|intimate)\b"
            ],
            "inappropriate": [
                r"\b(illegal|criminal|fraud|scam|drugs)\b",
                r"\b(harassment|bullying|threat)\b"
            ]
        }
    
    def _initialize_quality_criteria(self) -> Dict[str, Dict[str, Any]]:
        """Initialize quality assessment criteria"""
        return {
            "text": {
                "coherence": {"weight": 0.25, "description": "Logical flow and coherence"},
                "clarity": {"weight": 0.20, "description": "Clarity and readability"},
                "creativity": {"weight": 0.20, "description": "Creative and engaging content"},
                "relevance": {"weight": 0.25, "description": "Relevance to the prompt"},
                "grammar": {"weight": 0.10, "description": "Grammar and language quality"}
            },
            "image": {
                "visual_quality": {"weight": 0.30, "description": "Technical image quality"},
                "composition": {"weight": 0.25, "description": "Visual composition and balance"},
                "relevance": {"weight": 0.25, "description": "Relevance to the prompt"},
                "creativity": {"weight": 0.20, "description": "Creative and artistic value"}
            },
            "video": {
                "visual_quality": {"weight": 0.25, "description": "Video quality and clarity"},
                "audio_quality": {"weight": 0.15, "description": "Audio quality if applicable"},
                "storytelling": {"weight": 0.25, "description": "Narrative flow and engagement"},
                "technical_quality": {"weight": 0.20, "description": "Technical aspects"},
                "relevance": {"weight": 0.15, "description": "Relevance to requirements"}
            }
        }
    
    def _initialize_consistency_rules(self) -> Dict[str, Any]:
        """Initialize consistency validation rules"""
        return {
            "visual_style": {
                "color_palette": 0.3,
                "art_style": 0.4,
                "mood": 0.3
            },
            "narrative": {
                "tone": 0.4,
                "theme": 0.3,
                "character_consistency": 0.3
            },
            "technical": {
                "aspect_ratio": 0.5,
                "resolution": 0.3,
                "format": 0.2
            }
        }
    
    async def perform_quality_control(
        self,
        task: Task,
        content_data: Dict[str, Any],
        content_type: ContentType,
        db: Session
    ) -> QualityControlResult:
        """Perform comprehensive quality control on content"""
        
        self.logger.info(f"Starting quality control for task {task.task_id}, content type: {content_type.value}")
        
        result = QualityControlResult(overall_score=0.0)
        
        try:
            # Perform safety check
            result.safety_check = await self._perform_safety_check(content_data, content_type)
            
            # Perform quality assessment
            result.quality_assessment = await self._perform_quality_assessment(
                content_data, content_type, task
            )
            
            # Perform consistency check (if we have reference content)
            if content_type in [ContentType.IMAGE, ContentType.VIDEO]:
                result.consistency_check = await self._perform_consistency_check(
                    task, content_data, content_type, db
                )
            
            # Calculate overall score
            result.overall_score = self._calculate_overall_score(result)
            
            # Determine if human review is required
            result.requires_human_review = self._requires_human_review(result)
            
            # Determine approval status
            result.approved = self._determine_approval(result)
            
            self.logger.info(f"Quality control completed. Score: {result.overall_score:.2f}, "
                           f"Approved: {result.approved}, Review Required: {result.requires_human_review}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"Quality control failed: {str(e)}")
            # Return failed result
            result.overall_score = 0.0
            result.approved = False
            result.requires_human_review = True
            return result
    
    async def _perform_safety_check(
        self,
        content_data: Dict[str, Any],
        content_type: ContentType
    ) -> SafetyCheck:
        """Perform content safety and moderation check"""
        
        safety_check = SafetyCheck(
            content_type=content_type,
            safety_level=ContentSafetyLevel.SAFE,
            confidence=1.0
        )
        
        if content_type == ContentType.TEXT:
            safety_check = await self._check_text_safety(content_data)
        elif content_type == ContentType.IMAGE:
            safety_check = await self._check_image_safety(content_data)
        elif content_type == ContentType.VIDEO:
            safety_check = await self._check_video_safety(content_data)
        
        return safety_check
    
    async def _check_text_safety(self, content_data: Dict[str, Any]) -> SafetyCheck:
        """Check text content safety"""
        
        text_content = ""
        
        # Extract text from different sources
        if "content" in content_data:
            text_content += content_data["content"]
        if "script" in content_data:
            text_content += " " + content_data["script"]
        if "description" in content_data:
            text_content += " " + content_data["description"]
        
        safety_check = SafetyCheck(
            content_type=ContentType.TEXT,
            safety_level=ContentSafetyLevel.SAFE,
            confidence=0.8
        )
        
        # Check against local patterns
        issues_found = []
        flagged_content = []
        
        for category, patterns in self.safety_patterns.items():
            for pattern in patterns:
                matches = re.findall(pattern, text_content.lower(), re.IGNORECASE)
                if matches:
                    issues_found.append(f"Potential {category} content detected")
                    flagged_content.extend(matches)
        
        if issues_found:
            safety_check.safety_level = ContentSafetyLevel.MODERATE
            safety_check.issues = issues_found
            safety_check.flagged_content = flagged_content
            safety_check.confidence = 0.6
            safety_check.recommendations = [
                "Review flagged content manually",
                "Consider content modification",
                "Apply additional filtering"
            ]
        
        # Use external moderation API if available
        try:
            if settings.OPENAI_API_KEY and text_content:
                external_check = await self._check_with_openai_moderation(text_content)
                if external_check:
                    # Combine results
                    if external_check["flagged"]:
                        safety_check.safety_level = ContentSafetyLevel.UNSAFE
                        safety_check.confidence = max(safety_check.confidence, 0.9)
                        
                        for category, flagged in external_check["categories"].items():
                            if flagged:
                                safety_check.issues.append(f"OpenAI moderation flagged: {category}")
        
        except Exception as e:
            self.logger.warning(f"External moderation check failed: {e}")
        
        return safety_check
    
    async def _check_image_safety(self, content_data: Dict[str, Any]) -> SafetyCheck:
        """Check image content safety"""
        
        safety_check = SafetyCheck(
            content_type=ContentType.IMAGE,
            safety_level=ContentSafetyLevel.SAFE,
            confidence=0.7  # Lower confidence without visual analysis
        )
        
        # Check image prompts and descriptions
        text_to_check = ""
        if "prompt_used" in content_data:
            text_to_check += content_data["prompt_used"]
        if "description" in content_data:
            text_to_check += " " + content_data["description"]
        
        if text_to_check:
            text_safety = await self._check_text_safety({"content": text_to_check})
            safety_check.safety_level = text_safety.safety_level
            safety_check.issues = text_safety.issues
            safety_check.flagged_content = text_safety.flagged_content
        
        # TODO: Implement actual image content analysis using vision models
        # This would require additional image analysis services
        
        return safety_check
    
    async def _check_video_safety(self, content_data: Dict[str, Any]) -> SafetyCheck:
        """Check video content safety"""
        
        safety_check = SafetyCheck(
            content_type=ContentType.VIDEO,
            safety_level=ContentSafetyLevel.SAFE,
            confidence=0.6  # Lower confidence without video analysis
        )
        
        # Check video prompts and descriptions
        text_to_check = ""
        if "prompt_used" in content_data:
            text_to_check += content_data["prompt_used"]
        if "description" in content_data:
            text_to_check += " " + content_data["description"]
        
        if text_to_check:
            text_safety = await self._check_text_safety({"content": text_to_check})
            safety_check.safety_level = text_safety.safety_level
            safety_check.issues = text_safety.issues
            safety_check.flagged_content = text_safety.flagged_content
        
        # TODO: Implement actual video content analysis
        # This would require video analysis services
        
        return safety_check
    
    async def _check_with_openai_moderation(self, text: str) -> Optional[Dict[str, Any]]:
        """Check content using OpenAI moderation API"""
        
        try:
            headers = {
                "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "input": text
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.moderation_apis["openai"],
                    headers=headers,
                    json=payload
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        return result["results"][0]
                    else:
                        self.logger.warning(f"OpenAI moderation API error: {response.status}")
                        return None
        
        except Exception as e:
            self.logger.warning(f"OpenAI moderation check failed: {e}")
            return None
    
    async def _perform_quality_assessment(
        self,
        content_data: Dict[str, Any],
        content_type: ContentType,
        task: Task
    ) -> QualityAssessment:
        """Perform quality assessment of content"""
        
        assessment = QualityAssessment(
            content_type=content_type,
            quality_level=QualityLevel.ACCEPTABLE,
            quality_score=5.0
        )
        
        criteria = self.quality_criteria.get(content_type.value, {})
        
        if content_type == ContentType.TEXT:
            assessment = await self._assess_text_quality(content_data, criteria, task)
        elif content_type == ContentType.IMAGE:
            assessment = await self._assess_image_quality(content_data, criteria, task)
        elif content_type == ContentType.VIDEO:
            assessment = await self._assess_video_quality(content_data, criteria, task)
        
        # Determine quality level based on score
        if assessment.quality_score >= 9:
            assessment.quality_level = QualityLevel.EXCELLENT
        elif assessment.quality_score >= 7:
            assessment.quality_level = QualityLevel.GOOD
        elif assessment.quality_score >= 5:
            assessment.quality_level = QualityLevel.ACCEPTABLE
        elif assessment.quality_score >= 3:
            assessment.quality_level = QualityLevel.POOR
        else:
            assessment.quality_level = QualityLevel.UNACCEPTABLE
        
        return assessment
    
    async def _assess_text_quality(
        self,
        content_data: Dict[str, Any],
        criteria: Dict[str, Any],
        task: Task
    ) -> QualityAssessment:
        """Assess text content quality"""
        
        assessment = QualityAssessment(
            content_type=ContentType.TEXT,
            quality_level=QualityLevel.ACCEPTABLE,
            quality_score=5.0
        )
        
        text_content = content_data.get("content", "")
        if not text_content:
            text_content = content_data.get("script", "")
        
        if not text_content:
            assessment.quality_score = 1.0
            assessment.weaknesses.append("No text content found")
            return assessment
        
        # Use AI to assess text quality
        try:
            quality_prompt = f"""
            Assess the quality of the following text content on a scale of 1-10 for each criterion.
            Provide specific feedback and suggestions for improvement.
            
            Text to assess: {text_content}
            
            Original prompt: {task.input_parameters.get('user_prompt', '')}
            
            Please provide assessment in this JSON format:
            {{
                "coherence": {{"score": 0, "feedback": ""}},
                "clarity": {{"score": 0, "feedback": ""}},
                "creativity": {{"score": 0, "feedback": ""}},
                "relevance": {{"score": 0, "feedback": ""}},
                "grammar": {{"score": 0, "feedback": ""}},
                "strengths": ["list of strengths"],
                "weaknesses": ["list of weaknesses"],
                "suggestions": ["list of suggestions"]
            }}
            """
            
            response = await enhanced_ai_client.generate_text(
                prompt=quality_prompt,
                model="gpt-4o-mini",
                max_tokens=1000,
                temperature=0.3,
                response_format={"type": "json_object"}
            )
            
            # Parse response
            quality_data = json.loads(response["content"])
            
            # Calculate weighted score
            total_score = 0.0
            for criterion, config in criteria.items():
                if criterion in quality_data:
                    score = quality_data[criterion]["score"]
                    weight = config["weight"]
                    total_score += score * weight
                    assessment.assessment_criteria[criterion] = score
            
            assessment.quality_score = total_score
            assessment.strengths = quality_data.get("strengths", [])
            assessment.weaknesses = quality_data.get("weaknesses", [])
            assessment.suggestions = quality_data.get("suggestions", [])
            
        except Exception as e:
            self.logger.warning(f"AI quality assessment failed: {e}")
            # Fallback to basic assessment
            assessment = await self._basic_text_assessment(text_content, task)
        
        return assessment
    
    async def _basic_text_assessment(self, text: str, task: Task) -> QualityAssessment:
        """Basic text quality assessment without AI"""
        
        assessment = QualityAssessment(
            content_type=ContentType.TEXT,
            quality_level=QualityLevel.ACCEPTABLE,
            quality_score=5.0
        )
        
        # Basic metrics
        word_count = len(text.split())
        sentence_count = len(re.findall(r'[.!?]+', text))
        
        score = 5.0  # Base score
        
        # Length check
        if word_count < 10:
            score -= 2
            assessment.weaknesses.append("Text is too short")
        elif word_count > 500:
            score += 1
            assessment.strengths.append("Comprehensive content")
        
        # Basic grammar check (very simple)
        if text.count('.') == 0 and text.count('!') == 0 and text.count('?') == 0:
            score -= 1
            assessment.weaknesses.append("Missing punctuation")
        
        # Check for repetition
        words = text.lower().split()
        if len(set(words)) < len(words) * 0.5:
            score -= 1
            assessment.weaknesses.append("High word repetition")
        
        assessment.quality_score = max(1.0, min(10.0, score))
        
        return assessment
    
    async def _assess_image_quality(
        self,
        content_data: Dict[str, Any],
        criteria: Dict[str, Any],
        task: Task
    ) -> QualityAssessment:
        """Assess image content quality"""
        
        assessment = QualityAssessment(
            content_type=ContentType.IMAGE,
            quality_level=QualityLevel.ACCEPTABLE,
            quality_score=6.0  # Default score for images
        )
        
        # Basic assessment based on available metadata
        score = 6.0
        
        # Check if image was successfully generated
        if "image_url" in content_data or "image_base64" in content_data:
            assessment.strengths.append("Image generated successfully")
        else:
            score -= 3
            assessment.weaknesses.append("Image generation failed")
        
        # Check prompt usage
        if "prompt_used" in content_data:
            prompt_length = len(content_data["prompt_used"])
            if prompt_length > 50:
                score += 1
                assessment.strengths.append("Detailed prompt used")
            elif prompt_length < 20:
                score -= 1
                assessment.weaknesses.append("Prompt too brief")
        
        # Check for revised prompt (indicates AI enhancement)
        if content_data.get("revised_prompt"):
            score += 0.5
            assessment.strengths.append("AI-enhanced prompt")
        
        # Check generation parameters
        if content_data.get("quality") == "hd":
            score += 1
            assessment.strengths.append("High quality generation")
        
        assessment.quality_score = max(1.0, min(10.0, score))
        
        # TODO: Implement actual image analysis using computer vision
        # This would require image analysis services or models
        
        return assessment
    
    async def _assess_video_quality(
        self,
        content_data: Dict[str, Any],
        criteria: Dict[str, Any],
        task: Task
    ) -> QualityAssessment:
        """Assess video content quality"""
        
        assessment = QualityAssessment(
            content_type=ContentType.VIDEO,
            quality_level=QualityLevel.ACCEPTABLE,
            quality_score=6.0
        )
        
        # Basic assessment based on available metadata
        score = 6.0
        
        # Check if video was successfully generated
        if "video_url" in content_data:
            assessment.strengths.append("Video generated successfully")
        else:
            score -= 3
            assessment.weaknesses.append("Video generation failed")
        
        # Check duration
        duration = content_data.get("duration", 0)
        if duration > 0:
            if duration >= 3:  # Minimum viable duration
                assessment.strengths.append("Appropriate duration")
            else:
                score -= 1
                assessment.weaknesses.append("Video too short")
        
        # Check for completion status
        if content_data.get("status") == "COMPLETED":
            score += 1
            assessment.strengths.append("Generation completed successfully")
        
        assessment.quality_score = max(1.0, min(10.0, score))
        
        return assessment
    
    async def _perform_consistency_check(
        self,
        task: Task,
        content_data: Dict[str, Any],
        content_type: ContentType,
        db: Session
    ) -> ConsistencyCheck:
        """Perform consistency check across generated content"""
        
        consistency_check = ConsistencyCheck(
            consistency_score=1.0
        )
        
        try:
            # Get all content for this task
            scenes = db.query(Scene).filter(Scene.task_id == task.id).all()
            resources = db.query(Resource).filter(Resource.task_id == task.id).all()
            
            if not scenes:
                consistency_check.consistency_score = 0.5
                consistency_check.issues.append("No reference scenes found")
                return consistency_check
            
            # Check visual consistency
            if content_type in [ContentType.IMAGE, ContentType.VIDEO]:
                consistency_check = await self._check_visual_consistency(
                    content_data, scenes, resources
                )
            
            # Check narrative consistency
            if content_type == ContentType.TEXT:
                consistency_check = await self._check_narrative_consistency(
                    content_data, scenes, task
                )
            
        except Exception as e:
            self.logger.warning(f"Consistency check failed: {e}")
            consistency_check.consistency_score = 0.5
            consistency_check.issues.append("Consistency check failed")
        
        return consistency_check
    
    async def _check_visual_consistency(
        self,
        content_data: Dict[str, Any],
        scenes: List[Scene],
        resources: List[Resource]
    ) -> ConsistencyCheck:
        """Check visual consistency across scenes"""
        
        consistency_check = ConsistencyCheck(
            consistency_score=0.8  # Default decent score
        )
        
        # Get reference visual elements from first scene
        if scenes:
            reference_scene = scenes[0]
            consistency_check.reference_elements = {
                "art_style": reference_scene.art_style,
                "color_palette": reference_scene.color_palette,
                "mood": reference_scene.mood_and_atmosphere
            }
            
            # Check if current content matches reference
            current_prompt = content_data.get("prompt_used", "")
            
            # Simple keyword matching for consistency
            if reference_scene.art_style and reference_scene.art_style.lower() in current_prompt.lower():
                consistency_check.consistency_score += 0.1
            else:
                consistency_check.issues.append("Art style inconsistency detected")
                consistency_check.consistency_score -= 0.2
            
            # Check color palette consistency
            if reference_scene.color_palette:
                palette_match = any(
                    color.lower() in current_prompt.lower() 
                    for color in reference_scene.color_palette
                )
                if palette_match:
                    consistency_check.consistency_score += 0.1
                else:
                    consistency_check.issues.append("Color palette inconsistency")
                    consistency_check.consistency_score -= 0.1
        
        consistency_check.consistency_score = max(0.0, min(1.0, consistency_check.consistency_score))
        
        return consistency_check
    
    async def _check_narrative_consistency(
        self,
        content_data: Dict[str, Any],
        scenes: List[Scene],
        task: Task
    ) -> ConsistencyCheck:
        """Check narrative consistency"""
        
        consistency_check = ConsistencyCheck(
            consistency_score=0.8
        )
        
        # Get the original concept and requirements
        original_prompt = task.input_parameters.get("user_prompt", "")
        video_style = task.input_parameters.get("video_style", "")
        
        content_text = content_data.get("content", "")
        if not content_text:
            content_text = content_data.get("script", "")
        
        # Check consistency with original requirements
        if original_prompt and content_text:
            # Simple keyword matching
            original_keywords = set(original_prompt.lower().split())
            content_keywords = set(content_text.lower().split())
            
            common_keywords = original_keywords & content_keywords
            consistency_ratio = len(common_keywords) / max(len(original_keywords), 1)
            
            if consistency_ratio > 0.3:
                consistency_check.consistency_score += 0.1
            else:
                consistency_check.issues.append("Low relevance to original prompt")
                consistency_check.consistency_score -= 0.2
        
        # Check style consistency
        if video_style and content_text:
            if video_style.lower() in content_text.lower():
                consistency_check.consistency_score += 0.1
            else:
                consistency_check.recommendations.append(f"Consider incorporating {video_style} style elements")
        
        consistency_check.consistency_score = max(0.0, min(1.0, consistency_check.consistency_score))
        
        return consistency_check
    
    def _calculate_overall_score(self, result: QualityControlResult) -> float:
        """Calculate overall quality score"""
        
        scores = []
        weights = []
        
        # Safety score (critical)
        if result.safety_check:
            safety_score = self._safety_to_score(result.safety_check.safety_level)
            scores.append(safety_score)
            weights.append(0.4)  # High weight for safety
        
        # Quality score
        if result.quality_assessment:
            scores.append(result.quality_assessment.quality_score)
            weights.append(0.4)
        
        # Consistency score
        if result.consistency_check:
            consistency_score = result.consistency_check.consistency_score * 10  # Convert to 1-10 scale
            scores.append(consistency_score)
            weights.append(0.2)
        
        if not scores:
            return 0.0
        
        # Calculate weighted average
        weighted_sum = sum(score * weight for score, weight in zip(scores, weights))
        total_weight = sum(weights)
        
        return weighted_sum / total_weight if total_weight > 0 else 0.0
    
    def _safety_to_score(self, safety_level: ContentSafetyLevel) -> float:
        """Convert safety level to numeric score"""
        mapping = {
            ContentSafetyLevel.SAFE: 10.0,
            ContentSafetyLevel.MODERATE: 6.0,
            ContentSafetyLevel.UNSAFE: 2.0,
            ContentSafetyLevel.REVIEW_REQUIRED: 4.0
        }
        return mapping.get(safety_level, 5.0)
    
    def _requires_human_review(self, result: QualityControlResult) -> bool:
        """Determine if content requires human review"""
        
        # Safety concerns
        if result.safety_check:
            if result.safety_check.safety_level in [ContentSafetyLevel.UNSAFE, ContentSafetyLevel.REVIEW_REQUIRED]:
                return True
            if result.safety_check.confidence < self.review_thresholds["safety_confidence"]:
                return True
        
        # Low quality score
        if result.quality_assessment:
            if result.quality_assessment.quality_score < self.review_thresholds["quality_score"]:
                return True
        
        # Low consistency
        if result.consistency_check:
            if result.consistency_check.consistency_score < self.review_thresholds["consistency_score"]:
                return True
        
        # Overall score too low
        if result.overall_score < 5.0:
            return True
        
        return False
    
    def _determine_approval(self, result: QualityControlResult) -> bool:
        """Determine if content is approved"""
        
        # Not approved if unsafe
        if result.safety_check and result.safety_check.safety_level == ContentSafetyLevel.UNSAFE:
            return False
        
        # Not approved if requires human review (unless manually overridden)
        if result.requires_human_review:
            return False
        
        # Approved if overall score is acceptable
        return result.overall_score >= 5.0
    
    async def batch_quality_control(
        self,
        task: Task,
        content_batch: List[Tuple[Dict[str, Any], ContentType]],
        db: Session
    ) -> List[QualityControlResult]:
        """Perform quality control on multiple content pieces"""
        
        self.logger.info(f"Starting batch quality control for {len(content_batch)} items")
        
        # Process items concurrently with limit
        semaphore = asyncio.Semaphore(3)  # Limit concurrent processing
        
        async def process_item(content_data: Dict[str, Any], content_type: ContentType):
            async with semaphore:
                return await self.perform_quality_control(task, content_data, content_type, db)
        
        # Execute all quality checks
        results = await asyncio.gather(*[
            process_item(content_data, content_type)
            for content_data, content_type in content_batch
        ], return_exceptions=True)
        
        # Handle exceptions
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                self.logger.error(f"Quality control failed for item {i}: {result}")
                # Create failed result
                failed_result = QualityControlResult(
                    overall_score=0.0,
                    approved=False,
                    requires_human_review=True
                )
                final_results.append(failed_result)
            else:
                final_results.append(result)
        
        self.logger.info(f"Batch quality control completed. "
                        f"Approved: {sum(1 for r in final_results if r.approved)}, "
                        f"Review Required: {sum(1 for r in final_results if r.requires_human_review)}")
        
        return final_results
    
    def get_quality_summary(self, results: List[QualityControlResult]) -> Dict[str, Any]:
        """Generate quality summary from results"""
        
        if not results:
            return {"error": "No results provided"}
        
        total_results = len(results)
        approved_count = sum(1 for r in results if r.approved)
        review_required_count = sum(1 for r in results if r.requires_human_review)
        
        avg_score = sum(r.overall_score for r in results) / total_results
        
        safety_levels = {}
        quality_levels = {}
        
        for result in results:
            if result.safety_check:
                level = result.safety_check.safety_level.value
                safety_levels[level] = safety_levels.get(level, 0) + 1
            
            if result.quality_assessment:
                level = result.quality_assessment.quality_level.value
                quality_levels[level] = quality_levels.get(level, 0) + 1
        
        return {
            "total_items": total_results,
            "approved": approved_count,
            "review_required": review_required_count,
            "approval_rate": approved_count / total_results if total_results > 0 else 0,
            "average_score": avg_score,
            "safety_distribution": safety_levels,
            "quality_distribution": quality_levels,
            "recommendations": self._generate_quality_recommendations(results)
        }
    
    def _generate_quality_recommendations(self, results: List[QualityControlResult]) -> List[str]:
        """Generate recommendations based on quality control results"""
        
        recommendations = []
        
        # Analyze patterns in the results
        safety_issues = []
        quality_issues = []
        consistency_issues = []
        
        for result in results:
            if result.safety_check and result.safety_check.issues:
                safety_issues.extend(result.safety_check.issues)
            
            if result.quality_assessment and result.quality_assessment.weaknesses:
                quality_issues.extend(result.quality_assessment.weaknesses)
            
            if result.consistency_check and result.consistency_check.issues:
                consistency_issues.extend(result.consistency_check.issues)
        
        # Generate recommendations based on common issues
        if len(safety_issues) > len(results) * 0.3:
            recommendations.append("Consider implementing stricter content filtering")
        
        if len(quality_issues) > len(results) * 0.4:
            recommendations.append("Review and improve content generation prompts")
        
        if len(consistency_issues) > len(results) * 0.3:
            recommendations.append("Implement stronger consistency validation across workflow")
        
        return recommendations


# Global instance
quality_control_service = QualityControlService()
