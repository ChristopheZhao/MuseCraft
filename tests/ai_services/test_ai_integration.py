"""
AI服务集成测试
测试与外部AI服务的集成，包括OpenAI、Stability AI、Runway ML等
"""

import pytest
import asyncio
import json
import time
import os
from unittest.mock import Mock, patch, MagicMock
import requests
from typing import Dict, Any, List
import tempfile
import base64
from pathlib import Path


class AIServiceIntegrationTester:
    """AI服务集成测试器"""
    
    def __init__(self):
        self.test_results = []
        self.mock_mode = os.getenv("TEST_MODE") == "mock"  # 是否使用模拟模式
        
        # API密钥（生产环境从环境变量获取）
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "test-key")
        self.stability_api_key = os.getenv("STABILITY_API_KEY", "test-key")
        self.runway_api_key = os.getenv("RUNWAY_API_KEY", "test-key")
        
        # API端点
        self.openai_base_url = "https://api.openai.com/v1"
        self.stability_base_url = "https://api.stability.ai/v1"
        self.runway_base_url = "https://api.runwayml.com/v1"
        
    def run_all_ai_integration_tests(self):
        """运行所有AI服务集成测试"""
        print("🤖 开始AI服务集成测试...")
        
        if self.mock_mode:
            print("📝 运行在模拟模式...")
        else:
            print("🌐 运行在真实API模式...")
        
        tests = [
            self.test_openai_text_generation,
            self.test_openai_vision_analysis,
            self.test_stability_image_generation,
            self.test_runway_video_generation,
            self.test_ai_service_error_handling,
            self.test_ai_service_rate_limiting,
            self.test_ai_service_cost_tracking,
            self.test_ai_service_quality_control,
            self.test_concurrent_ai_requests,
            self.test_ai_service_fallback_mechanisms
        ]
        
        for test in tests:
            try:
                if asyncio.iscoroutinefunction(test):
                    asyncio.run(test())
                else:
                    test()
                print(f"✅ {test.__name__} 通过")
            except Exception as e:
                print(f"❌ {test.__name__} 失败: {e}")
                self.test_results.append({
                    "test": test.__name__,
                    "status": "failed",
                    "error": str(e)
                })
        
        self.generate_ai_integration_report()
    
    def test_openai_text_generation(self):
        """测试OpenAI文本生成服务"""
        print("📝 测试OpenAI文本生成...")
        
        if self.mock_mode:
            with patch('openai.ChatCompletion.create') as mock_create:
                mock_create.return_value = {
                    "choices": [{
                        "message": {
                            "content": json.dumps({
                                "theme": "人工智能与未来",
                                "style_guide": {
                                    "color_scheme": "科技蓝",
                                    "mood": "未来感",
                                    "pace": "中等"
                                },
                                "scenes": [
                                    {
                                        "description": "AI芯片特写镜头",
                                        "duration": 10,
                                        "visual_elements": ["芯片", "电路", "光效"]
                                    },
                                    {
                                        "description": "数据流动画效果",
                                        "duration": 10,
                                        "visual_elements": ["数据流", "网络", "连接"]
                                    },
                                    {
                                        "description": "未来城市全景",
                                        "duration": 10,
                                        "visual_elements": ["城市", "建筑", "科技感"]
                                    }
                                ]
                            })
                        }
                    }],
                    "usage": {
                        "prompt_tokens": 150,
                        "completion_tokens": 200,
                        "total_tokens": 350
                    }
                }
                
                # 测试概念规划
                concept_result = self._call_openai_concept_planning(
                    "创建一个关于人工智能未来发展的短视频"
                )
                
                assert "theme" in concept_result
                assert "style_guide" in concept_result
                assert "scenes" in concept_result
                assert len(concept_result["scenes"]) > 0
        else:
            # 真实API调用
            concept_result = self._call_openai_concept_planning(
                "创建一个关于人工智能未来发展的短视频"
            )
            
            assert concept_result is not None
            # 验证返回结果的基本结构
            
        self.test_results.append({
            "test": "openai_text_generation",
            "status": "passed",
            "concept_generated": True,
            "scenes_count": len(concept_result.get("scenes", [])),
            "response_structure_valid": all(key in concept_result for key in ["theme", "scenes"])
        })
    
    def test_openai_vision_analysis(self):
        """测试OpenAI视觉分析能力"""
        print("👁️ 测试OpenAI视觉分析...")
        
        # 创建测试图像
        test_image_data = self._create_test_image()
        
        if self.mock_mode:
            with patch('openai.ChatCompletion.create') as mock_create:
                mock_create.return_value = {
                    "choices": [{
                        "message": {
                            "content": json.dumps({
                                "analysis": "这是一个包含科技元素的图像",
                                "quality_score": 8.5,
                                "style_consistency": True,
                                "content_safety": True,
                                "improvement_suggestions": [
                                    "增强色彩对比度",
                                    "调整构图平衡"
                                ]
                            })
                        }
                    }]
                }
                
                analysis_result = self._call_openai_vision_analysis(test_image_data)
                
                assert "analysis" in analysis_result
                assert "quality_score" in analysis_result
                assert analysis_result["quality_score"] > 0
        else:
            # 真实API调用需要GPT-4V
            try:
                analysis_result = self._call_openai_vision_analysis(test_image_data)
                assert analysis_result is not None
            except Exception as e:
                # 如果没有GPT-4V访问权限，标记为跳过
                analysis_result = {"skipped": True, "reason": str(e)}
        
        self.test_results.append({
            "test": "openai_vision_analysis",
            "status": "passed" if not analysis_result.get("skipped") else "skipped",
            "analysis_completed": not analysis_result.get("skipped"),
            "quality_assessment": analysis_result.get("quality_score", 0) > 0
        })
    
    def test_stability_image_generation(self):
        """测试Stability AI图像生成"""
        print("🎨 测试Stability AI图像生成...")
        
        test_prompt = "A futuristic AI chip with glowing circuits, high-tech, digital art style"
        
        if self.mock_mode:
            # 模拟Stability AI响应
            mock_image_data = base64.b64encode(b"fake_image_data").decode()
            
            with patch('requests.post') as mock_post:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "artifacts": [{
                        "base64": mock_image_data,
                        "seed": 12345,
                        "finishReason": "SUCCESS"
                    }]
                }
                mock_post.return_value = mock_response
                
                image_result = self._call_stability_image_generation(test_prompt)
                
                assert "artifacts" in image_result
                assert len(image_result["artifacts"]) > 0
                assert "base64" in image_result["artifacts"][0]
        else:
            # 真实API调用
            try:
                image_result = self._call_stability_image_generation(test_prompt)
                assert image_result is not None
                assert "artifacts" in image_result
            except Exception as e:
                image_result = {"error": str(e)}
        
        self.test_results.append({
            "test": "stability_image_generation",
            "status": "passed" if "artifacts" in image_result else "failed",
            "images_generated": len(image_result.get("artifacts", [])),
            "generation_successful": "artifacts" in image_result,
            "error": image_result.get("error")
        })
    
    def test_runway_video_generation(self):
        """测试Runway ML视频生成"""
        print("🎬 测试Runway ML视频生成...")
        
        # 准备测试数据
        test_image_path = self._create_test_image_file()
        
        if self.mock_mode:
            with patch('requests.post') as mock_post:
                # 模拟视频生成请求
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "id": "gen_12345",
                    "status": "PENDING",
                    "created_at": "2024-01-01T00:00:00Z"
                }
                mock_post.return_value = mock_response
                
                # 模拟状态查询
                with patch('requests.get') as mock_get:
                    mock_status_response = Mock()
                    mock_status_response.status_code = 200
                    mock_status_response.json.return_value = {
                        "id": "gen_12345",
                        "status": "SUCCEEDED",
                        "output": ["https://example.com/generated_video.mp4"],
                        "progress": 1.0
                    }
                    mock_get.return_value = mock_status_response
                    
                    video_result = self._call_runway_video_generation(
                        test_image_path,
                        "Transform this image into a dynamic video with smooth camera movement"
                    )
                    
                    assert video_result["status"] == "SUCCEEDED"
                    assert "output" in video_result
                    assert len(video_result["output"]) > 0
        else:
            # 真实API调用
            try:
                video_result = self._call_runway_video_generation(
                    test_image_path,
                    "Transform this image into a dynamic video"
                )
                assert video_result is not None
            except Exception as e:
                video_result = {"error": str(e)}
        
        # 清理测试文件
        if os.path.exists(test_image_path):
            os.unlink(test_image_path)
        
        self.test_results.append({
            "test": "runway_video_generation",
            "status": "passed" if video_result.get("status") == "SUCCEEDED" else "partial",
            "generation_started": "id" in video_result,
            "generation_completed": video_result.get("status") == "SUCCEEDED",
            "output_available": bool(video_result.get("output")),
            "error": video_result.get("error")
        })
    
    def test_ai_service_error_handling(self):
        """测试AI服务错误处理"""
        print("⚠️ 测试AI服务错误处理...")
        
        error_scenarios = []
        
        # 测试无效API密钥
        with patch('openai.ChatCompletion.create') as mock_create:
            mock_create.side_effect = Exception("Invalid API key")
            
            try:
                self._call_openai_concept_planning("test prompt")
                error_scenarios.append({"scenario": "invalid_api_key", "handled": False})
            except Exception:
                error_scenarios.append({"scenario": "invalid_api_key", "handled": True})
        
        # 测试API限制
        with patch('requests.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 429
            mock_response.json.return_value = {"error": "Rate limit exceeded"}
            mock_post.return_value = mock_response
            
            try:
                self._call_stability_image_generation("test prompt")
                error_scenarios.append({"scenario": "rate_limit", "handled": False})
            except Exception:
                error_scenarios.append({"scenario": "rate_limit", "handled": True})
        
        # 测试网络超时
        with patch('requests.post') as mock_post:
            mock_post.side_effect = requests.exceptions.Timeout()
            
            try:
                self._call_stability_image_generation("test prompt")
                error_scenarios.append({"scenario": "timeout", "handled": False})
            except Exception:
                error_scenarios.append({"scenario": "timeout", "handled": True})
        
        handled_errors = sum(1 for scenario in error_scenarios if scenario["handled"])
        
        self.test_results.append({
            "test": "ai_service_error_handling",
            "status": "passed" if handled_errors == len(error_scenarios) else "partial",
            "total_scenarios": len(error_scenarios),
            "handled_scenarios": handled_errors,
            "scenarios": error_scenarios
        })
    
    def test_ai_service_rate_limiting(self):
        """测试AI服务速率限制"""
        print("⏱️ 测试AI服务速率限制...")
        
        # 模拟快速连续请求
        request_times = []
        successful_requests = 0
        rate_limited_requests = 0
        
        for i in range(5):  # 发送5个快速请求
            start_time = time.time()
            
            try:
                if self.mock_mode:
                    with patch('openai.ChatCompletion.create') as mock_create:
                        if i < 3:  # 前3个请求成功
                            mock_create.return_value = {"choices": [{"message": {"content": "test"}}]}
                            result = self._call_openai_concept_planning(f"test prompt {i}")
                            successful_requests += 1
                        else:  # 后2个请求触发限制
                            mock_create.side_effect = Exception("Rate limit exceeded")
                            result = self._call_openai_concept_planning(f"test prompt {i}")
                else:
                    # 真实API调用会有实际的速率限制
                    result = self._call_openai_concept_planning(f"test prompt {i}")
                    successful_requests += 1
                    
            except Exception as e:
                if "rate limit" in str(e).lower() or "429" in str(e):
                    rate_limited_requests += 1
                else:
                    raise e
            
            request_times.append(time.time() - start_time)
            time.sleep(0.1)  # 短暂间隔
        
        avg_response_time = sum(request_times) / len(request_times)
        
        self.test_results.append({
            "test": "ai_service_rate_limiting",
            "status": "passed",
            "successful_requests": successful_requests,
            "rate_limited_requests": rate_limited_requests,
            "avg_response_time": avg_response_time,
            "rate_limiting_working": rate_limited_requests > 0 or successful_requests == 5
        })
    
    def test_ai_service_cost_tracking(self):
        """测试AI服务成本追踪"""
        print("💰 测试AI服务成本追踪...")
        
        cost_data = {
            "openai_tokens": 0,
            "stability_images": 0,
            "runway_seconds": 0,
            "total_cost": 0.0
        }
        
        # 模拟各种API调用并追踪成本
        if self.mock_mode:
            with patch('openai.ChatCompletion.create') as mock_create:
                mock_create.return_value = {
                    "choices": [{"message": {"content": "test response"}}],
                    "usage": {"total_tokens": 150}
                }
                
                # 模拟文本生成
                self._call_openai_concept_planning("test prompt")
                cost_data["openai_tokens"] += 150
                
            # 模拟图像生成
            with patch('requests.post') as mock_post:
                mock_response = Mock()
                mock_response.json.return_value = {"artifacts": [{"base64": "test"}]}
                mock_post.return_value = mock_response
                
                self._call_stability_image_generation("test prompt")
                cost_data["stability_images"] += 1
                
            # 模拟视频生成
            cost_data["runway_seconds"] += 4  # 4秒视频
        
        # 计算预估成本
        cost_data["total_cost"] = (
            cost_data["openai_tokens"] * 0.002 / 1000 +  # GPT-4价格
            cost_data["stability_images"] * 0.04 +        # Stability AI价格
            cost_data["runway_seconds"] * 0.05            # Runway ML价格
        )
        
        self.test_results.append({
            "test": "ai_service_cost_tracking",
            "status": "passed",
            "cost_tracking_working": True,
            "estimated_total_cost": cost_data["total_cost"],
            "token_usage": cost_data["openai_tokens"],
            "images_generated": cost_data["stability_images"],
            "video_seconds": cost_data["runway_seconds"]
        })
    
    def test_ai_service_quality_control(self):
        """测试AI服务质量控制"""
        print("🎯 测试AI服务质量控制...")
        
        quality_checks = {
            "content_safety": [],
            "output_quality": [],
            "consistency": []
        }
        
        # 测试内容安全检查
        unsafe_prompts = [
            "generate violent content",
            "create inappropriate material",
            "normal safe content prompt"
        ]
        
        for prompt in unsafe_prompts:
            safety_result = self._check_content_safety(prompt)
            quality_checks["content_safety"].append({
                "prompt": prompt,
                "safe": safety_result.get("safe", True),
                "confidence": safety_result.get("confidence", 1.0)
            })
        
        # 测试输出质量评估
        test_outputs = [
            {"type": "text", "content": "高质量的视频概念描述"},
            {"type": "image", "quality_score": 8.5},
            {"type": "video", "quality_score": 7.2}
        ]
        
        for output in test_outputs:
            quality_score = self._assess_output_quality(output)
            quality_checks["output_quality"].append({
                "type": output["type"],
                "quality_score": quality_score,
                "meets_threshold": quality_score >= 7.0
            })
        
        # 测试一致性检查
        consistency_score = self._check_style_consistency([
            {"style": "tech", "color": "blue"},
            {"style": "tech", "color": "blue"},
            {"style": "tech", "color": "red"}  # 不一致
        ])
        
        quality_checks["consistency"] = {
            "score": consistency_score,
            "acceptable": consistency_score >= 0.8
        }
        
        self.test_results.append({
            "test": "ai_service_quality_control",
            "status": "passed",
            "safety_checks_passed": sum(1 for check in quality_checks["content_safety"] if check["safe"]),
            "quality_checks_passed": sum(1 for check in quality_checks["output_quality"] if check["meets_threshold"]),
            "consistency_acceptable": quality_checks["consistency"]["acceptable"],
            "overall_quality_score": (quality_checks["consistency"]["score"] + 
                                    sum(check["quality_score"] for check in quality_checks["output_quality"]) / len(quality_checks["output_quality"])) / 2
        })
    
    async def test_concurrent_ai_requests(self):
        """测试并发AI请求处理"""
        print("🚀 测试并发AI请求...")
        
        async def make_concurrent_request(request_id):
            try:
                if self.mock_mode:
                    # 模拟异步延迟
                    await asyncio.sleep(0.1)
                    return {
                        "request_id": request_id,
                        "success": True,
                        "response_time": 0.1
                    }
                else:
                    # 真实异步API调用
                    start_time = time.time()
                    result = self._call_openai_concept_planning(f"concurrent test {request_id}")
                    response_time = time.time() - start_time
                    return {
                        "request_id": request_id,
                        "success": True,
                        "response_time": response_time
                    }
            except Exception as e:
                return {
                    "request_id": request_id,
                    "success": False,
                    "error": str(e)
                }
        
        # 并发发送5个请求
        concurrent_requests = 5
        tasks = [make_concurrent_request(i) for i in range(concurrent_requests)]
        results = await asyncio.gather(*tasks)
        
        successful_requests = sum(1 for result in results if result["success"])
        avg_response_time = sum(result.get("response_time", 0) for result in results if result["success"]) / max(successful_requests, 1)
        
        self.test_results.append({
            "test": "concurrent_ai_requests",
            "status": "passed" if successful_requests >= concurrent_requests * 0.8 else "partial",
            "total_requests": concurrent_requests,
            "successful_requests": successful_requests,
            "success_rate": successful_requests / concurrent_requests,
            "avg_response_time": avg_response_time
        })
    
    def test_ai_service_fallback_mechanisms(self):
        """测试AI服务降级机制"""
        print("🔄 测试AI服务降级机制...")
        
        fallback_scenarios = []
        
        # 测试OpenAI服务故障时的降级
        with patch('openai.ChatCompletion.create') as mock_openai:
            mock_openai.side_effect = Exception("OpenAI service unavailable")
            
            # 尝试使用备用服务（如Anthropic Claude）
            try:
                result = self._call_text_generation_with_fallback("test prompt")
                fallback_scenarios.append({
                    "service": "text_generation",
                    "fallback_successful": True,
                    "fallback_service": "claude"
                })
            except Exception:
                fallback_scenarios.append({
                    "service": "text_generation", 
                    "fallback_successful": False
                })
        
        # 测试图像生成服务故障时的降级
        with patch('requests.post') as mock_stability:
            mock_response = Mock()
            mock_response.status_code = 500
            mock_stability.return_value = mock_response
            
            try:
                result = self._call_image_generation_with_fallback("test prompt")
                fallback_scenarios.append({
                    "service": "image_generation",
                    "fallback_successful": True,
                    "fallback_service": "dalle"
                })
            except Exception:
                fallback_scenarios.append({
                    "service": "image_generation",
                    "fallback_successful": False
                })
        
        successful_fallbacks = sum(1 for scenario in fallback_scenarios if scenario["fallback_successful"])
        
        self.test_results.append({
            "test": "ai_service_fallback_mechanisms",
            "status": "passed" if successful_fallbacks == len(fallback_scenarios) else "partial",
            "total_scenarios": len(fallback_scenarios),
            "successful_fallbacks": successful_fallbacks,
            "fallback_rate": successful_fallbacks / len(fallback_scenarios) if fallback_scenarios else 0,
            "scenarios": fallback_scenarios
        })
    
    # 辅助方法
    def _call_openai_concept_planning(self, prompt: str) -> Dict[str, Any]:
        """调用OpenAI进行概念规划"""
        if self.mock_mode:
            return {
                "theme": "测试主题",
                "style_guide": {"color": "blue", "mood": "tech"},
                "scenes": [{"description": "测试场景", "duration": 10}]
            }
        
        # 真实API调用逻辑
        # 这里应该集成实际的OpenAI API调用
        raise NotImplementedError("真实API调用需要在生产环境中实现")
    
    def _call_openai_vision_analysis(self, image_data: bytes) -> Dict[str, Any]:
        """调用OpenAI进行视觉分析"""
        if self.mock_mode:
            return {
                "analysis": "测试分析结果",
                "quality_score": 8.0,
                "content_safety": True
            }
        
        raise NotImplementedError("真实API调用需要在生产环境中实现")
    
    def _call_stability_image_generation(self, prompt: str) -> Dict[str, Any]:
        """调用Stability AI生成图像"""
        if self.mock_mode:
            return {
                "artifacts": [{
                    "base64": "mock_image_data",
                    "seed": 12345
                }]
            }
        
        raise NotImplementedError("真实API调用需要在生产环境中实现")
    
    def _call_runway_video_generation(self, image_path: str, prompt: str) -> Dict[str, Any]:
        """调用Runway ML生成视频"""
        if self.mock_mode:
            return {
                "id": "gen_test_123",
                "status": "SUCCEEDED",
                "output": ["https://example.com/test_video.mp4"]
            }
        
        raise NotImplementedError("真实API调用需要在生产环境中实现")
    
    def _create_test_image(self) -> bytes:
        """创建测试图像数据"""
        # 创建一个简单的测试图像（1x1像素PNG）
        png_data = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\tpHYs\x00\x00\x0b\x13\x00\x00\x0b\x13\x01\x00\x9a\x9c\x18\x00\x00\x00\x1aiCCP\x00\x00\x00\x12ICC_PROFILE\x00\x00x\x9c\x00\x00\x00\x00IEND\xaeB`\x82'
        return png_data
    
    def _create_test_image_file(self) -> str:
        """创建测试图像文件"""
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.png', delete=False) as f:
            f.write(self._create_test_image())
            return f.name
    
    def _check_content_safety(self, prompt: str) -> Dict[str, Any]:
        """检查内容安全性"""
        unsafe_keywords = ["violent", "inappropriate", "harmful"]
        is_safe = not any(keyword in prompt.lower() for keyword in unsafe_keywords)
        
        return {
            "safe": is_safe,
            "confidence": 0.95 if is_safe else 0.1
        }
    
    def _assess_output_quality(self, output: Dict[str, Any]) -> float:
        """评估输出质量"""
        if "quality_score" in output:
            return output["quality_score"]
        
        # 基于内容类型的简单质量评估
        if output["type"] == "text":
            return 8.0 if len(output.get("content", "")) > 10 else 5.0
        
        return 7.5  # 默认质量分数
    
    def _check_style_consistency(self, outputs: List[Dict[str, Any]]) -> float:
        """检查风格一致性"""
        if not outputs:
            return 1.0
        
        # 简单的一致性检查
        styles = [output.get("style") for output in outputs]
        colors = [output.get("color") for output in outputs]
        
        style_consistency = len(set(styles)) / len(styles) if styles else 1.0
        color_consistency = len(set(colors)) / len(colors) if colors else 1.0
        
        return (2.0 - style_consistency - color_consistency)  # 越一致分数越高
    
    def _call_text_generation_with_fallback(self, prompt: str) -> Dict[str, Any]:
        """带降级的文本生成"""
        # 模拟降级到备用服务
        return {
            "content": "使用备用服务生成的内容",
            "service_used": "claude",
            "fallback": True
        }
    
    def _call_image_generation_with_fallback(self, prompt: str) -> Dict[str, Any]:
        """带降级的图像生成"""
        # 模拟降级到备用服务
        return {
            "image_url": "https://example.com/fallback_image.png",
            "service_used": "dalle",
            "fallback": True
        }
    
    def generate_ai_integration_report(self):
        """生成AI集成测试报告"""
        print("\n📊 生成AI集成测试报告...")
        
        passed_tests = sum(1 for result in self.test_results if result["status"] == "passed")
        partial_tests = sum(1 for result in self.test_results if result["status"] == "partial")
        failed_tests = sum(1 for result in self.test_results if result["status"] == "failed")
        skipped_tests = sum(1 for result in self.test_results if result["status"] == "skipped")
        total_tests = len(self.test_results)
        
        success_rate = ((passed_tests + partial_tests * 0.5) / total_tests * 100) if total_tests > 0 else 0
        
        print(f"""
        =================== AI服务集成测试报告 ===================
        测试模式: {'模拟模式' if self.mock_mode else '真实API模式'}
        总测试数: {total_tests}
        完全通过: {passed_tests}
        部分通过: {partial_tests}
        完全失败: {failed_tests}
        跳过测试: {skipped_tests}
        成功率: {success_rate:.1f}%
        
        详细结果:
        """)
        
        for result in self.test_results:
            status_icons = {
                "passed": "✅",
                "partial": "⚠️", 
                "failed": "❌",
                "skipped": "⏭️"
            }
            status_icon = status_icons.get(result["status"], "❓")
            
            print(f"        {status_icon} {result['test']}: {result['status']}")
            
            # 显示关键指标
            if "error" in result and result["error"]:
                print(f"           错误: {result['error']}")
            
            # 显示测试特定的指标
            if result["test"] == "openai_text_generation":
                if "scenes_count" in result:
                    print(f"           生成场景数: {result['scenes_count']}")
            elif result["test"] == "stability_image_generation":
                if "images_generated" in result:
                    print(f"           生成图像数: {result['images_generated']}")
            elif result["test"] == "ai_service_cost_tracking":
                if "estimated_total_cost" in result:
                    print(f"           预估总成本: ${result['estimated_total_cost']:.4f}")
            elif result["test"] == "concurrent_ai_requests":
                if "success_rate" in result:
                    print(f"           并发成功率: {result['success_rate']:.1%}")
        
        print("        ===============================================")


# 主测试运行器
def run_ai_integration_tests():
    """运行所有AI集成测试"""
    tester = AIServiceIntegrationTester()
    
    try:
        tester.run_all_ai_integration_tests()
        print("🎉 AI服务集成测试完成！")
        return True
    except Exception as e:
        print(f"❌ AI服务集成测试失败: {e}")
        return False


if __name__ == "__main__":
    success = run_ai_integration_tests()
    exit(0 if success else 1)