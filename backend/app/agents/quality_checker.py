"""
Quality Checker Agent - Analyzes and validates the final video quality
"""
import os
import json
from typing import Dict, Any, List
from sqlalchemy.orm import Session

from .base import BaseAgent, AgentError
from ..models import Task, AgentType, Resource, ResourceType
from ..services.ai_client import AIClient
from ..services.file_storage import FileStorageService


class QualityCheckerAgent(BaseAgent):
    """
    Quality Checker Agent analyzes the final video for quality, consistency,
    and adherence to requirements
    """
    
    def __init__(self, llms=None, memory_services=None):
        super().__init__(
            agent_type=AgentType.QUALITY_CHECKER,
            agent_name="quality_checker",
            timeout_seconds=180,  # 3 minutes for quality analysis
            max_retries=1,
            tools=["quality_analysis_tool"],  # 🚀 Phase 1.3 - 使用原子性质量分析工具
            llms=llms,
            memory_services=memory_services,
        )
        # 移除直接AI客户端依赖
        self.file_storage = FileStorageService()
    
    async def _execute_impl(
        self, 
        task: Task, 
        input_data: Dict[str, Any], 
        db: Session
    ) -> Dict[str, Any]:
        """Perform comprehensive quality check on the final video"""
        
        # Validate input
        self._validate_input(input_data, ["workflow_state_id"])
        
        workflow_state_id = input_data["workflow_state_id"]
        
        # 🧠 Phase 1.2 - 实现MAS记忆共享：QualityChecker检索创意指导和质量标准
        original_concept_plan = {}
        try:
            retrieved_guidance = await self.retrieve_creative_guidance(workflow_state_id)
            if retrieved_guidance:
                original_concept_plan = retrieved_guidance
                self.logger.info(f"🧠 QualityChecker: 成功检索到原始创意指导，用于质量对比验证")
            else:
                self.logger.warning(f"⚠️ QualityChecker: 未找到创意指导记忆，无法进行原始需求对比")
        except Exception as e:
            self.logger.warning(f"⚠️ QualityChecker: 记忆检索失败 - {e}")
        
        # 从 Shared Working Memory 读取事实视图
        from .utils.memory_helpers import get_mas_working_memory, read_shared_fact
        wm = None
        try:
            wm = get_mas_working_memory(str(workflow_state_id))
        except Exception as _wm_err:
            self.logger.warning(f"MAS WM unavailable, degrading: {str(_wm_err)}")
        view = wm.get("scene_overview", {}) if wm else {"scenes": {}}
        
        await self._update_progress(10, "Loading final video from workflow", db)
        
        # Get final video facts from MAS WM
        fv = wm.get("project.final_video", {}) if wm else {}
        final_video_url = fv.get("url") or fv.get("path") or ""
        concept_plan = wm.get("project.concept_plan", {}) if wm else {}
        
        # 组合时间线：从场景概览推导（start/end/duration）
        composition_timeline = []
        try:
            scenes = view.get("scenes") if isinstance(view, dict) else []
            cursor = 0.0
            for scene in scenes or []:
                if not isinstance(scene, dict):
                    continue
                try:
                    sn = int(scene.get("scene_number"))
                except Exception:
                    continue
                try:
                    dur = float(scene.get("duration") or 0.0)
                except Exception:
                    dur = 0.0
                start = cursor
                end = start + dur
                composition_timeline.append({
                    "scene_number": sn,
                    "start": start,
                    "end": end,
                    "duration": dur,
                })
                cursor = end
        except Exception:
            composition_timeline = []
        # 视频元数据：优先 facts.final_video.metadata，其次基于时间线估算总时长
        video_metadata = fv.get("metadata", {}) if isinstance(fv, dict) else {}
        if not video_metadata:
            try:
                total = sum(float(x.get("duration") or 0.0) for x in composition_timeline)
                video_metadata = {"duration": total}
            except Exception:
                video_metadata = {}
        
        if not final_video_url:
            # If no final video, try to get from scene_overview (fallback)
            scenes_data = view.get("scenes") if isinstance(view, dict) else []
            if scenes_data and len(scenes_data) > 0:
                first_scene = scenes_data[0] if isinstance(scenes_data[0], dict) else {}
                if first_scene.get("video_url"):
                    final_video_url = first_scene.get("video_url")
                    self.logger.warning("Using first scene video for quality check - no final composed video available")
                else:
                    # 检查是否有图像可用（降级场景）
                    has_image = any(isinstance(s, dict) and (s.get("image_path") or s.get("image_url")) for s in scenes_data)
                    if has_image:
                        self.logger.warning("No videos available, performing image-based quality check")
                        return await self._perform_image_based_quality_check(scenes_data, input_data, execution, db)
                    else:
                        raise AgentError("No video content available for quality check")
            else:
                raise AgentError("No video content found in workflow state")
        
        await self._update_progress(20, "Performing technical analysis", db)
        
        # Perform technical quality checks
        technical_quality = await self._analyze_technical_quality(
            final_video_url, video_metadata
        )
        
        await self._update_progress(40, "Analyzing content quality", db)
        
        # Perform content quality analysis
        content_quality = await self._analyze_content_quality(
            concept_plan,
            composition_timeline,
            final_video_url,
            original_concept_plan,
            video_metadata
        )
        
        await self._update_progress(60, "Checking requirement compliance", db)
        
        # Check compliance with original requirements
        compliance_check = await self._check_requirement_compliance(
            task, concept_plan, composition_timeline, video_metadata
        )
        
        await self._update_progress(80, "Generating quality report", db)
        
        # Generate overall quality score and recommendations
        quality_assessment = await self._generate_quality_assessment(
            technical_quality, content_quality, compliance_check, execution
        )
        
        await self._update_progress(95, "Finalizing quality check", db)
        
        # Update task with quality information
        task.quality_score = quality_assessment["overall_score"]
        task.quality_feedback = quality_assessment["summary"]
        task.requires_human_review = quality_assessment["requires_human_review"]
        db.commit()
        
        output_data = {
            "quality_score": quality_assessment["overall_score"],
            "quality_grade": quality_assessment["quality_grade"],
            "requires_human_review": quality_assessment["requires_human_review"],
            "technical_quality": technical_quality,
            "content_quality": content_quality,
            "compliance_check": compliance_check,
            "quality_assessment": quality_assessment,
            "recommendations": quality_assessment["recommendations"],
            "approval_status": quality_assessment["approval_status"]
        }
        
        await self._update_progress(100, "Quality check completed", db)
        
        return output_data
    
    async def _perform_image_based_quality_check(
        self, 
        scenes_data: List, 
        input_data: Dict[str, Any], 
        db: Session
    ) -> Dict[str, Any]:
        """对图像进行质量检查（当没有视频时的降级方案）"""
        
        await self._update_progress(30, "Analyzing image quality", db)
        
        # 收集所有可用图像（SceneSnapshot.image_url；image_path 不一定存在）
        available_images = []
        for scene in scenes_data:
            url = getattr(scene, 'image_url', '')
            path = getattr(scene, 'image_path', '') if hasattr(scene, 'image_path') else ''
            if path or url:
                available_images.append({
                    "scene_number": getattr(scene, 'scene_number', None),
                    "image_path": path,
                    "image_url": url,
                    "description": getattr(scene, 'visual_description', '')
                })
        
        await self._update_progress(60, "Evaluating content appropriateness", db)
        
        # 简化的质量检查
        quality_score = 75  # 图像质量默认分数
        
        # 基础检查
        technical_issues = []
        content_issues = []
        
        if len(available_images) < len(scenes_data):
            technical_issues.append("Some scenes are missing images")
        
        # 内容适宜性检查（基于描述）
        for img in available_images:
            description = img.get("description", "").lower()
            if any(word in description for word in ["violent", "inappropriate", "explicit"]):
                content_issues.append(f"Scene {img['scene_number']} may contain inappropriate content")
        
        await self._update_progress(80, "Generating quality report", db)
        
        # 生成建议
        suggestions = []
        if technical_issues:
            suggestions.append("Consider regenerating missing images")
        if content_issues:
            suggestions.append("Review content for appropriateness")
        suggestions.append("Video generation timed out - consider trying again later")
        
        # 计算整体分数
        if content_issues:
            quality_score -= 20
        if technical_issues:
            quality_score -= 10
        
        quality_rating = "Good" if quality_score >= 70 else "Fair" if quality_score >= 50 else "Poor"
        
        output_data = {
            "overall_score": quality_score,
            "quality_rating": quality_rating,
            "check_type": "image_fallback",
            "total_images_checked": len(available_images),
            "technical_analysis": {
                "issues_found": technical_issues,
                "images_available": len(available_images),
                "total_scenes": len(scenes_data)
            },
            "content_analysis": {
                "appropriateness_score": 85,
                "issues_found": content_issues,
                "safe_for_all_audiences": len(content_issues) == 0
            },
            "suggestions": suggestions,
            "quality_summary": f"Image-based quality check completed. {len(available_images)} images analyzed.",
            "workflow_state_id": input_data.get("workflow_state_id"),
            "fallback_reason": "no_videos_available"
        }
        
        await self._update_progress(100, "Quality check completed", db)
        
        return output_data
    
    async def _analyze_technical_quality(
        self, 
        video_url: str, 
        video_metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Analyze technical aspects of the video"""
        
        technical_checks = {
            "file_integrity": True,  # File exists and is readable
            "duration_check": True,
            "resolution_check": True,
            "file_size_check": True,
            "format_compliance": True
        }
        
        issues = []
        
        # Check file exists and is accessible
        # Convert URL to local path if needed
        video_path = video_url.replace("file://", "") if video_url.startswith("file://") else video_url
        if not os.path.exists(video_path):
            technical_checks["file_integrity"] = False
            issues.append("Video file not found or inaccessible")
        
        # Check duration is reasonable
        duration = video_metadata.get("duration", 0)
        if duration < 5:  # Less than 5 seconds
            technical_checks["duration_check"] = False
            issues.append("Video duration is too short")
        elif duration > 300:  # More than 5 minutes
            technical_checks["duration_check"] = False
            issues.append("Video duration is too long")
        
        # Check file size
        file_size_mb = video_metadata.get("file_size_mb", 0)
        if file_size_mb > 500:  # Larger than 500MB
            technical_checks["file_size_check"] = False
            issues.append("Video file size is too large")
        elif file_size_mb < 0.1:  # Smaller than 100KB
            technical_checks["file_size_check"] = False
            issues.append("Video file size is suspiciously small")
        
        # Check format
        if video_metadata.get("format") != "mp4":
            technical_checks["format_compliance"] = False
            issues.append("Video format is not MP4")
        
        # Calculate technical score
        passed_checks = sum(1 for check in technical_checks.values() if check)
        technical_score = int((passed_checks / len(technical_checks)) * 100)
        
        return {
            "score": technical_score,
            "checks": technical_checks,
            "issues": issues,
            "metadata": video_metadata,
            "file_integrity": technical_checks["file_integrity"],
            "recommendations": self._get_technical_recommendations(issues)
        }
    
    async def _analyze_content_quality(
        self,
        concept_plan: Dict[str, Any],
        composition_timeline: List[Dict],
        video_url: str,
        original_requirements: Dict[str, Any],
        video_metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Analyze content quality and coherence"""
        
        content_analysis = {
            "scene_continuity": True,
            "visual_consistency": True,
            "narrative_flow": True,
            "message_clarity": True,
            "target_audience_fit": True
        }
        
        issues = []
        
        # Check scene continuity
        if len(composition_timeline) < 2:
            content_analysis["scene_continuity"] = False
            issues.append("Insufficient scenes for proper narrative flow")
        
        # Check for missing scenes
        expected_scenes = len(concept_plan.get("scenes", []))
        actual_scenes = len(composition_timeline)
        
        if actual_scenes < expected_scenes * 0.7:  # Less than 70% of planned scenes
            content_analysis["narrative_flow"] = False
            issues.append(f"Missing scenes: expected {expected_scenes}, got {actual_scenes}")
        
        # Analyze scene types distribution
        scene_types = [entry.get("scene_type", "main_content") for entry in composition_timeline]
        
        if "intro" not in scene_types:
            issues.append("Missing introduction scene")
        
        if "outro" not in scene_types and len(composition_timeline) > 2:
            issues.append("Missing conclusion scene")
        
        # Calculate content score
        passed_checks = sum(1 for check in content_analysis.values() if check)
        content_score = int((passed_checks / len(content_analysis)) * 100)
        
        # Use AI to analyze content if available
        ai_content_analysis = await self._ai_content_analysis(
            concept_plan,
            composition_timeline,
            original_requirements,
            video_metadata
        )
        
        return {
            "score": content_score,
            "analysis": content_analysis,
            "issues": issues,
            "scene_breakdown": self._analyze_scene_breakdown(composition_timeline),
            "ai_analysis": ai_content_analysis,
            "recommendations": self._get_content_recommendations(issues, scene_types)
        }
    
    async def _ai_content_analysis(
        self,
        concept_plan: Dict[str, Any],
        composition_timeline: List[Dict],
        original_requirements: Dict[str, Any],
        video_metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Use AI to analyze content quality"""
        
        try:
            # 使用新的提示词模板系统，从25+行硬编码减少到简单的模板调用
            analysis_prompt = self.render_prompt(
                "video_quality_analysis",
                concept_plan=json.dumps(concept_plan, indent=2),
                composition_timeline=json.dumps(composition_timeline, indent=2)
            )
            
            # 使用AI配置管理器获取适合的模型
            from ..core.ai_config import get_ai_config
            ai_config_manager = get_ai_config()
            quality_model = ai_config_manager.get_model_for_agent("quality_checker")
            model_config = ai_config_manager.get_model_config(quality_model)
            
            # 构造视频数据摘要供质量分析工具使用
            try:
                total_scenes = len(composition_timeline or [])
            except Exception:
                total_scenes = 0
            video_data = {
                "total_scenes": total_scenes,
                "actual_duration": video_metadata.get("duration", 0),
                "file_size": video_metadata.get("file_size_mb", 0.0),
                "resolution": video_metadata.get("resolution", ""),
                "video_quality": ""  # 占位：可由技术分析结果提供
            }
            # 供应商解耦：使用统一的 llm_function_call，不依赖特定SDK
            # 构造系统+用户消息（保持中立，不暴露具体工具名/参数）
            messages = []
            try:
                from ..core.prompt_manager import get_prompt_manager
                pm = get_prompt_manager()
                sys_text = pm.render_template("mas_system", "system", variables={}, use_cache=True, auto_reload=False)
                if isinstance(sys_text, str) and sys_text.strip():
                    messages.append({"role": "system", "content": sys_text})
            except Exception:
                pass
            # 将视频数据摘要附在提示之后，方便LLM给出更具体建议
            user_content = analysis_prompt + "\n\n## 视频数据摘要\n" + json.dumps(video_data, ensure_ascii=False)
            messages.append({"role": "user", "content": user_content})

            resp = await self.llm_function_call(
                messages=messages,
                model=quality_model,
                context_description="Analyze video content quality and output JSON report",
                temperature=(model_config.temperature if model_config else 0.3),
                max_tokens=(model_config.max_tokens if model_config else 1000),
                response_format={"type": "json_object"},
                thinking={"type": "disabled"}
            )

            content = (resp.get("content") or "").strip()
            if not content:
                raise Exception("Empty content from quality LLM")
            return json.loads(content)
            
        except Exception as e:
            self.logger.warning(f"AI content analysis failed: {str(e)}")
            return {
                "narrative_coherence": "Unable to analyze",
                "message_clarity": "Unable to analyze",
                "overall_assessment": "AI analysis unavailable"
            }
    
    async def _check_requirement_compliance(
        self, 
        task: Task, 
        concept_plan: Dict[str, Any], 
        composition_timeline: List[Dict],
        video_metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Check compliance with original requirements"""
        
        # Get original requirements from task parameters
        original_params = task.input_parameters or {}
        
        compliance_checks = {
            "duration_compliance": True,
            "style_compliance": True,
            "content_compliance": True,
            "technical_compliance": True
        }
        
        issues = []
        
        # Check duration compliance
        requested_duration = original_params.get("duration", 30)
        actual_duration = video_metadata.get("duration", 0)
        
        duration_variance = abs(actual_duration - requested_duration) / requested_duration
        if duration_variance > 0.3:  # More than 30% variance
            compliance_checks["duration_compliance"] = False
            issues.append(f"Duration mismatch: requested {requested_duration}s, got {actual_duration}s")
        
        # Check style compliance
        requested_style = original_params.get("video_style", "professional")
        concept_style = concept_plan.get("visual_style", "")
        
        if requested_style.lower() not in concept_style.lower():
            compliance_checks["style_compliance"] = False
            issues.append(f"Style mismatch: requested {requested_style}")
        
        # Check aspect ratio compliance
        requested_aspect = original_params.get("aspect_ratio", "16:9")
        # Note: In a full implementation, we would extract actual video dimensions
        
        # Calculate compliance score
        passed_checks = sum(1 for check in compliance_checks.values() if check)
        compliance_score = int((passed_checks / len(compliance_checks)) * 100)
        
        return {
            "score": compliance_score,
            "checks": compliance_checks,
            "issues": issues,
            "original_requirements": original_params,
            "variance_analysis": {
                "duration_variance": f"{duration_variance:.1%}",
                "style_match": requested_style in concept_style
            }
        }
    
    async def _generate_quality_assessment(
        self, 
        technical_quality: Dict[str, Any], 
        content_quality: Dict[str, Any],
        compliance_check: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Generate overall quality assessment and recommendations"""
        
        # Calculate weighted overall score
        technical_weight = 0.3
        content_weight = 0.4
        compliance_weight = 0.3
        
        overall_score = int(
            technical_quality["score"] * technical_weight +
            content_quality["score"] * content_weight +
            compliance_check["score"] * compliance_weight
        )
        
        # Determine quality grade
        if overall_score >= 90:
            quality_grade = "Excellent"
            approval_status = "approved"
            requires_human_review = False
        elif overall_score >= 80:
            quality_grade = "Good"
            approval_status = "approved"
            requires_human_review = False
        elif overall_score >= 70:
            quality_grade = "Acceptable"
            approval_status = "conditional"
            requires_human_review = True
        elif overall_score >= 60:
            quality_grade = "Poor"
            approval_status = "needs_revision"
            requires_human_review = True
        else:
            quality_grade = "Unacceptable"
            approval_status = "rejected"
            requires_human_review = True
        
        # Collect all issues and recommendations
        all_issues = (
            technical_quality.get("issues", []) +
            content_quality.get("issues", []) +
            compliance_check.get("issues", [])
        )
        
        all_recommendations = (
            technical_quality.get("recommendations", []) +
            content_quality.get("recommendations", [])
        )
        
        # Generate summary
        summary = self._generate_quality_summary(
            overall_score, quality_grade, all_issues
        )
        
        return {
            "overall_score": overall_score,
            "quality_grade": quality_grade,
            "approval_status": approval_status,
            "requires_human_review": requires_human_review,
            "summary": summary,
            "detailed_scores": {
                "technical": technical_quality["score"],
                "content": content_quality["score"],
                "compliance": compliance_check["score"]
            },
            "issues_found": len(all_issues),
            "critical_issues": [issue for issue in all_issues if "missing" in issue.lower() or "failed" in issue.lower()],
            "recommendations": all_recommendations[:10],  # Top 10 recommendations
            "review_notes": self._generate_review_notes(all_issues, overall_score)
        }
    
    def _analyze_scene_breakdown(self, composition_timeline: List[Dict]) -> Dict[str, Any]:
        """Analyze the breakdown of scenes in the composition"""
        
        total_scenes = len(composition_timeline)
        total_duration = sum(entry["duration"] for entry in composition_timeline)
        
        scene_types = {}
        for entry in composition_timeline:
            scene_type = entry.get("scene_type", "main_content")
            scene_types[scene_type] = scene_types.get(scene_type, 0) + 1
        
        return {
            "total_scenes": total_scenes,
            "total_duration": total_duration,
            "average_scene_duration": total_duration / total_scenes if total_scenes > 0 else 0,
            "scene_type_distribution": scene_types,
            "shortest_scene": min((entry["duration"] for entry in composition_timeline), default=0),
            "longest_scene": max((entry["duration"] for entry in composition_timeline), default=0)
        }
    
    def _get_technical_recommendations(self, issues: List[str]) -> List[str]:
        """Generate technical recommendations based on issues"""
        
        recommendations = []
        
        if any("file size" in issue for issue in issues):
            recommendations.append("Optimize video compression settings")
            recommendations.append("Consider reducing resolution or bitrate")
        
        if any("duration" in issue for issue in issues):
            recommendations.append("Review scene timing and pacing")
            recommendations.append("Adjust composition timeline")
        
        if any("format" in issue for issue in issues):
            recommendations.append("Convert video to MP4 format")
            recommendations.append("Ensure H.264 codec compatibility")
        
        return recommendations
    
    def _get_content_recommendations(self, issues: List[str], scene_types: List[str]) -> List[str]:
        """Generate content recommendations based on issues"""
        
        recommendations = []
        
        if "Missing introduction scene" in issues:
            recommendations.append("Add an engaging introduction scene")
        
        if "Missing conclusion scene" in issues:
            recommendations.append("Include a clear conclusion or call-to-action")
        
        if any("Missing scenes" in issue for issue in issues):
            recommendations.append("Regenerate missing scenes to complete the narrative")
        
        if len(set(scene_types)) < 2:
            recommendations.append("Add variety in scene types for better engagement")
        
        return recommendations
    
    def _generate_quality_summary(
        self, 
        overall_score: int, 
        quality_grade: str, 
        issues: List[str]
    ) -> str:
        """Generate a quality summary description"""
        
        if overall_score >= 90:
            return f"Excellent quality video ({overall_score}/100). Ready for delivery with minimal issues."
        elif overall_score >= 80:
            return f"Good quality video ({overall_score}/100). Minor issues present but acceptable for most use cases."
        elif overall_score >= 70:
            return f"Acceptable quality video ({overall_score}/100). Some issues found that may require attention."
        elif overall_score >= 60:
            return f"Poor quality video ({overall_score}/100). Multiple issues found requiring revision before delivery."
        else:
            return f"Unacceptable quality video ({overall_score}/100). Significant issues found requiring major revision."
    
    def _generate_review_notes(self, issues: List[str], overall_score: int) -> List[str]:
        """Generate notes for human reviewers"""
        
        notes = []
        
        if overall_score < 70:
            notes.append("Video requires human review before approval")
        
        if issues:
            notes.append(f"Found {len(issues)} issues requiring attention")
        
        critical_issues = [issue for issue in issues if "missing" in issue.lower() or "failed" in issue.lower()]
        if critical_issues:
            notes.append(f"Critical issues found: {len(critical_issues)}")
        
        if overall_score >= 80:
            notes.append("Video meets quality standards for automatic approval")
        
        return notes
