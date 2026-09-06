# PLAN-20260808-069 A5 real-Agent mainline checkpoint

- Recorded at: `2026-08-16T04:03:07Z`
- Git base: `0c81520`
- Worktree state: uncommitted WIP; this checkpoint is evidence, not a commit or hosted-CI result.
- Verdict: local pass; PLAN-069 remains `in_progress` pending hosted CI and explicit user acceptance.

## Negative-first evidence

1. Episode outer coordination returned `waiting_gate`; the pre-A5 application allowlist accepted it and the parent completion side effect ran. The new counterexample failed with `DID NOT RAISE` before the caller-specific allowlist was introduced.
2. SeriesPlanner host returned `waiting_gate`; the pre-A5 application allowlist promoted the returned project definition. The new counterexample failed with `DID NOT RAISE` before project planning was restricted to terminal status.
3. Replacing the E2E specialist Agents had hidden two production facts. Once the production Agents ran, `build_video_generation_context` returned an empty `scenes_to_generate` set for a valid text-to-video scene because it hard-coded a reference-image prerequisite. The focused counterexample failed with `assert [] == [1]` before that capability assumption was removed.
4. Final receipt-authority review found that the same builder removed a planned scene whenever raw `video_path`/`video_url` existed, even without an accepted receipt. The counterexample again failed with `assert [] == [1]`; this proved that the context adapter was acting as a second completion source and could erase planned membership across ReAct turns.

## Implemented boundary corrections

- `QueuedExecutionUseCase` now uses caller-owned status sets: Quick runtime accepts explicit `waiting_gate`/`completed`; SeriesPlanner and Episode outer coordination accept only `completed`. Validation happens before project promotion or parent completion.
- `EpisodeExecutionCoordinator` separately validates child `waiting_gate`/`completed`; it never supplies a missing child status.
- `build_video_generation_context` projects the complete published scene plan into canonical membership, including scenes without `image_url`. It no longer reads `scene_outputs.video` or infers completion from artifact paths. The optional reference remains a fact for the LLM/tool schema; accepted/remaining progress is projected only by the existing receipt-backed `progress_read_model`.
- The maintained Quick E2E uses the production composition and real `ConceptPlannerAgent`, `ScriptWriterAgent`, `VideoGeneratorAgent`, and `VideoComposerAgent`. Deterministic implementations exist only at Celery, LLM, and allocated tool ports.

## Local validation

- Focused status/context/read-model suite: `51 passed`.
- Exact local equivalent of the hosted MAS runtime job: `154 passed, 25 deselected`; the new `receipt_authority` selector proves the counterexample is included.
- Maintained Quick E2E: `1 passed`.
- Full backend unit suite: `704 passed`.
- Architecture suite: `32 passed`.
- Offline VideoComposer ReAct/voiceover integrations: `2 passed`.
- `git diff --check`: passed; only platform line-ending warnings were emitted.
- `docs/plans/PLAN_INDEX.json`: valid JSON.

## MAS ownership review

- Decision owner: status wrappers validate and forward caller-owned states; they do not infer success. Video generation strategy remains with the LLM over the exposed tool schema.
- Layer boundary: queue/Celery remain transport only; attempts, gates, continuation and terminal state remain in the MAS control plane; clients still consume the runtime read model.
- Contract integrity: one thin exact-status validator is parameterized by the caller boundary; complete scene membership is derived only from the published scene contract, accepted progress only from receipt-validated `scene_outputs.video`, and final composition only from the current execution-bound finalize receipt.
- Symptom-patch drift: no legacy adapter, Agent replacement, test-only production branch, success default, fixed Agent-order assertion, provider-name branch, or parallel status/read-model source was added.

The real production `ScriptWriterAgent` still explicitly identifies itself as a `deterministic_mas_stage` with `native_agent=false`. A5 did not introduce or hide that existing boundary and does not claim that every specialist is a native ReAct Agent; changing its domain execution strategy is outside A5 and requires separate governance if selected.
