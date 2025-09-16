Principles for Agents and Tools

- Tools-First: Agents must perform external I/O and service calls strictly via registered tools. Avoid direct SDK/HTTP calls in agents. Encapsulate providers in tools or service interfaces.
- Memory Decoupling: Agents consume context via the ContextAssembler and write results via MemoryWriter. If memory is unavailable, degrade gracefully to info-level behavior without breaking flows.
- Supplier-Agnostic: Prefer service interfaces and provider configs over hardcoding vendor names, endpoints, or capabilities. Inject provider capabilities (durations, models) into LLM context instead of branching on if/else.
- Anti-Hardcoding: Do not encode LLM decisions in code via regex or if/else. Express priors and constraints in system/context messages and tool schemas; let the LLM choose within schema.
- Prompt Neutrality: Prompts must not include tool names, parameter names, or value ranges. Expose capabilities exclusively via tools schema; let validation happen in tools.
- Fallbacks as System Guarantees: Fail fast on missing capabilities at tool level, provide minimal, safe fallbacks only where explicitly designed. Surface diagnostics early (keys, endpoints, capabilities).
- Root‑Cause First (TDD mindset): When a failure or mismatch appears, diagnose and fix the root cause before adding case‑specific workarounds. Avoid “for this case only” hardcoding. For LLM JSON outputs that require structure, always request `response_format={"type":"json_object"}` and ensure messages/payloads are JSON‑serializable primitives (no runtime objects). Keep supplier constraints in tool schemas; where a supplier cannot guarantee a constraint (e.g., precise audio duration), treat it as a soft hint and enforce exactness via post‑processing tools. Add small tests/telemetry to prevent regressions and capture fallback_reason when degradation occurs.
- ReAct Loops: Image/Video generators should iterate plan–act–observe–reflect. Use FC schemas to select tools and parameters; update workflow state and continuity memory each turn; stop on clear success criteria.
- Content Safety: Prompts and templates must avoid explicit or sensitive body-part phrasing and NSFW content. Prefer neutral, professional descriptions of attire, posture, and composition.
- Config over Constants: Enforce constraints via schemas driven by config (e.g., video durations from provider config) and environment (.env) for timeouts and limits.

Archived Modules

- The following legacy/example modules are archived and must not be imported in production; attempting to import them raises ImportError:
  - app.agents.video_generator_old, app.agents.video_generator_legacy, app.agents.video_generator_old_loop
  - app.agents.image_generator_old, app.agents.image_generator_old_react, app.agents.image_generator_simple
  - app.agents.video_generator_llm_broken, app.agents.script_writer_old_loop, app.agents.script_writer_react_broken
  - app.agents.concept_planner_old, app.agents.function_call_agent_example
- Rationale: They contain historical prompts/flows that may reference tools/parameters explicitly, violating Prompt Neutrality.

Placement

- This AGENTS.md lives in the repo root for Codex CLI compatibility. Keep it principle-level (no implementation details) and reference per-file docs where needed.

Environment

- Use a Linux-compatible shell for local orchestration. WSL2 (Ubuntu) is verified and recommended when developing on Windows; keep tooling aligned with the container/runtime configuration.

## FC 暴露策略与工具分配（中文补充）

- 工具分配（allocated_tools）用于为 Agent 注入“可用的工具集合”（工具级权限）。
- FC 暴露（Function Call schema）用于控制“在已分配工具中，哪些动作允许 LLM 自主选择”（动作级白名单）。
- 最小暴露：默认不对 LLM 暴露高风险/副作用工具与动作（如存储、记忆、外部写操作）。必要时由策略显式开放。
- 策略来源：
  - 工具默认可见性：各工具可通过 `get_fc_visibility()` 给出默认建议（如 `{"expose": true, "allowed_actions": [...]}`）。
  - 全局策略：`backend/config/mas/fc_policies.yaml` 可集中覆盖（支持 `per_agent`）。
  - BaseAgent 构建 FC schema 时动态加载策略与工具元数据，热生效，无需重启。

## ReAct 编排器（FC化）

- ReAct 编排的 THINK/PLAN 阶段通过 FC 只暴露“编排控制工具”的极简动作（如继续/重复/中止），避免在编排器中硬编码 if/else。
- ACT 阶段统一通过 `agent.execute(...)` 调用子 Agent，继承进度/超时/重试/WebSocket/记忆钩子等系统保障。
- REFLECT 使用事实驱动的完成判定（必需步骤 + 质量阈值或迭代上限），减少对 LLM 文本反思的强依赖。

## Composer 可重入与音频职责

- Composer 是“统一装配者”，可在工作流多阶段被多次调用：
  - 先做场景视频拼接（video-only）；
  - AudioAgent 交付等长可用的 BGM 后，Composer 再次执行“加配乐”；
  - 未来可在 VO/SRT/SFX 就绪后再做多轨混合、响度标准化与 ducking。
- AudioAgent 的职责：
  - 观测（总时长/时间线/概念）→ 规划（AudioDesignPlan）→ 生成（供应商无关）→ 分析（静音/能量/候选截断点）→ 智能对齐（裁剪/循环/淡化），交付“等长可用”的音轨。
  - 不在 Agent 内直接做混流（除非回退模式），混流由 Composer 统一执行。

## 记忆解耦与可选回写（ReAct 基类）

- ReAct 基类提供可选的“每轮回写钩子”（默认关闭，通过 `REACT_ITERATION_MEMORY_ENABLED` 控制），写入轻量的迭代摘要；不抛异常，完全非侵入。
- 生产路径仍由 `ContextAssembler`（读取）与 `MemoryWriter`（回写）在编排层统一挂钩，确保记忆解耦与一致性。

## 故障定位与降级准则（重要）

- 先定位原因，后考虑降级：出现错误时不得直接走降级掩盖问题，必须先输出诊断并明确根因；仅在系统设计的场景下才允许最小化降级。
- 结构化输出强约束：凡要求 LLM 输出 JSON，调用端必须设置 `response_format: { "type": "json_object" }` 并在模板中明确“仅输出 JSON”。
