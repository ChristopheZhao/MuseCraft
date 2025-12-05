"""
Workflow Optimization Engine
- Intelligent parallel execution of compatible agents
- Dynamic load balancing and resource allocation
- Advanced caching and result reuse
- Workflow dependency management
- Performance optimization and bottleneck detection
"""
import asyncio
import logging
import time
from typing import Dict, Any, List, Optional, Set, Tuple, Callable, Union
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
import json
import hashlib
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy.orm import Session

from ..models import Task, AgentType, TaskStatus
from ..models.agent import AgentStatus
from .enhanced_ai_client import enhanced_ai_client
import redis.asyncio as redis
from ..core.config import settings


class ExecutionStrategy(str, Enum):
    SEQUENTIAL = "sequential"           # Execute agents one by one
    PARALLEL = "parallel"              # Execute compatible agents in parallel
    ADAPTIVE = "adaptive"              # Intelligently choose based on resources
    PIPELINE = "pipeline"              # Pipeline execution with data streaming


class OptimizationLevel(str, Enum):
    CONSERVATIVE = "conservative"       # Prioritize reliability
    BALANCED = "balanced"              # Balance speed and reliability
    AGGRESSIVE = "aggressive"          # Maximize speed and parallelization


@dataclass
class AgentNode:
    """Represents an agent in the workflow graph"""
    agent_type: AgentType
    dependencies: Set[AgentType] = field(default_factory=set)
    dependents: Set[AgentType] = field(default_factory=set)
    estimated_duration: float = 60.0  # seconds
    resource_requirements: Dict[str, float] = field(default_factory=dict)
    can_run_parallel: bool = True
    priority: int = 1  # Lower number = higher priority


@dataclass
class ExecutionPlan:
    """Execution plan for workflow optimization"""
    execution_groups: List[List[AgentType]]  # Groups that can run in parallel
    estimated_total_time: float
    resource_allocation: Dict[AgentType, Dict[str, float]]
    caching_strategy: Dict[AgentType, Dict[str, Any]]
    fallback_options: Dict[AgentType, List[AgentType]]


@dataclass
class WorkflowMetrics:
    """Metrics for workflow execution"""
    total_duration: float = 0.0
    agent_durations: Dict[AgentType, float] = field(default_factory=dict)
    parallel_efficiency: float = 0.0
    cache_hit_rate: float = 0.0
    cost_savings: float = 0.0
    bottlenecks: List[AgentType] = field(default_factory=list)


class WorkflowOptimizer:
    """Advanced workflow optimization engine"""
    
    def __init__(self):
        self.logger = logging.getLogger("workflow_optimizer")
        
        # Initialize Redis for distributed coordination
        self.redis_client = None
        self._init_redis()
        
        # Workflow graph and dependencies
        self.workflow_graph = self._build_workflow_graph()
        
        # Performance history for optimization
        self.performance_history: Dict[str, List[WorkflowMetrics]] = {}
        
        # Resource pool management
        self.max_concurrent_agents = 4
        self.resource_limits = {
            "cpu": 8.0,      # CPU cores
            "memory": 16.0,  # GB
            "gpu": 1.0,      # GPU units
            "api_calls": 60  # API calls per minute
        }
        
        # Caching configuration
        self.cache_strategies = {
            AgentType.CONCEPT_PLANNER: {"ttl": 3600, "reuse_threshold": 0.8},
            AgentType.SCRIPT_WRITER: {"ttl": 1800, "reuse_threshold": 0.7},
            AgentType.IMAGE_GENERATOR: {"ttl": 7200, "reuse_threshold": 0.9},
            AgentType.VIDEO_GENERATOR: {"ttl": 3600, "reuse_threshold": 0.8},
            AgentType.VIDEO_COMPOSER: {"ttl": 1800, "reuse_threshold": 0.6},
            AgentType.QUALITY_CHECKER: {"ttl": 900, "reuse_threshold": 0.7}
        }
    
    async def _init_redis(self):
        """Initialize Redis connection for distributed coordination"""
        try:
            self.redis_client = redis.from_url(settings.REDIS_URL)
            await self.redis_client.ping()
            self.logger.info("Redis connection established for workflow optimization")
        except Exception as e:
            self.logger.warning(f"Redis connection failed: {e}")
            self.redis_client = None
    
    def _build_workflow_graph(self) -> Dict[AgentType, AgentNode]:
        """Build workflow dependency graph"""
        
        graph = {
            AgentType.CONCEPT_PLANNER: AgentNode(
                agent_type=AgentType.CONCEPT_PLANNER,
                dependencies=set(),
                estimated_duration=45.0,
                resource_requirements={"cpu": 0.5, "memory": 1.0, "api_calls": 2},
                can_run_parallel=True,
                priority=1
            ),
            AgentType.SCRIPT_WRITER: AgentNode(
                agent_type=AgentType.SCRIPT_WRITER,
                dependencies={AgentType.CONCEPT_PLANNER},
                estimated_duration=60.0,
                resource_requirements={"cpu": 0.5, "memory": 1.0, "api_calls": 3},
                can_run_parallel=True,
                priority=2
            ),
            AgentType.IMAGE_GENERATOR: AgentNode(
                agent_type=AgentType.IMAGE_GENERATOR,
                dependencies={AgentType.CONCEPT_PLANNER, AgentType.SCRIPT_WRITER},
                estimated_duration=180.0,
                resource_requirements={"cpu": 1.0, "memory": 2.0, "gpu": 0.8, "api_calls": 8},
                can_run_parallel=True,
                priority=2
            ),
            AgentType.VIDEO_GENERATOR: AgentNode(
                agent_type=AgentType.VIDEO_GENERATOR,
                dependencies={AgentType.IMAGE_GENERATOR},
                estimated_duration=300.0,
                resource_requirements={"cpu": 2.0, "memory": 4.0, "gpu": 1.0, "api_calls": 6},
                can_run_parallel=False,  # Video generation is resource intensive
                priority=3
            ),
            AgentType.VIDEO_COMPOSER: AgentNode(
                agent_type=AgentType.VIDEO_COMPOSER,
                dependencies={AgentType.VIDEO_GENERATOR},
                estimated_duration=120.0,
                resource_requirements={"cpu": 1.5, "memory": 3.0, "api_calls": 0},
                can_run_parallel=True,
                priority=4
            ),
            AgentType.QUALITY_CHECKER: AgentNode(
                agent_type=AgentType.QUALITY_CHECKER,
                dependencies={AgentType.VIDEO_COMPOSER},
                estimated_duration=45.0,
                resource_requirements={"cpu": 0.5, "memory": 1.0, "api_calls": 2},
                can_run_parallel=True,
                priority=5
            )
        }
        
        # Build reverse dependencies
        for node in graph.values():
            for dep in node.dependencies:
                graph[dep].dependents.add(node.agent_type)
        
        return graph
    
    async def create_execution_plan(
        self,
        task: Task,
        input_data: Dict[str, Any],
        strategy: ExecutionStrategy = ExecutionStrategy.ADAPTIVE,
        optimization_level: OptimizationLevel = OptimizationLevel.BALANCED
    ) -> ExecutionPlan:
        """Create optimized execution plan for workflow"""
        
        self.logger.info(f"Creating execution plan for task {task.task_id} with strategy {strategy.value}")
        
        # Analyze task requirements and historical data
        task_signature = self._generate_task_signature(task, input_data)
        historical_metrics = await self._get_historical_metrics(task_signature)
        
        # Check for cached results
        cached_results = await self._check_cached_results(task, input_data)
        
        # Determine which agents can be skipped due to caching
        skippable_agents = set()
        for agent_type, cache_data in cached_results.items():
            if cache_data and self._should_reuse_cache(agent_type, cache_data, input_data):
                skippable_agents.add(agent_type)
        
        # Build execution groups considering dependencies and resources
        execution_groups = self._build_execution_groups(
            skippable_agents, strategy, optimization_level, historical_metrics
        )
        
        # Estimate execution time and allocate resources
        estimated_time, resource_allocation = self._estimate_execution_time(
            execution_groups, historical_metrics, skippable_agents
        )
        
        # Create caching strategy
        caching_strategy = self._create_caching_strategy(task, input_data)
        
        # Define fallback options
        fallback_options = self._create_fallback_options()
        
        plan = ExecutionPlan(
            execution_groups=execution_groups,
            estimated_total_time=estimated_time,
            resource_allocation=resource_allocation,
            caching_strategy=caching_strategy,
            fallback_options=fallback_options
        )
        
        self.logger.info(f"Execution plan created: {len(execution_groups)} groups, "
                        f"estimated time: {estimated_time:.1f}s")
        
        return plan
    
    def _build_execution_groups(
        self,
        skippable_agents: Set[AgentType],
        strategy: ExecutionStrategy,
        optimization_level: OptimizationLevel,
        historical_metrics: Optional[List[WorkflowMetrics]]
    ) -> List[List[AgentType]]:
        """Build execution groups based on dependencies and strategy"""
        
        # Get all agents excluding skippable ones
        remaining_agents = set(self.workflow_graph.keys()) - skippable_agents
        
        if strategy == ExecutionStrategy.SEQUENTIAL:
            return self._build_sequential_groups(remaining_agents)
        elif strategy == ExecutionStrategy.PARALLEL:
            return self._build_parallel_groups(remaining_agents, optimization_level)
        elif strategy == ExecutionStrategy.PIPELINE:
            return self._build_pipeline_groups(remaining_agents)
        else:  # ADAPTIVE
            return self._build_adaptive_groups(remaining_agents, optimization_level, historical_metrics)
    
    def _build_sequential_groups(self, agents: Set[AgentType]) -> List[List[AgentType]]:
        """Build sequential execution groups"""
        
        # Topological sort for dependency order
        ordered_agents = self._topological_sort(agents)
        return [[agent] for agent in ordered_agents]
    
    def _build_parallel_groups(
        self,
        agents: Set[AgentType],
        optimization_level: OptimizationLevel
    ) -> List[List[AgentType]]:
        """Build parallel execution groups"""
        
        groups = []
        remaining = agents.copy()
        
        while remaining:
            # Find agents with no dependencies in remaining set
            current_group = []
            for agent in list(remaining):
                node = self.workflow_graph[agent]
                if not (node.dependencies & remaining):
                    # Check resource constraints
                    if self._can_add_to_group(current_group, agent, optimization_level):
                        current_group.append(agent)
            
            # Remove current group from remaining
            for agent in current_group:
                remaining.discard(agent)
            
            if current_group:
                groups.append(current_group)
            else:
                # Fallback: add one agent to break deadlock
                agent = min(remaining, key=lambda a: len(self.workflow_graph[a].dependencies))
                groups.append([agent])
                remaining.discard(agent)
        
        return groups
    
    def _build_pipeline_groups(self, agents: Set[AgentType]) -> List[List[AgentType]]:
        """Build pipeline execution groups with data streaming"""
        
        # For pipeline, we want to minimize the number of groups
        # while respecting dependencies
        groups = []
        remaining = agents.copy()
        
        # Group agents that can stream data between each other
        while remaining:
            current_group = []
            
            # Start with highest priority agent with no dependencies
            start_agent = None
            for agent in remaining:
                node = self.workflow_graph[agent]
                if not (node.dependencies & remaining):
                    if start_agent is None or node.priority < self.workflow_graph[start_agent].priority:
                        start_agent = agent
            
            if start_agent:
                current_group.append(start_agent)
                remaining.discard(start_agent)
                
                # Add dependent agents that can be pipelined
                while True:
                    added_any = False
                    for agent in list(remaining):
                        node = self.workflow_graph[agent]
                        # Check if all dependencies are in current group or previous groups
                        deps_satisfied = all(
                            dep not in remaining for dep in node.dependencies
                        )
                        if deps_satisfied and len(current_group) < 3:  # Limit pipeline length
                            current_group.append(agent)
                            remaining.discard(agent)
                            added_any = True
                            break
                    
                    if not added_any:
                        break
            
            if current_group:
                groups.append(current_group)
            elif remaining:
                # Fallback
                agent = remaining.pop()
                groups.append([agent])
        
        return groups
    
    def _build_adaptive_groups(
        self,
        agents: Set[AgentType],
        optimization_level: OptimizationLevel,
        historical_metrics: Optional[List[WorkflowMetrics]]
    ) -> List[List[AgentType]]:
        """Build adaptive execution groups based on historical performance"""
        
        # Analyze historical bottlenecks
        bottleneck_agents = set()
        if historical_metrics:
            for metrics in historical_metrics[-10:]:  # Last 10 executions
                bottleneck_agents.update(metrics.bottlenecks)
        
        # Start with parallel strategy
        groups = self._build_parallel_groups(agents, optimization_level)
        
        # Optimize based on historical data
        if historical_metrics and bottleneck_agents:
            # Separate bottleneck agents to dedicated groups
            optimized_groups = []
            for group in groups:
                bottleneck_in_group = [agent for agent in group if agent in bottleneck_agents]
                non_bottleneck_in_group = [agent for agent in group if agent not in bottleneck_agents]
                
                # Create separate groups for bottlenecks
                for bottleneck_agent in bottleneck_in_group:
                    optimized_groups.append([bottleneck_agent])
                
                # Keep non-bottlenecks together if any
                if non_bottleneck_in_group:
                    optimized_groups.append(non_bottleneck_in_group)
            
            groups = optimized_groups if optimized_groups else groups
        
        return groups
    
    def _can_add_to_group(
        self,
        current_group: List[AgentType],
        candidate: AgentType,
        optimization_level: OptimizationLevel
    ) -> bool:
        """Check if agent can be added to current execution group"""
        
        candidate_node = self.workflow_graph[candidate]
        
        # Check if agent supports parallel execution
        if not candidate_node.can_run_parallel:
            return len(current_group) == 0
        
        # Calculate total resource requirements
        total_resources = {"cpu": 0, "memory": 0, "gpu": 0, "api_calls": 0}
        for agent in current_group:
            node = self.workflow_graph[agent]
            for resource, amount in node.resource_requirements.items():
                total_resources[resource] += amount
        
        # Add candidate requirements
        for resource, amount in candidate_node.resource_requirements.items():
            total_resources[resource] += amount
        
        # Check against limits based on optimization level
        multipliers = {
            OptimizationLevel.CONSERVATIVE: 0.7,
            OptimizationLevel.BALANCED: 0.85,
            OptimizationLevel.AGGRESSIVE: 1.0
        }
        multiplier = multipliers[optimization_level]
        
        for resource, used in total_resources.items():
            if used > self.resource_limits.get(resource, float('inf')) * multiplier:
                return False
        
        return True
    
    def _topological_sort(self, agents: Set[AgentType]) -> List[AgentType]:
        """Topological sort of agents based on dependencies"""
        
        result = []
        remaining = agents.copy()
        temp_mark = set()
        perm_mark = set()
        
        def visit(agent: AgentType):
            if agent in perm_mark:
                return
            if agent in temp_mark:
                raise ValueError("Circular dependency detected")
            
            temp_mark.add(agent)
            
            # Visit dependencies first
            node = self.workflow_graph[agent]
            for dep in node.dependencies:
                if dep in remaining:
                    visit(dep)
            
            temp_mark.remove(agent)
            perm_mark.add(agent)
            result.append(agent)
        
        while remaining:
            # Find agent with no dependencies in remaining set
            agent = None
            for candidate in remaining:
                node = self.workflow_graph[candidate]
                if not (node.dependencies & remaining):
                    agent = candidate
                    break
            
            if agent is None:
                # Pick any remaining agent (shouldn't happen with valid DAG)
                agent = next(iter(remaining))
            
            if agent not in perm_mark:
                visit(agent)
            remaining.discard(agent)
        
        return result
    
    async def execute_workflow_optimized(
        self,
        task: Task,
        input_data: Dict[str, Any],
        execution_plan: ExecutionPlan,
        agents: Dict[AgentType, Any],  # Agent instances
        db: Session
    ) -> Dict[str, Any]:
        """Execute workflow with optimization"""
        
        self.logger.info(f"Starting optimized workflow execution for task {task.task_id}")
        
        start_time = time.time()
        workflow_data = input_data.copy()
        workflow_results = {}
        metrics = WorkflowMetrics()
        
        try:
            # Execute each group
            for group_index, agent_group in enumerate(execution_plan.execution_groups):
                group_start_time = time.time()
                
                self.logger.info(f"Executing group {group_index + 1}: {[a.value for a in agent_group]}")
                
                # Update task progress
                progress = int((group_index / len(execution_plan.execution_groups)) * 90)
                task.update_progress(f"Executing group {group_index + 1}", progress)
                db.commit()
                
                if len(agent_group) == 1:
                    # Single agent execution
                    agent_type = agent_group[0]
                    agent = agents[agent_type]
                    
                    # Check cache first
                    cached_result = await self._get_cached_agent_result(
                        task, agent_type, workflow_data
                    )
                    
                    if cached_result:
                        self.logger.info(f"Using cached result for {agent_type.value}")
                        agent_result = cached_result
                        metrics.cache_hit_rate += 1
                    else:
                        # Execute agent
                        agent_start_time = time.time()
                        agent_result = await agent.execute(
                            task=task,
                            input_data=workflow_data,
                            db=db,
                            execution_order=group_index + 1
                        )
                        agent_duration = time.time() - agent_start_time
                        metrics.agent_durations[agent_type] = agent_duration
                        
                        # Cache result
                        await self._cache_agent_result(
                            task, agent_type, workflow_data, agent_result
                        )
                    
                    workflow_results[agent_type.value] = agent_result
                    workflow_data.update(agent_result)
                
                else:
                    # Parallel execution
                    parallel_results = await self._execute_agents_parallel(
                        agent_group, agents, task, workflow_data, db, group_index + 1
                    )
                    
                    for agent_type, agent_result in parallel_results.items():
                        workflow_results[agent_type.value] = agent_result
                        workflow_data.update(agent_result)
                        
                        # Update metrics
                        if hasattr(agent_result, 'execution_time'):
                            metrics.agent_durations[agent_type] = agent_result['execution_time']
                
                group_duration = time.time() - group_start_time
                
                # Check for bottlenecks
                avg_group_time = sum(execution_plan.estimated_total_time) / len(execution_plan.execution_groups)
                if group_duration > avg_group_time * 1.5:
                    metrics.bottlenecks.extend(agent_group)
                
                self.logger.info(f"Group {group_index + 1} completed in {group_duration:.1f}s")
            
            # Final progress update
            task.update_progress("Workflow completed", 100)
            task.status = TaskStatus.COMPLETED
            db.commit()
            
            # Calculate final metrics
            total_duration = time.time() - start_time
            metrics.total_duration = total_duration
            
            # Calculate parallel efficiency
            sequential_time = sum(execution_plan.estimated_total_time for group in execution_plan.execution_groups)
            metrics.parallel_efficiency = sequential_time / total_duration if total_duration > 0 else 1.0
            
            # Store metrics for future optimization
            await self._store_execution_metrics(task, metrics)
            
            self.logger.info(f"Workflow completed in {total_duration:.1f}s "
                           f"(efficiency: {metrics.parallel_efficiency:.2f}x)")
            
            return {
                "workflow_status": "completed",
                "results": workflow_results,
                "execution_metrics": {
                    "total_duration": total_duration,
                    "parallel_efficiency": metrics.parallel_efficiency,
                    "cache_hit_rate": metrics.cache_hit_rate / len(execution_plan.execution_groups),
                    "bottlenecks": [bt.value for bt in metrics.bottlenecks]
                },
                "final_video_url": workflow_results.get("video_composer", {}).get("final_video_url"),
                "quality_score": workflow_results.get("quality_checker", {}).get("quality_score")
            }
            
        except Exception as e:
            error_msg = f"Optimized workflow execution failed: {str(e)}"
            task.status = TaskStatus.FAILED
            task.add_error(error_msg)
            db.commit()
            
            self.logger.error(error_msg)
            raise Exception(error_msg) from e
    
    async def _execute_agents_parallel(
        self,
        agent_group: List[AgentType],
        agents: Dict[AgentType, Any],
        task: Task,
        workflow_data: Dict[str, Any],
        db: Session,
        execution_order: int
    ) -> Dict[AgentType, Dict[str, Any]]:
        """Execute multiple agents in parallel"""
        
        self.logger.info(f"Executing {len(agent_group)} agents in parallel")
        
        # Create tasks for parallel execution
        async def execute_single_agent(agent_type: AgentType) -> Tuple[AgentType, Dict[str, Any]]:
            agent = agents[agent_type]
            
            # Check cache first
            cached_result = await self._get_cached_agent_result(task, agent_type, workflow_data)
            if cached_result:
                self.logger.info(f"Using cached result for {agent_type.value}")
                return agent_type, cached_result
            
            # Execute agent
            start_time = time.time()
            result = await agent.execute(
                task=task,
                input_data=workflow_data,
                db=db,
                execution_order=execution_order
            )
            execution_time = time.time() - start_time
            result['execution_time'] = execution_time
            
            # Cache result
            await self._cache_agent_result(task, agent_type, workflow_data, result)
            
            return agent_type, result
        
        # Execute all agents in parallel with semaphore for resource control
        semaphore = asyncio.Semaphore(self.max_concurrent_agents)
        
        async def controlled_execution(agent_type: AgentType):
            async with semaphore:
                return await execute_single_agent(agent_type)
        
        # Wait for all agents to complete
        tasks = [controlled_execution(agent_type) for agent_type in agent_group]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        parallel_results = {}
        for result in results:
            if isinstance(result, Exception):
                raise result
            agent_type, agent_result = result
            parallel_results[agent_type] = agent_result
        
        return parallel_results
    
    def _generate_task_signature(self, task: Task, input_data: Dict[str, Any]) -> str:
        """Generate unique signature for task caching"""
        
        signature_data = {
            "task_type": task.task_type.value,
            "user_prompt": input_data.get("user_prompt", ""),
            "video_style": input_data.get("video_style", ""),
            "duration": input_data.get("duration", 30),
            "aspect_ratio": input_data.get("aspect_ratio", "16:9")
        }
        
        signature_str = json.dumps(signature_data, sort_keys=True)
        return hashlib.md5(signature_str.encode()).hexdigest()
    
    async def _get_historical_metrics(self, task_signature: str) -> Optional[List[WorkflowMetrics]]:
        """Get historical metrics for similar tasks"""
        
        if task_signature in self.performance_history:
            return self.performance_history[task_signature][-10:]  # Last 10 executions
        
        # Try to load from Redis
        if self.redis_client:
            try:
                metrics_data = await self.redis_client.get(f"workflow_metrics:{task_signature}")
                if metrics_data:
                    metrics_list = json.loads(metrics_data)
                    return [WorkflowMetrics(**m) for m in metrics_list[-10:]]
            except Exception as e:
                self.logger.warning(f"Failed to load historical metrics: {e}")
        
        return None
    
    async def _check_cached_results(
        self,
        task: Task,
        input_data: Dict[str, Any]
    ) -> Dict[AgentType, Optional[Dict[str, Any]]]:
        """Check for cached results for each agent"""
        
        cached_results = {}
        
        for agent_type in AgentType:
            cached_result = await self._get_cached_agent_result(task, agent_type, input_data)
            cached_results[agent_type] = cached_result
        
        return cached_results
    
    def _should_reuse_cache(
        self,
        agent_type: AgentType,
        cache_data: Dict[str, Any],
        input_data: Dict[str, Any]
    ) -> bool:
        """Determine if cached result should be reused"""
        
        strategy = self.cache_strategies.get(agent_type, {"reuse_threshold": 0.7})
        
        # Check cache age
        cache_timestamp = cache_data.get("timestamp")
        if cache_timestamp:
            cache_age = datetime.now() - datetime.fromisoformat(cache_timestamp)
            if cache_age > timedelta(seconds=strategy["ttl"]):
                return False
        
        # Calculate similarity score (simplified)
        similarity_score = self._calculate_input_similarity(
            cache_data.get("input_data", {}),
            input_data
        )
        
        return similarity_score >= strategy["reuse_threshold"]
    
    def _calculate_input_similarity(
        self,
        cached_input: Dict[str, Any],
        current_input: Dict[str, Any]
    ) -> float:
        """Calculate similarity between input data sets"""
        
        # Simple similarity based on key matching and value comparison
        common_keys = set(cached_input.keys()) & set(current_input.keys())
        if not common_keys:
            return 0.0
        
        matches = 0
        for key in common_keys:
            if cached_input[key] == current_input[key]:
                matches += 1
            elif isinstance(cached_input[key], str) and isinstance(current_input[key], str):
                # String similarity (simplified)
                if len(cached_input[key]) > 0 and len(current_input[key]) > 0:
                    common_chars = set(cached_input[key].lower()) & set(current_input[key].lower())
                    total_chars = set(cached_input[key].lower()) | set(current_input[key].lower())
                    char_similarity = len(common_chars) / len(total_chars) if total_chars else 0
                    if char_similarity > 0.8:
                        matches += 0.5
        
        return matches / len(common_keys)
    
    async def _get_cached_agent_result(
        self,
        task: Task,
        agent_type: AgentType,
        input_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Get cached result for specific agent"""
        
        # Generate cache key
        cache_key = self._generate_agent_cache_key(agent_type, input_data)
        
        # Check Redis first
        if self.redis_client:
            try:
                cached_data = await self.redis_client.get(f"agent_result:{cache_key}")
                if cached_data:
                    result = json.loads(cached_data)
                    
                    # Check if cache is still valid
                    cache_timestamp = result.get("timestamp")
                    if cache_timestamp:
                        cache_age = datetime.now() - datetime.fromisoformat(cache_timestamp)
                        strategy = self.cache_strategies.get(agent_type, {"ttl": 3600})
                        
                        if cache_age.total_seconds() <= strategy["ttl"]:
                            return result.get("data")
                        else:
                            # Remove expired cache
                            await self.redis_client.delete(f"agent_result:{cache_key}")
            except Exception as e:
                self.logger.warning(f"Failed to get cached agent result: {e}")
        
        return None
    
    async def _cache_agent_result(
        self,
        task: Task,
        agent_type: AgentType,
        input_data: Dict[str, Any],
        result: Dict[str, Any]
    ):
        """Cache agent result"""
        
        cache_key = self._generate_agent_cache_key(agent_type, input_data)
        strategy = self.cache_strategies.get(agent_type, {"ttl": 3600})
        
        cache_data = {
            "data": result,
            "timestamp": datetime.now().isoformat(),
            "input_data": input_data,
            "task_type": task.task_type.value,
            "agent_type": agent_type.value
        }
        
        if self.redis_client:
            try:
                await self.redis_client.setex(
                    f"agent_result:{cache_key}",
                    strategy["ttl"],
                    json.dumps(cache_data, default=str)
                )
            except Exception as e:
                self.logger.warning(f"Failed to cache agent result: {e}")
    
    def _generate_agent_cache_key(self, agent_type: AgentType, input_data: Dict[str, Any]) -> str:
        """Generate cache key for agent result"""
        
        # Include relevant input parameters based on agent type
        relevant_params = {}
        
        if agent_type == AgentType.CONCEPT_PLANNER:
            relevant_params = {
                "user_prompt": input_data.get("user_prompt", ""),
                "video_style": input_data.get("video_style", ""),
                "duration": input_data.get("duration", 30)
            }
        elif agent_type == AgentType.SCRIPT_WRITER:
            relevant_params = {
                "concept_plan": str(input_data.get("concept_plan", {})),
                "video_style": input_data.get("video_style", "")
            }
        elif agent_type in [AgentType.IMAGE_GENERATOR, AgentType.VIDEO_GENERATOR]:
            relevant_params = {
                "scenes": str(input_data.get("scenes", [])),
                "concept_plan": str(input_data.get("concept_plan", {}))
            }
        
        cache_str = f"{agent_type.value}:{json.dumps(relevant_params, sort_keys=True)}"
        return hashlib.md5(cache_str.encode()).hexdigest()
    
    def _estimate_execution_time(
        self,
        execution_groups: List[List[AgentType]],
        historical_metrics: Optional[List[WorkflowMetrics]],
        skippable_agents: Set[AgentType]
    ) -> Tuple[float, Dict[AgentType, Dict[str, float]]]:
        """Estimate total execution time and resource allocation"""
        
        total_time = 0.0
        resource_allocation = {}
        
        for group in execution_groups:
            # For parallel groups, time is max of group
            group_time = 0.0
            group_resources = {"cpu": 0, "memory": 0, "gpu": 0, "api_calls": 0}
            
            for agent_type in group:
                if agent_type in skippable_agents:
                    continue
                
                node = self.workflow_graph[agent_type]
                
                # Use historical data if available
                agent_time = node.estimated_duration
                if historical_metrics:
                    avg_time = sum(
                        m.agent_durations.get(agent_type, node.estimated_duration)
                        for m in historical_metrics
                    ) / len(historical_metrics)
                    agent_time = avg_time
                
                # For parallel execution, time is max
                if len(group) > 1:
                    group_time = max(group_time, agent_time)
                else:
                    group_time += agent_time
                
                # Accumulate resources
                for resource, amount in node.resource_requirements.items():
                    group_resources[resource] += amount
                
                resource_allocation[agent_type] = node.resource_requirements.copy()
            
            total_time += group_time
        
        return total_time, resource_allocation
    
    def _create_caching_strategy(
        self,
        task: Task,
        input_data: Dict[str, Any]
    ) -> Dict[AgentType, Dict[str, Any]]:
        """Create caching strategy for each agent"""
        
        caching_strategy = {}
        
        for agent_type, strategy in self.cache_strategies.items():
            caching_strategy[agent_type] = {
                "enabled": True,
                "ttl": strategy["ttl"],
                "reuse_threshold": strategy["reuse_threshold"],
                "cache_key": self._generate_agent_cache_key(agent_type, input_data)
            }
        
        return caching_strategy
    
    def _create_fallback_options(self) -> Dict[AgentType, List[AgentType]]:
        """Create fallback options for each agent"""
        
        # Simple fallback strategy - for now, no direct fallbacks
        # In a more advanced system, we might have alternative agents
        return {agent_type: [] for agent_type in AgentType}
    
    async def _store_execution_metrics(self, task: Task, metrics: WorkflowMetrics):
        """Store execution metrics for future optimization"""
        
        task_signature = self._generate_task_signature(task, task.input_parameters)
        
        # Store in memory
        if task_signature not in self.performance_history:
            self.performance_history[task_signature] = []
        
        self.performance_history[task_signature].append(metrics)
        
        # Keep only last 50 executions
        self.performance_history[task_signature] = self.performance_history[task_signature][-50:]
        
        # Store in Redis
        if self.redis_client:
            try:
                metrics_data = [
                    {
                        "total_duration": m.total_duration,
                        "agent_durations": {k.value: v for k, v in m.agent_durations.items()},
                        "parallel_efficiency": m.parallel_efficiency,
                        "cache_hit_rate": m.cache_hit_rate,
                        "cost_savings": m.cost_savings,
                        "bottlenecks": [b.value for b in m.bottlenecks]
                    }
                    for m in self.performance_history[task_signature]
                ]
                
                await self.redis_client.setex(
                    f"workflow_metrics:{task_signature}",
                    86400,  # 24 hours
                    json.dumps(metrics_data)
                )
            except Exception as e:
                self.logger.warning(f"Failed to store execution metrics: {e}")
    
    def get_optimization_recommendations(
        self,
        task_signature: str
    ) -> List[Dict[str, Any]]:
        """Get optimization recommendations based on historical data"""
        
        recommendations = []
        
        if task_signature not in self.performance_history:
            return recommendations
        
        metrics_history = self.performance_history[task_signature]
        
        if len(metrics_history) < 3:
            return recommendations
        
        # Analyze trends
        recent_efficiency = sum(m.parallel_efficiency for m in metrics_history[-5:]) / min(5, len(metrics_history))
        
        if recent_efficiency < 1.2:
            recommendations.append({
                "type": "parallelization",
                "message": "Consider more aggressive parallelization",
                "impact": "medium"
            })
        
        # Check for consistent bottlenecks
        bottleneck_frequency = {}
        for metrics in metrics_history[-10:]:
            for bottleneck in metrics.bottlenecks:
                bottleneck_frequency[bottleneck] = bottleneck_frequency.get(bottleneck, 0) + 1
        
        for agent, frequency in bottleneck_frequency.items():
            if frequency >= 3:
                recommendations.append({
                    "type": "bottleneck",
                    "agent": agent.value,
                    "message": f"Agent {agent.value} is frequently a bottleneck",
                    "impact": "high"
                })
        
        # Check cache hit rates
        avg_cache_rate = sum(m.cache_hit_rate for m in metrics_history[-5:]) / min(5, len(metrics_history))
        if avg_cache_rate < 0.3:
            recommendations.append({
                "type": "caching",
                "message": "Low cache hit rate - consider adjusting cache strategies",
                "impact": "medium"
            })
        
        return recommendations


# Global instance
workflow_optimizer = WorkflowOptimizer()
