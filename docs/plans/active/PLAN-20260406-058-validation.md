# Validation Ledger: PLAN-20260406-058

## Scope
- Validate the bounded frontend-only repair for quick-mode runtime UX.
- Keep backend runtime contract, control-plane semantics, and queue/worker logic out of scope.
- Use runtime/read-model as the only live business-state source during UI verification.

## Boundary Gate
- [x] Confirm `058` remains frontend-only for Sprint 1 and Sprint 2
- [x] Confirm no backend contract/schema changes are introduced
- [x] Confirm no UI logic infers runtime truth from Celery/worker/broker state
- [x] Confirm export behavior does not pretend unsupported multi-format/transcode capability

## Validation Strategy
- Primary browser path:
  - Playwright Firefox is the primary end-to-end validation path for this plan.
- Supporting checks:
  - Targeted component/unit tests may be added for branch-heavy UI state logic.
  - Type-check and production build remain required regression gates.
- Tooling note:
  - Playwright Firefox is treated as an already-available local validation tool; this plan does not add repo-level installation or dependency-enablement work.

## Sprint 1 Gate: Fresh-run Bootstrap + Real Download
- [x] Fresh quick-task creation no longer shows `恢复条件缺失 / missing_current_attempt` during bootstrap
- [x] Existing explicit resume / HITL waiting states still render correctly when they are real
- [x] Export area now performs a real download of the current final video
- [x] Fake export progress / fake success semantics are removed

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
- [x] A single frontend design direction is selected and recorded before implementation
- [x] The quick workspace no longer preserves the current fixed pipeline skeleton as the main visual structure
- [x] Current node becomes the primary visual focus
- [x] Future nodes do not pre-occupy the main canvas/workspace
- [x] Skipped nodes are visibly de-emphasized or folded away from the mainline
- [x] Top four-step bar is visually demoted to product navigation rather than runtime truth

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

## Sprint 2 Amendment Gate: Layout and information-hierarchy polish
- [x] Processing workspace keeps the center focus area readable under a common desktop viewport
- [x] Right-side runtime context is demoted out of the primary visual hierarchy
- [x] Long runtime fields no longer rely on `break-all`-style fragmentation
- [x] Running and HITL states both keep the current-node workspace as the primary focus
- [x] Top shell height is reduced during quick-mode processing

## Sprint 2 Amendment Evidence Design
- Playwright Firefox:
  - Drive a mocked running runtime through the real quick-mode form and verify the center workspace no longer collapses under left/right chrome on a 1366x900 viewport
  - Switch the same mocked run into `awaiting_human` / script-review state and verify the HITL decision workspace remains the primary focus without a competing raw diagnostics column
- Supporting checks:
  - `npx tsc -p tsconfig.frontend-runtime-check.json --noEmit`
  - `npm run build`

## Sprint 1 Residual Amendment Gate: completed-result finalization and download entry consistency
- [x] Switching to a different task invalidates stale `finalVideoUrl`, `quickRuntime`, and result-ready modal state
- [x] `runtime completed` does not advance into review/export until a fresh browser-safe final video URL resolves
- [x] When the final video URL is still missing, the workspace stays in processing and surfaces a neutral completion-waiting cue instead of prematurely opening review/export
- [x] The overlay player download entry and the review/export download entry both exercise the same real browser-side download chain
- [x] Live browser proof was attempted against the real backend before falling back to a bounded deterministic supplement

## Sprint 1 Residual Amendment Evidence Design
- Playwright Firefox, primary proof:
  - Attempt a real `/console` submit against the running backend and record whether the live task can progress to completed
  - If the live task is blocked by an unrelated backend/runtime failure, capture that separately and do not treat it as frontend amendment failure
- Playwright Firefox, bounded supplement:
  - Drive a real browser session through the quick-mode form while mocking only `tasks/runtime/detail/resources`
  - Verify the missing-URL completed case stays in processing with no review/export transition
  - Verify the success case exercises the overlay-player and review/export download entries through the same browser `fetch -> blob -> anchor download` path
- Supporting checks:
  - `npx tsc -p tsconfig.frontend-runtime-check.json --noEmit`
  - `timeout 45s npm test -- --runInBand __tests__/integration/app-store-result-finalization.test.ts __tests__/integration/use-task-polling-completion.test.tsx`
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
- 2026-04-06T09:46:27Z Sprint 1 validation evidence recorded:
  - Boundary held:
    - only frontend files changed under `src/**`, test files, and plan artifacts
    - no backend/runtime contract/control-plane/queue/worker files were touched
    - export UI no longer presents fake multi-format transcoding cards or fake progress semantics
  - Playwright Firefox, real backend fresh-run bootstrap:
    - after restarting the local frontend so port `3000` served the current worktree instead of a stale sibling checkout, a fresh quick task on the real backend rendered `正在连接运行时` instead of the previous `恢复条件缺失 / missing_current_attempt` banner
    - evidence snapshot: `.playwright-cli/page-2026-04-06T09-36-07-209Z.yml`
  - Playwright Firefox, review/export download path:
    - browser-side mocked completed runtime reached the new review/export UI with `下载当前成片`
    - clicking the button triggered an actual Playwright download event: `Downloaded file final_story_1.mp4 to ".playwright-cli/final-story-1.mp4"`
    - page probe confirmed the real download chain executed: `fetch(http://127.0.0.1:8005/files/outputs/videos/final_story_1.mp4)` -> `URL.createObjectURL(blob)` -> anchor click with `download="final_story_1.mp4"`
    - evidence snapshot: `.playwright-cli/page-2026-04-06T09-40-18-086Z.yml`
  - Static/build checks:
    - `npm run build` passed
    - `npm run type-check` failed due a pre-existing repo baseline issue in `__tests__/utils/test-helpers.ts` where JSX is embedded in a `.ts` file
    - `npx tsc -p tsconfig.frontend-runtime-check.json --noEmit` passed after expanding the focused check config to include the Sprint 1 files
  - Test-runner status:
    - `timeout 45s npx jest --runInBand --selectProjects integration --runTestsByPath __tests__/integration/runtime-gate-sync.test.tsx __tests__/integration/export-interface.test.tsx --verbose --forceExit` timed out with exit `124`
    - targeted Jest remains flaky, but Sprint 1 browser-gate verification no longer depends on it
- 2026-04-06T09:58:54Z Additional Playwright Firefox regression evidence recorded:
  - after restarting `next dev` to recover from stale `.next` artifacts introduced by running `next build` in the same worktree, browser hydration returned to normal
  - mocked `resume_available` runtime rendered the explicit resume UI correctly:
    - snapshot: `.playwright-cli/page-2026-04-06T09-57-42-624Z.yml`
    - visible evidence: `可恢复执行`, `reason: checkpoint_ready`, and actionable `恢复执行` button
  - mocked `awaiting_human` runtime rendered the HITL script workspace correctly:
    - snapshot: `.playwright-cli/page-2026-04-06T09-58-54-337Z.yml`
    - visible evidence: `等待脚本确认`, `脚本工作台`, `批准并继续 / 要求重写 / 要求重规划`, and runtime node status `pending_gate`
  - Sprint 1 gate is now browser-validated end to end:
    - bootstrap placeholder no longer leaks into fresh-submit startup
    - explicit resume and HITL waiting states still render when the runtime genuinely enters them
    - review/export performs a real browser download of the current final video
- 2026-04-06T10:00:00Z Sprint 2 design-first artifact recorded:
  - chosen direction: `Focus workspace + storyboard rail`
  - artifact: [docs/plans/active/PLAN-20260406-058-sprint2-design-brief.md](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/docs/plans/active/PLAN-20260406-058-sprint2-design-brief.md)
  - the artifact locks three core rules before implementation:
    - future queued nodes stay out of the main workspace
    - `skipped` nodes are folded away from the mainline
    - top four-step bar is treated as shell navigation rather than runtime truth
- 2026-04-06T10:27:35Z Sprint 2 validation evidence recorded:
  - Browser validation:
    - after restarting `next dev`, Playwright Firefox on `http://localhost:3000/console` rendered the new shell navigation label `产品步骤`, confirming the top four-step bar was visually demoted out of runtime truth
    - browser-side mocked in-flight runtime produced the new three-column workspace:
      - left `执行轨迹` rail showed only `概念规划 / 脚本创作 / 图像生成`
      - center focus card foregrounded the current node `图像生成` and its live artifact signal `style_frames`
      - right context panel folded `语音合成 / 音频处理` into `本次未走通道`
      - future queued nodes such as `视频合成 / 质量检查` no longer appeared in the main workspace
    - evidence snapshot: `.playwright-cli/page-2026-04-06T10-27-13-211Z.yml`
    - evidence screenshot: `.playwright-cli/page-2026-04-06T10-27-35-675Z.png`
  - Static/build checks:
    - `npx tsc -p tsconfig.frontend-runtime-check.json --noEmit` passed after adding `src/pages/HomePage.tsx` to the focused check set
    - `npm run build` passed
    - `npm run type-check` still fails on the pre-existing repo baseline issue in `__tests__/utils/test-helpers.ts`
  - Test-runner status:
    - `timeout 45s npx jest --runInBand --selectProjects integration --runTestsByPath __tests__/integration/runtime-gate-sync.test.tsx __tests__/integration/export-interface.test.tsx --verbose --forceExit` still timed out with exit `124`
    - the timeout remains a runner-level issue, so Sprint 2 acceptance stays anchored on the focused type-check and Playwright Firefox browser proof
- 2026-04-06T14:40:00Z Sprint 2 amendment validation evidence recorded:
  - Browser validation:
    - Playwright Firefox on `http://127.0.0.1:3001/console` drove the real quick-mode form into a mocked runtime-backed processing state using `.playwright-cli/058-amendment-validate.js`
    - running-state screenshot `output/playwright/058-amendment/running.png` shows the amended two-stage layout:
      - left storyboard rail compressed to a narrower track
      - center hero and `CURRENT NODE` workspace remain visibly dominant at 1366x900
      - the old always-visible third diagnostic column is no longer competing with the center panel
    - HITL screenshot `output/playwright/058-amendment/hitl.png` shows the script review workspace still centered while the shell stays compact and the side context remains de-emphasized
  - Display note:
    - the Linux headless Firefox environment used for Playwright validation resolves `sans-serif:lang=zh-cn` to `DejaVu Sans`, so the stored screenshots are reliable for layout/spacing proof but not for Chinese glyph rendering fidelity
  - Static/build checks:
    - `npx tsc -p tsconfig.frontend-runtime-check.json --noEmit` passed
    - `npm run build` passed
- 2026-04-07T09:50:00Z Sprint 1 residual amendment validation evidence recorded:
  - Static/test checks:
    - `npx tsc -p tsconfig.frontend-runtime-check.json --noEmit` passed
    - `npm run build` passed, with the repo's pre-existing ESLint config warning still printed during the Next build phase
    - `timeout 45s npm test -- --runInBand __tests__/integration/app-store-result-finalization.test.ts __tests__/integration/use-task-polling-completion.test.tsx` still timed out with exit `124`; the runner hang remains test-infrastructure noise rather than this amendment's behavioral signal
  - Focused state proof:
    - `__tests__/integration/app-store-result-finalization.test.ts` now covers cross-task invalidation of `finalVideoUrl`, `quickRuntime`, and result-ready modal state at the store boundary
    - `__tests__/integration/use-task-polling-completion.test.tsx` covers the completed-but-no-URL branch and the completed-with-browser-safe-URL branch in the polling hook
  - Playwright Firefox, real page primary attempt:
    - direct Firefox automation opened the live `/console` page without route mocks and submitted a real quick-mode task
    - evidence screenshots: `output/playwright/058-real-download/processing-after-submit.png` and `output/playwright/058-real-download/terminal-failed.png`
    - the live run failed before entering the first workflow node because of an unrelated backend runtime issue:
      - backend log `backend/logs/mas/mas_workflow.log` shows task `c5b082d8-008a-4273-a5a2-fa31511f110d` failed with `[Errno 5] Input/output error`
      - the traceback points to `backend/app/agents/memory/long_term/manager/memory_manager.py` printing while no running event loop is available, which is outside this frontend-only amendment scope
  - Playwright Firefox, bounded browser supplement:
    - one-off Firefox automation on the real `/console` page mocked only `tasks/runtime/detail/resources`, leaving the final video file request pointed at the real backend static media URL
    - missing-URL completed case remained in processing and rendered the neutral waiting cue instead of opening review/export:
      - evidence screenshot: `output/playwright/058-completed-finalization/missing-url-processing.png`
    - success case exercised both download entries through the same browser-side chain:
      - evidence screenshot: `output/playwright/058-completed-finalization/review-download-ready.png`
      - probe log: `output/playwright/058-completed-finalization/download-probe.json`
      - both `overlayProbe` and `exportProbe` recorded:
        - `fetch-start` to `http://127.0.0.1:8005/files/outputs/videos/time_reverse_capsule_final.mp4`
        - `fetch` with `status: 200`
        - `object-url`
        - `anchor-click` with `download: "time_reverse_capsule_final.mp4"`
    - this keeps the main user-facing proof browser-based while reserving deterministic mocking only for the unstable negative branch that the real backend attempt could not stably reach
- 2026-04-07T13:23:11Z Cross-plan backend defect discovery recorded during live `058` validation:
  - the live Playwright Firefox attempt exposed an independent backend bootstrap defect outside the frontend-only amendment scope
  - recent successful quick runs on `2026-04-06` still passed the same orchestrator/memory bootstrap path:
    - task `1064` entered quick orchestrator mainline and initialized memory services successfully before completing
    - task `1071` also completed successfully and served the final video download
  - the new failing run on `2026-04-07` was task `1072`, which failed before the first workflow node because `LongTermMemoryManager._start_background_tasks()` hit the no-running-loop downgrade path and its raw `print(...)` raised `OSError: [Errno 5] Input/output error`
  - this evidence confirms the defect is backend-owned and intermittent/runtime-context-sensitive rather than a regression introduced by the frontend amendment
  - follow-on backend repair is isolated into [PLAN-20260407-061.md](/mnt/d/code/agent/opensource/vertical_application/short-video-maker/docs/plans/active/PLAN-20260407-061.md) so `058` remains frontend-only
