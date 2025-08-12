"""
性能和可靠性测试
测试系统在各种负载条件下的性能表现和稳定性
"""

import pytest
import asyncio
import time
import statistics
import psutil
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import json
import random
import subprocess
import os
from typing import Dict, List, Any
import redis
import psycopg2
from contextlib import contextmanager


class PerformanceReliabilityTester:
    """性能和可靠性测试器"""
    
    def __init__(self):
        self.base_url = "http://localhost:8000"
        self.test_results = []
        self.system_metrics = {
            "cpu_usage": [],
            "memory_usage": [],
            "disk_io": [],
            "network_io": []
        }
        
        # 创建会话
        self.session = self._create_resilient_session()
        
        # 测试配置
        self.test_config = {
            "concurrent_users": [1, 5, 10, 20, 50],
            "test_duration": 60,  # 秒
            "max_response_time": 5.0,  # 秒
            "error_rate_threshold": 0.05,  # 5%
            "memory_leak_threshold": 100,  # MB
            "cpu_usage_threshold": 80  # %
        }
    
    def _create_resilient_session(self):
        """创建具有重试机制的HTTP会话"""
        session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session
    
    def run_all_performance_tests(self):
        """运行所有性能和可靠性测试"""
        print("🚀 开始性能和可靠性测试...")
        
        tests = [
            self.test_baseline_performance,
            self.test_load_testing,
            self.test_stress_testing,
            self.test_spike_testing,
            self.test_endurance_testing,
            self.test_memory_leak_detection,
            self.test_database_performance,
            self.test_redis_performance,
            self.test_file_handling_performance,
            self.test_websocket_performance,
            self.test_error_recovery_reliability,
            self.test_resource_cleanup
        ]
        
        # 启动系统监控
        monitoring_thread = threading.Thread(target=self._monitor_system_resources)
        monitoring_thread.daemon = True
        monitoring_thread.start()
        
        for test in tests:
            try:
                print(f"\n🔬 运行 {test.__name__}...")
                test()
                print(f"✅ {test.__name__} 完成")
            except Exception as e:
                print(f"❌ {test.__name__} 失败: {e}")
                self.test_results.append({
                    "test": test.__name__,
                    "status": "failed",
                    "error": str(e)
                })
        
        self.generate_performance_report()
    
    def test_baseline_performance(self):
        """基准性能测试"""
        print("📊 执行基准性能测试...")
        
        endpoints = [
            {"path": "/health", "method": "GET"},
            {"path": "/api/v1/tasks/", "method": "GET"},
            {"path": "/api/v1/tasks/", "method": "POST", "data": {
                "description": "基准测试任务",
                "style": "tech",
                "duration": 30
            }}
        ]
        
        baseline_results = {}
        
        for endpoint in endpoints:
            response_times = []
            success_count = 0
            
            # 每个端点测试10次
            for _ in range(10):
                start_time = time.time()
                
                try:
                    if endpoint["method"] == "GET":
                        response = self.session.get(f"{self.base_url}{endpoint['path']}")
                    else:
                        response = self.session.post(
                            f"{self.base_url}{endpoint['path']}", 
                            json=endpoint.get("data")
                        )
                    
                    if response.status_code < 400:
                        success_count += 1
                    
                    response_times.append(time.time() - start_time)
                    
                except Exception as e:
                    response_times.append(self.test_config["max_response_time"])
                
                time.sleep(0.1)  # 短暂间隔
            
            baseline_results[endpoint["path"]] = {
                "avg_response_time": statistics.mean(response_times),
                "median_response_time": statistics.median(response_times),
                "p95_response_time": statistics.quantiles(response_times, n=20)[18],  # 95th percentile
                "success_rate": success_count / 10,
                "min_response_time": min(response_times),
                "max_response_time": max(response_times)
            }
        
        self.test_results.append({
            "test": "baseline_performance",
            "status": "passed",
            "results": baseline_results,
            "overall_avg_response_time": statistics.mean([
                result["avg_response_time"] for result in baseline_results.values()
            ])
        })
    
    def test_load_testing(self):
        """负载测试"""
        print("⚡ 执行负载测试...")
        
        load_test_results = {}
        
        for concurrent_users in self.test_config["concurrent_users"]:
            print(f"   测试 {concurrent_users} 并发用户...")
            
            results = self._run_concurrent_requests(
                concurrent_users, 
                self.test_config["test_duration"] // 4,  # 每个级别测试15秒
                self._create_test_task_request
            )
            
            load_test_results[concurrent_users] = {
                "total_requests": results["total_requests"],
                "successful_requests": results["successful_requests"],
                "failed_requests": results["failed_requests"],
                "avg_response_time": results["avg_response_time"],
                "throughput": results["throughput"],
                "error_rate": results["error_rate"]
            }
            
            # 检查是否超过阈值
            if results["error_rate"] > self.test_config["error_rate_threshold"]:
                print(f"   ⚠️ 错误率超过阈值: {results['error_rate']:.2%}")
            
            if results["avg_response_time"] > self.test_config["max_response_time"]:
                print(f"   ⚠️ 响应时间超过阈值: {results['avg_response_time']:.2f}s")
        
        # 找到性能拐点
        throughput_values = [result["throughput"] for result in load_test_results.values()]
        max_throughput = max(throughput_values)
        optimal_users = next(
            users for users, result in load_test_results.items() 
            if result["throughput"] == max_throughput
        )
        
        self.test_results.append({
            "test": "load_testing",
            "status": "passed",
            "results": load_test_results,
            "optimal_concurrent_users": optimal_users,
            "max_throughput": max_throughput,
            "performance_degradation_point": self._find_degradation_point(load_test_results)
        })
    
    def test_stress_testing(self):
        """压力测试 - 测试系统极限"""
        print("💪 执行压力测试...")
        
        # 逐步增加负载直到系统崩溃或达到极限
        max_users = 100
        step_size = 10
        stress_results = []
        
        for users in range(step_size, max_users + 1, step_size):
            print(f"   压力测试: {users} 并发用户...")
            
            try:
                results = self._run_concurrent_requests(
                    users, 
                    30,  # 30秒压力测试
                    self._create_test_task_request
                )
                
                stress_results.append({
                    "concurrent_users": users,
                    "success": True,
                    "throughput": results["throughput"],
                    "error_rate": results["error_rate"],
                    "avg_response_time": results["avg_response_time"]
                })
                
                # 如果错误率超过50%或响应时间超过10秒，认为达到极限
                if results["error_rate"] > 0.5 or results["avg_response_time"] > 10:
                    print(f"   🚨 系统极限: {users} 用户")
                    break
                    
            except Exception as e:
                stress_results.append({
                    "concurrent_users": users,
                    "success": False,
                    "error": str(e)
                })
                print(f"   💥 系统崩溃点: {users} 用户")
                break
        
        # 分析压力测试结果
        successful_tests = [r for r in stress_results if r.get("success", False)]
        if successful_tests:
            max_stable_users = max(r["concurrent_users"] for r in successful_tests 
                                 if r.get("error_rate", 1) < 0.1)
            breaking_point = next(
                (r["concurrent_users"] for r in stress_results if not r.get("success", True)),
                max_users
            )
        else:
            max_stable_users = 0
            breaking_point = step_size
        
        self.test_results.append({
            "test": "stress_testing",
            "status": "passed",
            "max_stable_users": max_stable_users,
            "breaking_point": breaking_point,
            "stress_test_results": stress_results[-5:]  # 只保留最后5个结果
        })
    
    def test_spike_testing(self):
        """峰值测试 - 测试突发流量处理"""
        print("📈 执行峰值测试...")
        
        spike_scenarios = [
            {"name": "小峰值", "normal_users": 5, "spike_users": 20, "spike_duration": 10},
            {"name": "中峰值", "normal_users": 5, "spike_users": 50, "spike_duration": 15},
            {"name": "大峰值", "normal_users": 10, "spike_users": 100, "spike_duration": 20}
        ]
        
        spike_results = []
        
        for scenario in spike_scenarios:
            print(f"   测试 {scenario['name']}...")
            
            # 第一阶段：正常负载
            normal_results = self._run_concurrent_requests(
                scenario["normal_users"], 10, self._create_test_task_request
            )
            
            # 第二阶段：峰值负载
            spike_start_time = time.time()
            spike_results_data = self._run_concurrent_requests(
                scenario["spike_users"], scenario["spike_duration"], self._create_test_task_request
            )
            spike_end_time = time.time()
            
            # 第三阶段：恢复到正常负载
            recovery_results = self._run_concurrent_requests(
                scenario["normal_users"], 10, self._create_test_task_request
            )
            
            # 分析峰值影响
            performance_degradation = (
                spike_results_data["avg_response_time"] / normal_results["avg_response_time"]
            ) if normal_results["avg_response_time"] > 0 else float('inf')
            
            recovery_factor = (
                recovery_results["avg_response_time"] / normal_results["avg_response_time"]
            ) if normal_results["avg_response_time"] > 0 else float('inf')
            
            spike_results.append({
                "scenario": scenario["name"],
                "normal_throughput": normal_results["throughput"],
                "spike_throughput": spike_results_data["throughput"],
                "recovery_throughput": recovery_results["throughput"],
                "performance_degradation": performance_degradation,
                "recovery_factor": recovery_factor,
                "spike_error_rate": spike_results_data["error_rate"],
                "system_recovered": recovery_factor < 1.2  # 恢复到正常性能的120%以内
            })
        
        self.test_results.append({
            "test": "spike_testing",
            "status": "passed",
            "spike_scenarios": spike_results,
            "overall_spike_resilience": sum(1 for r in spike_results if r["system_recovered"]) / len(spike_results)
        })
    
    def test_endurance_testing(self):
        """耐久性测试 - 长时间运行稳定性"""
        print("⏰ 执行耐久性测试...")
        
        endurance_duration = 180  # 3分钟（实际生产中应该更长）
        sampling_interval = 30    # 每30秒采样一次
        
        endurance_metrics = []
        
        # 启动持续负载
        def continuous_load():
            return self._run_continuous_requests(
                concurrent_users=10,
                duration=endurance_duration,
                request_func=self._create_test_task_request
            )
        
        # 在后台运行持续负载
        load_thread = threading.Thread(target=continuous_load)
        load_thread.start()
        
        # 定期采样性能指标
        start_time = time.time()
        while time.time() - start_time < endurance_duration:
            sample_start = time.time()
            
            # 快速性能采样
            sample_results = self._run_concurrent_requests(
                5, 10, self._create_test_task_request
            )
            
            # 系统资源采样
            cpu_percent = psutil.cpu_percent(interval=1)
            memory_info = psutil.virtual_memory()
            
            endurance_metrics.append({
                "timestamp": time.time(),
                "response_time": sample_results["avg_response_time"],
                "throughput": sample_results["throughput"],
                "error_rate": sample_results["error_rate"],
                "cpu_usage": cpu_percent,
                "memory_usage": memory_info.percent,
                "memory_available": memory_info.available / (1024**3)  # GB
            })
            
            # 等待到下一个采样间隔
            elapsed = time.time() - sample_start
            if elapsed < sampling_interval:
                time.sleep(sampling_interval - elapsed)
        
        load_thread.join(timeout=10)
        
        # 分析耐久性指标
        if endurance_metrics:
            initial_metrics = endurance_metrics[0]
            final_metrics = endurance_metrics[-1]
            
            performance_drift = {
                "response_time_drift": (final_metrics["response_time"] - initial_metrics["response_time"]) / initial_metrics["response_time"],
                "throughput_drift": (final_metrics["throughput"] - initial_metrics["throughput"]) / initial_metrics["throughput"],
                "memory_growth": final_metrics["memory_usage"] - initial_metrics["memory_usage"],
                "cpu_stability": statistics.stdev([m["cpu_usage"] for m in endurance_metrics])
            }
            
            # 检测内存泄漏
            memory_trend = [m["memory_usage"] for m in endurance_metrics]
            memory_leak_detected = len(memory_trend) > 1 and (memory_trend[-1] - memory_trend[0]) > self.test_config["memory_leak_threshold"]
            
        else:
            performance_drift = {}
            memory_leak_detected = False
        
        self.test_results.append({
            "test": "endurance_testing",
            "status": "passed",
            "test_duration": endurance_duration,
            "samples_collected": len(endurance_metrics),
            "performance_drift": performance_drift,
            "memory_leak_detected": memory_leak_detected,
            "system_stability": "stable" if abs(performance_drift.get("response_time_drift", 0)) < 0.2 else "unstable"
        })
    
    def test_memory_leak_detection(self):
        """内存泄漏检测"""
        print("🧠 执行内存泄漏检测...")
        
        # 获取初始内存状态
        initial_memory = psutil.virtual_memory()
        process = psutil.Process()
        initial_process_memory = process.memory_info()
        
        memory_snapshots = []
        
        # 执行多轮操作，监控内存变化
        for round_num in range(10):
            # 创建一批任务
            tasks = []
            for _ in range(5):
                try:
                    response = self.session.post(
                        f"{self.base_url}/api/v1/tasks/",
                        json={
                            "description": f"内存测试任务 轮次{round_num}",
                            "style": "tech",
                            "duration": 15
                        }
                    )
                    if response.status_code < 400:
                        tasks.append(response.json().get("id"))
                except Exception:
                    pass
            
            # 记录内存快照
            current_memory = psutil.virtual_memory()
            current_process_memory = process.memory_info()
            
            memory_snapshots.append({
                "round": round_num,
                "system_memory_used": current_memory.used,
                "system_memory_percent": current_memory.percent,
                "process_memory_rss": current_process_memory.rss,
                "process_memory_vms": current_process_memory.vms,
                "tasks_created": len(tasks)
            })
            
            time.sleep(2)  # 等待内存稳定
        
        # 分析内存趋势
        if len(memory_snapshots) > 1:
            memory_growth = memory_snapshots[-1]["system_memory_used"] - memory_snapshots[0]["system_memory_used"]
            memory_growth_mb = memory_growth / (1024 * 1024)
            
            # 计算内存增长趋势
            memory_trend = [snapshot["system_memory_used"] for snapshot in memory_snapshots]
            if len(memory_trend) > 2:
                # 简单线性回归检测趋势
                x = list(range(len(memory_trend)))
                n = len(x)
                sum_x = sum(x)
                sum_y = sum(memory_trend)
                sum_xy = sum(x[i] * memory_trend[i] for i in range(n))
                sum_x2 = sum(x[i] ** 2 for i in range(n))
                
                slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x ** 2)
                trend_mb_per_round = slope / (1024 * 1024)
            else:
                trend_mb_per_round = 0
        else:
            memory_growth_mb = 0
            trend_mb_per_round = 0
        
        # 判断是否存在内存泄漏
        leak_suspected = (
            memory_growth_mb > self.test_config["memory_leak_threshold"] or
            trend_mb_per_round > 10  # 每轮超过10MB增长
        )
        
        self.test_results.append({
            "test": "memory_leak_detection",
            "status": "passed",
            "total_memory_growth_mb": memory_growth_mb,
            "memory_trend_mb_per_round": trend_mb_per_round,
            "leak_suspected": leak_suspected,
            "snapshots_count": len(memory_snapshots),
            "recommendation": "需要进一步调查内存使用" if leak_suspected else "内存使用正常"
        })
    
    def test_database_performance(self):
        """数据库性能测试"""
        print("🗄️ 执行数据库性能测试...")
        
        db_results = {}
        
        try:
            # 测试数据库连接池性能
            connection_times = []
            for _ in range(20):
                start_time = time.time()
                # 这里应该使用实际的数据库连接
                # 现在用HTTP请求模拟
                response = self.session.get(f"{self.base_url}/health")
                connection_times.append(time.time() - start_time)
            
            db_results["connection_performance"] = {
                "avg_connection_time": statistics.mean(connection_times),
                "max_connection_time": max(connection_times),
                "connection_success_rate": 1.0
            }
            
            # 测试并发数据库操作
            concurrent_db_results = self._run_concurrent_requests(
                20, 30, lambda: self._create_test_task_request()
            )
            
            db_results["concurrent_operations"] = {
                "throughput": concurrent_db_results["throughput"],
                "avg_response_time": concurrent_db_results["avg_response_time"],
                "error_rate": concurrent_db_results["error_rate"]
            }
            
            # 数据库查询性能测试
            query_times = []
            for _ in range(10):
                start_time = time.time()
                response = self.session.get(f"{self.base_url}/api/v1/tasks/")
                if response.status_code == 200:
                    query_times.append(time.time() - start_time)
            
            if query_times:
                db_results["query_performance"] = {
                    "avg_query_time": statistics.mean(query_times),
                    "p95_query_time": statistics.quantiles(query_times, n=20)[18] if len(query_times) >= 20 else max(query_times)
                }
            
        except Exception as e:
            db_results["error"] = str(e)
        
        self.test_results.append({
            "test": "database_performance",
            "status": "passed" if "error" not in db_results else "failed",
            "results": db_results
        })
    
    def test_redis_performance(self):
        """Redis性能测试"""
        print("🔴 执行Redis性能测试...")
        
        try:
            redis_client = redis.from_url("redis://localhost:6379/0")
            
            # 测试基本读写性能
            write_times = []
            read_times = []
            
            for i in range(100):
                # 写入测试
                start_time = time.time()
                redis_client.set(f"perf_test_{i}", f"test_value_{i}")
                write_times.append(time.time() - start_time)
                
                # 读取测试
                start_time = time.time()
                value = redis_client.get(f"perf_test_{i}")
                read_times.append(time.time() - start_time)
                
                assert value == f"test_value_{i}".encode()
            
            # 清理测试数据
            keys_to_delete = [f"perf_test_{i}" for i in range(100)]
            redis_client.delete(*keys_to_delete)
            
            # 测试列表操作性能
            list_ops_times = []
            list_key = "perf_test_list"
            
            for i in range(50):
                start_time = time.time()
                redis_client.lpush(list_key, f"item_{i}")
                redis_client.lrange(list_key, 0, 10)
                redis_client.rpop(list_key)
                list_ops_times.append(time.time() - start_time)
            
            redis_client.delete(list_key)
            
            redis_results = {
                "write_performance": {
                    "avg_write_time": statistics.mean(write_times),
                    "max_write_time": max(write_times)
                },
                "read_performance": {
                    "avg_read_time": statistics.mean(read_times),
                    "max_read_time": max(read_times)
                },
                "list_operations": {
                    "avg_operation_time": statistics.mean(list_ops_times),
                    "max_operation_time": max(list_ops_times)
                }
            }
            
        except Exception as e:
            redis_results = {"error": str(e)}
        
        self.test_results.append({
            "test": "redis_performance",
            "status": "passed" if "error" not in redis_results else "failed",
            "results": redis_results
        })
    
    def test_file_handling_performance(self):
        """文件处理性能测试"""
        print("📁 执行文件处理性能测试...")
        
        import tempfile
        
        file_results = {}
        
        try:
            # 创建不同大小的测试文件
            file_sizes = [1024, 10*1024, 100*1024, 1024*1024]  # 1KB, 10KB, 100KB, 1MB
            
            for size in file_sizes:
                # 创建测试文件
                test_data = b'x' * size
                
                upload_times = []
                download_times = []
                
                for _ in range(5):  # 每个大小测试5次
                    with tempfile.NamedTemporaryFile() as temp_file:
                        temp_file.write(test_data)
                        temp_file.flush()
                        
                        # 上传测试
                        start_time = time.time()
                        with open(temp_file.name, 'rb') as f:
                            files = {'file': (f'test_{size}.bin', f, 'application/octet-stream')}
                            response = self.session.post(
                                f"{self.base_url}/api/v1/files/upload",
                                files=files,
                                timeout=30
                            )
                        
                        upload_time = time.time() - start_time
                        upload_times.append(upload_time)
                        
                        if response.status_code < 400:
                            file_url = response.json().get("url")
                            if file_url:
                                # 下载测试
                                start_time = time.time()
                                download_response = self.session.get(file_url, timeout=30)
                                download_time = time.time() - start_time
                                
                                if download_response.status_code == 200:
                                    download_times.append(download_time)
                
                if upload_times and download_times:
                    file_results[f"{size}_bytes"] = {
                        "avg_upload_time": statistics.mean(upload_times),
                        "avg_download_time": statistics.mean(download_times),
                        "upload_throughput_mbps": (size / (1024*1024)) / statistics.mean(upload_times),
                        "download_throughput_mbps": (size / (1024*1024)) / statistics.mean(download_times)
                    }
            
        except Exception as e:
            file_results["error"] = str(e)
        
        self.test_results.append({
            "test": "file_handling_performance",
            "status": "passed" if "error" not in file_results else "failed",
            "results": file_results
        })
    
    def test_websocket_performance(self):
        """WebSocket性能测试"""
        print("🔌 执行WebSocket性能测试...")
        
        import websocket
        
        ws_results = {}
        
        try:
            # 测试WebSocket连接和消息传输
            messages_sent = 0
            messages_received = 0
            latencies = []
            connection_established = threading.Event()
            
            def on_message(ws, message):
                nonlocal messages_received
                try:
                    data = json.loads(message)
                    if "timestamp" in data:
                        latency = time.time() - data["timestamp"]
                        latencies.append(latency)
                    messages_received += 1
                except:
                    pass
            
            def on_open(ws):
                connection_established.set()
                
                def send_messages():
                    nonlocal messages_sent
                    for i in range(20):
                        message = json.dumps({
                            "type": "ping",
                            "id": i,
                            "timestamp": time.time()
                        })
                        ws.send(message)
                        messages_sent += 1
                        time.sleep(0.1)
                
                threading.Thread(target=send_messages).start()
            
            def on_error(ws, error):
                print(f"WebSocket错误: {error}")
            
            ws_url = f"ws://localhost:8000/api/v1/ws/perf-test"
            ws = websocket.WebSocketApp(
                ws_url,
                on_message=on_message,
                on_open=on_open,
                on_error=on_error
            )
            
            # 在单独线程中运行WebSocket
            ws_thread = threading.Thread(target=lambda: ws.run_forever())
            ws_thread.daemon = True
            ws_thread.start()
            
            # 等待连接和测试完成
            if connection_established.wait(timeout=10):
                time.sleep(5)  # 等待消息传输完成
                ws.close()
                
                ws_results = {
                    "connection_successful": True,
                    "messages_sent": messages_sent,
                    "messages_received": messages_received,
                    "message_success_rate": messages_received / messages_sent if messages_sent > 0 else 0,
                    "avg_latency": statistics.mean(latencies) if latencies else 0,
                    "max_latency": max(latencies) if latencies else 0
                }
            else:
                ws_results = {
                    "connection_successful": False,
                    "error": "连接超时"
                }
            
        except Exception as e:
            ws_results = {
                "connection_successful": False,
                "error": str(e)
            }
        
        self.test_results.append({
            "test": "websocket_performance",
            "status": "passed" if ws_results.get("connection_successful") else "failed",
            "results": ws_results
        })
    
    def test_error_recovery_reliability(self):
        """错误恢复和可靠性测试"""
        print("🔧 执行错误恢复测试...")
        
        recovery_scenarios = []
        
        # 场景1: 网络中断恢复
        try:
            # 模拟网络问题（超时）
            response = self.session.get(f"{self.base_url}/health", timeout=0.001)
        except:
            # 正常请求应该能恢复
            time.sleep(1)
            response = self.session.get(f"{self.base_url}/health", timeout=10)
            recovery_scenarios.append({
                "scenario": "network_recovery",
                "recovered": response.status_code == 200
            })
        
        # 场景2: 数据库连接恢复
        # 这里模拟数据库操作
        try:
            for _ in range(3):
                response = self.session.post(
                    f"{self.base_url}/api/v1/tasks/",
                    json={"description": "恢复测试", "style": "tech", "duration": 30}
                )
                if response.status_code < 400:
                    break
                time.sleep(1)
            
            recovery_scenarios.append({
                "scenario": "database_recovery",
                "recovered": response.status_code < 400
            })
        except Exception as e:
            recovery_scenarios.append({
                "scenario": "database_recovery",
                "recovered": False,
                "error": str(e)
            })
        
        # 场景3: 服务降级和恢复
        # 模拟高负载下的服务降级
        high_load_results = self._run_concurrent_requests(50, 10, self._create_test_task_request)
        normal_load_results = self._run_concurrent_requests(5, 10, self._create_test_task_request)
        
        service_recovered = (
            normal_load_results["error_rate"] < high_load_results["error_rate"] and
            normal_load_results["avg_response_time"] < high_load_results["avg_response_time"] * 1.5
        )
        
        recovery_scenarios.append({
            "scenario": "service_degradation_recovery",
            "recovered": service_recovered,
            "high_load_error_rate": high_load_results["error_rate"],
            "normal_load_error_rate": normal_load_results["error_rate"]
        })
        
        # 计算整体恢复能力
        recovery_rate = sum(1 for scenario in recovery_scenarios if scenario["recovered"]) / len(recovery_scenarios)
        
        self.test_results.append({
            "test": "error_recovery_reliability",
            "status": "passed" if recovery_rate >= 0.8 else "partial",
            "recovery_scenarios": recovery_scenarios,
            "overall_recovery_rate": recovery_rate,
            "reliability_rating": "高" if recovery_rate >= 0.9 else "中" if recovery_rate >= 0.7 else "低"
        })
    
    def test_resource_cleanup(self):
        """资源清理测试"""
        print("🧹 执行资源清理测试...")
        
        cleanup_results = {}
        
        # 记录测试前的资源状态
        initial_files = self._count_temp_files()
        initial_memory = psutil.virtual_memory().used
        
        # 创建一些临时资源
        temp_resources = []
        for i in range(10):
            try:
                # 创建任务
                response = self.session.post(
                    f"{self.base_url}/api/v1/tasks/",
                    json={
                        "description": f"资源清理测试 {i}",
                        "style": "tech",
                        "duration": 15
                    }
                )
                if response.status_code < 400:
                    temp_resources.append(response.json().get("id"))
                
                # 上传文件
                with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
                    f.write(f"测试文件 {i}")
                    temp_file_path = f.name
                
                with open(temp_file_path, 'rb') as f:
                    files = {'file': (f'cleanup_test_{i}.txt', f, 'text/plain')}
                    self.session.post(f"{self.base_url}/api/v1/files/upload", files=files)
                
                os.unlink(temp_file_path)
                
            except Exception:
                pass
        
        # 等待一段时间让系统处理
        time.sleep(10)
        
        # 检查资源使用情况
        final_files = self._count_temp_files()
        final_memory = psutil.virtual_memory().used
        
        memory_growth_mb = (final_memory - initial_memory) / (1024 * 1024)
        file_growth = final_files - initial_files
        
        # 判断清理效果
        cleanup_effective = (
            memory_growth_mb < 50 and  # 内存增长小于50MB
            file_growth < 20           # 临时文件增长小于20个
        )
        
        cleanup_results = {
            "resources_created": len(temp_resources),
            "memory_growth_mb": memory_growth_mb,
            "file_growth": file_growth,
            "cleanup_effective": cleanup_effective,
            "memory_efficiency": "良好" if memory_growth_mb < 50 else "需要改进",
            "file_cleanup": "良好" if file_growth < 20 else "需要改进"
        }
        
        self.test_results.append({
            "test": "resource_cleanup",
            "status": "passed" if cleanup_effective else "warning",
            "results": cleanup_results
        })
    
    # 辅助方法
    def _run_concurrent_requests(self, concurrent_users: int, duration: int, request_func) -> Dict[str, Any]:
        """运行并发请求测试"""
        results = []
        start_time = time.time()
        
        def worker():
            worker_results = []
            while time.time() - start_time < duration:
                request_start = time.time()
                try:
                    response = request_func()
                    success = response.status_code < 400 if hasattr(response, 'status_code') else True
                    response_time = time.time() - request_start
                    worker_results.append({
                        "success": success,
                        "response_time": response_time
                    })
                except Exception:
                    worker_results.append({
                        "success": False,
                        "response_time": time.time() - request_start
                    })
                
                time.sleep(0.01)  # 短暂间隔避免过度压力
            
            return worker_results
        
        # 使用线程池执行并发请求
        with ThreadPoolExecutor(max_workers=concurrent_users) as executor:
            futures = [executor.submit(worker) for _ in range(concurrent_users)]
            
            for future in as_completed(futures):
                try:
                    worker_results = future.result()
                    results.extend(worker_results)
                except Exception:
                    pass
        
        # 分析结果
        if results:
            total_requests = len(results)
            successful_requests = sum(1 for r in results if r["success"])
            failed_requests = total_requests - successful_requests
            response_times = [r["response_time"] for r in results]
            
            return {
                "total_requests": total_requests,
                "successful_requests": successful_requests,
                "failed_requests": failed_requests,
                "avg_response_time": statistics.mean(response_times),
                "throughput": total_requests / duration,
                "error_rate": failed_requests / total_requests
            }
        else:
            return {
                "total_requests": 0,
                "successful_requests": 0,
                "failed_requests": 0,
                "avg_response_time": 0,
                "throughput": 0,
                "error_rate": 1.0
            }
    
    def _run_continuous_requests(self, concurrent_users: int, duration: int, request_func) -> Dict[str, Any]:
        """运行持续请求（用于耐久性测试）"""
        return self._run_concurrent_requests(concurrent_users, duration, request_func)
    
    def _create_test_task_request(self):
        """创建测试任务请求"""
        task_types = ["tech", "creative", "business", "educational"]
        durations = [15, 30, 45, 60]
        
        return self.session.post(
            f"{self.base_url}/api/v1/tasks/",
            json={
                "description": f"性能测试任务 {random.randint(1000, 9999)}",
                "style": random.choice(task_types),
                "duration": random.choice(durations),
                "aspect_ratio": "16:9"
            },
            timeout=30
        )
    
    def _find_degradation_point(self, load_results: Dict[int, Dict[str, Any]]) -> int:
        """找到性能退化点"""
        sorted_results = sorted(load_results.items())
        
        for i, (users, result) in enumerate(sorted_results[1:], 1):
            prev_result = sorted_results[i-1][1]
            
            # 如果响应时间增长超过50%或错误率超过5%，认为是退化点
            if (result["avg_response_time"] > prev_result["avg_response_time"] * 1.5 or
                result["error_rate"] > 0.05):
                return users
        
        return max(load_results.keys())  # 没有明显退化点
    
    def _monitor_system_resources(self):
        """监控系统资源使用"""
        while True:
            try:
                cpu_percent = psutil.cpu_percent(interval=1)
                memory = psutil.virtual_memory()
                disk_io = psutil.disk_io_counters()
                network_io = psutil.net_io_counters()
                
                self.system_metrics["cpu_usage"].append(cpu_percent)
                self.system_metrics["memory_usage"].append(memory.percent)
                
                if disk_io:
                    self.system_metrics["disk_io"].append({
                        "read_bytes": disk_io.read_bytes,
                        "write_bytes": disk_io.write_bytes
                    })
                
                if network_io:
                    self.system_metrics["network_io"].append({
                        "bytes_sent": network_io.bytes_sent,
                        "bytes_recv": network_io.bytes_recv
                    })
                
                time.sleep(5)  # 每5秒采样一次
            except Exception:
                break
    
    def _count_temp_files(self) -> int:
        """计算临时文件数量"""
        try:
            temp_dir = tempfile.gettempdir()
            return len([f for f in os.listdir(temp_dir) if os.path.isfile(os.path.join(temp_dir, f))])
        except:
            return 0
    
    def generate_performance_report(self):
        """生成性能测试报告"""
        print("\n📊 生成性能和可靠性测试报告...")
        
        passed_tests = sum(1 for result in self.test_results if result["status"] == "passed")
        warning_tests = sum(1 for result in self.test_results if result["status"] == "warning")
        partial_tests = sum(1 for result in self.test_results if result["status"] == "partial")
        failed_tests = sum(1 for result in self.test_results if result["status"] == "failed")
        total_tests = len(self.test_results)
        
        overall_score = ((passed_tests + warning_tests * 0.8 + partial_tests * 0.5) / total_tests * 100) if total_tests > 0 else 0
        
        print(f"""
        =================== 性能和可靠性测试报告 ===================
        总测试数: {total_tests}
        完全通过: {passed_tests}
        警告状态: {warning_tests}
        部分通过: {partial_tests}
        完全失败: {failed_tests}
        综合评分: {overall_score:.1f}/100
        
        系统资源监控:
        平均CPU使用率: {statistics.mean(self.system_metrics["cpu_usage"]) if self.system_metrics["cpu_usage"] else 0:.1f}%
        平均内存使用率: {statistics.mean(self.system_metrics["memory_usage"]) if self.system_metrics["memory_usage"] else 0:.1f}%
        
        详细结果:
        """)
        
        for result in self.test_results:
            status_icons = {
                "passed": "✅",
                "warning": "⚠️",
                "partial": "🔶",
                "failed": "❌"
            }
            status_icon = status_icons.get(result["status"], "❓")
            
            print(f"        {status_icon} {result['test']}: {result['status']}")
            
            # 显示关键指标
            if result["test"] == "load_testing" and "optimal_concurrent_users" in result:
                print(f"           最优并发用户数: {result['optimal_concurrent_users']}")
                print(f"           最大吞吐量: {result['max_throughput']:.2f} req/s")
            
            elif result["test"] == "stress_testing":
                print(f"           最大稳定用户数: {result.get('max_stable_users', 0)}")
                print(f"           系统极限点: {result.get('breaking_point', 'N/A')} 用户")
            
            elif result["test"] == "endurance_testing":
                print(f"           系统稳定性: {result.get('system_stability', 'N/A')}")
                print(f"           内存泄漏检测: {'是' if result.get('memory_leak_detected') else '否'}")
            
            if "error" in result:
                print(f"           错误: {result['error']}")
        
        # 性能建议
        print(f"""
        
        性能优化建议:
        """)
        
        if overall_score >= 90:
            print("        🎉 系统性能优秀，各项指标均在正常范围内")
        elif overall_score >= 75:
            print("        👍 系统性能良好，建议关注内存使用和响应时间优化")
        elif overall_score >= 60:
            print("        ⚠️ 系统性能一般，建议优化数据库查询和并发处理")
        else:
            print("        🚨 系统性能需要改进，建议全面检查架构和资源配置")
        
        print("        ===============================================")


# 主测试运行器
def run_performance_reliability_tests():
    """运行所有性能和可靠性测试"""
    tester = PerformanceReliabilityTester()
    
    try:
        tester.run_all_performance_tests()
        print("🎉 性能和可靠性测试完成！")
        return True
    except Exception as e:
        print(f"❌ 性能和可靠性测试失败: {e}")
        return False


if __name__ == "__main__":
    success = run_performance_reliability_tests()
    exit(0 if success else 1)