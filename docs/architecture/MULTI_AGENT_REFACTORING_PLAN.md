# Hierarchical Multi-Agent System Refactoring Plan

## 目标：从Agentic Workflow重构为Hierarchical Multi-Agent System

### 当前系统分析
- **现状**：Agentic Workflow - 外部编排，单次执行，无迭代循环
- **问题**：SubAgent无ReAct循环、无自主决策、无Agent间通信
- **目标**：Hierarchical MAS - Central Coordinator + ReAct SubAgents

## 核心架构理解

### 1. Hierarchical Architecture (中心化层次结构)

```
Coordinator Agent (中心协调者 - LLM-based)
├── ConceptPlanner SubAgent (ReAct循环)
├── ScriptWriter SubAgent (ReAct循环) 
├── ImageGenerator SubAgent (ReAct循环)
├── VideoGenerator SubAgent (ReAct循环)
├── VideoComposer SubAgent (ReAct循环)
└── QualityChecker SubAgent (ReAct循环)
```

**注意**：这不是分布式MAS，是中心化的层次结构，分布式MAS是下下阶段目标。

### 2. 核心技术挑战 (基于学术研究)

#### 2.1 Coordinator Agent 设计挑战
- **任务分解策略**：LLM-based hierarchical task decomposition
- **SubAgent选择和调度**：动态Agent选择和任务分配
- **全局规划**：维护整体任务执行策略和上下文
- **通信管理**：协调SubAgent间的信息传递和状态同步

#### 2.2 SubAgent ReAct循环实现
```python
class ReActSubAgent(BaseAgent):
    """每个SubAgent都有独立的ReAct循环"""
    
    async def react_cycle(self, task_context: TaskContext) -> AgentResult:
        for iteration in range(max_iterations):
            # OBSERVE: 观察当前任务状态和环境
            observation = await self.observe(task_context)
            
            # THINK: LLM-based推理和分析
            reasoning = await self.think(observation)
            
            # PLAN: 制定具体行动计划
            action_plan = await self.plan(reasoning)
            
            # ACT: 执行行动(工具调用、与Coordinator通信等)
            action_result = await self.act(action_plan)
            
            # REFLECT: 反思结果，决定是否继续
            reflection = await self.reflect(action_result)
            
            # 更新个人记忆和共享上下文
            await self.update_memory(action_result, reflection)
            
            # 与Coordinator通信进度和结果
            await self.communicate_with_coordinator(reflection)
            
            if reflection.task_completed:
                break
                
        return task_context.get_final_result()
```

#### 2.3 Coordinator Agent 实现
```python
class CoordinatorAgent(ReActAgent):
    """
    中心协调者 - LLM-based任务分解和SubAgent协调
    基于研究论文的Central LLM-based Agent设计
    """
    
    async def coordinate_task(self, user_request: Dict) -> TaskResult:
        # 全局ReAct循环
        for global_iteration in range(max_global_iterations):
            # OBSERVE: 观察整体任务状态
            global_state = await self.observe_global_state()
            
            # THINK: 分析任务进展和下一步策略
            strategic_reasoning = await self.think_strategically(global_state)
            
            # PLAN: 决定SubAgent任务分配
            coordination_plan = await self.plan_coordination(strategic_reasoning)
            
            # ACT: 协调SubAgent执行
            coordination_result = await self.coordinate_subagents(coordination_plan)
            
            # REFLECT: 评估整体进展
            global_reflection = await self.reflect_globally(coordination_result)
            
            if global_reflection.task_completed:
                break
                
        return final_result
    
    async def decompose_task(self, user_request: Dict) -> List[SubTask]:
        """LLM-based hierarchical task decomposition"""
        
    async def select_and_schedule_agents(self, subtasks: List[SubTask]) -> AgentSchedule:
        """动态Agent选择和调度"""
        
    async def manage_shared_memory(self) -> None:
        """中央控制的记忆管理和上下文同步"""
```

#### 2.4 通信协议设计 (Hierarchical Only)
```python
class CoordinatorMessage:
    """Coordinator与SubAgent间的通信协议"""
    
    message_type: MessageType  # TASK_ASSIGN, PROGRESS_REQUEST, CONTEXT_UPDATE
    sender: str  # 总是 "coordinator" 或 subagent_id
    receiver: str
    content: Dict[str, Any]
    shared_context: SharedContext
    task_id: str
    timestamp: datetime

class MessageType(Enum):
    # Coordinator -> SubAgent
    TASK_ASSIGN = "task_assign"          # 任务分配
    CONTEXT_UPDATE = "context_update"    # 上下文更新
    PROGRESS_REQUEST = "progress_request" # 进度查询
    
    # SubAgent -> Coordinator  
    PROGRESS_REPORT = "progress_report"  # 进度报告
    TASK_COMPLETE = "task_complete"      # 任务完成
    HELP_REQUEST = "help_request"        # 请求协助
    ERROR_REPORT = "error_report"        # 错误报告

# 注意：SubAgent间不直接通信，都通过Coordinator中转
```

#### 2.5 记忆管理架构 (Central + Personal)
```python
class HierarchicalMemoryManager:
    """分层记忆管理系统"""
    
    # 共享记忆 - 所有Agent可访问
    shared_memory: SharedMemorySpace
    
    # 个人记忆 - 每个Agent独有
    personal_memories: Dict[str, PersonalMemorySpace]
    
    # 记忆反思 - 中央控制
    memory_reflection_controller: MemoryReflectionController
    
    async def update_shared_context(self, context_update: ContextUpdate):
        """Coordinator控制的共享上下文更新"""
        
    async def reflect_and_consolidate(self, agent_experiences: List[Experience]):
        """中央控制的记忆反思和整合"""
        
    async def provide_relevant_context(self, agent_id: str, task: Task) -> RelevantContext:
        """为特定Agent提供相关上下文"""
```

### 3. 重构工作量评估与阶段规划

#### 工作量分析 (基于学术研究复杂度)
1. **Coordinator Agent设计**：任务分解、全局规划、通信管理 (复杂度：高)
2. **6个SubAgent ReAct化**：每个都要重写ReAct循环 (复杂度：高)
3. **通信协议实现**：消息格式、路由、状态同步 (复杂度：中)
4. **分层记忆系统**：共享+个人+反思机制 (复杂度：高)  
5. **双层迭代循环**：全局+子任务循环协调 (复杂度：高)
6. **错误处理机制**：多Agent错误传播和恢复 (复杂度：中)

#### Phase 1: Coordinator Agent重构 (2-3周)
1. **创建CoordinatorAgent基类**
   - LLM-based任务分解能力
   - 全局ReAct循环实现
   - SubAgent选择和调度逻辑

2. **实现通信协议**
   - Coordinator-SubAgent消息系统
   - 状态同步机制
   - 进度监控机制

3. **分层记忆管理器**
   - 共享记忆空间设计
   - 中央记忆反思控制
   - 上下文传递机制

#### Phase 2: SubAgent ReAct化 (3-4周)
每个SubAgent都需要重写为ReAct模式，工作量巨大：

4. **ConceptPlannerAgent → ReAct**
   - OBSERVE: 分析用户需求和全局上下文
   - THINK: LLM-based创意分析和可行性评估  
   - PLAN: 制定概念设计策略
   - ACT: 执行概念生成和工具调用
   - REFLECT: 评估质量并与Coordinator通信

5. **ScriptWriterAgent → ReAct**
   - OBSERVE: 分析概念计划和视频要求
   - THINK: 推理叙事结构和风格选择
   - PLAN: 规划脚本编写步骤
   - ACT: 生成脚本内容
   - REFLECT: 质量评估和改进建议

6. **其他4个Agent类似重构** (ImageGenerator, VideoGenerator, VideoComposer, QualityChecker)

#### Phase 3: 高级协调机制 (2-3周)
7. **动态Agent协调**
   - 依赖关系分析和管理
   - 并行执行协调
   - 冲突检测和解决

8. **学习和优化机制**
   - 跨任务经验积累
   - 协调策略学习
   - 性能优化

### 4. 关键技术实现要点

#### 4.1 双层迭代循环设计
```python
# Coordinator的全局循环
async def coordinate_video_generation(self, user_request: Dict) -> TaskResult:
    for global_iteration in range(max_global_iterations):
        # 全局观察
        global_state = await self.observe_system_state()
        
        # 全局思考和规划
        coordination_plan = await self.think_and_plan_globally(global_state)
        
        # 协调SubAgent执行 (每个SubAgent有自己的ReAct循环)
        subagent_results = await self.coordinate_subagents(coordination_plan)
        
        # 全局反思
        global_reflection = await self.reflect_globally(subagent_results)
        
        if global_reflection.video_generation_complete:
            break

# SubAgent的局部ReAct循环  
async def subagent_react_cycle(self, assigned_task: SubTask) -> SubTaskResult:
    for local_iteration in range(max_local_iterations):
        observation = await self.observe_local_state(assigned_task)
        reasoning = await self.think_about_task(observation)
        action_plan = await self.plan_actions(reasoning)
        action_result = await self.execute_actions(action_plan)
        reflection = await self.reflect_on_results(action_result)
        
        # 与Coordinator通信
        await self.report_to_coordinator(reflection)
        
        if reflection.subtask_completed:
            break
```

#### 4.2 Context Sharing机制 (避免Agent间冲突)
基于研究论文强调的重要问题：
```python
class SharedContext:
    """确保所有Agent看到一致的上下文，避免冲突决策"""
    
    # 全局任务状态
    global_task_state: GlobalTaskState
    
    # 各SubAgent的完整执行历史 (不只是消息)
    agent_execution_traces: Dict[str, List[ExecutionTrace]]
    
    # 共享资源状态
    shared_resources: SharedResourceState
    
    # 决策历史和隐含假设
    decision_history: List[Decision]
    implicit_assumptions: List[Assumption]
    
    def ensure_consistency(self) -> bool:
        """检查Agent间是否基于一致的假设工作"""
        
    def detect_conflicting_decisions(self) -> List[Conflict]:
        """检测可能的决策冲突"""
```

#### 4.3 记忆反思控制机制
```python
class CentralMemoryReflectionController:
    """中央控制的记忆更新机制"""
    
    async def control_memory_reflection(self, agent_experiences: Dict[str, Experience]):
        """
        Coordinator控制各SubAgent的记忆更新，确保系统一致性
        基于研究论文的Central LLM-based memory reflection control
        """
        
        # 收集所有Agent的新经验
        all_experiences = self.collect_agent_experiences()
        
        # 中央分析和整合
        consolidated_insights = await self.consolidate_experiences(all_experiences)
        
        # 向各Agent发送记忆更新指令
        for agent_id, insights in consolidated_insights.items():
            await self.send_memory_update_signal(agent_id, insights)
```

### 5. 总结与实施策略

#### 重构复杂度评估
基于学术研究分析，这是一个**重大架构升级**，涉及：

1. **Coordinator Agent设计** - 需要LLM-based任务分解、全局规划、通信管理
2. **6个SubAgent完全重写** - 每个都要实现完整ReAct循环  
3. **通信协议设计** - Hierarchical模式下的消息传递机制
4. **分层记忆管理** - 共享记忆 + 个人记忆 + 中央反思控制
5. **双层迭代循环** - 全局协调循环 + 子任务ReAct循环的协调
6. **Context Sharing** - 避免Agent间基于冲突假设的决策

#### 总工作量估计: 7-10周

#### 实施策略
1. **渐进式重构**：保持现有API兼容性，逐步替换组件
2. **并行开发**：可以同时进行基础架构和SubAgent重构
3. **测试驱动**：每个阶段都要有完整的测试验证
4. **分阶段上线**：先实现基础功能，再逐步增加高级特性

#### 关键成功因素
- [ ] Coordinator能有效进行LLM-based任务分解
- [ ] 每个SubAgent能独立完成ReAct循环
- [ ] 通信机制确保信息一致性，避免冲突决策
- [ ] 记忆系统支持经验积累和学习
- [ ] 系统性能满足实际使用需求

#### 与分布式MAS的区别
- **当前目标**：Hierarchical (中心化层次结构)
- **下下阶段**：Distributed (去中心化网络结构)
- **关键差异**：Hierarchical通过Coordinator中转，Distributed支持Agent间直接通信

#### 风险评估
- **高风险**：双层迭代循环的复杂性，可能导致无限循环或性能问题
- **中风险**：记忆系统集成复杂度，上下文一致性维护
- **低风险**：现有API兼容性，基础工具和模型集成

---

**结论**: 这是从Agentic Workflow向Hierarchical Multi-Agent System的重大升级，技术挑战很大但架构先进性显著。建议完成当前系统调试后立即开始重构工作。