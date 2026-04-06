import asyncio

from app.services.prompt_safety import rewrite as rewrite_module


def test_rewrite_prompt_uses_project_text_client_for_glm_models(monkeypatch):
    class FakeProjectClient:
        async def generate_text(self, **kwargs):
            assert kwargs["model"] == "glm-4.5-air"
            return {
                "content": "更安全的 <<LOCKED_0>> 静态构图",
                "usage": {"total_tokens": 11},
                "model": "glm-4.5-air",
                "provider": "glm",
            }

    monkeypatch.setattr(rewrite_module, "_enhanced_client_supports_prompt_rewrite", lambda: False)
    monkeypatch.setattr(rewrite_module, "_get_project_text_client", lambda: FakeProjectClient())

    rewritten, telemetry = asyncio.run(
        rewrite_module.rewrite_prompt_preserving_locks(
            "危险的 青袍青年 战斗画面",
            ["青袍青年"],
            model="glm-4.5-air",
        )
    )

    assert rewritten == "更安全的 青袍青年 静态构图"
    assert telemetry["backend"] == "project_ai_client"
    assert telemetry["provider"] == "glm"
    assert telemetry["result"] == "success"


def test_rewrite_prompt_falls_back_after_enhanced_backend_error(monkeypatch):
    calls = []

    async def fake_call(backend, payload, *, model):
        calls.append(backend)
        if backend == "enhanced_ai_client":
            raise RuntimeError("All text generation providers failed. Last error: None")
        return {
            "content": "收敛后的 <<LOCKED_0>> 单帧画面",
            "usage": {"total_tokens": 9},
            "model": model,
            "provider": "glm",
        }

    monkeypatch.setattr(rewrite_module, "_model_prefers_project_text_client", lambda model: False)
    monkeypatch.setattr(rewrite_module, "_enhanced_client_supports_prompt_rewrite", lambda: True)
    monkeypatch.setattr(rewrite_module, "_call_text_rewrite_backend", fake_call)

    rewritten, telemetry = asyncio.run(
        rewrite_module.rewrite_prompt_preserving_locks(
            "过强的 青竹剑 激战提示词",
            ["青竹剑"],
            model="glm-4.5-air",
        )
    )

    assert calls == ["enhanced_ai_client", "project_ai_client"]
    assert rewritten == "收敛后的 青竹剑 单帧画面"
    assert telemetry["backend"] == "project_ai_client"
    assert telemetry["result"] == "success"
