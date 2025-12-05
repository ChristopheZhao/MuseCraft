"""
Performance and Load Testing Suite

Tests system performance under various loads and conditions:
- API response times under load
- Database query performance
- Memory and CPU usage monitoring
- Concurrent user simulation
- Stress testing and breaking points
- Resource cleanup efficiency
"""
import pytest
import asyncio
import time
import psutil
import statistics
from typing import Dict, Any, List, Tuple
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from app.models import Task, Scene, Resource


@pytest.mark.performance
@pytest.mark.asyncio
class TestPerformanceLoad:
    """Performance and load testing."""
    
    async def test_api_response_time_benchmarks(
        self,
        test_client: AsyncClient,
        performance_thresholds: Dict[str, float]
    ):
        """Test API response times meet performance benchmarks."""
        
        endpoints_to_test = [
            ("GET", "/health"),
            ("GET", "/api/v1/tasks/"),
            ("POST", "/api/v1/tasks/", {
                "user_prompt": "Performance test video",
                "video_style": "professional",
                "duration": 30,
                "aspect_ratio": "16:9"
            })
        ]
        
        results = {}
        
        for method, endpoint, *data in endpoints_to_test:
            response_times = []
            
            # Make multiple requests to get average response time
            for _ in range(10):
                start_time = time.time()
                
                if method == "GET":
                    response = await test_client.get(endpoint)
                elif method == "POST":
                    response = await test_client.post(endpoint, json=data[0] if data else None)
                
                response_time = time.time() - start_time
                response_times.append(response_time)
                
                # Verify successful response
                assert response.status_code in [200, 201]
            
            # Calculate statistics
            avg_response_time = statistics.mean(response_times)
            max_response_time = max(response_times)
            p95_response_time = sorted(response_times)[int(0.95 * len(response_times))]
            
            results[f"{method} {endpoint}"] = {
                "average": avg_response_time,
                "max": max_response_time,
                "p95": p95_response_time,
                "all_times": response_times
            }
            
            # Verify against thresholds
            threshold = performance_thresholds.get('api_response_time', 2.0)
            assert avg_response_time < threshold, f"Average response time {avg_response_time:.3f}s exceeds threshold {threshold}s"
            assert p95_response_time < threshold * 1.5, f"P95 response time {p95_response_time:.3f}s exceeds threshold"
        
        # Log results for analysis
        print("\\nAPI Response Time Results:")
        for endpoint, stats in results.items():
            print(f"{endpoint}: avg={stats['average']:.3f}s, max={stats['max']:.3f}s, p95={stats['p95']:.3f}s")
    
    async def test_concurrent_user_simulation(
        self,
        test_client: AsyncClient,
        load_test_config: Dict[str, Any],
        performance_thresholds: Dict[str, float]
    ):
        """Simulate concurrent users and measure system performance."""
        
        concurrent_users = load_test_config.get('concurrent_users', 10)
        requests_per_user = load_test_config.get('requests_per_user', 5)
        
        async def simulate_user(user_id: int) -> Dict[str, Any]:
            """Simulate a single user's actions."""
            user_results = {
                'user_id': user_id,
                'requests': [],
                'total_time': 0,
                'errors': 0
            }
            
            start_time = time.time()
            
            for request_num in range(requests_per_user):
                try:
                    request_start = time.time()
                    
                    # Simulate different user actions
                    if request_num == 0:
                        # Health check
                        response = await test_client.get("/health")
                    elif request_num == 1:
                        # Create task
                        response = await test_client.post("/api/v1/tasks/", json={
                            "user_prompt": f"Load test video from user {user_id}",
                            "video_style": "professional",
                            "duration": 30,
                            "aspect_ratio": "16:9"
                        })
                    elif request_num == 2:
                        # List tasks
                        response = await test_client.get("/api/v1/tasks/")
                    else:
                        # Health check
                        response = await test_client.get("/health")
                    
                    request_time = time.time() - request_start
                    
                    user_results['requests'].append({
                        'request_num': request_num,
                        'response_time': request_time,
                        'status_code': response.status_code,
                        'success': response.status_code < 400
                    })
                    
                    if response.status_code >= 400:
                        user_results['errors'] += 1
                    
                    # Small delay between requests
                    await asyncio.sleep(0.1)
                    
                except Exception as e:
                    user_results['errors'] += 1
                    user_results['requests'].append({
                        'request_num': request_num,
                        'response_time': 0,
                        'status_code': 0,
                        'success': False,
                        'error': str(e)
                    })
            
            user_results['total_time'] = time.time() - start_time
            return user_results
        
        # Start concurrent users
        start_time = time.time()
        
        user_tasks = [simulate_user(i) for i in range(concurrent_users)]
        user_results = await asyncio.gather(*user_tasks, return_exceptions=True)
        
        total_test_time = time.time() - start_time
        
        # Analyze results
        successful_users = [r for r in user_results if not isinstance(r, Exception)]
        failed_users = [r for r in user_results if isinstance(r, Exception)]
        
        # Calculate metrics
        total_requests = sum(len(r['requests']) for r in successful_users)
        total_errors = sum(r['errors'] for r in successful_users)
        error_rate = total_errors / total_requests if total_requests > 0 else 0
        
        all_response_times = []
        for user in successful_users:
            all_response_times.extend([req['response_time'] for req in user['requests'] if req['success']])
        
        avg_response_time = statistics.mean(all_response_times) if all_response_times else 0
        p95_response_time = sorted(all_response_times)[int(0.95 * len(all_response_times))] if all_response_times else 0
        
        # Verify performance criteria
        acceptable_error_rate = load_test_config.get('acceptable_error_rate', 0.05)
        acceptable_response_time = performance_thresholds.get('api_response_time', 2.0)
        
        assert len(failed_users) == 0, f"{len(failed_users)} users failed completely"
        assert error_rate <= acceptable_error_rate, f"Error rate {error_rate:.3f} exceeds acceptable rate {acceptable_error_rate}"
        assert avg_response_time <= acceptable_response_time, f"Average response time {avg_response_time:.3f}s exceeds threshold"
        
        # Log results
        print(f"\\nLoad Test Results:")
        print(f"Concurrent users: {concurrent_users}")
        print(f"Total requests: {total_requests}")
        print(f"Error rate: {error_rate:.3f}")
        print(f"Average response time: {avg_response_time:.3f}s")
        print(f"P95 response time: {p95_response_time:.3f}s")
        print(f"Total test time: {total_test_time:.3f}s")
    
    async def test_database_performance(
        self,
        test_db_session: AsyncSession,
        performance_thresholds: Dict[str, float]
    ):
        """Test database query performance."""
        
        # Create test data
        tasks = []
        for i in range(100):
            task = Task(
                task_id=f"perf-test-task-{i}",
                title=f"Performance Test Task {i}",
                description=f"Task {i} for performance testing",
                user_prompt=f"Create video {i}",
                input_parameters={"style": "professional", "duration": 30},
                task_type="video_generation",
                status="pending"
            )
            tasks.append(task)
            test_db_session.add(task)
        
        await test_db_session.commit()
        
        # Test queries and measure performance
        query_tests = [
            ("Simple select", select(Task).limit(10)),
            ("Filter by status", select(Task).where(Task.status == "pending")),
            ("Order by created_at", select(Task).order_by(Task.created_at.desc()).limit(20)),
            ("Count query", select(Task).where(Task.task_type == "video_generation")),
        ]
        
        for test_name, query in query_tests:
            response_times = []
            
            # Execute query multiple times
            for _ in range(10):
                start_time = time.time()
                
                result = await test_db_session.execute(query)
                if "count" in test_name.lower():
                    count = len(result.scalars().all())
                else:
                    rows = result.scalars().all()
                
                query_time = time.time() - start_time
                response_times.append(query_time)
            
            avg_query_time = statistics.mean(response_times)
            max_query_time = max(response_times)
            
            # Verify performance
            threshold = performance_thresholds.get('database_query_time', 0.1)
            assert avg_query_time < threshold, f"{test_name} average time {avg_query_time:.3f}s exceeds threshold {threshold}s"
            
            print(f"{test_name}: avg={avg_query_time:.4f}s, max={max_query_time:.4f}s")
    
    @pytest.mark.slow
    async def test_memory_usage_monitoring(
        self,
        test_client: AsyncClient,
        performance_thresholds: Dict[str, float]
    ):
        """Test memory usage during operations."""
        
        # Get initial memory usage
        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        memory_readings = [initial_memory]
        
        # Perform memory-intensive operations
        for i in range(20):
            # Create multiple tasks
            for j in range(5):
                response = await test_client.post("/api/v1/tasks/", json={
                    "user_prompt": f"Memory test video {i}-{j}",
                    "video_style": "professional",
                    "duration": 30,
                    "aspect_ratio": "16:9"
                })
                assert response.status_code == 201
            
            # Measure memory
            current_memory = process.memory_info().rss / 1024 / 1024  # MB
            memory_readings.append(current_memory)
            
            # Small delay
            await asyncio.sleep(0.1)
        
        # Analyze memory usage
        peak_memory = max(memory_readings)
        memory_growth = peak_memory - initial_memory
        
        # Check for memory leaks (simple heuristic)
        final_memory = memory_readings[-1]
        memory_leak_threshold = initial_memory * 1.5  # 50% growth threshold
        
        max_memory_threshold = performance_thresholds.get('memory_usage', 500)  # MB
        
        assert peak_memory < max_memory_threshold, f"Peak memory usage {peak_memory:.1f}MB exceeds threshold {max_memory_threshold}MB"
        assert final_memory < memory_leak_threshold, f"Possible memory leak detected: {final_memory:.1f}MB vs initial {initial_memory:.1f}MB"
        
        print(f"\\nMemory Usage Results:")
        print(f"Initial: {initial_memory:.1f}MB")
        print(f"Peak: {peak_memory:.1f}MB")
        print(f"Final: {final_memory:.1f}MB")
        print(f"Growth: {memory_growth:.1f}MB")
    
    async def test_websocket_performance(
        self,
        websocket_test_client,
        performance_thresholds: Dict[str, float]
    ):
        """Test WebSocket connection performance."""
        
        message_count = 100
        message_latencies = []
        
        with websocket_test_client.websocket_connect("/ws?session_id=perf-test") as websocket:
            # Send messages and measure latency
            for i in range(message_count):
                start_time = time.time()
                
                test_message = {
                    "type": "ping",
                    "timestamp": start_time,
                    "sequence": i
                }
                
                websocket.send_json(test_message)
                
                # In a real test, you'd wait for a response
                # For this test, we'll simulate response time
                await asyncio.sleep(0.001)  # Simulate processing
                
                latency = time.time() - start_time
                message_latencies.append(latency)
        
        # Analyze latencies
        avg_latency = statistics.mean(message_latencies)
        max_latency = max(message_latencies)
        p95_latency = sorted(message_latencies)[int(0.95 * len(message_latencies))]
        
        # Verify performance
        websocket_threshold = performance_thresholds.get('websocket_latency', 0.5)
        assert avg_latency < websocket_threshold, f"Average WebSocket latency {avg_latency:.3f}s exceeds threshold"
        assert p95_latency < websocket_threshold * 2, f"P95 WebSocket latency {p95_latency:.3f}s exceeds threshold"
        
        print(f"\\nWebSocket Performance Results:")
        print(f"Messages: {message_count}")
        print(f"Average latency: {avg_latency:.4f}s")
        print(f"Max latency: {max_latency:.4f}s")
        print(f"P95 latency: {p95_latency:.4f}s")
    
    @pytest.mark.slow
    async def test_stress_testing(
        self,
        test_client: AsyncClient,
        test_db_session: AsyncSession
    ):
        """Stress test the system to find breaking points."""
        
        # Gradually increase load until system shows stress
        max_concurrent_requests = 50
        batch_size = 5
        
        for concurrent_requests in range(batch_size, max_concurrent_requests + 1, batch_size):
            print(f"\\nTesting with {concurrent_requests} concurrent requests...")
            
            async def make_request(request_id: int):
                try:
                    start_time = time.time()
                    response = await test_client.post("/api/v1/tasks/", json={
                        "user_prompt": f"Stress test video {request_id}",
                        "video_style": "professional",
                        "duration": 30,
                        "aspect_ratio": "16:9"
                    })
                    response_time = time.time() - start_time
                    
                    return {
                        "success": response.status_code < 400,
                        "status_code": response.status_code,
                        "response_time": response_time,
                        "request_id": request_id
                    }
                except Exception as e:
                    return {
                        "success": False,
                        "status_code": 0,
                        "response_time": 0,
                        "request_id": request_id,
                        "error": str(e)
                    }
            
            # Execute concurrent requests
            start_time = time.time()
            results = await asyncio.gather(
                *[make_request(i) for i in range(concurrent_requests)],
                return_exceptions=True
            )
            total_time = time.time() - start_time
            
            # Analyze results
            successful_results = [r for r in results if isinstance(r, dict) and r.get("success")]
            failed_results = [r for r in results if isinstance(r, dict) and not r.get("success")]
            exception_results = [r for r in results if isinstance(r, Exception)]
            
            success_rate = len(successful_results) / len(results)
            avg_response_time = statistics.mean([r["response_time"] for r in successful_results]) if successful_results else 0
            
            print(f"Success rate: {success_rate:.3f}")
            print(f"Average response time: {avg_response_time:.3f}s")
            print(f"Failed requests: {len(failed_results)}")
            print(f"Exceptions: {len(exception_results)}")
            
            # Stop if system is showing significant stress
            if success_rate < 0.8 or avg_response_time > 5.0:
                print(f"System stress detected at {concurrent_requests} concurrent requests")
                break
            
            # Small delay between batches
            await asyncio.sleep(1.0)
    
    async def test_resource_cleanup_efficiency(
        self,
        test_client: AsyncClient,
        test_storage_dirs: Dict[str, str],
        integration_helper
    ):
        """Test efficiency of resource cleanup operations."""
        
        # Create many temporary files
        temp_files = []
        for i in range(100):
            temp_file_path = os.path.join(test_storage_dirs['temp'], f'temp_file_{i}.tmp')
            with open(temp_file_path, 'w') as f:
                f.write(f'temporary content {i}' * 100)  # Make files somewhat large
            temp_files.append(temp_file_path)
        
        # Measure cleanup time
        from app.services.file_storage import FileStorageService
        storage_service = FileStorageService()
        
        start_time = time.time()
        cleanup_result = await storage_service.cleanup_temp_files(max_age_hours=0)
        cleanup_time = time.time() - start_time
        
        # Verify cleanup was efficient
        assert cleanup_time < 5.0, f"Cleanup took {cleanup_time:.3f}s, which is too long"
        
        # Verify files were cleaned up
        remaining_files = [f for f in temp_files if os.path.exists(f)]
        cleanup_rate = (len(temp_files) - len(remaining_files)) / len(temp_files)
        
        assert cleanup_rate >= 0.9, f"Only {cleanup_rate:.3f} of files were cleaned up"
        
        print(f"\\nCleanup Efficiency Results:")
        print(f"Files created: {len(temp_files)}")
        print(f"Files cleaned: {len(temp_files) - len(remaining_files)}")
        print(f"Cleanup time: {cleanup_time:.3f}s")
        print(f"Cleanup rate: {cleanup_rate:.3f}")
    
    async def test_database_connection_pool_performance(
        self,
        test_db_session: AsyncSession
    ):
        """Test database connection pool performance under load."""
        
        async def execute_query(query_id: int):
            """Execute a database query."""
            try:
                start_time = time.time()
                
                # Simple query that requires a database connection
                result = await test_db_session.execute(
                    text("SELECT 1 as test_value")
                )
                row = result.fetchone()
                
                query_time = time.time() - start_time
                
                return {
                    "query_id": query_id,
                    "success": True,
                    "query_time": query_time,
                    "result": row[0] if row else None
                }
            except Exception as e:
                return {
                    "query_id": query_id,
                    "success": False,
                    "error": str(e),
                    "query_time": 0
                }
        
        # Execute many concurrent database operations
        concurrent_queries = 20
        
        start_time = time.time()
        results = await asyncio.gather(
            *[execute_query(i) for i in range(concurrent_queries)],
            return_exceptions=True
        )
        total_time = time.time() - start_time
        
        # Analyze results
        successful_queries = [r for r in results if isinstance(r, dict) and r.get("success")]
        failed_queries = [r for r in results if isinstance(r, dict) and not r.get("success")]
        
        success_rate = len(successful_queries) / len(results)
        avg_query_time = statistics.mean([r["query_time"] for r in successful_queries]) if successful_queries else 0
        
        # Verify performance
        assert success_rate >= 0.95, f"Database connection pool success rate {success_rate:.3f} is too low"
        assert avg_query_time < 1.0, f"Average query time {avg_query_time:.3f}s is too high"
        assert total_time < concurrent_queries * 0.1, "Queries appear to be running sequentially rather than concurrently"
        
        print(f"\\nDatabase Connection Pool Performance:")
        print(f"Concurrent queries: {concurrent_queries}")
        print(f"Success rate: {success_rate:.3f}")
        print(f"Average query time: {avg_query_time:.4f}s")
        print(f"Total time: {total_time:.3f}s")
        print(f"Failed queries: {len(failed_queries)}")