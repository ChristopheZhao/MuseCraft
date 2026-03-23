# MAS Runtime Contracts 细化设计稿

日期：2026-03-08

状态：Phase 0-4 合同设计稿

用途：作为 `PLAN-20260308-003` 的 P0-4 交付物，明确 `ExecutionIntent / ExecutionContract / GateResult` 三类核心 contract，替代当前散落在 orchestrator、shared memory 和 agent 输入中的隐式控制协议。

关联文档：

- [MAS 编排边界解耦与单 Episode Runtime Kernel 重构计划](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/docs/plans/active/PLAN-20260308-003.md)
- [MAS Runtime / Control-Plane 细化设计稿](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/docs/architecture/mas_runtime_control_plane_detailed_design_20260308.md)
- [MAS Orchestrator 重构专项审查清单](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/docs/architecture/mas_orchestrator_refactor_audit_checklist_20260308.md)
- [single_episode_harness_architecture_20260311.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/architecture/single_episode_harness_architecture_20260311.md)
- [MAS Architecture Alignment Note](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/architecture/mas_architecture_alignment_note_20260323.md)

说明：

- 本文档细化四层架构下的 contract vocabulary 与 assembler responsibility，不把 `Context/Contract Assembler` 定义为新的顶层层级

## 1. 设计目标

当前项目的主要问题之一，是控制语义散落在：

- `workflow.plan`
- `workflow.audio_route`
- `activation_pool / standby_pool`
- `input_data` 中的 ad hoc flags
- agent 内部对 `planned_calls` 的二次 patch

本设计稿的目标是：

- 用显式 contract 替代隐式协议
- 让每层只看自己应该看的对象
- 让 quick mode `HITL`、scene revise、project mode 复用都建立在稳定 contract 上

## 2. Contract 总览

本期统一使用三类 contract：

### 2.1 ExecutionIntent

拥有者：

- `orchestrator`

消费者：

- `control-plane`

用途：

- 表达“下一步希望做什么”
- 是 planner/runtime 的内部协作对象
- 不直接暴露给 leaf-agent

### 2.2 ExecutionContract

拥有者：

- `control-plane + contract assembler`

消费者：

- `leaf-agent`

用途：

- 表达“这次真正允许 agent 执行什么”
- 是 leaf-agent 唯一可见的控制面入口

### 2.3 GateResult

拥有者：

- `gate/evaluator`

消费者：

- `control-plane`
- `orchestrator`
- `UI/runtime view`

用途：

- 表达“交付事实是否满足契约”
- 统一承载 system evaluator 和 human review gate 的结果

## 3. ExecutionIntent

## 3.1 语义

`ExecutionIntent` 是 orchestrator 的输出。  
它回答的是：

- 当前 session 的下一个目标节点是什么
- 目标由哪个 agent 执行
- 目标作用域和期望产物是什么
- 本次意图有哪些硬约束

它不回答：

- 具体 tool 参数是什么
- gate 最终结果是什么
- node/attempt 的最终生命周期状态是什么

## 3.2 最小字段

```json
{
  "intent_version": "v1",
  "intent_id": "uuid",
  "session_id": "ws_xxx",
  "node_key": "scene_video:scene:3",
  "target_agent": "video_generator",
  "operation": "generate_scene_video",
  "scope": {
    "scope_type": "scene",
    "scope_ref": "3"
  },
  "goal": "Generate the approved scene video candidate for scene 3",
  "constraints": {
    "generate_audio": false
  },
  "expected_artifacts": [
    "scene_video",
    "video_receipt"
  ],
  "retry_policy_ref": "default_scene_video_retry"
}
```

## 3.3 关键约束

- 允许表达：
  - `target_agent`
  - `operation`
  - `scope`
  - `goal`
  - `constraints`
  - `expected_artifacts`
- 不允许表达：
  - `activation_pool`
  - `standby_pool`
  - `route_source`
  - `decision_reason`
  - `run_audio_agent`
  - `patch_tool_call`

换句话说，`ExecutionIntent` 只表达意图，不夹带历史兼容分支。

## 4. ExecutionContract

## 4.1 语义

`ExecutionContract` 是 leaf-agent 真正收到的控制面对象。  
它回答的是：

- 本次执行的操作是什么
- 作用域是什么
- 可用输入事实和产物引用是什么
- 显式执行约束是什么
- 期望输出什么
- 写回哪个存储作用域

它不回答：

- 为什么 orchestrator 选了这个 agent
- 当前还有哪些 standby agents
- 其它节点是否待执行
- 本次 decision 是谁做出的

## 4.2 最小字段

```json
{
  "contract_version": "v1",
  "contract_id": "uuid",
  "session_id": "ws_xxx",
  "attempt_id": "att_xxx",
  "agent": "video_generator",
  "operation": "generate_scene_video",
  "scope": {
    "scope_type": "scene",
    "scope_ref": "3"
  },
  "inputs": {
    "facts": {
      "scene_script": "...",
      "continuity_context": {}
    },
    "artifacts": [
      {
        "kind": "storyboard_image",
        "path": "...",
        "url": "..."
      }
    ]
  },
  "constraints": {
    "generate_audio": false,
    "duration_hint": 5.0
  },
  "expected_outputs": [
    "scene_video",
    "video_generation_receipt"
  ],
  "storage": {
    "workflow_state_id": "..."
  }
}
```

## 4.3 允许项

- `facts`
- `artifacts`
- `constraints`
- `expected_outputs`
- `storage.workflow_state_id`

## 4.4 禁止项

以下内容禁止进入 `ExecutionContract`：

- `workflow.plan`
- `workflow.audio_route`
- `activation_pool`
- `standby_pool`
- `route_id`
- `route_source`
- `decision_reason`
- `should_run_other_agent`
- 任意要求 leaf-agent 理解 sibling agent 行为的字段

## 4.5 合同组装责任

组装 `ExecutionContract` 的责任属于：

- `control-plane`
- `contract assembler / context assembler`

不属于：

- `orchestrator` 主循环
- leaf-agent

这意味着：

- leaf-agent 不应自己“补齐” contract
- 更不应在 ACT 前 patch tool calls

## 5. GateResult

## 5.1 语义

`GateResult` 统一表示：

- system evaluator 的结构化结果
- human review gate 的待审状态与可执行动作

它回答的是：

- 当前产物是否满足 gate 条件
- 检查到了哪些规范化事实
- 原因码是什么
- 当前允许什么动作

它不回答：

- 直接如何改执行队列
- 直接该激活哪个 standby agent

## 5.2 最小字段

```json
{
  "contract_version": "v1",
  "session_id": "ws_xxx",
  "node_id": "node_xxx",
  "attempt_id": "att_xxx",
  "gate_name": "scene_video_review",
  "gate_type": "human_review",
  "scope": {
    "scope_type": "scene",
    "scope_ref": "3"
  },
  "artifact_refs": [
    {
      "kind": "scene_video",
      "path": "...",
      "url": "...",
      "lineage_key": "scene_video:3:r1"
    }
  ],
  "facts": {
    "duration": 4.8,
    "has_audio": false,
    "file_integrity": true,
    "records_checked": 1
  },
  "result": "awaiting_human",
  "reason_code": "scene_video_generated",
  "diagnostics": [],
  "allowed_actions": [
    "approve",
    "revise"
  ],
  "recommended_action": "approve"
}
```

## 5.3 结果枚举

- `pass`
- `fail`
- `inconclusive`
- `awaiting_human`

## 5.4 allowed_actions 规则

本期固定：

- `script_review`: `approve | revise | replan`
- `storyboard_review`: `approve | revise`
- `scene_video_review`: `approve | revise`

## 6. Contract 生命周期

## 6.1 Orchestrator -> Control-Plane

- orchestrator 根据当前上下文产出 `ExecutionIntent`
- control-plane 校验意图是否与当前 node/session 状态兼容

## 6.2 Control-Plane -> Leaf-Agent

- control-plane 将 `ExecutionIntent` 组装成 `ExecutionContract`
- 创建新的 `workflow_node_attempt`
- leaf-agent 只消费 `ExecutionContract`

## 6.3 Gate/Evaluator -> Control-Plane

- leaf-agent 产出 artifact 后，gate/evaluator 输出 `GateResult`
- control-plane 决定：
  - `continue`
  - `retry`
  - `revise`
  - `replan`
  - `await_human`

## 6.4 Human/System Decision -> Control-Plane

- human 或 policy 生成 `workflow_gate_decision`
- control-plane 依据 `action + structured_constraints + invalidation_scope` 推进状态机

## 7. 合同与现有代码的替换关系

## 7.1 替换 workflow.plan / workflow.audio_route

当前反例：

- [video_generator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/video_generator.py#L324)
- [video_generator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/video_generator.py#L357)

替换后：

- orchestrator 只输出 `ExecutionIntent`
- leaf-agent 只读取 `ExecutionContract`
- `workflow.plan/audio_route` 最多作为 control-plane 内部兼容/诊断对象，不能再进入 leaf-agent live path

## 7.2 替换 ACT 前 patch tool calls

当前反例：

- [video_generator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/video_generator.py#L378)
- [video_generator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/video_generator.py#L423)

替换后：

- 必须在 contract 边界一次性组装约束
- ACT 阶段只执行模型和工具的正常 contract，不允许二次改写

## 7.3 替换 orchestrator 内部 gate helper

当前反例：

- [orchestrator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py#L1848)
- [orchestrator.py](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/backend/app/agents/orchestrator.py#L1941)

替换后：

- gate/evaluator 输出 `GateResult`
- orchestrator 不再直接读取探测事实

## 8. 反伪去规则化检查

本合同设计配套一条审核原则：

- 如果重构后只是把 `workflow.plan` 换成别的内部字段名
- 或只是把 `audio_route` 换成另一个 helper 返回值
- 但 leaf-agent 仍通过这些字段拿到控制语义

则应判定为“不通过”。

判定通过至少需要满足：

1. orchestrator 输出的是 `ExecutionIntent`，不是隐藏版 `plan`
2. leaf-agent 输入的是 `ExecutionContract`，不是换名后的 `route`
3. gate/evaluator 输出的是 `GateResult`，不是 orchestrator 内部 helper 的返回值
4. 三类 contract 的拥有者和消费者清晰分离

## 9. P0-4 完成标准

P0-4 视为完成，需要同时满足：

- `ExecutionIntent` 字段与拥有者明确
- `ExecutionContract` 字段与禁区明确
- `GateResult` 字段与动作规则明确
- 已明确替换当前 `workflow.plan/audio_route/planned_calls patch` 的关系
- 下一阶段可以直接开始 kernel 接入，而不需要再发明新的隐式控制协议
