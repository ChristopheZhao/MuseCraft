# Validation Ledger: PLAN-20260328-033

## Scope
- Plan:
  - [PLAN-20260328-033.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/plans/active/PLAN-20260328-033.md)
- Goal:
  - govern stale local `8005`-style API/worker residuals through the dev startup harness without reopening MAS runtime ownership

## Phase 0
- Status: completed
- Planned checks:
  - verify the live dev process inventory that produced stale `8005` / current `8006` coexistence
  - verify current startup scripts only clean residuals on exit and provide no startup preflight
  - verify existing reset tooling is intentionally narrow and does not already solve startup residual governance
- Evidence:
  - `ps -ef | rg 'uvicorn app.main:app|watchmedo auto-restart|celery -A app.services.celery_app'` showed long-lived `8005` API, worker, and beat processes from 10:14 plus a separate current-code `8006` uvicorn process from 11:54
  - [start_dev_uv.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/scripts/start_dev_uv.py) starts API/worker/beat but only does best-effort broad cleanup inside `cleanup_processes(...)` during shutdown; there is no startup-side residual detection or fail-fast gate
  - [start_dev.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/scripts/start_dev.py) and [dev.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/scripts/dev.py) confirm there is no alternate managed preflight path already governing repo-local stale services
  - [reset_celery_dev_state.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/scripts/reset_celery_dev_state.py) is intentionally limited to Redis broker/result flushing after services are stopped; it does not own process discovery or startup lifecycle governance
- Results:
  - stale `8005` is confirmed as a dev-harness process-lifecycle defect, not a MAS runtime regression
  - the missing capability is startup-time residual detection and explicit operator handling for repo-local managed services

## Phase 1
- Status: completed
- Planned checks:
  - classify whether manual `pkill -u "$USER" -f '/short-video-maker/backend/'` is a reasonable formal exit path or only an emergency operator tool
  - freeze launcher-vs-app-lifecycle ownership for dirty shutdown symptoms
  - freeze a bounded `Ctrl+C` contract that does not require broad kill semantics
- Evidence:
  - [start_dev_uv.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/scripts/start_dev_uv.py) launches long-lived children in separate process groups via `preexec_fn=os.setsid` and then blocks on `api_process.wait()`, so terminal `Ctrl+C` first interrupts the parent wait path rather than directly delivering shutdown semantics to every child process group
  - [start_dev_uv.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/scripts/start_dev_uv.py) only attempts child shutdown inside `cleanup_processes(...)`, and still falls back to broad `pkill` patterns for `uvicorn app.main:app`, `watchmedo auto-restart`, and `celery`
  - [monitoring_service.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/monitoring_service.py) creates `_init_redis()` tasks during object construction, and [enhanced_ai_client.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/services/enhanced_ai_client.py) does the same, which explains why `Task was destroyed but it is pending!` is an app-lifecycle hygiene signal rather than a launcher-ownership signal
  - [main.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/main.py) only manages the websocket cleanup task inside FastAPI lifespan; it does not own shutdown for those import-time service init tasks
  - the reported shell trace showed `KeyboardInterrupt` in the launcher's blocking wait followed by a later clean uvicorn shutdown only after manual repo-scoped `pkill`, confirming that the current standard exit path is insufficient while the repo-scoped `pkill` works as an emergency escape hatch
- Results:
  - manual repo-scoped `pkill` is acceptable as a temporary operator recovery tool, but not as the formal dev-launcher exit contract
  - launcher governance is now explicitly bounded to repo-scoped process discovery/spawn/stop only
  - app lifecycle hygiene is now explicitly bounded to import-time async init and shutdown cleanup, and must be fixed separately without pulling those responsibilities into the launcher
  - the next implementation slice should preserve this split: tighten `Ctrl+C` shutdown in the launcher and queue a separate app-lifecycle cleanup follow-up if pending-task warnings remain

## Phase 2
- Status: completed
- Planned checks:
  - decide whether the first implementation slice can stay fully inside `start_dev_uv.py` and its focused tests
  - freeze one shared scoped matcher for startup preflight, opt-in cleanup, and interrupt/exit cleanup
  - freeze the focused validation bundle without pulling app-lifecycle fixes into the same patch
- Evidence:
  - [test_start_dev_uv.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/tests/unit/test_start_dev_uv.py) currently covers only stdout/stderr forwarding behavior, leaving enough room to add residual-detection and interrupt-cleanup tests without touching unrelated suites
  - [start_dev.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/scripts/start_dev.py) and [dev.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/scripts/dev.py) are legacy/thin wrappers and do not need to become new governance owners for the first slice
  - [start_dev_uv.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/scripts/start_dev_uv.py) already centralizes launcher-owned responsibilities, so startup preflight and scoped interrupt cleanup can be added there without crossing into runtime or app-lifecycle owners
  - the Phase 1 boundary freeze already established that `main.py`, `monitoring_service.py`, and `enhanced_ai_client.py` must stay out of this initial patch, which keeps the slice architecture-safe
- Results:
  - first implementation slice is frozen to `start_dev_uv.py` + `test_start_dev_uv.py` only
  - startup preflight, opt-in cleanup, `Ctrl+C` shutdown, and exit residual cleanup must share one repo-scoped matcher contract
  - app-lifecycle pending-task cleanup is explicitly excluded from this slice and remains a separate follow-up concern if warnings persist after launcher fixes

## Phase 3
- Status: completed
- Planned checks:
  - verify the launcher patch stays inside `start_dev_uv.py` and direct launcher tests
  - verify startup residual detection and cleanup opt-in behavior with direct code-contract smokes
  - verify interrupt-time cleanup path without relying on app-lifecycle changes
  - record any runner-level verification anomalies separately from launcher correctness
- Evidence:
  - [start_dev_uv.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/scripts/start_dev_uv.py) now adds `ManagedProcessGroup`, repo-scoped process discovery via `/proc/<pid>/cwd`, startup preflight through `_handle_startup_residuals(...)`, explicit `--cleanup-residuals`, and scoped shutdown cleanup without broad `pkill`
  - [test_start_dev_uv.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/tests/unit/test_start_dev_uv.py) now covers repo-root filtering, fail-fast startup behavior, cleanup opt-in, scoped cleanup behavior, and the launcher `KeyboardInterrupt` path
  - `cd backend && uv run python -m py_compile scripts/start_dev_uv.py tests/unit/test_start_dev_uv.py`
  - `cd backend && uv run python -c "... _collect_repo_managed_process_groups(...) ..."` returned `collect_ok`
  - `cd backend && uv run python -c "... _handle_startup_residuals(..., cleanup_residuals=True) ..."` returned `preflight_ok`
  - `cd backend && uv run python -c "... m.main([]) ..."` returned `interrupt_ok`
  - `cd backend && uv run pytest ...` and `.venv/bin/python -m pytest --version` both hung in this environment, so pytest runner stability could not be used as acceptance evidence for this slice
- Results:
  - launcher-scoped implementation completed without crossing into `main.py`, `monitoring_service.py`, or `enhanced_ai_client.py`
  - direct code-contract smokes and `py_compile` validate the new matcher/preflight/interrupt behavior
  - pytest runner instability remains an environment issue to be handled separately from this plan

## Phase 4
- Status: completed
- Planned checks:
  - verify whether the latest operator retest still leaves repo-local child processes alive after the launcher parent exits
  - distinguish launcher live-exit/orphan defects from app-lifecycle pending-task warnings
  - keep the newly observed Doubao image-size failure out of launcher scope
- Evidence:
  - `ps -ef | grep -E 'start_dev_uv.py|uvicorn app.main:app|watchmedo auto-restart|celery -A app.services.celery_app' | grep -v grep` initially showed repo-local `uvicorn app.main:app --port 8005` and `celery beat` still alive while no `start_dev_uv.py` parent process remained, which justified the Phase 4 reopen
  - a minimal `uv run` signal probe that mimics `wait() -> except KeyboardInterrupt -> finally killpg` confirmed that top-level `uv run` still delivers `SIGINT` to Python and allows `finally` cleanup to execute
  - a real rerun of `cd backend && uv run python scripts/start_dev_uv.py --cleanup-residuals` printed startup residual detection, scoped cleanup, successful service startup, then on single `Ctrl+C` printed `🛑 Received interrupt signal`, `Shutting down services...`, `Stopping celery_worker...`, `Stopping celery_beat...`, `Stopping api_server...`, `✓ No repo-local managed service residuals remain`, and `🏁 All services stopped`
  - a follow-up `ps -ef | grep -E 'start_dev_uv.py|uvicorn app.main:app|watchmedo auto-restart|celery -A app.services.celery_app' | grep -v grep` returned empty
  - [mas_workflow.log](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/logs/mas/mas_workflow.log) now contains a corresponding clean shutdown closeout at `2026-03-28 14:50:52` (`Shutting down Short Video Maker API` / `Finished server process [1158477]`)
  - the same live run still surfaces Doubao image-size 400s and a pending-task warning, but those remain explicitly out of launcher scope and are tracked separately
- Results:
  - the current launcher code satisfies the bounded Phase 4 acceptance check: a real single `Ctrl+C` shutdown no longer requires manual `pkill` to clear repo-local managed API/worker/beat processes
  - the earlier orphan evidence is no longer reproducible under the controlled rerun, so no additional launcher code changes are justified within 033 at this point
  - image-generation size compatibility remains split out to 034 and will not be used to expand launcher scope

## Notes
- 2026-03-28T04:10:38Z completed Phase 0 successor audit only. The narrowest accepted next step is to freeze a startup preflight contract around repo-local `uvicorn` / `watchmedo` / `celery` residuals, with explicit diagnostics and opt-in cleanup, rather than adding more broad `pkill` behavior or touching runtime/control-plane code.
- 2026-03-28T04:18:52Z completed Phase 1 boundary review. The design remains within architecture lines because it treats dirty `Ctrl+C` behavior as a launcher contract problem and `Task was destroyed but it is pending!` as an app-lifecycle hygiene problem; it explicitly rejects turning manual `pkill` or launcher-side force-kill logic into the truth owner for in-process async cleanup.
- 2026-03-28T04:24:01Z completed Phase 2 implementation-cut review. The design stays within architecture lines because the first patch is constrained to the existing dev launcher and its direct tests, reuses one scoped matcher instead of introducing helper daemons or shadow state, and explicitly defers any process-internal async cleanup work to a separate application-lifecycle follow-up.
- 2026-03-28T04:35:26Z completed Phase 3 implementation review. Acceptance is based on launcher-scoped code-contract verification, not on pytest runner health: the patch stays within `start_dev_uv.py` plus its focused tests, `py_compile` passes, direct smokes prove matcher/preflight/interrupt behavior, and the local pytest hang is recorded as an orthogonal environment issue rather than a launcher regression.
- 2026-03-28T06:43:17Z reopened closeout after a real operator retest showed that the launcher parent can already be gone while repo-local `uvicorn` and `celery beat` children remain alive. This keeps 033 open strictly for live exit/orphan correction. The concurrently observed Doubao image-size failures are now tracked under [PLAN-20260328-034.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/plans/active/PLAN-20260328-034.md), preserving owner separation.
- 2026-03-28T06:52:09Z completed Phase 4 revalidation. Under a fresh controlled rerun, startup preflight cleared stale repo-local services, a single `Ctrl+C` executed launcher cleanup successfully, no repo-local managed residuals remained, and the API produced clean shutdown lines in `mas_workflow.log`. This leaves no outstanding launcher-scope defect in 033 beyond user acceptance / closeout governance.
