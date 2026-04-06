# Validation Ledger: PLAN-20260328-034

## Scope
- Plan:
  - [PLAN-20260328-034.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/plans/active/PLAN-20260328-034.md)
- Goal:
  - isolate and correct provider-aware image size contract drift without reopening launcher/process lifecycle or MAS runtime ownership

## Phase 0
- Status: completed
- Planned checks:
  - verify the latest real run failed at provider-side image size validation rather than launcher/runtime gating
  - inventory where current size defaults, FC guards, and provider adapters disagree
  - freeze owner to tool contract / provider capability boundaries only
- Evidence:
  - [mas_workflow.log](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/logs/mas/mas_workflow.log) shows Doubao selected as the current image provider and then rejects `1024x1024` with `image size must be at least 3686400 pixels`
  - [image_prompt_composer_tool.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/tools/image_prompt_composer_tool.py) still defaults `size` to `1024x1024`
  - [image_generation_tool.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/tools/ai_services/image_generation_tool.py) exposes `generate_image.size` as an arbitrary string and also defaults it to `1024x1024`
  - [fc_param_guard.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/utils/fc_param_guard.py) still allows only the old size set and treats violations as `warn`
  - [doubao_services.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/tools/ai_services/doubao_services.py) passes `size` through directly and surfaces the provider 400 without prior normalization
- Results:
  - the current fault is confirmed as a provider-aware tool contract defect, not a launcher or continuation regression
  - the next phase is narrowed to freezing a single normalization/validation chain for image size across FC guard, tool schema, and provider adapter

## Phase 1
- Status: completed
- Planned checks:
  - decide the single canonical owner for provider-aware image size capabilities
  - freeze one normalization/validation chain from FC inputs down to provider payload mapping
  - explicitly demote FC guard from size-truth owner to capability consumer
- Evidence:
  - [service_interfaces.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/tools/ai_services/service_interfaces.py) already provides the existing capability host for provider-specific constraints via `PromptCapability`, `EnumCapability`, and `VideoCapabilities`, plus central selected-provider resolution in `get_vlm_service(...)`
  - video providers already implement `get_capabilities()` in the same host, which means extending this host for VLM/image size avoids creating a second config or policy model
  - [image_prompt_composer_tool.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/tools/image_prompt_composer_tool.py) currently owns an obsolete `1024x1024` default, so Phase 1 freeze explicitly removes canonical default ownership from the composer layer
  - [image_generation_tool.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/tools/ai_services/image_generation_tool.py) already sits at the contract boundary between FC/tool calls and provider invocation, so it is the correct single normalization/validation owner
  - [fc_param_guard.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/utils/fc_param_guard.py) currently carries an outdated size list with `warn` semantics only, which confirms it must become a consumer of the same capability snapshot rather than remain an independent truth source
- Results:
  - the canonical owner is frozen to the existing capability host in `service_interfaces.py`, extended for VLM/image size
  - the single-path contract is frozen as `image_prompt_composer` pass-through only -> `image_generation_tool` normalize/validate using selected-provider capabilities -> provider adapter payload mapping only
  - `fc_param_guard` is formally demoted to pre-execution enforcement against the same capability snapshot, eliminating parallel size truth

## Phase 2
- Status: completed
- Planned checks:
  - implement the shared image-size capability host and reuse it across schema/guard/tool boundary/provider adapter
  - prove that composer no longer injects a default size while tool boundary now selects provider default / normalizes aliases / rejects unsupported sizes
  - capture verification results without widening scope into launcher or generic runner debugging
- Evidence:
  - [service_interfaces.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/tools/ai_services/service_interfaces.py) now exports `ImageGenerationCapabilities`, adds enum normalization helpers, and provides `get_vlm_capabilities()` as the single capability accessor
  - [doubao_services.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/tools/ai_services/doubao_services.py) now publishes canonical `2K` image-size capability plus compatibility aliases instead of leaving all size semantics implicit at the call site
  - [zhipu_services.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/tools/ai_services/zhipu_services.py) now explicitly publishes the existing three-size compatibility set so Zhipu remains on the same capability host
  - [image_prompt_composer_tool.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/tools/image_prompt_composer_tool.py) no longer defaults `size` to `1024x1024`, projects schema from the shared capability snapshot, and only forwards `size` when the caller explicitly supplies one
  - [image_generation_tool.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/tools/ai_services/image_generation_tool.py) is now the sole image-size normalization and validation boundary: it reads selected-provider capabilities, chooses provider default, normalizes aliases, and raises `invalid_image_size` / `image_size_capability_missing` before any provider request
  - [fc_param_guard.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/utils/fc_param_guard.py) now consumes `get_vlm_capabilities()` for image size and rejects invalid `image_prompt_composer.generate` size inputs instead of warn-only behavior
  - [test_image_generation_tool.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/tests/unit/test_image_generation_tool.py) adds normalization/fail-fast regressions for provider default, alias normalization, and invalid-size rejection
  - [test_image_size_contract.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/tests/unit/test_image_size_contract.py) adds focused coverage for provider capability publication, composer pass-through, and guard alignment
  - `uv run python -m py_compile backend/app/agents/tools/ai_services/service_interfaces.py backend/app/agents/tools/ai_services/image_generation_tool.py backend/app/agents/tools/image_prompt_composer_tool.py backend/app/agents/tools/ai_services/doubao_services.py backend/app/agents/tools/ai_services/zhipu_services.py backend/app/agents/utils/fc_param_guard.py backend/tests/unit/test_image_generation_tool.py backend/tests/unit/test_image_size_contract.py`
  - direct backend `.venv` calls returned:
    - provider capability export: `['2K']` for Doubao and `['1024x1024', '1024x1792', '1792x1024']` for Zhipu
    - enum helper normalization/default: `resolve('1024x1024') -> '2K'` and `default_option() -> '2K'`
    - guard alignment: alias input returned `True` while invalid `1920x1924` returned `reject-ok`
    - composer pass-through: `False` for `"size" in captured["image_params"]` and returned size `2K`
  - `backend` runner limitation recorded as out-of-scope: `uv run pytest -q tests/unit/test_image_generation_tool.py tests/unit/test_image_size_contract.py tests/unit/test_fc_policies_and_schema.py` remained stuck without producing results in this environment, and `uv run python`/`.venv` imports of the full `image_generation_tool` path follow a very heavy pre-existing import chain; this is noted but not folded into 034
- Results:
  - provider-aware image-size truth is now owned by the shared capability host rather than duplicated across composer/tool/guard/adapter
  - `image_prompt_composer` no longer owns the default image size
  - `image_generation_tool` now blocks unsupported sizes before provider 400s and normalizes legacy `1024x1024`-style inputs to provider-compatible canonical size for Doubao
  - FC guard now aligns with the same capability snapshot and rejects invalid image-size inputs instead of split-brain warn-only behavior
  - verification is sufficient to confirm the contract correction itself, while pytest/import-runner quality remains a separate environment issue

## Phase 3
- Status: completed
- Planned checks:
  - run one real provider-backed image-generation smoke without reopening launcher/process-lifecycle or generic runner debugging
  - ensure the live smoke uses a clean dev harness so broker backlog does not contaminate the result
  - distinguish `034` contract evidence from any other workflow/runtime failures observed along the way
- Evidence:
  - `uv run python scripts/start_dev_uv.py --cleanup-residuals` started a fresh repo-local dev stack, and shutdown still completed cleanly afterward with `No repo-local managed service residuals remain`
  - `.venv/bin/python scripts/reset_celery_dev_state.py --yes` flushed only `CELERY_BROKER_URL` (`localhost:6379/1`) and `CELERY_RESULT_BACKEND` (`localhost:6379/2`) before the clean rerun, so old queue backlog was removed without changing DB/runtime control-plane state
  - local loopback smoke creation succeeded through `POST /api/v1/tasks/` for task `756a5a91-1d84-4f79-8b68-a3baf2fb9ec9`, confirming the clean stack was reachable end to end
  - a direct real provider invocation via `uv run python` and [image_generation_tool.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/tools/ai_services/image_generation_tool.py) returned:
    - `size = "2K"`
    - `model = "doubao-seedream-5-0-lite-260128"`
    - a real Doubao TOS image URL
    - metadata keys `["image_url", "model", "provider", "raw"]`
  - the direct live result used input alias `size="1024x1024"`, which proves the tool boundary normalized the request before the real provider call instead of leaking the legacy size through to Doubao
  - the same clean-stack workflow smoke failed separately at runtime view / logs with:
    - runtime status `failed`, `current_node_key = "image"`
    - `script` node still `queued`
    - error `Missing runtime-input published deliverable ref: workflow_id=756a5a91-1d84-4f79-8b68-a3baf2fb9ec9 node_key=script prefer_approved=True status=missing_runtime_input_ref`
    - orchestrator log line `Workflow failed at step 2 (image_generator)`
- Results:
  - the real provider-backed image-generation smoke passed, so `034`'s contract correction is now validated beyond direct dry checks
  - live evidence confirms the fixed boundary does normalize alias sizes into Doubao-compatible canonical size and successfully produces an image
  - the newly exposed workflow-path failure is not a size-contract failure and should be tracked separately as a runtime/orchestration successor rather than folded back into `034`

## Notes
- 2026-03-28T06:43:17Z created this successor immediately after the latest real dev run made the split unavoidable: launcher live-exit/orphan remains in 033, while image provider size compatibility now has its own owner and acceptance path in 034.
- 2026-03-28T06:58:01Z completed Phase 1 freeze without implementation. The plan now reuses the existing capability host in `service_interfaces.py` instead of inventing a new provider-size model, and it freezes `image_generation_tool` as the single normalization/validation boundary while demoting `fc_param_guard` to a consumer of the same capability snapshot.
- 2026-03-28T07:55:06Z completed Phase 2 implementation and focused verification inside the frozen boundary. `py_compile` passed, direct backend `.venv` checks confirmed provider capability export, enum normalization, guard alias acceptance / invalid-size rejection, and composer pass-through without a hidden default size. The only remaining validation gap is the environment-level pytest/import runner stall, which is explicitly recorded but not treated as an image-size contract defect.
- 2026-03-28T08:00:51Z user confirmed the Phase 2 gate can be closed as implemented. No additional verification was added in this step; the overall plan remains open until a later decision is made on live smoke versus stopping at contract-level evidence.
- 2026-03-28T08:28:32Z completed Phase 3 live smoke. The direct real `image_generation` tool call succeeded against Doubao with alias-size normalization (`1024x1024 -> 2K`) and returned a real image URL, while the parallel workflow smoke exposed a separate `missing_runtime_input_ref` failure on the `concept -> image` path. The latter is explicitly recorded as out-of-scope successor evidence rather than a reason to reopen the image-size contract work.
- 2026-03-28T08:31:03Z user confirmed closeout. `034` is completed and hands off only the separate `script -> image` runtime prerequisite gap to successor [PLAN-20260328-035.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/plans/active/PLAN-20260328-035.md).
