# Checkpoint: Gate A5 thin contract boundaries

- Plan: `PLAN-20260718-068`
- Gate: A5
- Status: local_pass
- Recorded at: 2026-07-26T10:03:28+08:00

## Accepted Boundary

- The explicit orchestration report owns one outcome through its top-level `status`.
  Output payload and reflection fields remain domain data and are not reconciled into a
  second success state.
- Runtime boundary evaluation and attempt/gate transition occur before workflow output
  or final-video facts are published authoritatively.
- LLM task decomposition continues to request
  `response_format={"type":"json_object"}` and its task specs use the same thin,
  exact-type parser as continuation checkpoint persistence and resume.
- Scene-output acceptance receipts have one parser that checks required keys, JSON
  types, and canonical enum values. The acceptance evaluator consumes the parsed values
  without string, integer, whitespace, or case coercion.
- Empty standby authority, scene read-model precedence, continuation Agent owner
  agreement, and atomic project compare-and-delete remain accepted from A4/A3.

## Negative Cases Proved

- `output.success=false` and `reflection.completion_state=partial` cannot override an
  explicit report `status=completed`; a report `status=partial` still fails the runtime
  success boundary.
- Runtime-boundary failure leaves `workflow_results`, `workflow_data`,
  `project.final_video`, and `project.final_video_mix` unpublished.
- Continuation/task-spec mission, deliverable, constraints, order, runtime hints,
  conditional identity, trigger, scope, booleans, Agent identity, and checkpoint
  identity fields reject wrong JSON types instead of coercing them.
- Receipt `scene_number="1"`, `artifact_kind=" Image "`, and non-canonical status or
  producer status are rejected by the receipt parser.
- LLM task decomposition rejects malformed task-spec field types at the shared parser
  boundary and retains explicit JSON response-format coverage.

## Evidence

- A5 focused suite:
  `147 passed, 2 warnings`.
- MAS runtime CI selector:
  `137 passed, 18 deselected, 2 warnings`.
- Exact backend-boundaries CI file set:
  `62 passed, 2 warnings`.
- Feasible full backend unit regression:
  `613 passed, 2 deselected, 2 warnings`.
- The two deselections remain the known Windows Conda `pyOpenSSL`/OpenSSL incompatibility
  reached through `oss2`:
  `test_default_tool_registration_exposes_core_capabilities` and
  `test_draft_narration_generates_natural_text`.
- Scoped Black diff and isort checks passed. Python compilation, plan-index JSON,
  relevant YAML parsing, and `git diff --check` passed.

## Review Verdict

- Decision ownership remains in the MAS control plane.
- The correction does not add prompt-local patches, provider branches, queue-owned
  runtime semantics, or cross-field reconciliation rules.
- The contract surface is thinner than A4: one report outcome and one parser per
  module-owned structured output.
- The A4 checkpoint remains historical evidence but its thick-validator acceptance
  wording is superseded by this checkpoint.

## Remaining Gate

- The correction is committed locally as `4385e22`, `5660f4e`, `048a338`, and
  `ceffacd`; the tracked worktree is clean.
- No push was performed.
- Hosted `release-contracts`, `mas-runtime`, `backend-boundaries`, and
  `postgres-runtime-contracts` evidence remains pending an authorized push.
- PLAN-068 therefore remains `in_progress`.
