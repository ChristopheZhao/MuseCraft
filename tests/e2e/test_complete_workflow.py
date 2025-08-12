"""
端到端工作流测试套件
测试完整的用户输入 → 多智能体处理 → 视频输出流程
"""

import pytest
import asyncio
import websockets
import json
import time
from typing import Dict, Any, List
from unittest.mock import Mock, patch
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class E2EWorkflowTester:
    """端到端工作流测试器"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.ws_url = "ws://localhost:8000/api/v1/ws"
        self.session = self._create_session()
        self.test_results = []
        
    def _create_session(self):
        """创建带重试机制的HTTP会话"""
        session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session
    
    async def test_complete_video_generation_workflow(self):
        """测试完整的视频生成工作流"""
        print("🚀 开始端到端工作流测试...")
        
        # 测试用例数据
        test_input = {
            "description": "创建一个关于人工智能未来发展的30秒科技风格短视频",
            "style": "tech",
            "duration": 30,
            "aspect_ratio": "16:9",
            "voice_settings": {
                "voice_type": "professional",
                "speed": 1.0
            },
            "music_settings": {
                "genre": "electronic",
                "volume": 0.3
            }
        }
        
        # 1. 创建任务
        task_id = await self._test_task_creation(test_input)
        
        # 2. 监控智能体协作
        agent_results = await self._test_agent_collaboration(task_id)
        
        # 3. 验证中间结果
        await self._test_intermediate_results(task_id, agent_results)
        
        # 4. 验证最终输出
        await self._test_final_output(task_id)
        
        # 5. 生成测试报告
        self._generate_test_report()
        
        return True
    
    async def _test_task_creation(self, test_input: Dict[str, Any]) -> str:
        """测试任务创建过程"""
        print("📝 测试任务创建...")
        
        response = self.session.post(
            f"{self.base_url}/api/v1/tasks/",
            json=test_input,
            timeout=30
        )
        
        assert response.status_code == 201, f"任务创建失败: {response.text}"
        
        task_data = response.json()
        task_id = task_data["id"]
        
        assert task_data["status"] == "pending", "任务初始状态不正确"
        assert task_data["progress"] == 0, "任务初始进度不正确"
        
        self.test_results.append({
            "test": "task_creation",
            "status": "passed",
            "task_id": task_id,
            "response_time": response.elapsed.total_seconds()
        })
        
        print(f"✅ 任务创建成功: {task_id}")
        return task_id
    
    async def _test_agent_collaboration(self, task_id: str) -> Dict[str, Any]:
        """测试智能体协作过程"""
        print("🤖 测试智能体协作...")
        
        agent_results = {}
        agent_execution_times = {}
        websocket_messages = []
        
        # 通过WebSocket监控实时状态
        try:
            async with websockets.connect(f"{self.ws_url}/{task_id}") as websocket:
                start_time = time.time()
                timeout_duration = 300  # 5分钟超时
                
                while time.time() - start_time < timeout_duration:
                    try:
                        message = await asyncio.wait_for(
                            websocket.recv(), 
                            timeout=10.0
                        )
                        
                        data = json.loads(message)
                        websocket_messages.append(data)
                        
                        print(f"📡 WebSocket消息: {data.get('type', 'unknown')}")
                        
                        # 记录智能体执行结果
                        if data.get("type") == "agent_completed":
                            agent_name = data.get("agent")
                            agent_results[agent_name] = data.get("result")
                            agent_execution_times[agent_name] = data.get("execution_time", 0)
                        
                        # 检查是否完成
                        if data.get("type") == "task_completed":
                            break
                            
                        # 检查是否出错
                        if data.get("type") == "task_failed":
                            raise Exception(f"任务失败: {data.get('error')}")
                            
                    except asyncio.TimeoutError:
                        # 检查任务状态
                        status_response = self.session.get(f"{self.base_url}/api/v1/tasks/{task_id}")
                        if status_response.status_code == 200:
                            task_status = status_response.json()
                            if task_status["status"] in ["completed", "failed"]:
                                break
                        continue
                
        except Exception as e:
            print(f"❌ WebSocket连接错误: {e}")
            raise
        
        # 验证智能体执行结果
        expected_agents = [
            "concept_planner", "script_writer", "image_generator",
            "video_generator", "video_composer", "quality_checker"
        ]
        
        for agent in expected_agents:
            assert agent in agent_results, f"智能体 {agent} 未执行"
            assert agent_results[agent] is not None, f"智能体 {agent} 结果为空"
        
        self.test_results.append({
            "test": "agent_collaboration",
            "status": "passed",
            "agent_count": len(agent_results),
            "total_execution_time": sum(agent_execution_times.values()),
            "websocket_messages": len(websocket_messages)
        })
        
        print(f"✅ 智能体协作完成，执行了 {len(agent_results)} 个智能体")
        return agent_results
    
    async def _test_intermediate_results(self, task_id: str, agent_results: Dict[str, Any]):
        """验证中间结果的质量和完整性"""
        print("🔍 验证中间结果...")
        
        # 获取任务详细信息
        response = self.session.get(f"{self.base_url}/api/v1/tasks/{task_id}")
        assert response.status_code == 200
        
        task_data = response.json()
        scenes = task_data.get("scenes", [])
        
        # 验证概念规划结果
        concept_result = agent_results.get("concept_planner", {})
        assert "theme" in concept_result, "概念规划缺少主题"
        assert "style_guide" in concept_result, "概念规划缺少风格指南"
        assert "target_audience" in concept_result, "概念规划缺少目标受众"
        
        # 验证脚本编写结果
        script_result = agent_results.get("script_writer", {})
        assert "scenes" in script_result, "脚本编写缺少场景"
        assert len(script_result["scenes"]) > 0, "脚本场景为空"
        
        # 验证图像生成结果
        image_result = agent_results.get("image_generator", {})
        assert "generated_images" in image_result, "图像生成结果缺少图像"
        
        # 验证生成的图像文件
        for scene in scenes:
            if scene.get("image_urls"):
                for image_url in scene["image_urls"]:
                    image_response = self.session.head(image_url)
                    assert image_response.status_code == 200, f"图像文件不可访问: {image_url}"
        
        # 验证视频生成结果
        video_result = agent_results.get("video_generator", {})
        assert "generated_videos" in video_result, "视频生成结果缺少视频"
        
        self.test_results.append({
            "test": "intermediate_results",
            "status": "passed",
            "scenes_count": len(scenes),
            "concept_quality": len(concept_result),
            "script_quality": len(script_result.get("scenes", [])),
            "images_generated": len(image_result.get("generated_images", [])),
            "videos_generated": len(video_result.get("generated_videos", []))
        })
        
        print("✅ 中间结果验证通过")
    
    async def _test_final_output(self, task_id: str):
        """验证最终视频输出"""
        print("🎬 验证最终视频输出...")
        
        # 获取最终任务状态
        response = self.session.get(f"{self.base_url}/api/v1/tasks/{task_id}")
        assert response.status_code == 200
        
        task_data = response.json()
        assert task_data["status"] == "completed", "任务未完成"
        assert task_data["progress"] == 100, "任务进度不是100%"
        
        # 验证最终视频文件
        final_video_url = task_data.get("result", {}).get("final_video_url")
        assert final_video_url, "最终视频URL为空"
        
        # 检查视频文件可访问性
        video_response = self.session.head(final_video_url)
        assert video_response.status_code == 200, "最终视频文件不可访问"
        
        # 验证视频元数据
        video_metadata = task_data.get("result", {}).get("metadata", {})
        assert video_metadata.get("duration") > 0, "视频时长无效"
        assert video_metadata.get("resolution"), "视频分辨率缺失"
        assert video_metadata.get("file_size") > 0, "视频文件大小无效"
        
        self.test_results.append({
            "test": "final_output",
            "status": "passed",
            "video_duration": video_metadata.get("duration"),
            "video_resolution": video_metadata.get("resolution"),
            "file_size_mb": video_metadata.get("file_size", 0) / (1024 * 1024)
        })
        
        print("✅ 最终视频输出验证通过")
    
    def _generate_test_report(self):
        """生成测试报告"""
        print("\n📊 生成测试报告...")
        
        passed_tests = sum(1 for result in self.test_results if result["status"] == "passed")
        total_tests = len(self.test_results)
        
        print(f"""
        =================== 端到端测试报告 ===================
        总测试数: {total_tests}
        通过测试: {passed_tests}
        失败测试: {total_tests - passed_tests}
        成功率: {(passed_tests / total_tests * 100):.1f}%
        
        详细结果:
        """)
        
        for result in self.test_results:
            status_icon = "✅" if result["status"] == "passed" else "❌"
            print(f"        {status_icon} {result['test']}: {result['status']}")
            
            # 显示关键指标
            if result["test"] == "task_creation":
                print(f"           响应时间: {result['response_time']:.2f}秒")
            elif result["test"] == "agent_collaboration":
                print(f"           智能体数量: {result['agent_count']}")
                print(f"           总执行时间: {result['total_execution_time']:.2f}秒")
            elif result["test"] == "final_output":
                print(f"           视频时长: {result['video_duration']:.1f}秒")
                print(f"           文件大小: {result['file_size_mb']:.1f}MB")
        
        print("        ===============================================")


class MockAIServiceTester:
    """模拟AI服务测试器（用于测试环境）"""
    
    @staticmethod
    def mock_openai_response():
        return {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "theme": "AI未来发展",
                        "style_guide": {"color_scheme": "blue_tech", "mood": "optimistic"},
                        "scenes": [
                            {"description": "AI芯片特写", "duration": 10},
                            {"description": "数据流动画", "duration": 10},
                            {"description": "未来城市", "duration": 10}
                        ]
                    })
                }
            }]
        }
    
    @staticmethod
    def mock_dalle_response():
        return {
            "data": [{
                "url": "https://example.com/generated_image_1.png"
            }]
        }
    
    @staticmethod
    def mock_runway_response():
        return {
            "video_url": "https://example.com/generated_video_1.mp4",
            "status": "completed"
        }


# 测试运行器
async def run_e2e_tests():
    """运行端到端测试"""
    tester = E2EWorkflowTester()
    
    try:
        # 运行完整工作流测试
        await tester.test_complete_video_generation_workflow()
        print("🎉 所有端到端测试通过！")
        return True
        
    except Exception as e:
        print(f"❌ 端到端测试失败: {e}")
        return False


if __name__ == "__main__":
    # 运行测试
    success = asyncio.run(run_e2e_tests())
    exit(0 if success else 1)