# Source Thread: Audio Orchestration Boundary Alignment (2026-03-06)

## boundary-thread
- Topic: orchestration semantic boundary in multi-agent audio pipeline.
- Key conclusion: orchestration decisions should not degrade into mode enums and bool routing flags.
- Key architectural rule: fallback is runtime replan action, not preflight mode label.

## p1-review-followup
- Topic: P1 review interpretation and contract-driven behavior distinction.
- Key conclusion: capability flags represent planning priors, not runtime outcome guarantees.
- Key architectural rule: gate outputs quality signals; orchestrator owns replan decisions.
