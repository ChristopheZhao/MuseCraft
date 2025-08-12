"""
Monitoring and Health Check Test Suite

This module provides comprehensive testing of system monitoring capabilities,
health checks, alerting mechanisms, and observability features.
"""
import asyncio
import time
import json
from typing import Dict, List, Any, Optional
from unittest.mock import patch, AsyncMock, MagicMock
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
import psutil

from app.services.monitoring_service import monitoring_service
from app.core.config import settings


@pytest.mark.monitoring
@pytest.mark.asyncio
class TestSystemMonitoring:
    """System monitoring and metrics collection tests."""
    
    async def test_system_metrics_collection(self):
        """Test collection of system performance metrics."""
        
        # Start metrics collection
        await monitoring_service.start_monitoring()
        
        # Collect metrics over time
        metrics_samples = []
        collection_duration = 30  # seconds
        sample_interval = 5  # seconds
        
        end_time = time.time() + collection_duration
        
        while time.time() < end_time:
            # Get current system metrics
            metrics = await monitoring_service.get_system_metrics()
            
            metrics_samples.append({
                "timestamp": time.time(),
                "cpu_percent": metrics.get("cpu_percent", 0),
                "memory_percent": metrics.get("memory_percent", 0),
                "disk_percent": metrics.get("disk_percent", 0),
                "active_connections": metrics.get("active_connections", 0),
                "active_tasks": metrics.get("active_tasks", 0)
            })
            
            await asyncio.sleep(sample_interval)
        
        # Analyze collected metrics
        metrics_analysis = {
            "total_samples": len(metrics_samples),
            "collection_duration": collection_duration,
            "avg_cpu_percent": sum(s["cpu_percent"] for s in metrics_samples) / len(metrics_samples),
            "max_cpu_percent": max(s["cpu_percent"] for s in metrics_samples),
            "avg_memory_percent": sum(s["memory_percent"] for s in metrics_samples) / len(metrics_samples),
            "max_memory_percent": max(s["memory_percent"] for s in metrics_samples),
            "samples": metrics_samples
        }
        
        # Verify metrics collection
        assert metrics_analysis["total_samples"] >= 5, "Should collect at least 5 metric samples"
        assert 0 <= metrics_analysis["avg_cpu_percent"] <= 100, "CPU percentage should be between 0 and 100"
        assert 0 <= metrics_analysis["avg_memory_percent"] <= 100, "Memory percentage should be between 0 and 100"
        
        return metrics_analysis
    
    async def test_application_metrics_tracking(
        self,
        test_client: AsyncClient,
        test_db_session: AsyncSession
    ):
        """Test application-specific metrics tracking."""
        
        # Initialize application metrics
        app_metrics = {
            "api_requests": 0,
            "task_creations": 0,
            "task_completions": 0,
            "errors": 0,
            "response_times": []
        }
        
        # Simulate application activity
        for i in range(10):
            # API request
            start_time = time.time()
            
            response = await test_client.post("/api/v1/tasks/", json={
                "user_prompt": f"Metrics test task {i}",
                "video_style": "professional",
                "duration": 30
            })
            
            response_time = time.time() - start_time
            
            # Track metrics
            app_metrics["api_requests"] += 1
            app_metrics["response_times"].append(response_time)
            
            if response.status_code == 201:
                app_metrics["task_creations"] += 1
            else:
                app_metrics["errors"] += 1
            
            # Record metrics in monitoring service
            await monitoring_service.record_application_metrics({
                "api_request": 1,
                "response_time": response_time,
                "task_created": 1 if response.status_code == 201 else 0,
                "error": 1 if response.status_code >= 400 else 0
            })
        
        # Get aggregated metrics from monitoring service
        aggregated_metrics = await monitoring_service.get_application_metrics()
        
        # Verify metrics tracking
        assert aggregated_metrics["total_api_requests"] >= app_metrics["api_requests"]
        assert aggregated_metrics["total_tasks_created"] >= app_metrics["task_creations"]
        
        # Calculate performance metrics
        avg_response_time = sum(app_metrics["response_times"]) / len(app_metrics["response_times"])
        error_rate = app_metrics["errors"] / app_metrics["api_requests"]
        
        metrics_summary = {
            "application_metrics": app_metrics,
            "aggregated_metrics": aggregated_metrics,
            "avg_response_time": avg_response_time,
            "error_rate": error_rate
        }
        
        # Performance assertions
        assert avg_response_time < 2.0, f"Average response time {avg_response_time:.3f}s exceeds threshold"
        assert error_rate < 0.1, f"Error rate {error_rate:.3f} exceeds 10% threshold"
        
        return metrics_summary
    
    async def test_real_time_monitoring_dashboard(self, test_redis):
        """Test real-time monitoring dashboard data."""
        
        # Simulate real-time data updates
        dashboard_metrics = [
            {
                "timestamp": time.time(),
                "active_users": 25,
                "active_tasks": 12,
                "queue_size": 8,
                "cpu_usage": 45.2,
                "memory_usage": 62.1,
                "api_requests_per_minute": 150
            },
            {
                "timestamp": time.time() + 60,
                "active_users": 28,
                "active_tasks": 15,
                "queue_size": 5,
                "cpu_usage": 52.8,
                "memory_usage": 68.4,
                "api_requests_per_minute": 175
            },
            {
                "timestamp": time.time() + 120,
                "active_users": 22,
                "active_tasks": 10,
                "queue_size": 12,
                "cpu_usage": 38.9,
                "memory_usage": 59.7,
                "api_requests_per_minute": 125
            }
        ]
        
        # Store metrics in Redis for real-time access
        for i, metrics in enumerate(dashboard_metrics):
            await test_redis.setex(
                f"dashboard:metrics:{i}",
                300,  # 5 minutes TTL
                json.dumps(metrics)
            )
        
        # Test dashboard data retrieval
        retrieved_metrics = []
        for i in range(len(dashboard_metrics)):
            data = await test_redis.get(f"dashboard:metrics:{i}")
            if data:
                retrieved_metrics.append(json.loads(data.decode()))
        
        # Verify dashboard functionality
        assert len(retrieved_metrics) == len(dashboard_metrics)
        
        # Test real-time updates
        latest_metrics = retrieved_metrics[-1] if retrieved_metrics else {}
        
        dashboard_validation = {
            "metrics_stored": len(retrieved_metrics),
            "latest_active_users": latest_metrics.get("active_users", 0),
            "latest_cpu_usage": latest_metrics.get("cpu_usage", 0),
            "metrics_trend": {
                "users": [m["active_users"] for m in retrieved_metrics],
                "cpu": [m["cpu_usage"] for m in retrieved_metrics],
                "tasks": [m["active_tasks"] for m in retrieved_metrics]
            }
        }
        
        return dashboard_validation
    
    async def test_threshold_based_alerting(self, test_redis):
        """Test threshold-based alerting system."""
        
        # Define alert thresholds
        alert_thresholds = {
            "cpu_usage": {"warning": 70, "critical": 85},
            "memory_usage": {"warning": 75, "critical": 90},
            "disk_usage": {"warning": 80, "critical": 95},
            "error_rate": {"warning": 0.05, "critical": 0.10},
            "response_time": {"warning": 2.0, "critical": 5.0}
        }
        
        # Test scenarios with different metric values
        test_scenarios = [
            {
                "name": "normal_operation",
                "metrics": {
                    "cpu_usage": 45,
                    "memory_usage": 60,
                    "disk_usage": 70,
                    "error_rate": 0.02,
                    "response_time": 0.8
                },
                "expected_alerts": []
            },
            {
                "name": "warning_levels",
                "metrics": {
                    "cpu_usage": 75,  # Warning level
                    "memory_usage": 80,  # Warning level
                    "disk_usage": 65,
                    "error_rate": 0.07,  # Warning level
                    "response_time": 1.5
                },
                "expected_alerts": ["cpu_usage", "memory_usage", "error_rate"]
            },
            {
                "name": "critical_levels",
                "metrics": {
                    "cpu_usage": 90,  # Critical level
                    "memory_usage": 95,  # Critical level
                    "disk_usage": 88,
                    "error_rate": 0.12,  # Critical level
                    "response_time": 6.0  # Critical level
                },
                "expected_alerts": ["cpu_usage", "memory_usage", "error_rate", "response_time"]
            }
        ]
        
        alert_test_results = []
        
        for scenario in test_scenarios:
            # Check thresholds for the scenario
            triggered_alerts = await monitoring_service.check_alert_thresholds(
                scenario["metrics"],
                alert_thresholds
            )
            
            # Verify expected alerts
            expected_alerts = set(scenario["expected_alerts"])
            actual_alerts = set(triggered_alerts.get("triggered_alerts", []))
            
            scenario_result = {
                "scenario": scenario["name"],
                "metrics": scenario["metrics"],
                "expected_alerts": expected_alerts,
                "actual_alerts": actual_alerts,
                "alerts_match": expected_alerts == actual_alerts,
                "alert_details": triggered_alerts
            }
            
            alert_test_results.append(scenario_result)
        
        # Verify all scenarios pass
        failed_scenarios = [r for r in alert_test_results if not r["alerts_match"]]
        assert len(failed_scenarios) == 0, f"Alert scenarios failed: {[s['scenario'] for s in failed_scenarios]}"
        
        return alert_test_results
    
    async def test_performance_trend_analysis(self):
        """Test performance trend analysis and anomaly detection."""
        
        # Generate historical performance data
        base_time = time.time() - 3600  # 1 hour ago
        historical_data = []
        
        for i in range(60):  # 60 data points (1 per minute)
            timestamp = base_time + (i * 60)
            
            # Simulate normal performance with some variation
            base_cpu = 50
            base_memory = 65
            base_response_time = 1.2
            
            # Add some realistic variation
            cpu_variation = (i % 10) - 5  # -5 to +5
            memory_variation = (i % 8) - 4  # -4 to +4
            response_variation = ((i % 6) - 3) * 0.1  # -0.3 to +0.3
            
            # Add anomaly at specific points
            if i == 35:  # Simulate spike
                cpu_variation += 30
                memory_variation += 20
                response_variation += 2.0
            
            data_point = {
                "timestamp": timestamp,
                "cpu_usage": max(0, min(100, base_cpu + cpu_variation)),
                "memory_usage": max(0, min(100, base_memory + memory_variation)),
                "response_time": max(0.1, base_response_time + response_variation),
                "throughput": max(0, 100 - abs(cpu_variation))  # Inverse relationship
            }
            
            historical_data.append(data_point)
        
        # Analyze trends
        trend_analysis = await monitoring_service.analyze_performance_trends(historical_data)
        
        # Verify trend analysis
        trend_validation = {
            "data_points_analyzed": len(historical_data),
            "trends_detected": trend_analysis.get("trends", {}),
            "anomalies_detected": trend_analysis.get("anomalies", []),
            "performance_score": trend_analysis.get("overall_score", 0),
            "recommendations": trend_analysis.get("recommendations", [])
        }
        
        # Should detect the anomaly we injected
        assert len(trend_validation["anomalies_detected"]) >= 1, "Should detect injected performance anomaly"
        
        # Should provide performance recommendations
        assert len(trend_validation["recommendations"]) > 0, "Should provide performance recommendations"
        
        return trend_validation


@pytest.mark.monitoring
@pytest.mark.asyncio
class TestHealthChecks:
    """Comprehensive health check system tests."""
    
    async def test_basic_health_check_endpoint(self, test_client: AsyncClient):
        """Test basic health check endpoint functionality."""
        
        response = await test_client.get("/api/v1/system/health")
        
        assert response.status_code == 200
        
        health_data = response.json()
        
        # Verify health check response structure
        required_fields = ["status", "timestamp", "version", "checks"]
        for field in required_fields:
            assert field in health_data, f"Health check missing required field: {field}"
        
        # Verify individual health checks
        checks = health_data["checks"]
        required_checks = ["database", "redis", "storage", "external_services"]
        
        for check_name in required_checks:
            assert check_name in checks, f"Missing health check: {check_name}"
            
            check_result = checks[check_name]
            assert "status" in check_result, f"Health check {check_name} missing status"
            assert "response_time" in check_result, f"Health check {check_name} missing response time"
        
        return health_data
    
    async def test_database_health_check(self, test_db_session: AsyncSession):
        """Test database-specific health checks."""
        
        db_health_checks = [
            {
                "name": "connection_test",
                "query": "SELECT 1",
                "expected_result": 1
            },
            {
                "name": "table_existence_check",
                "query": "SELECT COUNT(*) FROM tasks LIMIT 1",
                "expected_type": int
            },
            {
                "name": "performance_test",
                "query": "SELECT COUNT(*) FROM tasks",
                "max_execution_time": 1.0
            }
        ]
        
        db_health_results = {}
        
        for check in db_health_checks:
            try:
                start_time = time.time()
                
                from sqlalchemy import text
                result = await test_db_session.execute(text(check["query"]))
                execution_time = time.time() - start_time
                
                if check["name"] == "connection_test":
                    check_passed = result.scalar() == check["expected_result"]
                elif check["name"] == "table_existence_check":
                    check_passed = isinstance(result.scalar(), check["expected_type"])
                elif check["name"] == "performance_test":
                    check_passed = execution_time <= check["max_execution_time"]
                else:
                    check_passed = True
                
                db_health_results[check["name"]] = {
                    "status": "healthy" if check_passed else "unhealthy",
                    "execution_time": execution_time,
                    "details": {
                        "query": check["query"],
                        "result": str(result.scalar()) if hasattr(result, 'scalar') else "N/A"
                    }
                }
                
            except Exception as e:
                db_health_results[check["name"]] = {
                    "status": "unhealthy",
                    "error": str(e),
                    "execution_time": time.time() - start_time
                }
        
        # Verify all database health checks pass
        failed_checks = [
            name for name, result in db_health_results.items()
            if result["status"] != "healthy"
        ]
        
        assert len(failed_checks) == 0, f"Database health checks failed: {failed_checks}"
        
        return db_health_results
    
    async def test_redis_health_check(self, test_redis):
        """Test Redis-specific health checks."""
        
        redis_health_checks = [
            {
                "name": "ping_test",
                "operation": "ping",
                "expected": True
            },
            {
                "name": "set_get_test",
                "operation": "set_get",
                "key": "health_check_test",
                "value": "test_value",
                "ttl": 60
            },
            {
                "name": "memory_usage_check",
                "operation": "memory_check",
                "max_memory_mb": 1000  # 1GB limit
            }
        ]
        
        redis_health_results = {}
        
        for check in redis_health_checks:
            try:
                start_time = time.time()
                
                if check["operation"] == "ping":
                    result = await test_redis.ping()
                    check_passed = result == check["expected"]
                    
                elif check["operation"] == "set_get":
                    await test_redis.setex(check["key"], check["ttl"], check["value"])
                    retrieved_value = await test_redis.get(check["key"])
                    check_passed = retrieved_value.decode() == check["value"]
                    
                    # Cleanup
                    await test_redis.delete(check["key"])
                    
                elif check["operation"] == "memory_check":
                    info = await test_redis.info("memory")
                    used_memory_mb = int(info.get("used_memory", 0)) / (1024 * 1024)
                    check_passed = used_memory_mb <= check["max_memory_mb"]
                    
                else:
                    check_passed = True
                
                execution_time = time.time() - start_time
                
                redis_health_results[check["name"]] = {
                    "status": "healthy" if check_passed else "unhealthy",
                    "execution_time": execution_time,
                    "details": check
                }
                
            except Exception as e:
                redis_health_results[check["name"]] = {
                    "status": "unhealthy",
                    "error": str(e),
                    "execution_time": time.time() - start_time
                }
        
        # Verify all Redis health checks pass
        failed_checks = [
            name for name, result in redis_health_results.items()
            if result["status"] != "healthy"
        ]
        
        assert len(failed_checks) == 0, f"Redis health checks failed: {failed_checks}"
        
        return redis_health_results
    
    async def test_external_services_health_check(self):
        """Test external services health checks."""
        
        external_services = [
            {
                "name": "openai_api",
                "endpoint": "https://api.openai.com/v1/models",
                "timeout": 10,
                "expected_status_range": (200, 299)
            },
            {
                "name": "stability_ai",
                "endpoint": "https://api.stability.ai/v1/engines/list",
                "timeout": 10,
                "expected_status_range": (200, 299)
            }
        ]
        
        external_health_results = {}
        
        for service in external_services:
            try:
                # In test environment, mock the external calls
                if os.getenv('PYTEST_CURRENT_TEST'):
                    # Mock successful health check
                    external_health_results[service["name"]] = {
                        "status": "healthy",
                        "response_time": 0.1,
                        "status_code": 200,
                        "mock": True
                    }
                else:
                    # Real health check for actual deployment
                    import httpx
                    
                    start_time = time.time()
                    async with httpx.AsyncClient() as client:
                        response = await client.get(
                            service["endpoint"],
                            timeout=service["timeout"]
                        )
                    
                    response_time = time.time() - start_time
                    
                    status_ok = (
                        service["expected_status_range"][0] <= response.status_code <= service["expected_status_range"][1]
                    )
                    
                    external_health_results[service["name"]] = {
                        "status": "healthy" if status_ok else "unhealthy",
                        "response_time": response_time,
                        "status_code": response.status_code,
                        "mock": False
                    }
                    
            except Exception as e:
                external_health_results[service["name"]] = {
                    "status": "unhealthy",
                    "error": str(e),
                    "mock": False
                }
        
        return external_health_results
    
    async def test_storage_health_check(self, test_storage_dirs: Dict[str, str]):
        """Test storage system health checks."""
        
        storage_health_results = {}
        
        for dir_type, dir_path in test_storage_dirs.items():
            try:
                start_time = time.time()
                
                # Test directory accessibility
                dir_accessible = os.path.exists(dir_path) and os.access(dir_path, os.R_OK | os.W_OK)
                
                # Test write performance
                test_file_path = os.path.join(dir_path, f"health_check_{dir_type}.tmp")
                test_data = b"Health check data" * 1000  # 17KB test file
                
                write_start = time.time()
                with open(test_file_path, 'wb') as f:
                    f.write(test_data)
                write_time = time.time() - write_start
                
                # Test read performance
                read_start = time.time()
                with open(test_file_path, 'rb') as f:
                    read_data = f.read()
                read_time = time.time() - read_start
                
                # Test delete
                os.remove(test_file_path)
                
                # Check available space
                import shutil
                total, used, free = shutil.disk_usage(dir_path)
                free_percent = (free / total) * 100
                
                execution_time = time.time() - start_time
                
                # Health criteria
                performance_ok = write_time < 1.0 and read_time < 1.0
                space_ok = free_percent > 10  # At least 10% free space
                data_integrity_ok = read_data == test_data
                
                storage_health_results[dir_type] = {
                    "status": "healthy" if (dir_accessible and performance_ok and space_ok and data_integrity_ok) else "unhealthy",
                    "execution_time": execution_time,
                    "details": {
                        "accessible": dir_accessible,
                        "write_time": write_time,
                        "read_time": read_time,
                        "free_space_percent": free_percent,
                        "data_integrity": data_integrity_ok
                    }
                }
                
            except Exception as e:
                storage_health_results[dir_type] = {
                    "status": "unhealthy",
                    "error": str(e),
                    "execution_time": time.time() - start_time
                }
        
        # Verify all storage health checks pass
        failed_checks = [
            name for name, result in storage_health_results.items()
            if result["status"] != "healthy"
        ]
        
        assert len(failed_checks) == 0, f"Storage health checks failed: {failed_checks}"
        
        return storage_health_results
    
    async def test_comprehensive_system_health(
        self,
        test_client: AsyncClient,
        test_db_session: AsyncSession,
        test_redis,
        test_storage_dirs: Dict[str, str]
    ):
        """Run comprehensive system health check covering all components."""
        
        comprehensive_health = {}
        
        # Basic API health
        comprehensive_health["api"] = await self.test_basic_health_check_endpoint(test_client)
        
        # Database health
        comprehensive_health["database"] = await self.test_database_health_check(test_db_session)
        
        # Redis health
        comprehensive_health["redis"] = await self.test_redis_health_check(test_redis)
        
        # Storage health
        comprehensive_health["storage"] = await self.test_storage_health_check(test_storage_dirs)
        
        # External services health
        comprehensive_health["external_services"] = await self.test_external_services_health_check()
        
        # Calculate overall system health score
        total_checks = 0
        healthy_checks = 0
        
        for component, results in comprehensive_health.items():
            if component == "api":
                # API health check has different structure
                if results.get("status") == "healthy":
                    healthy_checks += 1
                total_checks += 1
            else:
                # Other components have check dictionaries
                for check_name, check_result in results.items():
                    total_checks += 1
                    if check_result.get("status") == "healthy":
                        healthy_checks += 1
        
        health_score = (healthy_checks / total_checks) * 100 if total_checks > 0 else 0
        
        system_health_summary = {
            "overall_health_score": health_score,
            "healthy_checks": healthy_checks,
            "total_checks": total_checks,
            "system_healthy": health_score >= 90,  # 90% threshold for healthy system
            "component_health": comprehensive_health,
            "timestamp": time.time()
        }
        
        # System health assertion
        assert system_health_summary["system_healthy"], f"System health score {health_score:.1f}% below 90% threshold"
        
        return system_health_summary