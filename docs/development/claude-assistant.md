# CLAUDE.md

Guidance for Claude Code (claude.ai/code) in this repository. Abstract principles, constraints, and boundaries only — commands, setup steps, and file lists belong in README and `docs/`.

## Core Architecture

MuseCraft is a multi-agent creative platform that turns text prompts into videos. The canonical runtime is the **single-episode harness**: a four-layer architecture (**编排 / 控制 / 门控 / 治理**) that both **Quick Mode** (one-shot) and **Project Mode** (multi-episode wrapper) share as their kernel.

### Architectural Invariants

Violating any of these is a regression, not a refactor:

- **Single mainline**: one `OrchestratorAgent` owns the single-episode lifecycle. No parallel orchestrators; historical variants were retired 2026-03-25.
- **Nested loops, not switchable modes**: the outer loop is the orchestrator advancing a fixed Leaf Agent sequence via a *policy-first* decision path (`report → gate → decision → apply`). The inner loop is ReAct, implemented **inside execution-class Leaf Agents only**. Never model these as two interchangeable execution modes.
- **Planning vs execution split is deliberate**: planning agents (Concept, Script, Quality Checker) run a single `BaseAgent` pass; execution agents (Image, Video, Audio, Voice, Composer) inherit `ReActAgent`. Moving an agent between these roles is an architectural decision.
- **Four layers only**: do not promote supporting capabilities (`ContextAssembler`, memory views, runtime substrate) or project wrappers (`EpisodeOrchestratorAgent`, `SeriesPlanner`) into a fifth layer.
- **Contract-frozen boundaries**: scene contract, consistency asset, script/video prompt, orchestration-context memory, and planner-execution-progress boundaries are frozen. Extending a frozen boundary requires opening a successor freeze, not editing in place.

### Agent Responsibility Boundaries

Each agent owns a non-overlapping decision domain. Do not let one agent re-plan another's decisions:

- **ConceptPlanner**: scene count, per-scene duration (chosen from provider-injected capabilities), intelligent style design.
- **ScriptWriter**: script content, scene continuity, narrative structure.
- **ImageGenerator**: keyframe visuals with consistency injection. No scene re-planning.
- **VideoGenerator**: per-segment synthesis using upstream decisions. No re-planning. If `image_generation` appears in its tool set, it is a sensitive-content replacement fallback only, not a primary image source.
- **VideoComposer**: FFmpeg assembly and audio mix. No scene or duration decisions.
- **QualityChecker**: validation only. If QC surfaces defects, the fix flows through the orchestrator, not by QC mutating upstream artifacts.
- **Tools**: pure executors. Tools analyze and suggest; they never decide.

### ReAct Scope

ReAct is an **agent-level inner loop**, never an orchestrator-level mode. Only execution-class Leaf Agents run it; the orchestrator runs a policy-first decision path over its fixed agent sequence. Do not introduce a second "ReAct orchestrator" alongside it.

## Design Philosophy

### Composition Over Single-Call

The system's value is in **composing discrete AI capabilities into cinematic output through agent orchestration**, not in any single API call. Video APIs expose discrete capabilities (e.g., 5s or 10s clips); agents decide scene count, per-scene duration, and style to produce arbitrary-length coherent video. This architecture's value *increases* with API evolution — new capabilities are absorbed by the composer layer without touching agents.

### Style Is Designed, Not Chosen

Agents create custom styles from a multi-dimensional framework (表现形式 / 叙事风格 / 制作品味 / 情感基调); they do not pick from preset lists. User intent (content) and intelligent style (visual execution) are kept separate and both flow downstream.

### Goal-Oriented, Not Bug-Driven

Work toward feature correctness, not the smallest patch that clears the current error. If FFmpeg is missing, surface the dependency — do not silently return the first scene's clip as a "fallback." Degradation paths are legitimate only when they preserve the feature's meaning; they are not shortcuts for closing an issue.

## Agent Design Principles

### Thinking Mode
- Planning agents enable thinking; execution agents disable it. Mixed agents split phases — upstream planning with thinking, downstream finalization without.
- Selection is a priori by agent role, not by content-complexity heuristics at the call site.

### Token Budgeting
- Two-tier defaults (standard vs thinking) live in central config, overridable by `.env`. Call sites do not hardcode token budgets.

### Function Call Discipline
- All tool steps go through Function Call — expose the function list, let the LLM choose.
- Thinking controls reasoning budget only; it does not affect FC decision capability.
- Pure LLM abilities (prompt enhancement, text polishing) use direct LLM calls, not tools.
- Chinese FC output rule: if tools are needed, return only `tool_calls`; if not, return the final Chinese answer in `content`. No explanations, headings, or code fences around either.

### Tool Architecture
- Tools are the **only** way agents extend LLM capability. All side-effects (IO, network, system) MUST be tools.
- Tools are registered centrally; swapping an implementation must not touch agent code.
- Tool layer owns dependency validation, timeout/retry/rate-limit, and observability. Agents do not replicate these.
- Agents are restricted to orchestration, strategy selection, pure transforms, and prompt assembly. They do not call external services directly.

### Memory and Fallback
- Context and creative guidance flow through a shared memory interface. Memory unavailability produces warnings, not workflow blocks.
- Read/write rules, tags, TTLs live in config, not code.
- Fallback paths go through tools or memory, not temporary IO.
- Retries are bounded by config; exhaustion degrades to a minimal viable result.

### Anti-Hardcoding
- No if/else/rule-trees that replace LLM semantic understanding, tool selection, or parameter decisions.
- Tool names and schemas are centrally defined (configuration, not hardcoding).
- Business thresholds move to config; no scattered magic numbers.
- Domain priors enter via system prompts and few-shot, not code branches.
- Preserve LLM Function Call decision rights. Agents declare capability boundaries; they do not override the LLM's choice.

## Code Style

- **Python**: type hints, async/await, PEP 8.
- **TypeScript**: strict mode; prefer interfaces over types.
- **Imports**: absolute; destructure when possible.
- **Errors**: real handling and logging, not swallowed exceptions.
- **Testing**: TDD — tests before implementation.
- **Commits**: conventional format with Chinese descriptions.

## Canonical References

When code and an older doc disagree, trust the canonical baseline, not the snapshot.

- **Baseline**: `docs/architecture/single_episode_harness_architecture_20260311.md` + `mas_architecture_alignment_note_20260323.md` define the four layers and vocabulary. Other architecture docs may only refine, never redefine.
- **Historical snapshots** (`multi-agent-system-analysis.md`, `MULTI_AGENT_REFACTORING_PLAN.md`, `multi-agent-communication-architecture.md`) predate the 2026-03-25 retirement and are for context only.
- **Deferred guardrails**: `docs/deferred-plans/CURRENT.md` holds active long-horizon constraints (e.g., media authority direction). Treat these as binding even when the target migration is not yet scheduled.

## Environment

- The project uses the **uv** Python environment. Run Python and tests through `uv run`.
- Backend default port 8000 (`API_HOST` / `API_PORT`); frontend default port 3000 (`PORT`). Operational commands and setup live in README and `docs/`.
