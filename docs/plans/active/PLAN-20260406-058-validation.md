# Validation Ledger: PLAN-20260406-058

## Scope
- Validate the bounded frontend-only repair for quick-mode runtime UX.
- Keep backend runtime contract, control-plane semantics, and queue/worker logic out of scope.
- Use runtime/read-model as the only live business-state source during UI verification.

## Boundary Gate
- [ ] Confirm `058` remains frontend-only for Sprint 1 and Sprint 2
- [ ] Confirm no backend contract/schema changes are introduced
- [ ] Confirm no UI logic infers runtime truth from Celery/worker/broker state
- [ ] Confirm export behavior does not pretend unsupported multi-format/transcode capability

## Validation Strategy
- Primary browser path:
  - Playwright Firefox is the primary end-to-end validation path for this plan.
- Supporting checks:
  - Targeted component/unit tests may be added for branch-heavy UI state logic.
  - Type-check and production build remain required regression gates.
- Tooling note:
  - Playwright Firefox is treated as an already-available local validation tool; this plan does not add repo-level installation or dependency-enablement work.

## Sprint 1 Gate: Fresh-run Bootstrap + Real Download
- [ ] Fresh quick-task creation no longer shows `恢复条件缺失 / missing_current_attempt` during bootstrap
- [ ] Existing explicit resume / HITL waiting states still render correctly when they are real
- [ ] Export area now performs a real download of the current final video
- [ ] Fake export progress / fake success semantics are removed

## Sprint 1 Evidence Design
- Playwright Firefox:
  - Start a fresh quick task and observe the processing view during the first polling window
  - Assert no `resume_blocked` warning banner is shown for bootstrap-only `missing_current_attempt`
  - Drive a completed-task review/export path and assert a browser download is triggered
- Regression checks:
  - Verify real HITL waiting state still presents a blocking review/continue cue
  - Verify failed runtime state still presents failure diagnostics rather than a bootstrap placeholder
- Automated checks:
  - `npm run type-check`
  - `npm run build`
  - bounded frontend test command(s) covering bootstrap banner logic and export action behavior

## Sprint 2 Gate: Runtime-driven Workspace Reshape
- [ ] A single frontend design direction is selected and recorded before implementation
- [ ] The quick workspace no longer preserves the current fixed pipeline skeleton as the main visual structure
- [ ] Current node becomes the primary visual focus
- [ ] Future nodes do not pre-occupy the main canvas/workspace
- [ ] Skipped nodes are visibly de-emphasized or folded away from the mainline
- [ ] Top four-step bar is visually demoted to product navigation rather than runtime truth

## Sprint 2 Evidence Design
- Design review evidence:
  - Capture the chosen workspace direction and rejected alternatives in the plan or linked artifact
- Playwright Firefox:
  - Exercise an in-flight runtime and verify the workspace foregrounds the current node rather than a pre-rendered full pipeline
  - Exercise a runtime where `voice` / `audio` are skipped and verify they do not appear as equal-weight mandatory mainline steps
  - Verify current artifact/diagnostic panels remain visible and coherent while the runtime advances
- Supporting checks:
  - targeted component tests for node-visibility derivation and skipped-node presentation rules
  - `npm run type-check`
  - `npm run build`

## Sprint 3 Gate: Infinite-canvas Spike
- [ ] Sprint 3 starts only after Sprint 2 completion and explicit need confirmation
- [ ] Prototype stays isolated from the stable quick-mode path
- [ ] Spike ends with an explicit keep/promote/reject verdict
- [ ] Any backend graph-metadata requirement is documented as a follow-on contract plan, not silently assumed

## Sprint 3 Evidence Design
- Playwright Firefox or equivalent manual prototype walkthrough:
  - Verify pan/zoom/focus behavior if a canvas prototype is implemented
  - Verify the prototype still consumes runtime/read-model truth rather than invented graph semantics
- Decision evidence:
  - Record why the spike is worth keeping, promoting, or rejecting
  - Record which missing graph metadata would be required for a true graph workspace

## Regression Rules
- Do not treat `task detail` or `resources` projection as live runtime truth.
- Do not show bootstrap attachment as a resume failure.
- Do not claim export success without an actual file download path.
- Do not reintroduce a fixed all-nodes skeleton as the main runtime workspace.

## Evidence Log
- 2026-04-06T08:31:00Z Validation ledger created for `PLAN-20260406-058`.
- 2026-04-06T08:31:00Z Validation approach frozen:
  - Playwright Firefox is the primary browser validation path
  - Sprint gates remain frontend-only unless a future graph contract plan is explicitly opened
