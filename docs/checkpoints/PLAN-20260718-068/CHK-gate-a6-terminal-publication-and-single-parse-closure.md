# Checkpoint: Gate A6 terminal publication and single-parse closure

- Plan: `PLAN-20260718-068`
- Gate: A6
- Status: local_pass
- Recorded at: 2026-07-26T12:44:20+08:00

## Accepted Boundary

- Runtime report `status` is the only orchestration outcome forwarded to runtime
  policy. The protocol projection removes the legacy reflection
  `completion_state` alias without reconciling it with output payload data.
- Non-script runtime success now evaluates the runtime boundary, publishes
  authoritative output, and only then completes the attempt. Publication or terminal
  transition failure rolls back workflow maps and composer facts.
- LLM decomposition and continuation persistence use one task-spec parser for
  required control fields, exact JSON types, candidate uniqueness, candidate/spec
  ownership, and exact checkpoint version type. Queue, context, read-model, resume,
  and conditional activation consumers use the parsed identity and control values
  without reconstructing defaults or coercing them.
- VideoGenerator finalization explicitly loads MAS shared scene-output authority.
  Shared-authority load failure is typed, and only producer-issued receipts whose
  single `status` outcome is `accepted` enter final scene outputs.
- Receipt enum parsing checks JSON type before membership, and receipt issuance does
  not manufacture integer scene identity from malformed source data. Producer and
  storage fields remain optional diagnostics rather than competing acceptance states.

## Negative Cases Proved

- Composer publication failure cannot leave a completed attempt, workflow result
  mutation, or partial `project.final_video` / `project.final_video_mix` publication.
- Terminal attempt completion failure rolls back the publication that preceded it.
- Missing primary `run`, duplicate candidates, candidate/spec owner mismatch, float
  checkpoint version, and non-canonical conditional Agent identity are rejected.
- Explicit empty candidate/standby collections remain authoritative rather than
  falling back to inferred execution.
- Video artifacts present only in MAS shared WM finalize once; rejected receipts are
  excluded; shared-authority load failure never falls back to Agent-scoped memory.
- Receipt enum values supplied as list/dict return typed rejection, and a string scene
  number cannot be converted into a canonical receipt.
- Post-receipt storage diagnostics do not override the receipt's single accepted
  outcome, while receipt identity and provenance mismatches remain explicit.

## Evidence

- A6 focused suite:
  `228 passed, 2 warnings`.
- MAS runtime CI selector:
  `140 passed, 20 deselected, 2 warnings`.
- Exact backend-boundaries CI file set:
  `62 passed, 2 warnings`.
- Feasible full backend unit regression:
  `628 passed, 2 deselected, 2 warnings`.
- The two deselections remain the known Windows Conda `pyOpenSSL`/OpenSSL
  incompatibility reached through `oss2`:
  `test_default_tool_registration_exposes_core_capabilities` and
  `test_draft_narration_generates_natural_text`.
- Black checked all 15 changed Python files with a workspace-local cache; isort,
  Python compilation, plan-index JSON, workflow YAML, and `git diff --check` passed.

## Review Verdict

- Verdict: root-cause fix.
- Decision ownership remains in the MAS control plane; queue and external scheduler
  layers do not acquire runtime semantics.
- Contract code parses and projects representations without inventing missing mission
  content or reconciling multiple success signals.
- Scene acceptance remains producer-issued and read-model-driven; no consumer-side
  compatibility fallback or prompt-local patch was added.
- No SQL engineering, Docker, launcher, authentication, open-source packaging,
  provider, or project-deletion scope entered A6.

## Remaining Gate

- The A6 implementation and tests are committed locally as `b6c6f32`, `b925b82`,
  and `58da249`; this checkpoint and the plan/index synchronization are carried by
  the accompanying governance commit. Local commits must not be represented as
  shipped work.
- No push was performed.
- Hosted `release-contracts`, `mas-runtime`, `backend-boundaries`, and
  `postgres-runtime-contracts` evidence remains pending an authorized push.
- PLAN-068 therefore remains `in_progress`.
