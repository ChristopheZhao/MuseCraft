"""
Comprehensive Monitoring and Analytics Service
- Real-time performance tracking and metrics collection
- Cost analysis and optimization recommendations
- System health monitoring and alerting
- Advanced analytics and insights
- Performance bottleneck detection
"""
import asyncio
import os
import logging
import time
import psutil
import json
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import redis.asyncio as redis
from sqlalchemy.orm import Session
from sqlalchemy import func

from ..models import Task, AgentType, TaskStatus, AgentStatus
from ..core.config import settings
from .enhanced_ai_client import enhanced_ai_client, AIServiceProvider


class MetricType(str, Enum):
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMER = "timer"


class AlertLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class Metric:
    """Individual metric data point"""
    name: str
    value: float
    metric_type: MetricType
    timestamp: datetime
    labels: Dict[str, str] = field(default_factory=dict)
    description: str = ""


@dataclass
class Alert:
    """System alert"""
    id: str
    level: AlertLevel
    title: str
    message: str
    timestamp: datetime
    source: str
    resolved: bool = False
    resolution_time: Optional[datetime] = None


@dataclass
class PerformanceInsight:
    """Performance insight and recommendation"""
    category: str
    title: str
    description: str
    impact: str  # low, medium, high
    recommendation: str
    metric_evidence: List[str]
    estimated_savings: Optional[float] = None


class MonitoringService:
    """Comprehensive monitoring and analytics service"""
    
    def __init__(self):
        self.logger = logging.getLogger("monitoring_service")
        
        # Initialize Redis for metrics storage
        self.redis_client = None
        # Safely initialize async Redis from a sync context
        try:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = None
            if loop and loop.is_running():
                loop.create_task(self._init_redis())
            else:
                asyncio.run(self._init_redis())
        except Exception as _e:
            self.logger.warning(f"Redis async init deferred: {_e}")
            try:
                self.redis_client = redis.from_url(settings.REDIS_URL)
            except Exception:
                self.redis_client = None
        
        # Metrics collection
        self.metrics_buffer: List[Metric] = []
        self.metrics_flush_interval = 30  # seconds
        
        # Alerts
        self.active_alerts: Dict[str, Alert] = {}
        self.alert_rules: List[Dict[str, Any]] = []
        
        # Performance tracking
        self.performance_baselines: Dict[str, float] = {}
        self.performance_thresholds: Dict[str, Dict[str, float]] = {}
        
        # Cost tracking
        self.cost_tracking: Dict[str, List[Dict[str, Any]]] = {}
        
        # System resource monitoring
        self.resource_monitoring_enabled = True
        
        # Initialize alert rules
        self._initialize_alert_rules()
        
        # Initialize performance thresholds
        self._initialize_performance_thresholds()
        
        # Start background monitoring tasks
        self._start_background_tasks()
    
    async def _init_redis(self):
        """Initialize Redis connection"""
        try:
            self.redis_client = redis.from_url(settings.REDIS_URL)
            await self.redis_client.ping()
            self.logger.info("Redis connection established for monitoring")
        except Exception as e:
            self.logger.warning(f"Redis connection failed: {e}")
            self.redis_client = None
    
    def _initialize_alert_rules(self):
        """Initialize alert rules"""
        self.alert_rules = [
            {
                "id": "high_error_rate",
                "metric": "agent_failure_rate",
                "threshold": 0.2,
                "comparison": "greater_than",
                "level": AlertLevel.WARNING,
                "title": "High Agent Failure Rate",
                "message": "Agent failure rate exceeded 20%"
            },
            {
                "id": "slow_response_time",
                "metric": "avg_response_time",
                "threshold": 300,  # 5 minutes
                "comparison": "greater_than",
                "level": AlertLevel.WARNING,
                "title": "Slow Response Time",
                "message": "Average response time exceeded 5 minutes"
            },
            {
                "id": "high_cost_rate",
                "metric": "hourly_cost",
                "threshold": 10.0,
                "comparison": "greater_than",
                "level": AlertLevel.ERROR,
                "title": "High Cost Rate",
                "message": "Hourly cost exceeded $10"
            },
            {
                "id": "circuit_breaker_open",
                "metric": "circuit_breaker_open_count",
                "threshold": 1,
                "comparison": "greater_than_or_equal",
                "level": AlertLevel.CRITICAL,
                "title": "Circuit Breaker Open",
                "message": "One or more AI service circuit breakers are open"
            },
            {
                "id": "memory_usage_high",
                "metric": "memory_usage_percent",
                "threshold": 85,
                "comparison": "greater_than",
                "level": AlertLevel.WARNING,
                "title": "High Memory Usage",
                "message": "Memory usage exceeded 85%"
            }
        ]
    
    def _initialize_performance_thresholds(self):
        """Initialize performance thresholds for different metrics"""
        self.performance_thresholds = {
            "agent_execution_time": {
                "concept_planner": {"warning": 90, "critical": 180},
                "script_writer": {"warning": 120, "critical": 240},
                "image_generator": {"warning": 240, "critical": 480},
                "video_generator": {"warning": 420, "critical": 900},
                "video_composer": {"warning": 180, "critical": 360},
                "quality_checker": {"warning": 60, "critical": 120}
            },
            "task_completion_time": {
                "warning": 600,  # 10 minutes
                "critical": 1800  # 30 minutes
            },
            "api_response_time": {
                "warning": 30,  # 30 seconds
                "critical": 60   # 1 minute
            },
            "error_rate": {
                "warning": 0.1,  # 10%
                "critical": 0.25  # 25%
            }
        }
    
    def _start_background_tasks(self):
        """Start background monitoring tasks"""
        # These would typically be started as background tasks in the main application
        # For now, we'll provide the task functions that can be called
        pass
    
    async def record_metric(
        self,
        name: str,
        value: float,
        metric_type: MetricType = MetricType.GAUGE,
        labels: Optional[Dict[str, str]] = None,
        description: str = ""
    ):
        """Record a metric"""
        
        metric = Metric(
            name=name,
            value=value,
            metric_type=metric_type,
            timestamp=datetime.now(),
            labels=labels or {},
            description=description
        )
        
        self.metrics_buffer.append(metric)
        
        # Flush buffer if it's getting large
        if len(self.metrics_buffer) >= 100:
            await self._flush_metrics()
        
        # Check for alerts
        await self._check_alert_rules(metric)
    
    async def record_task_start(self, task: Task):
        """Record task start metrics"""
        await self.record_metric(
            "tasks_started_total",
            1,
            MetricType.COUNTER,
            labels={
                "task_type": task.task_type.value,
                "task_id": str(task.task_id)
            },
            description="Total number of tasks started"
        )
        
        await self.record_metric(
            "active_tasks",
            1,
            MetricType.GAUGE,
            labels={"status": "in_progress"},
            description="Number of active tasks"
        )
    
    async def record_task_completion(self, task: Task, duration: float):
        """Record task completion metrics"""
        status_label = "completed" if task.is_completed else "failed"
        
        await self.record_metric(
            "tasks_completed_total",
            1,
            MetricType.COUNTER,
            labels={
                "task_type": task.task_type.value,
                "status": status_label
            },
            description="Total number of tasks completed"
        )
        
        await self.record_metric(
            "task_duration_seconds",
            duration,
            MetricType.HISTOGRAM,
            labels={
                "task_type": task.task_type.value,
                "status": status_label
            },
            description="Task execution duration in seconds"
        )
        
        await self.record_metric(
            "active_tasks",
            -1,
            MetricType.GAUGE,
            labels={"status": "in_progress"},
            description="Number of active tasks"
        )
        
        # Check if duration exceeds thresholds
        thresholds = self.performance_thresholds.get("task_completion_time", {})
        if duration > thresholds.get("critical", float('inf')):
            await self._create_alert(
                "slow_task_execution",
                AlertLevel.CRITICAL,
                "Slow Task Execution",
                f"Task {task.task_id} took {duration:.1f}s to complete",
                source="task_monitoring"
            )
        elif duration > thresholds.get("warning", float('inf')):
            await self._create_alert(
                "slow_task_execution",
                AlertLevel.WARNING,
                "Slow Task Execution",
                f"Task {task.task_id} took {duration:.1f}s to complete",
                source="task_monitoring"
            )
    
    async def record_agent_execution(
        self,
        agent_type: AgentType,
        execution: Dict[str, Any],
        duration: float
    ):
        """Record agent execution metrics（DB 审计已移除，仅记录轻量计数）。"""

        status_label = 'completed'
        try:
            if isinstance(execution, dict):
                status_label = str(execution.get('status') or status_label)
        except Exception:
            status_label = 'completed'

        await self.record_metric(
            'agent_executions_total',
            1,
            MetricType.COUNTER,
            labels={
                'agent_type': agent_type.value,
                'status': status_label
            },
            description='Total number of agent executions'
        )

        await self.record_metric(
            'agent_execution_duration_seconds',
            duration,
            MetricType.HISTOGRAM,
            labels={
                'agent_type': agent_type.value,
                'status': status_label
            },
            description='Agent execution duration in seconds'
        )
        # 成本/Token 统计依赖审计表，已停用

    async def record_ai_service_call(
        self,
        provider: AIServiceProvider,
        operation: str,
        duration: float,
        success: bool,
        cost: float = 0.0,
        tokens_used: int = 0
    ):
        """Record AI service call metrics"""
        
        status_label = "success" if success else "failure"
        
        await self.record_metric(
            "ai_service_calls_total",
            1,
            MetricType.COUNTER,
            labels={
                "provider": provider.value,
                "operation": operation,
                "status": status_label
            },
            description="Total number of AI service calls"
        )
        
        await self.record_metric(
            "ai_service_response_time_seconds",
            duration,
            MetricType.HISTOGRAM,
            labels={
                "provider": provider.value,
                "operation": operation
            },
            description="AI service response time in seconds"
        )
        
        if cost > 0:
            await self.record_metric(
                "ai_service_cost_usd",
                cost,
                MetricType.HISTOGRAM,
                labels={
                    "provider": provider.value,
                    "operation": operation
                },
                description="AI service call cost in USD"
            )
        
        if tokens_used > 0:
            await self.record_metric(
                "ai_service_tokens_used",
                tokens_used,
                MetricType.HISTOGRAM,
                labels={
                    "provider": provider.value,
                    "operation": operation
                },
                description="Tokens used in AI service call"
            )
    
    async def record_system_metrics(self):
        """Record system resource metrics"""
        
        if not self.resource_monitoring_enabled:
            return
        
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            await self.record_metric(
                "cpu_usage_percent",
                cpu_percent,
                MetricType.GAUGE,
                description="CPU usage percentage"
            )
            
            # Memory usage
            memory = psutil.virtual_memory()
            await self.record_metric(
                "memory_usage_percent",
                memory.percent,
                MetricType.GAUGE,
                description="Memory usage percentage"
            )
            
            await self.record_metric(
                "memory_available_bytes",
                memory.available,
                MetricType.GAUGE,
                description="Available memory in bytes"
            )
            
            # Disk usage
            disk = psutil.disk_usage('/')
            await self.record_metric(
                "disk_usage_percent",
                (disk.used / disk.total) * 100,
                MetricType.GAUGE,
                description="Disk usage percentage"
            )
            
            # Network I/O
            network = psutil.net_io_counters()
            await self.record_metric(
                "network_bytes_sent",
                network.bytes_sent,
                MetricType.COUNTER,
                description="Total network bytes sent"
            )
            
            await self.record_metric(
                "network_bytes_received",
                network.bytes_recv,
                MetricType.COUNTER,
                description="Total network bytes received"
            )
            
        except Exception as e:
            self.logger.warning(f"Failed to collect system metrics: {e}")
    
    async def _flush_metrics(self):
        """Flush metrics buffer to storage"""
        
        if not self.metrics_buffer:
            return
        
        try:
            # Store metrics in Redis
            if self.redis_client:
                pipeline = self.redis_client.pipeline()
                
                for metric in self.metrics_buffer:
                    metric_key = f"metrics:{metric.name}"
                    metric_data = {
                        "value": metric.value,
                        "timestamp": metric.timestamp.isoformat(),
                        "labels": metric.labels,
                        "type": metric.metric_type.value
                    }
                    
                    # Store as time series data
                    pipeline.zadd(
                        metric_key,
                        {json.dumps(metric_data): time.time()}
                    )
                    
                    # Set expiration (keep metrics for 7 days)
                    pipeline.expire(metric_key, 604800)
                
                await pipeline.execute()
            
            # Clear buffer
            self.metrics_buffer.clear()
            
        except Exception as e:
            self.logger.error(f"Failed to flush metrics: {e}")

    def get_metrics_snapshot(self) -> List[Dict[str, Any]]:
        """Return a lightweight snapshot of current buffered metrics.

        This does not clear the buffer. Useful for quick inspection or tests.
        """
        snapshot: List[Dict[str, Any]] = []
        for m in self.metrics_buffer:
            snapshot.append({
                "name": m.name,
                "value": m.value,
                "type": m.metric_type.value,
                "timestamp": m.timestamp.isoformat(),
                "labels": m.labels,
                "description": m.description,
            })
        return snapshot

    async def dump_metrics_to_file(self, file_path: Optional[str] = None, max_items: int = 500):
        """Dump current buffered metrics to a local JSON file (for quick inspection).

        Args:
            file_path: Path to write JSON (defaults to backend/storage/metrics_snapshot.json)
            max_items: Limit number of items written to avoid large files
        """
        try:
            base_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "storage")
            if not file_path:
                file_path = os.path.join(base_dir, "metrics_snapshot.json")
            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            snapshot = self.get_metrics_snapshot()[:max_items]
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump({
                    "generated_at": datetime.now().isoformat(),
                    "count": len(snapshot),
                    "metrics": snapshot,
                }, f, ensure_ascii=False, indent=2)
            self.logger.info(f"Metrics snapshot written to {file_path} ({len(snapshot)} items)")
        except Exception as e:
            self.logger.warning(f"Failed to dump metrics to file: {e}")

    def log_metrics_snapshot(self, max_items: int = 50):
        """Log a small snapshot of current metrics (for quick debugging)."""
        try:
            snapshot = self.get_metrics_snapshot()[:max_items]
            self.logger.info(f"Metrics snapshot ({len(snapshot)} items):\n{json.dumps(snapshot, ensure_ascii=False)[:2000]}")
        except Exception as e:
            self.logger.warning(f"Failed to log metrics snapshot: {e}")
    
    async def _check_alert_rules(self, metric: Metric):
        """Check if metric triggers any alert rules"""
        
        for rule in self.alert_rules:
            if rule["metric"] == metric.name:
                threshold = rule["threshold"]
                comparison = rule["comparison"]
                
                triggered = False
                if comparison == "greater_than" and metric.value > threshold:
                    triggered = True
                elif comparison == "greater_than_or_equal" and metric.value >= threshold:
                    triggered = True
                elif comparison == "less_than" and metric.value < threshold:
                    triggered = True
                elif comparison == "less_than_or_equal" and metric.value <= threshold:
                    triggered = True
                elif comparison == "equals" and metric.value == threshold:
                    triggered = True
                
                if triggered:
                    await self._create_alert(
                        rule["id"],
                        AlertLevel(rule["level"]),
                        rule["title"],
                        f"{rule['message']} (value: {metric.value})",
                        source="alert_rules"
                    )
    
    async def _create_alert(
        self,
        alert_id: str,
        level: AlertLevel,
        title: str,
        message: str,
        source: str
    ):
        """Create a new alert"""
        
        # Check if alert already exists and is not resolved
        if alert_id in self.active_alerts and not self.active_alerts[alert_id].resolved:
            return
        
        alert = Alert(
            id=alert_id,
            level=level,
            title=title,
            message=message,
            timestamp=datetime.now(),
            source=source
        )
        
        self.active_alerts[alert_id] = alert
        
        # Log alert
        if level == AlertLevel.CRITICAL:
            self.logger.critical(f"ALERT: {title} - {message}")
        elif level == AlertLevel.ERROR:
            self.logger.error(f"ALERT: {title} - {message}")
        elif level == AlertLevel.WARNING:
            self.logger.warning(f"ALERT: {title} - {message}")
        else:
            self.logger.info(f"ALERT: {title} - {message}")
        
        # Store alert in Redis
        if self.redis_client:
            try:
                alert_data = {
                    "id": alert.id,
                    "level": alert.level.value,
                    "title": alert.title,
                    "message": alert.message,
                    "timestamp": alert.timestamp.isoformat(),
                    "source": alert.source,
                    "resolved": alert.resolved
                }
                
                await self.redis_client.setex(
                    f"alert:{alert_id}",
                    86400,  # 24 hours
                    json.dumps(alert_data)
                )
            except Exception as e:
                self.logger.warning(f"Failed to store alert: {e}")
    
    async def resolve_alert(self, alert_id: str):
        """Resolve an active alert"""
        
        if alert_id in self.active_alerts:
            self.active_alerts[alert_id].resolved = True
            self.active_alerts[alert_id].resolution_time = datetime.now()
            
            # Update in Redis
            if self.redis_client:
                try:
                    alert = self.active_alerts[alert_id]
                    alert_data = {
                        "id": alert.id,
                        "level": alert.level.value,
                        "title": alert.title,
                        "message": alert.message,
                        "timestamp": alert.timestamp.isoformat(),
                        "source": alert.source,
                        "resolved": alert.resolved,
                        "resolution_time": alert.resolution_time.isoformat()
                    }
                    
                    await self.redis_client.setex(
                        f"alert:{alert_id}",
                        86400,  # 24 hours
                        json.dumps(alert_data)
                    )
                except Exception as e:
                    self.logger.warning(f"Failed to update resolved alert: {e}")
    
    async def get_metrics(
        self,
        metric_name: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        labels: Optional[Dict[str, str]] = None
    ) -> List[Dict[str, Any]]:
        """Get metrics from storage"""
        
        if not self.redis_client:
            return []
        
        try:
            # Default to last hour if no time range specified
            if not start_time:
                start_time = datetime.now() - timedelta(hours=1)
            if not end_time:
                end_time = datetime.now()
            
            # Get metrics from Redis
            metric_key = f"metrics:{metric_name}"
            start_timestamp = start_time.timestamp()
            end_timestamp = end_time.timestamp()
            
            raw_metrics = await self.redis_client.zrangebyscore(
                metric_key,
                start_timestamp,
                end_timestamp,
                withscores=True
            )
            
            metrics = []
            for raw_data, timestamp in raw_metrics:
                try:
                    metric_data = json.loads(raw_data.decode() if isinstance(raw_data, bytes) else raw_data)
                    
                    # Filter by labels if specified
                    if labels:
                        metric_labels = metric_data.get("labels", {})
                        if not all(metric_labels.get(k) == v for k, v in labels.items()):
                            continue
                    
                    metrics.append({
                        "value": metric_data["value"],
                        "timestamp": metric_data["timestamp"],
                        "labels": metric_data.get("labels", {}),
                        "type": metric_data.get("type", "gauge")
                    })
                except (json.JSONDecodeError, KeyError):
                    continue
            
            return metrics
            
        except Exception as e:
            self.logger.error(f"Failed to get metrics: {e}")
            return []
    
    async def get_performance_summary(self, db: Session) -> Dict[str, Any]:
        """Get comprehensive performance summary"""
        
        # Get task statistics from database
        total_tasks = db.query(Task).count()
        completed_tasks = db.query(Task).filter(Task.status == TaskStatus.COMPLETED).count()
        failed_tasks = db.query(Task).filter(Task.status == TaskStatus.FAILED).count()
        
        # AgentExecution 已移除，平均耗时与 agent 级统计不可用
        avg_duration = 0
        agent_stats = {}
        
        # Get AI service performance from enhanced client
        ai_service_metrics = enhanced_ai_client.get_performance_metrics()
        
        # Get active alerts
        active_alerts_count = len([a for a in self.active_alerts.values() if not a.resolved])
        
        return {
            "summary": {
                "total_tasks": total_tasks,
                "completed_tasks": completed_tasks,
                "failed_tasks": failed_tasks,
                "success_rate": completed_tasks / total_tasks if total_tasks > 0 else 0,
                "average_duration": avg_duration,
                "active_alerts": active_alerts_count
            },
            "agent_performance": agent_stats,
            "ai_service_performance": ai_service_metrics,
            "alerts": {
                "active": len([a for a in self.active_alerts.values() if not a.resolved]),
                "total": len(self.active_alerts)
            },
            "timestamp": datetime.now().isoformat()
        }
    
    async def get_cost_analysis(self, db: Session, days: int = 7) -> Dict[str, Any]:
        """Get cost analysis and optimization recommendations"""
        
        # AgentExecution 表已移除，成本分析暂不可用
        start_date = datetime.now() - timedelta(days=days)
        total_cost = 0.0
        cost_by_agent = {agent_type.value: {"total_cost": 0, "executions": 0, "average_cost_per_execution": 0} for agent_type in AgentType}
        
        # Cost breakdown by AI service provider
        ai_service_costs = {}
        for provider, metrics in enhanced_ai_client.get_performance_metrics()["providers"].items():
            ai_service_costs[provider] = {
                "total_cost": metrics.get("total_cost", 0),
                "requests": metrics.get("total_requests", 0),
                "average_cost_per_request": (
                    metrics.get("total_cost", 0) / metrics.get("total_requests", 1)
                    if metrics.get("total_requests", 0) > 0 else 0
                )
            }
        
        # Cost optimization recommendations
        recommendations = []
        
        # Check for expensive agents
        for agent_type, stats in cost_by_agent.items():
            if stats["average_cost_per_execution"] > 1.0:  # $1 threshold
                recommendations.append({
                    "type": "cost_optimization",
                    "agent": agent_type,
                    "message": f"High cost per execution for {agent_type}",
                    "recommendation": "Consider caching or optimization strategies",
                    "potential_savings": stats["total_cost"] * 0.2  # Estimate 20% savings
                })
        
        # Check cache hit rates
        cache_stats = enhanced_ai_client.get_performance_metrics().get("cache_stats", {})
        potential_cache_savings = cache_stats.get("total_cache_cost_saved", 0)
        
        if potential_cache_savings > 0:
            recommendations.append({
                "type": "caching",
                "message": "Caching is providing cost savings",
                "savings_to_date": potential_cache_savings,
                "recommendation": "Continue current caching strategy"
            })
        
        return {
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": datetime.now().isoformat(),
                "days": days
            },
            "total_cost": total_cost,
            "daily_average_cost": total_cost / days,
            "cost_by_agent": cost_by_agent,
            "cost_by_ai_service": ai_service_costs,
            "recommendations": recommendations,
            "estimated_monthly_cost": total_cost * (30 / days) if days > 0 else 0
        }
    
    async def generate_performance_insights(self, db: Session) -> List[PerformanceInsight]:
        """Generate performance insights and recommendations"""
        
        insights = []
        
        # Analyze task success rates
        total_tasks = db.query(Task).count()
        failed_tasks = db.query(Task).filter(Task.status == TaskStatus.FAILED).count()
        
        if total_tasks > 10:  # Only analyze if we have enough data
            failure_rate = failed_tasks / total_tasks
            
            if failure_rate > 0.1:  # > 10% failure rate
                insights.append(PerformanceInsight(
                    category="reliability",
                    title="High Task Failure Rate",
                    description=f"Task failure rate is {failure_rate:.1%}",
                    impact="high",
                    recommendation="Investigate common failure patterns and improve error handling",
                    metric_evidence=[f"failure_rate: {failure_rate:.3f}"]
                ))
        
        # AgentExecution 审计已移除，此处不再分析 agent 级别执行历史

        # Check for resource utilization issues
        try:
            memory_percent = psutil.virtual_memory().percent
            cpu_percent = psutil.cpu_percent()
            
            if memory_percent > 80:
                insights.append(PerformanceInsight(
                    category="resources",
                    title="High Memory Usage",
                    description=f"Memory usage is {memory_percent:.1f}%",
                    impact="medium",
                    recommendation="Consider increasing memory allocation or optimizing memory usage",
                    metric_evidence=[f"memory_usage: {memory_percent:.1f}%"]
                ))
            
            if cpu_percent > 80:
                insights.append(PerformanceInsight(
                    category="resources",
                    title="High CPU Usage",
                    description=f"CPU usage is {cpu_percent:.1f}%",
                    impact="medium",
                    recommendation="Consider optimizing compute-intensive operations or scaling resources",
                    metric_evidence=[f"cpu_usage: {cpu_percent:.1f}%"]
                ))
        except Exception as e:
            self.logger.warning(f"Failed to get system resource metrics: {e}")
        
        return insights
    
    def get_active_alerts(self) -> List[Alert]:
        """Get all active alerts"""
        return [alert for alert in self.active_alerts.values() if not alert.resolved]
    
    def get_all_alerts(self) -> List[Alert]:
        """Get all alerts (active and resolved)"""
        return list(self.active_alerts.values())
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform system health check"""
        
        health_status = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "components": {}
        }
        
        # Check Redis connection
        if self.redis_client:
            try:
                await self.redis_client.ping()
                health_status["components"]["redis"] = {"status": "healthy"}
            except Exception as e:
                health_status["components"]["redis"] = {"status": "unhealthy", "error": str(e)}
                health_status["status"] = "degraded"
        else:
            health_status["components"]["redis"] = {"status": "unavailable"}
            health_status["status"] = "degraded"
        
        # Check AI services
        ai_health = await enhanced_ai_client.health_check()
        health_status["components"]["ai_services"] = ai_health
        
        if ai_health["overall_status"] != "healthy":
            health_status["status"] = "degraded"
        
        # Check system resources
        try:
            memory_percent = psutil.virtual_memory().percent
            cpu_percent = psutil.cpu_percent()
            disk_percent = psutil.disk_usage('/').percent
            
            resource_status = "healthy"
            if memory_percent > 90 or cpu_percent > 90 or disk_percent > 90:
                resource_status = "critical"
                health_status["status"] = "unhealthy"
            elif memory_percent > 80 or cpu_percent > 80 or disk_percent > 80:
                resource_status = "warning"
                if health_status["status"] == "healthy":
                    health_status["status"] = "degraded"
            
            health_status["components"]["system_resources"] = {
                "status": resource_status,
                "memory_percent": memory_percent,
                "cpu_percent": cpu_percent,
                "disk_percent": disk_percent
            }
        except Exception as e:
            health_status["components"]["system_resources"] = {
                "status": "unavailable",
                "error": str(e)
            }
        
        # Check active alerts
        critical_alerts = len([a for a in self.active_alerts.values() 
                             if not a.resolved and a.level == AlertLevel.CRITICAL])
        
        if critical_alerts > 0:
            health_status["status"] = "unhealthy"
            health_status["critical_alerts"] = critical_alerts
        
        return health_status


# Global instance
monitoring_service = MonitoringService()
