"""
Performance Benchmark Test Suite

This module provides comprehensive performance testing including load testing,
stress testing, and performance regression detection for the video generation platform.
"""
import asyncio
import time
import statistics
import psutil
import pytest
from typing import Dict, List, Any, Tuple
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from concurrent.futures import ThreadPoolExecutor
import numpy as np

from app.models import Task, TaskStatus
from app.services.monitoring_service import monitoring_service


@pytest.mark.performance
@pytest.mark.asyncio
class TestPerformanceBenchmarks:
    """Performance benchmark tests."""
    
    async def test_api_response_time_benchmarks(
        self,
        test_client: AsyncClient,
        performance_thresholds: Dict[str, float]
    ):
        """Benchmark API response times under various loads."""
        
        endpoints_to_test = [
            ("GET", "/api/v1/tasks/"),
            ("POST", "/api/v1/tasks/", {
                "user_prompt": "Benchmark test video",
                "video_style": "professional",
                "duration": 30
            }),
            ("GET", "/api/v1/files/"),
            ("GET", "/api/v1/system/health")
        ]
        
        benchmark_results = {}
        
        for method, endpoint, *payload in endpoints_to_test:
            response_times = []
            
            # Warm-up requests
            for _ in range(5):
                if method == "GET":
                    await test_client.get(endpoint)
                else:
                    await test_client.post(endpoint, json=payload[0] if payload else {})
            
            # Benchmark requests
            for _ in range(50):
                start_time = time.time()
                
                if method == "GET":
                    response = await test_client.get(endpoint)
                else:
                    response = await test_client.post(endpoint, json=payload[0] if payload else {})
                
                end_time = time.time()
                response_time = end_time - start_time
                
                if response.status_code < 500:  # Only count successful requests
                    response_times.append(response_time)
            
            # Calculate statistics
            if response_times:
                benchmark_results[f"{method} {endpoint}"] = {
                    "mean": statistics.mean(response_times),
                    "median": statistics.median(response_times),
                    "p95": np.percentile(response_times, 95),
                    "p99": np.percentile(response_times, 99),
                    "min": min(response_times),
                    "max": max(response_times),
                    "std_dev": statistics.stdev(response_times) if len(response_times) > 1 else 0
                }
        
        # Verify against thresholds
        acceptable_mean_time = performance_thresholds.get("api_response_time", 2.0)
        
        for endpoint, metrics in benchmark_results.items():
            assert metrics["mean"] < acceptable_mean_time, f"{endpoint} mean response time {metrics['mean']:.3f}s exceeds threshold {acceptable_mean_time}s"
            assert metrics["p95"] < acceptable_mean_time * 2, f"{endpoint} P95 response time {metrics['p95']:.3f}s exceeds threshold"
        
        return benchmark_results
    
    async def test_concurrent_request_performance(
        self,
        test_client: AsyncClient,
        load_test_config: Dict[str, Any]
    ):
        """Test performance under concurrent load."""
        
        concurrent_users = load_test_config["concurrent_users"]
        requests_per_user = load_test_config["requests_per_user"]
        
        async def user_simulation(user_id: int) -> Dict[str, Any]:
            """Simulate a single user's request pattern."""
            user_metrics = {
                "user_id": user_id,
                "requests_completed": 0,
                "total_response_time": 0,
                "errors": 0,
                "response_times": []
            }
            
            for request_num in range(requests_per_user):
                try:
                    start_time = time.time()
                    
                    # Simulate realistic user behavior
                    if request_num % 3 == 0:
                        # Create new task
                        response = await test_client.post("/api/v1/tasks/", json={
                            "user_prompt": f"Load test video from user {user_id}",
                            "video_style": "professional", 
                            "duration": 30
                        })
                    elif request_num % 3 == 1:
                        # Check task status
                        response = await test_client.get("/api/v1/tasks/")
                    else:
                        # Get system health
                        response = await test_client.get("/api/v1/system/health")
                    
                    end_time = time.time()
                    response_time = end_time - start_time
                    
                    user_metrics["response_times"].append(response_time)
                    user_metrics["total_response_time"] += response_time
                    
                    if response.status_code >= 400:
                        user_metrics["errors"] += 1
                    else:
                        user_metrics["requests_completed"] += 1
                    
                    # Small delay between requests
                    await asyncio.sleep(0.1)
                    
                except Exception as e:
                    user_metrics["errors"] += 1
            
            return user_metrics
        
        # Execute concurrent user simulations
        start_time = time.time()
        
        user_tasks = [
            user_simulation(i) for i in range(concurrent_users)
        ]
        
        user_results = await asyncio.gather(*user_tasks, return_exceptions=True)
        
        end_time = time.time()
        total_test_time = end_time - start_time
        
        # Aggregate results
        successful_users = [r for r in user_results if not isinstance(r, Exception)]
        
        total_requests = sum(user["requests_completed"] for user in successful_users)
        total_errors = sum(user["errors"] for user in successful_users)
        all_response_times = []
        
        for user in successful_users:
            all_response_times.extend(user["response_times"])
        
        # Calculate performance metrics
        error_rate = total_errors / (total_requests + total_errors) if (total_requests + total_errors) > 0 else 0
        throughput = total_requests / total_test_time
        
        performance_results = {
            "concurrent_users": concurrent_users,
            "total_requests": total_requests,
            "total_errors": total_errors,
            "error_rate": error_rate,
            "throughput_rps": throughput,
            "test_duration": total_test_time,
            "avg_response_time": statistics.mean(all_response_times) if all_response_times else 0,
            "p95_response_time": np.percentile(all_response_times, 95) if all_response_times else 0
        }
        
        # Verify performance criteria
        acceptable_error_rate = load_test_config.get("acceptable_error_rate", 0.05)
        acceptable_response_time = load_test_config.get("acceptable_response_time", 2.0)
        
        assert error_rate <= acceptable_error_rate, f"Error rate {error_rate:.3f} exceeds acceptable rate {acceptable_error_rate}"
        assert performance_results["avg_response_time"] <= acceptable_response_time, f"Average response time {performance_results['avg_response_time']:.3f}s exceeds threshold"
        
        return performance_results
    
    async def test_workflow_execution_performance(
        self,
        test_client: AsyncClient,
        test_db_session: AsyncSession,
        mock_ai_services: Dict[str, AsyncMock],
        performance_thresholds: Dict[str, float]
    ):
        """Test video generation workflow performance."""
        
        # Configure AI services for performance testing
        self._setup_performance_ai_mocks(mock_ai_services)
        
        workflow_scenarios = [
            {
                "name": "simple_professional",
                "request": {
                    "user_prompt": "Create a simple professional video",
                    "video_style": "professional",
                    "duration": 30,
                    "aspect_ratio": "16:9"
                },
                "expected_max_time": 60
            },
            {
                "name": "complex_creative",
                "request": {
                    "user_prompt": "Create a complex creative video with multiple scenes",
                    "video_style": "creative",
                    "duration": 120,
                    "aspect_ratio": "16:9",
                    "scene_count": 5
                },
                "expected_max_time": 180
            },
            {
                "name": "high_quality_cinematic",
                "request": {
                    "user_prompt": "Create a high-quality cinematic video",
                    "video_style": "cinematic",
                    "duration": 90,
                    "quality_level": "high",
                    "include_subtitles": True
                },
                "expected_max_time": 240
            }
        ]
        
        performance_results = {}
        
        for scenario in workflow_scenarios:
            scenario_results = []
            
            # Run multiple iterations for statistical significance
            for iteration in range(3):
                start_time = time.time()
                
                # Submit task
                response = await test_client.post("/api/v1/tasks/", json=scenario["request"])
                assert response.status_code == 201
                
                task_data = response.json()
                task_id = task_data["task_id"]
                
                # Execute workflow
                from app.agents.enhanced_orchestrator import EnhancedOrchestratorAgent
                orchestrator = EnhancedOrchestratorAgent()
                
                await orchestrator.execute(
                    task_id=task_id,
                    input_data=scenario["request"],
                    db=test_db_session
                )
                
                end_time = time.time()
                execution_time = end_time - start_time
                
                scenario_results.append({
                    "iteration": iteration,
                    "execution_time": execution_time,
                    "task_id": task_id
                })
                
                # Verify task completed
                stmt = select(Task).where(Task.task_id == task_id)
                result = await test_db_session.execute(stmt)
                task = result.scalar_one()
                assert task.status == TaskStatus.COMPLETED
            
            # Calculate scenario statistics
            execution_times = [r["execution_time"] for r in scenario_results]
            
            performance_results[scenario["name"]] = {
                "mean_execution_time": statistics.mean(execution_times),
                "min_execution_time": min(execution_times),
                "max_execution_time": max(execution_times),
                "std_dev": statistics.stdev(execution_times) if len(execution_times) > 1 else 0,
                "expected_max_time": scenario["expected_max_time"],
                "results": scenario_results
            }
            
            # Verify against expected performance
            assert max(execution_times) <= scenario["expected_max_time"], f"Scenario {scenario['name']} exceeded expected time"
        
        return performance_results
    
    async def test_system_resource_utilization(
        self,
        test_client: AsyncClient,
        performance_thresholds: Dict[str, float]
    ):
        """Test system resource utilization under load."""
        
        # Record baseline metrics
        baseline_metrics = self._get_system_metrics()
        
        # Generate load
        load_duration = 60  # seconds
        request_interval = 0.5  # seconds between requests
        
        metrics_history = []
        load_tasks = []
        
        async def generate_load():
            """Generate continuous load."""
            end_time = time.time() + load_duration
            
            while time.time() < end_time:
                try:
                    # Submit various types of requests
                    await test_client.post("/api/v1/tasks/", json={
                        "user_prompt": "Load test video",
                        "video_style": "professional",
                        "duration": 30
                    })
                    
                    await asyncio.sleep(request_interval)
                except Exception:
                    pass  # Continue load generation even if individual requests fail
        
        async def monitor_resources():
            """Monitor system resources during load test."""
            end_time = time.time() + load_duration
            
            while time.time() < end_time:
                metrics = self._get_system_metrics()
                metrics["timestamp"] = time.time()
                metrics_history.append(metrics)
                
                await asyncio.sleep(5)  # Sample every 5 seconds
        
        # Start load generation and monitoring
        await asyncio.gather(
            generate_load(),
            monitor_resources()
        )
        
        # Analyze resource utilization
        if metrics_history:
            cpu_usage = [m["cpu_percent"] for m in metrics_history]
            memory_usage = [m["memory_percent"] for m in metrics_history]
            disk_usage = [m["disk_percent"] for m in metrics_history]
            
            resource_analysis = {
                "baseline": baseline_metrics,
                "under_load": {
                    "cpu": {
                        "mean": statistics.mean(cpu_usage),
                        "max": max(cpu_usage),
                        "min": min(cpu_usage)
                    },
                    "memory": {
                        "mean": statistics.mean(memory_usage),
                        "max": max(memory_usage),
                        "min": min(memory_usage)
                    },
                    "disk": {
                        "mean": statistics.mean(disk_usage),
                        "max": max(disk_usage),
                        "min": min(disk_usage)
                    }
                },
                "samples": len(metrics_history)
            }
            
            # Verify resource usage within acceptable limits
            max_cpu_threshold = performance_thresholds.get("cpu_usage", 80)
            max_memory_threshold = performance_thresholds.get("memory_usage", 500)  # MB
            
            assert resource_analysis["under_load"]["cpu"]["max"] <= max_cpu_threshold, f"CPU usage exceeded threshold: {resource_analysis['under_load']['cpu']['max']}%"
            assert resource_analysis["under_load"]["memory"]["max"] <= max_memory_threshold, f"Memory usage exceeded threshold"
            
            return resource_analysis
    
    async def test_database_performance_under_load(
        self,
        test_db_session: AsyncSession,
        performance_thresholds: Dict[str, float]
    ):
        """Test database performance under concurrent operations."""
        
        # Test concurrent task creation
        concurrent_operations = 50
        
        async def create_task_batch(batch_id: int) -> List[float]:
            """Create a batch of tasks and measure query times."""
            query_times = []
            
            for i in range(10):  # 10 tasks per batch
                start_time = time.time()
                
                task = Task(
                    task_id=f"perf-test-{batch_id}-{i}",
                    title=f"Performance Test Task {batch_id}-{i}",
                    user_prompt="Performance test prompt",
                    status="pending"
                )
                
                test_db_session.add(task)
                await test_db_session.commit()
                
                end_time = time.time()
                query_times.append(end_time - start_time)
            
            return query_times
        
        # Execute concurrent database operations
        start_time = time.time()
        
        batch_tasks = [
            create_task_batch(i) for i in range(concurrent_operations // 10)
        ]
        
        batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # Analyze database performance
        successful_batches = [r for r in batch_results if not isinstance(r, Exception)]
        all_query_times = []
        
        for batch in successful_batches:
            all_query_times.extend(batch)
        
        if all_query_times:
            db_performance = {
                "total_operations": len(all_query_times),
                "total_time": total_time,
                "operations_per_second": len(all_query_times) / total_time,
                "avg_query_time": statistics.mean(all_query_times),
                "p95_query_time": np.percentile(all_query_times, 95),
                "max_query_time": max(all_query_times),
                "min_query_time": min(all_query_times)
            }
            
            # Verify against thresholds
            max_query_time = performance_thresholds.get("database_query_time", 0.1)
            assert db_performance["avg_query_time"] <= max_query_time, f"Average database query time {db_performance['avg_query_time']:.3f}s exceeds threshold"
            
            return db_performance
    
    async def test_websocket_performance(
        self,
        mock_websocket: MagicMock,
        performance_thresholds: Dict[str, float]
    ):
        """Test WebSocket performance and message delivery."""
        
        from app.services.websocket import websocket_manager
        
        session_id = "performance-test-session"
        websocket_manager.active_connections[session_id] = mock_websocket
        
        # Test message delivery performance
        message_counts = [10, 50, 100, 500]
        performance_results = {}
        
        for count in message_counts:
            mock_websocket.messages.clear()
            
            start_time = time.time()
            
            # Send messages rapidly
            for i in range(count):
                await websocket_manager.send_message(session_id, {
                    "type": "performance-test",
                    "message_id": i,
                    "data": f"Performance test message {i}"
                })
            
            end_time = time.time()
            delivery_time = end_time - start_time
            
            performance_results[f"{count}_messages"] = {
                "total_messages": count,
                "delivery_time": delivery_time,
                "messages_per_second": count / delivery_time,
                "avg_time_per_message": delivery_time / count,
                "messages_delivered": len(mock_websocket.messages)
            }
            
            # Verify all messages were delivered
            assert len(mock_websocket.messages) == count, f"Not all messages delivered for {count} message test"
        
        # Verify WebSocket latency threshold
        max_latency = performance_thresholds.get("websocket_latency", 0.5)
        
        for result in performance_results.values():
            assert result["avg_time_per_message"] <= max_latency, f"WebSocket message latency exceeded threshold"
        
        return performance_results
    
    # Helper methods
    
    def _setup_performance_ai_mocks(self, mock_ai_services: Dict[str, AsyncMock]):
        """Setup AI service mocks optimized for performance testing."""
        
        # Fast responses to simulate optimal AI service performance
        mock_ai_services['openai'].chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content="Fast AI response"))
        ]
        
        mock_ai_services['stability'].generate.return_value = MagicMock(
            artifacts=[MagicMock(seed=123, binary=b"fast_generated_image")]
        )
        
        # Add minimal delays to simulate realistic network latency
        async def add_realistic_delay(*args, **kwargs):
            await asyncio.sleep(0.1)  # 100ms simulated latency
            return mock_ai_services['openai'].chat.completions.create.return_value
        
        mock_ai_services['openai'].chat.completions.create.side_effect = add_realistic_delay
    
    def _get_system_metrics(self) -> Dict[str, float]:
        """Get current system performance metrics."""
        
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        return {
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "memory_percent": memory.percent,
            "memory_used_mb": memory.used / (1024 * 1024),
            "disk_percent": disk.percent,
            "disk_used_gb": disk.used / (1024 * 1024 * 1024)
        }


@pytest.mark.performance
@pytest.mark.load
@pytest.mark.asyncio
class TestLoadAndStressTesting:
    """Load and stress testing scenarios."""
    
    async def test_peak_load_simulation(
        self,
        test_client: AsyncClient,
        load_test_config: Dict[str, Any]
    ):
        """Simulate peak load conditions."""
        
        # Simulate Black Friday / high traffic scenario
        peak_concurrent_users = load_test_config["concurrent_users"] * 3
        peak_duration = 300  # 5 minutes
        
        async def peak_load_user(user_id: int) -> Dict[str, Any]:
            """Simulate high-frequency user during peak load."""
            user_metrics = {
                "requests": 0,
                "errors": 0,
                "total_time": 0
            }
            
            end_time = time.time() + peak_duration
            
            while time.time() < end_time:
                try:
                    start = time.time()
                    
                    # More aggressive request pattern
                    response = await test_client.post("/api/v1/tasks/", json={
                        "user_prompt": f"Peak load test {user_id}",
                        "video_style": "professional",
                        "duration": 30
                    })
                    
                    user_metrics["total_time"] += time.time() - start
                    user_metrics["requests"] += 1
                    
                    if response.status_code >= 400:
                        user_metrics["errors"] += 1
                    
                    # Shorter delay between requests during peak
                    await asyncio.sleep(0.05)
                    
                except Exception:
                    user_metrics["errors"] += 1
            
            return user_metrics
        
        # Execute peak load test
        start_time = time.time()
        
        peak_users = [
            peak_load_user(i) for i in range(peak_concurrent_users)
        ]
        
        results = await asyncio.gather(*peak_users, return_exceptions=True)
        
        end_time = time.time()
        
        # Analyze peak load results
        successful_results = [r for r in results if not isinstance(r, Exception)]
        
        total_requests = sum(r["requests"] for r in successful_results)
        total_errors = sum(r["errors"] for r in successful_results)
        
        peak_performance = {
            "peak_concurrent_users": peak_concurrent_users,
            "test_duration": end_time - start_time,
            "total_requests": total_requests,
            "total_errors": total_errors,
            "error_rate": total_errors / total_requests if total_requests > 0 else 0,
            "requests_per_second": total_requests / (end_time - start_time),
            "successful_users": len(successful_results)
        }
        
        # System should maintain at least 90% success rate under peak load
        assert peak_performance["error_rate"] <= 0.10, f"Error rate {peak_performance['error_rate']:.3f} too high under peak load"
        
        return peak_performance
    
    async def test_stress_testing_breaking_point(
        self,
        test_client: AsyncClient
    ):
        """Find system breaking point through progressive stress testing."""
        
        stress_levels = [10, 25, 50, 100, 200, 500]  # Concurrent users
        breaking_point_results = {}
        
        for stress_level in stress_levels:
            print(f"Testing stress level: {stress_level} concurrent users")
            
            # Test for 60 seconds at each stress level
            test_duration = 60
            
            async def stress_user(user_id: int) -> Dict[str, Any]:
                """Single user generating stress load."""
                metrics = {"requests": 0, "errors": 0}
                end_time = time.time() + test_duration
                
                while time.time() < end_time:
                    try:
                        response = await test_client.post("/api/v1/tasks/", json={
                            "user_prompt": f"Stress test {stress_level}-{user_id}",
                            "video_style": "professional",
                            "duration": 30
                        })
                        
                        metrics["requests"] += 1
                        if response.status_code >= 400:
                            metrics["errors"] += 1
                            
                    except Exception:
                        metrics["errors"] += 1
                    
                    await asyncio.sleep(0.1)  # 10 RPS per user
                
                return metrics
            
            # Execute stress test
            start_time = time.time()
            stress_users = [stress_user(i) for i in range(stress_level)]
            
            try:
                user_results = await asyncio.gather(*stress_users, return_exceptions=True)
                
                successful_users = [r for r in user_results if not isinstance(r, Exception)]
                total_requests = sum(u["requests"] for u in successful_users)
                total_errors = sum(u["errors"] for u in successful_users)
                
                error_rate = total_errors / total_requests if total_requests > 0 else 1.0
                
                breaking_point_results[stress_level] = {
                    "concurrent_users": stress_level,
                    "total_requests": total_requests,
                    "total_errors": total_errors,
                    "error_rate": error_rate,
                    "successful_users": len(successful_users),
                    "system_stable": error_rate < 0.5  # System considered stable if <50% error rate
                }
                
                # If error rate exceeds 50%, we've likely found the breaking point
                if error_rate >= 0.5:
                    breaking_point_results[stress_level]["breaking_point"] = True
                    break
                    
            except Exception as e:
                breaking_point_results[stress_level] = {
                    "concurrent_users": stress_level,
                    "system_failure": True,
                    "error": str(e)
                }
                break
        
        return breaking_point_results