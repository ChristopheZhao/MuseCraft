Principles for Agents and Tools

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

References
- Composer Agent + Tools usage and ReAct guidelines: see docs/agents/composer_guidelines.md

## Working Memory and Context Editing Principles

- **Separate fact storage from context editing**: use working memory as the source of truth for iterate facts only (actions, observations, references). Keep context trimming/summary/usage receipts in a dedicated context editor layer with explicit contracts and budgets.
- **Prefer model-driven compaction with explicit diagnostics**: use LLM-based compaction or summarisation first, validate against a schema, and surface errors if the compacted view is still over budget or structurally invalid—never rely on silent fallbacks.
- **Drive policies through configuration**: express context budgets/quotas in configurable strategies; agents select strategies rather than hard-coding thresholds.
- **Load external state via adapters**: converting workflow state (or other business sources) into working memory snapshots should be handled by dedicated builders/adapters so agents depend on abstractions and retain single responsibility.

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

## Function-Call Exposure and Tool Assignment

- Assign tools explicitly per agent to define the available capability set; do not call providers directly from agent code.
- Expose function-call schemas selectively so the LLM may invoke only the safe/desired actions; high-risk operations should require explicit policy opt-in.
- Policies should be defined centrally (e.g., configuration files) and merged with tool metadata at runtime so changes take effect without code edits.
 - Tools are execution-only: do not split a tool into “plan” vs “execute” semantics at the agent layer. One FC round should produce the function calls and execute them in the same round; avoid maintaining intermediate planned_calls state in agents.

## ReAct 编排器（FC化）

- ReAct 编排的 THINK/PLAN 阶段通过 FC 只暴露“编排控制工具”的极简动作（如继续/重复/中止），避免在编排器中硬编码 if/else。
- ACT 阶段统一通过 `agent.execute(...)` 调用子 Agent，继承进度/超时/重试/WebSocket/记忆钩子等系统保障。
- REFLECT 使用事实驱动的完成判定（必需步骤 + 质量阈值或迭代上限），减少对 LLM 文本反思的强依赖。
- 当前 orchestrator 虽默认按工作流顺序调度，但内部依然走 ReAct 循环，任何 Agent 都需基于观察→计划→执行→反思决策；固定顺序只是过渡形态，便于随后在策略层按任务特征动态插入/跳过阶段。

## Composer 可重入与音频职责

- Composer 是“统一装配者”，可在工作流多阶段被多次调用：
  - 先做场景视频拼接（video-only）；
  - VoiceSynthesizerAgent 交付配音后，Composer 执行 add_voiceover 将旁白混入视频；
  - AudioAgent 交付等长可用的 BGM 后，Composer 再次执行“加配乐”；
  - 未来可在 SRT/SFX 就绪后再做多轨混合、响度标准化与 ducking。
- AudioAgent 的职责：
  - 观测（总时长/时间线/概念）→ 规划（AudioDesignPlan）→ 生成（供应商无关）→ 分析（静音/能量/候选截断点）→ 智能对齐（裁剪/循环/淡化），交付“等长可用”的音轨。
  - 不在 Agent 内直接做混流（除非回退模式），混流由 Composer 统一执行。
- VoiceSynthesizer 输出旁白时只做必要裁剪，不再强行把语音填满场景；Composer 根据工作流 `voice_mixing_state.timeline` 自动插入静音片段，保证时间线上声画对齐但保留自然留白。
- Composer 在混音阶段默认对背景音乐做自动压制（ducking），旁白出现时 BGM 自动降低 6~10 dB（可通过 `ducking_config` 调整），确保视频全流程在无人干预下也能得到清晰的语音与平衡的伴奏。
- VoiceSynthesizer 会基于 `voice_plan`、场景语气与 `voice_manifest.json` 的分类信息自动筛选音色，必要时再 fallback 到默认音色；若调用方传入 `auto_select=false` 则沿用指定音色。

## 记忆解耦与可选回写（ReAct 基类）

- ReAct 基类提供可选的“每轮回写钩子”（默认关闭，通过 `REACT_ITERATION_MEMORY_ENABLED` 控制），写入轻量的迭代摘要；不抛异常，完全非侵入。
- 生产路径仍由 `ContextAssembler`（读取）与 `MemoryWriter`（回写）在编排层统一挂钩，确保记忆解耦与一致性。

## 故障定位与降级准则（重要）

- 先定位原因，后考虑降级：出现错误时不得直接走降级掩盖问题，必须先输出诊断并明确根因；仅在系统设计的场景下才允许最小化降级。
- 结构化输出强约束：凡要求 LLM 输出 JSON，调用端必须设置 `response_format: { "type": "json_object" }` 并在模板中明确“仅输出 JSON”。
