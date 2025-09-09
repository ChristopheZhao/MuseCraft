# Agents Design Principles

## Thinking Mode Policy
- Planning agents: enable thinking. Examples: concept planning, scene/narrative design, task decomposition, strategy/orchestration.
- Execution agents: disable thinking. Examples: single-pass generation/augmentation, final one-line prompts, media/file ops.
- Mixed agents: split phases — upstream planning with thinking, downstream finalization without thinking.
- No heuristic complexity rules in code. Selection is a priori by agent role. Calls may still override explicitly when needed.

## Token Budgeting
- Two-tier defaults (no hardcoding at call sites):
  - Standard: used when thinking is disabled.
  - Thinking: larger budget when thinking is enabled.
- Centralized configuration: define global defaults in config with safe values; allow .env to override per environment. Keep per-call overrides optional.

## Output Constraints
- Even with thinking enabled, only place the final answer in `message.content` for downstream use; avoid returning explanations, headings, or code fences.
- For “one-line prompt” outputs, apply strict system prompts and minimal format requirements.

## Logging & Privacy
- Log summary signals only: `finish_reason`, token usage, content length preview. Do not persist full `reasoning_content`.
- Use warnings/fallbacks if `finish_reason=length` with empty `content`, but prefer preventing this via adequate token budgets.

## Configuration Guidance
- Define two global settings for max tokens (standard vs thinking) in config and allow `.env` overrides.
- Each agent declares its default thinking mode (planning/execution) in configuration (e.g., ai_config), not in code conditionals.
- Keep the surface simple: default to agent-level policy; allow explicit per-call overrides (`thinking`, `max_tokens`) when justified.

---

## 中文实践准则（当前默认）
- 工具仅通过 FC 的 tools schema 注入，不在提示中出现工具名/参数名/取值范围；`use_tool` 仅作为执行层（执行结构化函数调用）。
- thinking 与 FC 解耦：thinking 仅决定推理预算（两档 tokens），不影响是否能做 FC 决策。规划类 Agent 默认开启 thinking，执行类默认 standard。
- 纯 LLM 内生能力（如“提示词增强/文本润色”）不暴露为工具，统一用普通 LLM 步骤（messages → content），避免二次路由与循环风险。
- 提示形态：提供任务目标、事实上下文、进度与反思摘要、可分轮完成语义；不包含能力/工具/参数层信息。
- 执行保障（轻量）：
  - 工具执行失败仅一次带错误摘要友好重试；
  - 无结构化调用且无文本结果时，仅一次轻量重试后进入下一轮自纠；
  - 严格依赖 tools schema 与工具层校验参数。

---

## 依赖治理（简则）
核心依赖：声明并安装，缺失直接报错；可选能力：用特性开关/NoOp，不得静默降级。

## 工具原则（新增）
- 工具是 Agents 扩展 LLM 能力的唯一途径，通用能力不得零散实现在各 Agent 内部。
- 所有有副作用的外部集成（IO/网络/系统命令）必须以工具形态提供；Agent 只能通过工具访问外部能力，禁止直接依赖第三方 SDK/客户端。
- 工具应集中在工具层统一注册与复用，替换实现（本地/云）不影响 Agent 代码。
- 工具层负责依赖校验（缺失直接报错）、超时/重试/限流与可观测性埋点；Agent 仅负责编排与策略选择。
- 允许保留在 Agent 内的仅限：纯函数转换（无 IO/网络副作用）、Prompt 组装与状态流转。
- 仅使用已注册工具：Agent 可用工具列表由“工具分配器+注册表”提供，FC 的 tools 参数与 Schema 由注册表生成；禁止在 Agent/Prompt 中硬编码工具名或手写 Schema；未注册/无有效 Schema 的工具在初始化阶段直接 fail-fast。

## 记忆与兜底原则（新增）
- 记忆解耦：上下文/创意指导/场景引用统一经共享记忆接口读写；Agent 不维护跨任务的私有持久状态（执行期局部变量除外）。
- 缺失降级：记忆缺失、不可用或不一致时仅做告警与信息性降级，不阻断主流程；不得以临时写入/旁路缓存替代。
- 策略外置：取/写规则、标签与 TTL 通过配置/策略外置管理，避免在 Agent 内分叉或硬编码。
- 兜底是系统保障：工具不可用/返回空、或 FC 无有效输出时，必须进入兜底路径；兜底同样通过工具与记忆接口完成，不引入临时 IO、私有持久化或旁路逻辑。
- 重试原则：重试应有限且可配置；失败则兜底并返回最小可用结果与原因。

## 硬编码与自主化（新增）
- 硬编码的界定（澄清）：禁止用 if/else/规则树/大量正则 等程序逻辑，替代本应由 LLM 完成的语义理解、工具选择、参数决策、解析与路由（含“是否调用工具/调用哪个/用什么参数”）。
- 工具名/Schema 的约定：工具名与 JSON Schema 由工具注册表集中预定义与维护，属于约定与配置，不视为“硬编码”；但禁止在 Agent 内重复手写工具名/Schema 或分叉映射，应统一走注册表与模板。
- 业务阈值与流程：可调业务阈值与流程策略放入配置/策略文件；Agent 内禁止散落魔法数。工程级基础常量（如超时、重试上限）通过配置注入或统一默认。
- 先验的使用：领域先验/规则需注入到 LLM 上下文（system prompt、few-shot、策略标签/约束说明）或外置策略中，而不是在代码里以枚举/匹配（if/else/正则）驱动流程分支；用先验“引导/约束”而非“替代” LLM 决策。
- 决策与校验分离：先验可用于“安全/合规/边界条件”的校验与回退触发，但“工具选择、参数拟合与语义解析”仍由 LLM 基于上下文自主完成。
- 多智能体自主化基线：保留 LLM Function Call 的决策权（是否/何时/参数），Agent 仅声明能力边界与约束，避免用代码推演替代 LLM 决策。
- 可演进与防线迭代：以策略/配置为演进点，支持灰度与回滚；为关键决策设置守卫（限时、限重试、限资源），防止失控循环。
- 最小入侵：新增能力优先落在工具层/策略层/编排钩子，避免修改既有 Agent 主流程。
