# Sprint 2 Design Brief: Runtime-driven quick workspace reshape

- Parent plan: `PLAN-20260406-058`
- Scope: frontend-only quick workspace reshape
- Status: draft-ready-for-implementation
- Chosen direction: `Focus workspace + storyboard rail`

## 1. Why this direction
- Reject `显隐版固定流水线`:
  - the current node grid and pipeline list still start from a fully planted backend blueprint, so even if future nodes are dimmed, the user still reads the page as a pre-written pipeline
- Reject `Execution storyboard` as the primary container:
  - it is strong for narrative history, but weaker for pause/resume/HITL action states where the current node must dominate the screen
- Reject `Canvas-lite` for Sprint 2:
  - current runtime/read-model does not carry graph edges, branch provenance, or subgraph metadata
  - a canvas container would add motion and space without adding truth
- Choose `Focus workspace + storyboard rail`:
  - it makes the current runtime node the main visual subject
  - it still preserves an execution trail without reintroducing a full fixed skeleton
  - it fits pause/resume/HITL states better than a filmstrip-only layout

## 2. Information architecture
- Shell layer:
  - keep mode tabs and top four-step bar as product shell navigation only
  - visually demote the four-step bar so it no longer reads as runtime orchestration truth
- Main workspace:
  - left rail: execution storyboard of arrived nodes only
  - center focus card: current node, current status, primary artifact/diagnostic, primary action
  - right context panel: runtime metadata, pause/resume diagnostics, skipped-node summary, lightweight telemetry

## 3. Node visibility rules
- Current node:
  - always shown as the dominant focus card
  - if `active_gate.status === awaiting_human`, current node becomes the HITL workspace
- Arrived nodes:
  - nodes with status in `completed`, `running`, `pending_gate`, `approved`, `needs_revision`, `failed`, `stale`
  - current node is also included even if its raw node status still reads `queued`
- Future nodes:
  - raw `queued` nodes that are neither current nor previously arrived are hidden from the main workspace
- Skipped nodes:
  - not shown inline with the mainline storyboard
  - folded into a compact `本次未走通道` summary in the right context panel

## 4. State mapping rules
- Fresh submit bootstrap:
  - keep the existing `正在连接运行时` startup card until runtime leaves the bootstrap placeholder shape
- Resume available:
  - render a paused-runtime focus card with explicit `恢复执行` CTA
  - do not show bootstrap placeholder in this state
- Resume blocked:
  - render as `查看态诊断`, not as a startup state
- HITL waiting:
  - render script review controls directly in the focus card
  - storyboard rail shows the current node as `pending_gate`
- Failed runtime:
  - focus card becomes failure diagnostics
  - arrived-node rail remains visible as context
- Completed runtime:
  - focus card becomes final delivery summary
  - export/review remains the downstream destination

## 5. Layout sketch

```text
+---------------------------------------------------------------+
| shell: mode tabs | demoted 4-step shell nav                   |
+----------------------+---------------------------+-------------+
| storyboard rail      | focus workspace           | context     |
| completed node 1     | title + runtime status    | session     |
| completed node 2     | current node summary      | diagnostics  |
| current node         | primary artifact/gate     | skipped      |
| failed/revised node  | primary CTA               | telemetry    |
+----------------------+---------------------------+-------------+
```

## 6. Responsive behavior
- Desktop:
  - three-column layout: rail / focus / context
- Tablet:
  - focus card first, rail second, context third
- Mobile:
  - focus card first
  - storyboard rail becomes horizontal chips or stacked compact cards below focus
  - context panel collapses into accordion sections

## 7. Implementation slices
- Slice A:
  - add runtime display helpers for `arrived`, `current`, `future`, and `skipped` classification
- Slice B:
  - rewrite `QuickModeWorkspace` to use the new layout and stop embedding the old full pipeline grid as the main visual
- Slice C:
  - visually demote the top four-step bar in `HomePage`
- Slice D:
  - keep `AgentOrchestrator` and `RealTimeProgress` out of the quick-mode primary path unless repurposed into rail/context subcomponents

## 8. Acceptance translation
- Current node becomes the first thing users read
- Future nodes no longer pre-occupy the page
- `skipped` nodes no longer carry equal visual weight with the mainline
- HITL and resume states stay actionable without reverting to a fixed eight-node skeleton
- The page reads as `runtime is advancing a workspace`, not `a planted DAG is getting recolored`
