## 代理与工具原则 / Principles for Agents and Tools

- Tools-First: Agents must perform external I/O and service calls strictly via registered tools. Avoid direct SDK/HTTP calls in agents. Encapsulate providers in tools or service interfaces.
- Memory Decoupling: Agents consume context via the ContextAssembler and write results via MemoryWriter. If memory is unavailable, degrade gracefully to info-level behavior without breaking flows.
- Supplier-Agnostic: Prefer service interfaces and provider configs over hardcoding vendor names, endpoints, or capabilities. Inject provider capabilities (durations, models) into LLM context instead of branching on if/else.
- Anti-Hardcoding: Do not encode LLM decisions in code via regex or if/else. Express priors and constraints in system/context messages and tool schemas; let the LLM choose within schema.
- Prompt Neutrality: Prompts must not include tool names, parameter names, or value ranges. Expose capabilities exclusively via tools schema; let validation happen in tools.
- Fallbacks as System Guarantees: Fail fast on missing capabilities at tool level, provide minimal, safe fallbacks only where explicitly designed. Surface diagnostics early (keys, endpoints, capabilities).
- Non-Pipeline Autonomy: Agents should always follow the ReAct loop (observe → plan → act → reflect) instead of relying on hard-coded pipelines. Even if an orchestrator schedules agents in a fixed order today, the agent must still retain the freedom to skip/insert stages based on task traits so it can evolve toward higher autonomy later.
- Root‑Cause First (TDD mindset): When a failure or mismatch appears, diagnose and fix the root cause before adding case‑specific workarounds. Avoid “for this case only” hardcoding. For LLM JSON outputs that require structure, always request `response_format={"type":"json_object"}` and ensure messages/payloads are JSON‑serializable primitives (no runtime objects). Keep supplier constraints in tool schemas; where a supplier cannot guarantee a constraint (e.g., precise audio duration), treat it as a soft hint and enforce exactness via post‑processing tools. Add small tests/telemetry to prevent regressions and capture fallback_reason when degradation occurs.
- Contract‑First Normalization (no patchy fixes): Normalize and validate model/tool outputs at the contract boundary (parse/adapter) with explicit diagnostics. Do not add silent “consumption‑site” workarounds that mask errors. Temporary guards must be traceable and removed after root cause is fixed.
- Error Transparency: In agent flows, prefer surfacing explicit errors or prominent diagnostics over silent fallbacks—never mask unexpected states just to keep the run alive unless the product spec mandates a controlled downgrade.
- Correct Proven-Erroneous Designs: Once a design is confirmed faulty, fix or replace it outright—do not preserve compatibility layers or silent fallbacks for incorrect behaviour.
- Rework Over Residual Compatibility: During refactors, do not assume legacy implementations are valid when they conflict with new architecture. If an older approach is wrong, plan for the necessary breaking change, manage risk, and replace it instead of layering temporary shims.
- ReAct Loops: Image/Video generators should iterate plan–act–observe–reflect. Use FC schemas to select tools and parameters; update workflow state and continuity memory each turn; stop on clear success criteria.
- Content Safety: Prompts and templates must avoid explicit or sensitive body-part phrasing and NSFW content. Prefer neutral, professional descriptions of attire, posture, and composition.
- Config over Constants: Enforce constraints via schemas driven by config (e.g., video durations from provider config) and environment (.env) for timeouts and limits.

参考 / References
- Composer Agent + Tools usage and ReAct guidelines: see docs/agents/composer_guidelines.md

## 工作记忆与上下文剪裁 / Working Memory and Context Editing Principles

- **Separate fact storage from context editing**: use working memory as the source of truth for iterate facts only (actions, observations, references). Keep context trimming/summary/usage receipts in a dedicated context editor layer with explicit contracts and budgets.
- **Prefer model-driven compaction with explicit diagnostics**: use LLM-based compaction or summarisation first, validate against a schema, and surface errors if the compacted view is still over budget or structurally invalid—never rely on silent fallbacks.
- **Drive policies through configuration**: express context budgets/quotas in configurable strategies; agents select strategies rather than hard-coding thresholds.
- **Load external state via adapters**: converting workflow state (or other business sources) into working memory snapshots should be handled by dedicated builders/adapters so agents depend on abstractions and retain single responsibility.

归档模块 / Archived Modules

- 生产禁用的 legacy 示例位于 `app/agents/**` 的 *_old/legacy* 等归档目录，导入即报错。

放置位置 / Placement

- This AGENTS.md lives in the repo root for Codex CLI compatibility. Keep it principle-level (no implementation details) and reference per-file docs where needed.

环境 / Environment

- Use a Linux-compatible shell for local orchestration. WSL2 (Ubuntu) is verified and recommended when developing on Windows; keep tooling aligned with the container/runtime configuration.

## 工具暴露与分配 / Function-Call Exposure and Tool Assignment

- Assign tools explicitly per agent to define the available capability set; do not call providers directly from agent code.
- Expose function-call schemas selectively so the LLM may invoke only the safe/desired actions; high-risk operations should require explicit policy opt-in.
- Policies should be defined centrally (e.g., configuration files) and merged with tool metadata at runtime so changes take effect without code edits.
 - Tools are execution-only: do not split a tool into “plan” vs “execute” semantics at the agent layer. One FC round should produce the function calls and execute them in the same round; avoid maintaining intermediate planned_calls state in agents.

## ReAct 编排器（FC化） / ReAct Orchestrator (FC)

（架构说明-中文）编排层以事件/FC 形式驱动 ReAct 循环：计划阶段只暴露极简控制动作，执行阶段统一 `agent.execute`，反思阶段用事实/阈值判定，保持可插拔、可跳过的灵活性，避免硬编码流程。
- THINK/PLAN via minimal FC controls (continue/repeat/abort), avoid hard-coded if/else.
- ACT via unified `agent.execute(...)` with progress/timeout/retry/WS/memory hooks.
- REFLECT uses fact-driven completion (required steps + quality threshold/iteration cap).
- Orchestrator may run a default order, but each agent still runs observe→plan→act→reflect; fixed order is transitional for later dynamic insertion/skipping.

## 记忆解耦与可选回写（ReAct 基类） / Memory Decoupling & Optional Writeback

（架构说明-中文）ReAct 基类仅提供可选迭代回写钩子（默认关），生产读写统一在编排层的 ContextAssembler/MemoryWriter，保持记忆解耦。
- Optional per-iteration writeback hook (default off via `REACT_ITERATION_MEMORY_ENABLED`), lightweight summaries only.
- Production path: read via `ContextAssembler`, write via `MemoryWriter` at orchestration layer to keep memory decoupled.


## 故障定位与降级准则（重要）

- 先定位原因，后考虑降级：出现错误时不得直接走降级掩盖问题，必须先输出诊断并明确根因；仅在系统设计的场景下才允许最小化降级。
- 结构化输出强约束：凡要求 LLM 输出 JSON，调用端必须设置 `response_format: { "type": "json_object" }` 并在模板中明确“仅输出 JSON”。
