# Checkpoint: Gate A2 authority and transparency closure

- Plan: `PLAN-20260718-068`
- Gate: A2
- Status: passed
- Recorded at: 2026-07-21T10:14:29+08:00

## Accepted Boundary

- `ProjectDefinition` is the versioned authored/editorial write authority. Runtime
  state, workflow identity, generated assets, observed usage, and derived progress are
  excluded and unknown root fields fail strict normalization.
- Project planning and episode-enqueue commands use CAS and one application UoW for
  their project-definition and Task changes. A stale version returns
  `project_version_conflict` without a blind retry.
- `ProjectExecutionReadModel` is immutable and derived from project definition, Task,
  workflow runtime, approved deliverables, and attempt metrics without a save path.
- Fixed multi-episode sequencing is owned by `EpisodeExecutionCoordinator`, not an
  Agent. The MAS orchestrator is classified as control-plane logic and receives
  runtime/reference ports from an infrastructure composition root.
- Context assembly is read-only. ReAct contract failures halt with typed diagnostics,
  tool visibility errors expose no FC actions, optional memory writes return typed
  receipts, and Agent music allocation uses `music_generation` rather than a provider
  name.

## Expectation Checks

- A2.0: transitive Agent/control-plane dependency scanning reaches no SQLAlchemy,
  database composition, ORM model, or concrete store path.
- A2.1: same-version writes produce one commit and one typed conflict; an injected
  Task-completion failure rolls back the project-definition update.
- A2.2: API serialization consumes the immutable projection and leaves the definition
  version unchanged.
- A2.3: the episode coordinator is absent from Agent exports/allocation; the episode
  execution adapter creates the child runtime atomically but does not choose terminal
  Task/runtime state.
- A2.4: missing prepared scene references, ReAct evaluator/overlay failures, visibility
  exceptions, and memory write failures all produce the intended explicit outcome.
- A2.5: changing the configured provider behind `MusicGenerationTool` does not change
  the Agent allocation identifier.

## Evidence

- Full backend unit suite: `549 passed, 2 warnings`.
- Wider PLAN-066 runtime regression: `101 passed, 2 warnings` across orchestrator
  mainline, audio runtime gate, and task endpoints.
- Project/CAS/coordinator focused suite: `14 passed, 2 warnings`.
- Boundary-transparency focused suite: `33 passed, 3 failed` initially; all three
  failures were repaired and their focused rerun passed. The failures exposed dropped
  ReAct diagnostics and an incorrect scene-payload test assertion.
- Release migration contract: `4 passed, 2 warnings`, including upgrade/check/downgrade
  and one linear head at `20260719_0002`.
- Local static execution: 12 Agent/A2 architecture tests passed; `compileall`,
  `git diff --check`, and plan-index JSON validation passed.
- Scoped Black/isort passed for 23 new or fully rewritten files.
- Bounded mypy with `--follow-imports=skip` passed for 13 new boundary modules. The
  unrestricted focused mypy run timed out on WSL `/mnt/d` dependency traversal and is
  not claimed as evidence.

The two warnings are existing SQLAlchemy and Pydantic deprecations.

## Remaining Gates

Gate A2 does not complete `PLAN-20260718-068`. Gate E/F still require a clean
PostgreSQL fixture with accepted credentials, fresh release migration/preflight, uv
startup smoke, and PostgreSQL lease/gate/continuation transaction evidence. Existing
MySQL data remains out of scope and must not be stamped or modified.
