# LLM Streaming Consideration

## Context
Concept planner uses non-streaming LLM calls. For long JSON outputs, latency is dominated by full-response generation time.

## Current Decision
- Streaming is not required to fix the recent timeouts.
- Timeouts are handled by per-call budgets derived from the agent deadline and model/provider limits.

## Potential Follow-up
If future tasks need shorter time-to-first-token or more responsive UX, introduce streaming:
- Requires client changes to consume incremental chunks.
- Needs updated parsing/validation for partial JSON content.
- Adds complexity to retries and fallback handling.

## Related Issues (Recent)
- LLM may still emit invalid JSON even with response_format=json_object; observed bare text containing book-title brackets inside arrays. Mitigation: tighten JSON prompts and add minimal, targeted repair at parse boundary.
- Legacy concept planner prompt template under templates/ was not used by the active prompt manager and should live under archive to avoid confusion.
