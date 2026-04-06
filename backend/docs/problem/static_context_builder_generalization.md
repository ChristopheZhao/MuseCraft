# Static Context Builder Generalization

## Context
We currently build agent-specific static contexts from MAS WorkingMemory:
- image agent uses a dedicated builder (`build_image_generation_context`).
- video agent relies on a more generic media view (`build_media_agent_context`).

## Problem
Static context construction is not generalized. Each agent can end up with a different
shape/quality of executable context, which leads to inconsistent tool planning
behavior (e.g., video agent lacks a clear `scenes_to_generate` list).

## Impact
- Inconsistent agent planning reliability.
- Harder to reason about required fields across agents.
- Bug fixes become agent-specific rather than systemic.

## Next Step (Deferred)
Design a unified static-context builder that:
- Uses MAS WM as the single source of truth.
- Outputs a consistent, executable "task view" per modality.
- Avoids agent-specific ad-hoc extraction.
