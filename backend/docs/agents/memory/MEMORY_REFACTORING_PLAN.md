### Memory Refactor Summary

1. **阶段 1 – 依赖注入**  
   - `MemoryServices` 统一封装 WorkingMemory/MAS facts/长期存储；在 Orchestrator 启动时集中构建。  
   - BaseAgent 与所有下游 Agent/工具/服务通过构造函数注入同一份 `memory_services`，彻底删除 `get_global_memory_service` / `get_workflow_fact_store` 单例入口。  
   - `WorkingMemoryService`、`DataPersistenceService`、`MasSharedMemoryFacade`、测试等也全部改为依赖注入，保证任意工作流或测试都可替换 backend。

2. **阶段 2 – 抽象事实存储**  
   - 在 `memory.interfaces.storage` 中新增 `WorkflowFactsBackend`，`WorkflowFactStore` 只依赖该接口。  
   - 默认实现 `SlotFactsBackend` 将 alias → slot 的映射与 ACL 校验封装在存储层，业务代码不再关心 slot 细节。

3. **阶段 3 – 可配置 backend & 文档**  
   - 新增配置项  
     | 设置项 | 默认值 | 说明 |  
     | --- | --- | --- |  
     | `MEMORY_WORKFLOW_BACKEND` | `slot` | 工作流级 KV 的 backend 名称 |  
     | `MEMORY_FACTS_BACKEND` | `slot` | 事实存储 backend 名称 |  
     | `MEMORY_SLOTS_PATH` | `app/agents/memory/config/memory_slots.yaml` | slot 定义文件 |  
     | `MEMORY_FACT_ALIASES_PATH` | `app/agents/memory/config/fact_aliases.yaml` | fact alias 定义 |  
   - `build_memory_management()` 和 `build_memory_services()` 会读取上述配置并通过 `create_workflow_backend` / `create_workflow_facts_backend` 工厂创建后端。更换 redis/vector 只需扩展工厂并修改配置。  
   - 文档层强调：  
     - “集中构建 + 注入” 是唯一入口；禁用直接 new 或单例。  
     - backend 选择、alias 配置、slots 路径可通过环境变量调整。  
     - 测试可调用 `build_memory_services()` / `set_memory_services()` 注入专属实例。
