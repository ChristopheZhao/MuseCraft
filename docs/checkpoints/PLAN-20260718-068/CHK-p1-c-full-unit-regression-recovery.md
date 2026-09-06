# P1-C Full Unit Regression Recovery

- Timestamp: `2026-07-19T07:20:29+08:00`
- Status: pass for backend unit and architecture regression; P1-C remains open
- Scope: stale contract tests, cross-platform assertions, context normalization, and constructor I/O lifecycle

## Expected Outcomes Checked

- [x] Full unit failures were reproduced before edits: `525 passed, 17 failed, 1 skipped`.
- [x] Consistency tests now consume explicit `scene_info_ref` snapshots; missing or unknown refs fail closed instead of restoring facts/memory fallbacks.
- [x] The context editor emits normalized `prepared_assets_refs`, matching its prompt/schema contract.
- [x] Root environment documentation is tested at its actual repository-owned location; deprecated duration settings are not restored for a stale test.
- [x] Media-path and quality-context assertions are platform-independent and compare resolved paths.
- [x] Suno rewrite tests inject the registered storage capability boundary instead of failing on an unrelated missing tool.
- [x] Removed memory-coordinator and pending-regeneration private APIs are not recreated for compatibility-only tests.
- [x] FFmpeg fallback fixtures now represent real probe output and exercise the existing ducking fallback branch.
- [x] Enhanced AI and monitoring service constructors create lazy Redis clients without pinging or scheduling connection coroutines during import/initialization.
- [x] The former unmarked async registration script is now a synchronous assertion-based tool-registration contract; no test is silently skipped.

## Evidence

- Complete backend unit suite: `545 passed, 2 warnings`, zero failures and zero skipped tests.
- Complete backend architecture suite: `22 passed, 2 warnings`.
- Focused remediation suite: `44 passed, 2 warnings`.
- Context editor mypy: no issues in one source file.
- New/reworked files pass Black; all modified files pass isort.
- `git diff --check`: pass.
- Existing warnings are SQLAlchemy `as_declarative` and Pydantic class-config deprecations.
- The prior pending Redis coroutine/event-loop shutdown errors no longer appear.

## Expectation Check

The recovery preserves the intended MAS boundaries. Tests were moved to the current scene snapshot, memory facade, and tool registration contracts rather than making production code emulate removed behavior. The two production fixes are contract/lifecycle corrections with focused coverage, not compatibility shims.

P1-C remains open because its uv/PostgreSQL startup portion is still blocked by the Gate E clean-database fixture. Broad mypy is also not claimed: focused analysis of `monitoring_service.py` reports existing psutil stub and internal typing debt outside the changed constructor path.
