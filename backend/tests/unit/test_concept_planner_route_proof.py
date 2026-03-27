import asyncio
import json
from types import SimpleNamespace

from app.agents.concept_planner import ConceptPlannerAgent
from app.agents.tools.ai_services.service_interfaces import LLMServiceInterface, ServiceProvider
from app.agents.utils import llm_policy as llm_policy_module


class _StubTask:
    def __init__(self, task_id: str):
        self.task_id = task_id
        self.status = "pending"

    def update_progress(self, *_args, **_kwargs):
        return None


class _StubDB:
    def add(self, *_args, **_kwargs):
        return None

    def commit(self, *_args, **_kwargs):
        return None

    def refresh(self, *_args, **_kwargs):
        return None


class _ProviderConfig:
    duration_capabilities = [5, 10]


class _VideoConfigStub:
    def get_system_duration_capability(self):
        return {"min_duration": 5, "max_duration": 60}

    def validate_duration_request(self, duration):
        return {"is_valid": True, "provider": "stub", "suggestion": duration}

    def get_current_provider_config(self):
        return _ProviderConfig()

    def calculate_optimal_scene_count(self, _duration):
        return 1


class _RecordingPlanService(LLMServiceInterface):
    def __init__(self):
        self.calls = []

    async def chat_completion(self, messages, model=None, temperature=0.7, max_tokens=2000, **kwargs):
        stage = messages[-1]["content"]
        self.calls.append(
            {
                "stage": stage,
                "model": model,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "request_timeout": kwargs.get("request_timeout"),
                "response_format": kwargs.get("response_format"),
            }
        )
        payload = self._payload_for_stage(stage)
        return {
            "content": json.dumps(payload, ensure_ascii=False),
            "model": model,
            "provider": "deepseek",
            "usage": {"total_tokens": 11},
            "finish_reason": "stop",
        }

    async def function_call(self, messages, tools, tool_choice="auto", model=None, temperature=0.3, **kwargs):
        return await self.chat_completion(messages, model=model, temperature=temperature, **kwargs)

    def get_supported_models(self):
        return ["deepseek-chat", "deepseek-reasoner"]

    def get_provider_name(self) -> str:
        return "deepseek"

    def is_available(self) -> bool:
        return True

    def _payload_for_stage(self, stage: str):
        if stage == "skeleton_generation":
            return {
                "overview": "Moon rescue story",
                "genre_and_theme": {"genre": "animation", "theme": "teamwork"},
                "target_audience": "general",
                "key_messages": ["teamwork wins"],
                "scene_blueprint": [
                    {
                        "scene_number": 1,
                        "title": "Moonlight setup",
                        "duration_hint": 10,
                    }
                ],
            }
        if stage == "style_elements_generation":
            return {
                "intelligent_style_design": {
                    "style_name": "Ink Moon",
                    "style_description": "Painterly moonlit animation",
                },
                "content_elements": {
                    "characters": [
                        {
                            "canonical_name": "monkey",
                            "display_name": "Monkey",
                        }
                    ]
                },
                "consistency_hints": {
                    "visual": "Keep the monkey silhouette readable",
                    "narrative": "Maintain a playful mythic tone",
                    "color_palette": ["ink-black", "moon-silver"],
                },
            }
        if stage == "voice_plan_generation":
            return {
                "voice_plan": {
                    "enabled": True,
                    "mode": "narration",
                    "persona": "storyteller",
                    "tone_keywords": ["warm", "playful"],
                    "scene_guidance": [
                        {
                            "scene_number": 1,
                            "should_narrate": True,
                            "objective": "Set the mythic setup",
                            "emotion": "wonder",
                            "key_points": ["moon", "reflection"],
                            "pace_tag": "medium",
                        }
                    ],
                }
            }
        if stage.startswith("scene_detail_batch_generation"):
            return {
                "scenes": [
                    {
                        "scene_number": 1,
                        "title": "Moonlight setup",
                        "duration": 10,
                        "visual_description": "Monkeys gather around a bright moonlit well.",
                        "narrative_description": "The group mistakes the moon reflection for a fallen moon.",
                        "mood_and_atmosphere": "mythic",
                        "camera_language": "slow push-in",
                        "key_actions": ["look into the well", "reach toward the reflection"],
                        "audio_cues": ["gentle night ambience"],
                        "transition_hint": "fade",
                    }
                ],
                "notes": {
                    "consistency": "Keep the moon reflection bright and centered.",
                    "duration_adjustment": "Single-scene proof path keeps the full 10s allocation.",
                },
            }
        raise AssertionError(f"Unexpected concept-planner stage: {stage}")


def _capture_messages(storage):
    def _capture(template, *args, **_kwargs):
        if args:
            try:
                storage.append(template % args)
                return
            except Exception:
                pass
        storage.append(str(template))

    return _capture


def _make_memory_services():
    return SimpleNamespace(
        global_service=None,
        long_term=None,
        short_term=object(),
    )


def test_concept_planner_execute_proves_deepseek_route_and_budget_diagnostics(monkeypatch):
    selected_providers = []
    plan_service = _RecordingPlanService()

    monkeypatch.setattr(
        llm_policy_module,
        "get_llm_service",
        lambda provider=None: selected_providers.append(provider) or plan_service,
    )
    monkeypatch.setattr("app.core.video_config_manager.get_video_config", lambda: _VideoConfigStub())
    monkeypatch.setattr("app.agents.concept_planner.read_shared_fact", lambda *args, **kwargs: {})
    monkeypatch.setattr("app.agents.concept_planner.write_shared_fact", lambda *args, **kwargs: None)

    agent = ConceptPlannerAgent(memory_services=_make_memory_services())
    log_messages = []
    monkeypatch.setattr(agent, "_build_system_prompt", lambda: "concept-system")
    monkeypatch.setattr(agent, "render_prompt", lambda template_name, **kwargs: template_name)
    monkeypatch.setattr(agent.logger, "info", _capture_messages(log_messages))
    monkeypatch.setattr(agent.logger, "warning", _capture_messages(log_messages))
    monkeypatch.setattr(agent.logger, "error", _capture_messages(log_messages))

    async def _noop_progress(*_args, **_kwargs):
        return None

    async def _noop_store(*_args, **_kwargs):
        return False

    agent._update_progress = _noop_progress  # type: ignore[attr-defined]
    agent.store_creative_guidance = _noop_store  # type: ignore[attr-defined]

    result = asyncio.run(
        agent._execute_impl(
            _StubTask("concept-proof-task"),
            {
                "user_prompt": "制作猴子捞月动画短片",
                "duration": 10,
                "aspect_ratio": "16:9",
                "workflow_state_id": "wf-proof",
                "concept_mode": "episode",
            },
            _StubDB(),
        )
    )

    assert selected_providers
    assert all(provider == ServiceProvider.DEEPSEEK for provider in selected_providers)
    assert plan_service.calls
    assert all(call["model"] == "deepseek-chat" for call in plan_service.calls)
    assert result["concept_plan"]["intelligent_style_design"]["style_name"] == "Ink Moon"
    assert result["concept_plan"]["scenes"][0]["scene_number"] == 1

    assert any(
        "CONCEPT_PLAN_ROUTE provider=deepseek model=deepseek-chat fallback_model=deepseek-reasoner"
        in message
        for message in log_messages
    )
    assert any(
        "CONCEPT_MODEL_CALL stage=skeleton_generation" in message and "fallback_used=False" in message
        for message in log_messages
    )
    assert any(
        "TIME_BUDGET stage=scene_batch" in message
        for message in log_messages
    )
