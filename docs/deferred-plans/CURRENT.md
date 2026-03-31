# Current Deferred Plan

- Deferred Plan ID: DP-20260331-001
- Title: Converge media authority toward obs-ledger SoT
- Status: active
- Scope Tags: backend, agents, memory, media, image
- Topic Tags: authority, obs-ledger, event-sourcing, read-model, dual-write
- Plan Kinds: architecture, guardrail

## Goal
- Freeze obs-ledger as the target authority direction for media generation and prevent further expansion of scene_outputs.* as a co-authority surface while the migration remains deferred.

## Why Not Now
- A full authority inversion requires a cross-cutting migration of write paths, reducers/materializers, recovery semantics, and downstream consumers; that is larger than the current bugfix and follow-up slices.

## Do Not
- Do not add new authority semantics, completion truth, or correctness ownership to direct scene_outputs.* write paths.
- Do not introduce planner-owned completed-scene projections or any second completed-state authority.
- Do not promote audit or statistics views into active planning authority.

## Allowed Now
- Keep scene_outputs.* only as transitional compatibility reads or materialized-view style surfaces; do not treat them as the long-horizon authority target.
- Implement narrow contract, precedence, lease, and execution-boundary fixes needed for current failures without expanding dual-write ownership.
- Prepare event schema, reducers, and migration slices that move future authority toward an obs-ledger without forcing a repo-wide rewrite in the same change.

## Reopen Trigger
- Before any new work extends scene_outputs.* semantics, write paths, or ownership beyond compatibility/read-model needs.
- When scheduling the first dedicated authority-inversion slice for image or media generation.

## Source
- docs/deferred-plans/active/DP-20260331-001.md
