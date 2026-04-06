# MAS Refactor Development Note

这轮重构最初是从一个很具体的工程问题开始的：项目里的多 agent 编排虽然名义上已经采用了 orchestrator + subagents 的结构，但实际实现逐渐滑向了以规则为中心的显式编排。`orchestrator` 不仅负责下发任务，还同时承担了流程控制、门控触发、fallback 组织、状态持久化和一部分兼容逻辑，随着功能不断叠加，系统越来越像一个规则系统，而不是一个以 LLM 决策为核心的 `hybrid subagents`。这轮工作的真正目标，并不是简单地“重写 orchestrator”，而是把系统重新拉回到更合理的 AI-Native 工程边界：让 orchestrator 回到 `llm-decision-based orchestration`，让 control-plane、gate、observability 和 leaf-agent 各自回到自己的位置。

在推进过程中，团队先完成了一轮必要的基础收敛。runtime kernel、runtime session 和 `script gate` 的最小闭环先落了地，`video_generator` 从读取 `workflow.plan/audio_route` 这种明显错误的控制协议中被拉出来，`video_composer` 也改成了显式执行边界驱动。与此同时，quick mode 前端只做了最小适配，用来验证后端的 gate 和 runtime 设计是否真的可消费，而不是把本期重心拖向更重的 HITL 产品化。随着这些工作推进，团队逐步确认了一条更明确的架构原则：本期的重点不是 HITL 本身，而是 MAS 去规则中心化；HITL 可以作为后续扩展，但必须建立在正确的 orchestrator、control-plane 和 gate 边界之上。

真正的难点出现在中后段。几轮实现、复核和修正之后，项目表面上已经消除了很多显眼的坏模式，但进一步审查发现，主循环 ownership 其实并没有真正收干净。`orchestrator` 仍然在主循环里主动串起 `report -> gate -> decision -> apply`，runtime controller 仍然持有 queue、activation 和 fallback spec 的一部分控制逻辑，协议层也还没有形成真正严格的主从边界。这一阶段最重要的认识，不是“还有几个 helper 需要继续迁出”，而是看清了一个更本质的事实：架构重构最容易失败的地方，不是函数太长，也不是文件太多，而是 ownership 只是换了宿主，却没有真正迁走。把规则从 orchestrator 挪到 policy、adapter 或 controller，并不等于完成解耦；如果控制语义还在代码里显式生成 plan、activation 或 replan，系统仍然没有回到 `more llm decision, less hard-coding` 的目标上。

也正因为如此，这轮工作最后没有被强行推到“完成”。随着多轮计划叠加和阶段性结论累积，团队明显感受到了 `context rot`：同一份计划里混入了大量中间判断、过时结论和过渡设计，继续在同一上下文里硬推收尾，只会放大误判。最终的处理方式不是把旧计划标成完成，而是做一次 checkpoint，把已经达成的阶段成果、仍未收口的问题、已经失效的旧判断和新的聚焦计划入口全部固定下来，然后基于更窄的新计划继续推进。这一步本身也是这轮研发的重要结论：对于长周期 MAS 架构重构，checkpoint 不是失败，而是一种必要的治理手段。它的目的不是中断工作，而是避免旧上下文继续污染后续判断，让下一阶段的工作重新聚焦到真正的 blocker 上。

从当前结果看，这轮研发并没有完成最终迁移，但它的价值已经非常明确。团队已经把“什么才算真正的 MAS 去规则中心化收口”讲清楚了，也把“什么只是局部 seam cleanup、什么属于 ownership 迁移失败”区分清楚了。更重要的是，这轮工作沉淀出了一条之后仍然有效的工程判断：生产级 MAS 的核心确实是自主编排，但只有把控制层、门控层、可观测层和治理闭环一起建立起来，自主性才不会退化成不可维护的规则系统。对这个项目来说，真正的后续重点也因此非常明确：继续收 orchestrator 主循环 ownership，补强主从通信协议，压缩 controller 的控制语义，并用更真实的主循环链路测试去验证这条架构是否真的站住了。

如需继续追踪本轮工作的上下文，可结合以下文档阅读：`docs/architecture/mas_refactor_checkpoint_20260310.md`、`docs/architecture/mas_refactor_retrospective_20260310.md`、`docs/plans/active/PLAN-20260310-004.md`。
