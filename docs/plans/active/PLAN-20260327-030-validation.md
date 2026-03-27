# PLAN-20260327-030 Validation

- Plan ID: PLAN-20260327-030
- Recorded At: 2026-03-27T09:23:14Z
- Status: completed

## Purpose
- Record phase-by-phase verification for [PLAN-20260327-030](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/plans/active/PLAN-20260327-030.md).
- Keep this MAS-level provider-routing work separate from [PLAN-20260327-029](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/plans/active/PLAN-20260327-029.md), which remains an already-implemented schema fix awaiting lifecycle closeout.

## Validation Matrix
### Phase 0
- Status: completed
- Planned checks:
  - confirm the current `concept_planner -> BaseAgent -> LLMPolicyManager -> service registry` LLM path
  - confirm where provider/model/fallback ownership currently overlaps between `llm_policy`, `ai_config`, and registry code
  - confirm the successor scope excludes `029` closeout, project-level work, and runtime/control-plane changes
  - `python3 -m json.tool docs/plans/PLAN_INDEX.json`
- Evidence:
  - [concept_planner.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/concept_planner.py) reads `concept_model` and `fallback_model` from `ai_config`, then passes `model=model_name` explicitly into `_invoke_concept_model(...)`
  - `_invoke_concept_model(...)` uses `self.get_llm("plan")`, so the actual provider service comes from the role handle loaded by [base.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/base.py) and [llm_policy.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/utils/llm_policy.py)
  - [llm_policy.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/utils/llm_policy.py) currently maps every non-`zhipu` provider back to `ServiceProvider.ZHIPU`
  - [service_interfaces.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/tools/ai_services/service_interfaces.py) currently registers only `zhipu` for LLM and will silently return another available LLM provider if the selected provider is unavailable
  - repo grep found no `deepseek` / `DEEPSEEK_*` provider wiring in the current backend/app + backend/config surfaces
- Results:
  - `rg -n "def get_llm\\(|def _resolve_llm_for_role\\(|LLMPolicyManager|build_llms_for_agent|chat_completion\\(|get_model_for_agent|get_model_provider|get_fallback_model_for_agent|get_provider_config|get_llm_service\\(|register_llm_service|No LLM services available|selected=%s|AI_SERVICE_PROVIDER_UNAVAILABLE" backend/app/agents/base.py backend/app/agents/utils/llm_policy.py backend/app/core/ai_config.py backend/app/agents/tools/ai_services/service_interfaces.py`
  - `rg -n "DEEPSEEK|deepseek|glm-default|glm-light|provider:" backend/app backend/config .env*`
  - `python3 -m json.tool docs/plans/PLAN_INDEX.json`
  - Phase 0 freeze result: provider/model routing must move to a single resolved route contract; `concept_planner` keeps only stage-budget/JSON-call semantics; service registry must stop doing cross-provider silent fallback

### Phase 1
- Status: completed
- Planned checks:
  - provider resolution no longer collapses non-`zhipu` policy entries back to `zhipu`
  - selected unavailable LLM provider path surfaces explicit diagnostics instead of silent provider switching
  - focused tests cover provider-routing substrate changes and establish that provider switching is owned outside the concept agent implementation
- Evidence:
  - [llm_policy.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/utils/llm_policy.py) now resolves each role through `_resolve_role_route(...)`, infers/validates provider against model metadata, and rejects unsupported or mismatched provider/model combinations instead of folding all non-`zhipu` routes back into `ServiceProvider.ZHIPU`
  - [service_interfaces.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/tools/ai_services/service_interfaces.py) now exposes explicit LLM provider-name mapping helpers and fails fast when a selected LLM provider is unregistered or unavailable, including startup diagnostics, instead of silently returning another registered LLM provider
  - Added [test_llm_provider_routing.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/tests/unit/test_llm_provider_routing.py) to cover non-`zhipu` provider resolution, provider/model mismatch rejection, and no-cross-provider-fallback behavior in the registry
- Results:
  - `.venv/bin/python -m py_compile app/agents/utils/llm_policy.py app/agents/tools/ai_services/service_interfaces.py tests/unit/test_llm_provider_routing.py`
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q --confcutdir=tests/unit tests/unit/test_llm_provider_routing.py`
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q --confcutdir=tests/unit tests/unit/test_zhipu_services.py`
  - Result summary: `test_llm_provider_routing.py` 4 passed; `test_zhipu_services.py` 5 passed

### Phase 2
- Status: completed
- Planned checks:
  - DeepSeek LLM service registers through the shared service interface
  - config surfaces include DeepSeek provider/model metadata and startup diagnostics
  - JSON-only planning calls remain compatible with `response_format={"type":"json_object"}`
  - DeepSeek is added as an available provider option, not as a new hardcoded concept-agent binding
- Evidence:
  - [deepseek_services.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/tools/ai_services/deepseek_services.py) adds a dedicated DeepSeek `LLMServiceInterface` implementation that uses the shared `/chat/completions` contract, preserves `response_format`, and normalizes `reasoning_content` / `tool_calls` back into the repo's LLM response shape
  - [service_interfaces.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/tools/ai_services/service_interfaces.py) now registers DeepSeek via the shared LLM registry and startup path, passes provider-config credentials/base_url/timeout/default_model into the service, and treats config-backed provider keys as satisfying startup diagnostics instead of warning only on missing env vars
  - [ai_config.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/core/ai_config.py) plus [ai_config.yaml](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/config/ai_config.yaml) now carry DeepSeek provider/model metadata in the same provider/model registry used by other suppliers, without changing concept-agent implementation
  - Added [test_deepseek_services.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/tests/unit/test_deepseek_services.py) for DeepSeek chat JSON mode and function-call parsing, plus [test_ai_config_deepseek.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/tests/unit/test_ai_config_deepseek.py) for DeepSeek provider/model merge, config-backed diagnostics, and shared-registry registration
- Results:
  - `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m py_compile app/core/config.py app/core/ai_config.py app/agents/tools/ai_services/service_interfaces.py app/agents/tools/ai_services/deepseek_services.py tests/unit/test_deepseek_services.py tests/unit/test_ai_config_deepseek.py`
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q --confcutdir=tests/unit tests/unit/test_deepseek_services.py`
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q --confcutdir=tests/unit tests/unit/test_ai_config_deepseek.py`
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q --confcutdir=tests/unit tests/unit/test_llm_provider_routing.py`
  - Result summary: `test_deepseek_services.py` 2 passed; `test_ai_config_deepseek.py` 3 passed; `test_llm_provider_routing.py` 4 passed

### Phase 3
- Status: completed
- Planned checks:
  - `concept_planner` primary planning route resolves to DeepSeek via policy/config, not stage-specific branching or agent-level provider binding
  - provider/model selection can switch without modifying concept-agent code
  - fallback semantics remain explicit and diagnostically visible
  - `009` timeout-budget semantics remain intact
- Evidence:
  - [base.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/base.py) now exposes shared route metadata through `get_llm_route(...)`, so concept-side code can consume provider/model policy resolution without instantiating or branching on provider-specific services
  - [llm_policy.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/utils/llm_policy.py) now exposes `resolve_route_for_agent(...)` and `RoleLLM.default_model`, keeping route metadata and injected handles on the same policy contract
  - [concept_planner.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/concept_planner.py) now resolves its planning route from shared policy metadata, derives fallback only from model metadata, and fails fast on cross-provider fallback instead of silently mixing owners
  - [llm_policies.yaml](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/config/llm_policies.yaml) now points `agents.concept_planner.default` and `agents.concept_planner.plan` to `deepseek` / `deepseek-chat`
  - Added [test_concept_planner_routing.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/tests/unit/test_concept_planner_routing.py) to cover route ownership, repo-policy DeepSeek cutover, and cross-provider fallback rejection
- Results:
  - `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m py_compile app/agents/utils/llm_policy.py app/agents/base.py app/agents/concept_planner.py tests/unit/test_concept_planner_routing.py`
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q --confcutdir=tests/unit tests/unit/test_concept_planner_routing.py`
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q --confcutdir=tests/unit tests/unit/test_concept_planner_timeouts.py`
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q --confcutdir=tests/unit tests/unit/test_llm_provider_routing.py`
  - Residual gap: `tests/unit/test_concept_planner_project_mode.py` still skips under the narrowed harness, and when forced with explicit async plugin loading it did not yield a clean executable validation result; that test was not counted as passing evidence for this phase
  - Result summary: `test_concept_planner_routing.py` 3 passed; `test_concept_planner_timeouts.py` 2 passed; `test_llm_provider_routing.py` 4 passed

### Phase 4
- Status: completed
- Planned checks:
  - focused unit/integration validation passes
  - `concept_planner` route proof shows explicit provider selection and interpretable budget diagnostics
  - governance assets stay in sync before any lifecycle closeout
  - `.env.example` and `backend/.env.example` expose the `DEEPSEEK_*` knobs required to actually configure the selected DeepSeek route
  - the repo no longer presents `ai_config.yaml` legacy `agent_model_mapping.concept_planner` as if it were the active concept-planning route authority
- Evidence:
  - Added [test_concept_planner_route_proof.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/tests/unit/test_concept_planner_route_proof.py), which executes the real [concept_planner.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/agents/concept_planner.py) `_execute_impl(...)` path under the repo `llm_policies.yaml` route, patches the shared LLM service registry at the policy boundary, and records the selected provider, selected model, and emitted diagnostics
  - The proof harness confirms that the `plan` role resolves to `ServiceProvider.DEEPSEEK`, that planning calls use `deepseek-chat`, and that the execution path emits both `CONCEPT_PLAN_ROUTE ... fallback_model=deepseek-reasoner` and `TIME_BUDGET stage=scene_batch ...` diagnostics without introducing provider-specific branching into the agent
  - Governance assets were refreshed in [PLAN-20260327-030.md](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/plans/active/PLAN-20260327-030.md), this validation ledger, and [PLAN_INDEX.json](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/docs/plans/PLAN_INDEX.json) while keeping the plan lifecycle itself at `in_progress` pending explicit user acceptance
  - [.env.example](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/.env.example) and [backend/.env.example](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/.env.example) now expose `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, and `DEEPSEEK_DEFAULT_MODEL`, matching the policy-selected concept-planning route
  - [llm_policies.yaml](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/app/config/llm_policies.yaml) now labels itself as the `concept_planner` supplier authority, while [ai_config.yaml](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/config/ai_config.yaml) marks its `concept_planner` mappings as compatibility-only metadata rather than the active planning route source
  - Added [test_concept_llm_config_surface.py](/mnt/d/code/agent/Opensource/vertical_application/short-video-maker/backend/tests/unit/test_concept_llm_config_surface.py) to assert that a DeepSeek-selected `concept_planner.plan` route cannot exist without matching `DEEPSEEK_*` exposure in both env templates, and that `ai_config.yaml` continues to flag the `concept_planner` mapping as compatibility-only
  - Live DeepSeek acceptance probing now confirms the configured credentials actually work: a real `DeepSeekLLMService` JSON call succeeded on `deepseek-chat`, a bounded 2/4/6 concurrency probe completed without 429 or timeout failures, and a minimal real `concept_planner` execution completed with the DeepSeek route plus interpretable `TIME_BUDGET` diagnostics
- Results:
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q --confcutdir=tests/unit tests/unit/test_deepseek_services.py`
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q --confcutdir=tests/unit tests/unit/test_ai_config_deepseek.py`
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q --confcutdir=tests/unit tests/unit/test_llm_provider_routing.py`
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q --confcutdir=tests/unit tests/unit/test_concept_planner_routing.py`
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q --confcutdir=tests/unit tests/unit/test_concept_planner_route_proof.py`
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q --confcutdir=tests/unit tests/unit/test_concept_planner_timeouts.py`
  - `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m py_compile app/agents/utils/llm_policy.py app/agents/base.py app/agents/concept_planner.py app/agents/tools/ai_services/service_interfaces.py app/agents/tools/ai_services/deepseek_services.py tests/unit/test_deepseek_services.py tests/unit/test_ai_config_deepseek.py tests/unit/test_llm_provider_routing.py tests/unit/test_concept_planner_routing.py tests/unit/test_concept_planner_route_proof.py tests/unit/test_concept_planner_timeouts.py`
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q --confcutdir=tests/unit tests/unit/test_concept_llm_config_surface.py`
  - `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m py_compile tests/unit/test_concept_llm_config_surface.py`
  - `uv run python - <<'PY' ... DeepSeekLLMService JSON smoke ... PY`
  - Live smoke result: success on `deepseek-chat`, elapsed `2.23s`, `finish_reason=stop`, JSON payload returned as requested
  - `uv run python - <<'PY' ... DeepSeekLLMService bounded concurrency probe (2/4/6) ... PY`
  - Live concurrency result: `2/4/6` all succeeded with `0` failures; batch latencies `2.88s / 3.66s / 4.77s`; no `429`, no timeout exceptions observed in the tested range
  - `uv run python - <<'PY' ... minimal real ConceptPlannerAgent _execute_impl live path ... PY`
  - Live concept result: success in `111.59s`, DeepSeek route log `provider=deepseek model=deepseek-chat fallback_model=deepseek-reasoner`, `scene_count=3`, and stage-budget diagnostics present without budget exhaustion
  - Result summary: `test_deepseek_services.py` 2 passed; `test_ai_config_deepseek.py` 3 passed; `test_llm_provider_routing.py` 4 passed; `test_concept_planner_routing.py` 3 passed; `test_concept_planner_route_proof.py` 1 passed; `test_concept_planner_timeouts.py` 2 passed; `test_concept_llm_config_surface.py` 2 passed
  - Residual gap: `tests/unit/test_concept_planner_project_mode.py` still was not counted as passing evidence for this phase because the narrowed unit harness does not yet produce a clean async validation result there

## Notes
- 2026-03-27T09:23:14Z created the validation ledger together with the new managed successor plan so subsequent Phase 0+ evidence can stay isolated from the already-implemented `029` schema-alignment fix and the earlier `009` timeout-governance work.
- 2026-03-27T09:31:47Z completed Phase 0 audit. The repo currently splits route ownership across `ai_config` (agent model/fallback), `llm_policy` (role handle/provider), and service registry fallback behavior; the next implementation phases are now frozen to remove that overlap, keep `concept_planner` provider-agnostic, and disallow implicit provider switching.
- 2026-03-27T09:42:23Z completed Phase 1 substrate work. Verification had to use `--confcutdir=tests/unit` plus `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` because the repo-level backend integration `conftest.py` adds global fixtures unrelated to this pure unit slice; under the narrowed unit harness, both the new routing tests and the existing Zhipu timeout/fallback regressions passed.
- 2026-03-27T10:01:31Z completed Phase 2. DeepSeek now enters through the shared LLM provider registry and the same `ai_config` provider/model surface as other suppliers; focused validation proved JSON-mode chat behavior, function-call parsing, config-backed startup diagnostics, and registry registration while keeping concept-agent code unchanged and leaving policy-driven cutover for Phase 3.
- 2026-03-27T10:16:21Z completed Phase 3. The concept-side primary route now comes from shared llm policy metadata instead of `agent_model_mapping`, the repo policy points concept-planning to DeepSeek, and cross-provider fallback contracts are rejected explicitly. Focused routing/timeout regressions passed; the existing async `project_mode` unit test remains a residual harness gap rather than passing evidence.
- 2026-03-27T10:33:01Z completed Phase 4 focused validation. The new quasi-real proof test executes the real `concept_planner` planning path against a policy-resolved DeepSeek route and captures explicit route/budget diagnostics, the full focused validation bundle passed under the narrowed unit harness, changed-file `py_compile` passed, and the residual async `project_mode` gap remains explicitly outside the passing evidence set.
- 2026-03-27T12:31:43Z reopened Phase 4 after user review identified a delivery/configuration gap rather than a runtime routing bug: the DeepSeek route is implemented and validated, but the env templates still do not expose `DEEPSEEK_*` and `ai_config.yaml` still presents a misleading legacy `concept_planner` agent-model mapping. Remaining work is narrowed to config-surface closure plus guardrail validation.
- 2026-03-27T12:35:19Z completed the Phase 4 configuration-exposure closeout. Both env templates now surface the DeepSeek knobs required to configure the selected concept-planning route, policy-vs-metadata authority is explicitly labeled in `llm_policies.yaml` and `ai_config.yaml`, the new config-surface guardrail test passed together with the existing concept-routing and DeepSeek-config regressions, and the residual async `project_mode` gap remains outside the passing evidence set.
- 2026-03-27T12:50:57Z completed live DeepSeek acceptance probing. Real credentials were exercised successfully through the shared DeepSeek service contract, bounded 2/4/6 concurrency did not surface provider-rate-limit or timeout failures in the tested range, and a minimal real `concept_planner` main path completed with DeepSeek-selected routing and visible stage-budget diagnostics.
- 2026-03-27T13:26:17Z user confirmed lifecycle closeout after the live DeepSeek validation gate passed. This validation ledger is now closed together with `PLAN-20260327-030`; residual async `project_mode` harness work remains explicitly outside the accepted evidence scope for this plan.
