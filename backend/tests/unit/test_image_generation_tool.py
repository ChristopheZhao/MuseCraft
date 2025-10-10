import asyncio

from app.agents.tools.ai_services import image_generation_tool as img_module
from app.agents.tools.ai_services.image_generation_tool import ImageGenerationTool
from app.agents.tools.base_tool import ToolError
from app.core.consistency_policy import ConsistencyPolicy, PromptSafetyPolicy


def test_image_sensitive_error_triggers_one_shot_rewrite(monkeypatch):
    # Enable rewrite-on-sensitive policy
    policy = ConsistencyPolicy(
        prompt_safety=PromptSafetyPolicy(
            enabled=True,
            level="moderate",
            preserve_locked_sections=True,
            rewrite_model="glm-4.5-air",
            enable_rewrite_on_sensitive_error=True,
        )
    )
    monkeypatch.setattr(img_module, "get_consistency_policy", lambda: policy)

    # Stub sanitize_with_locks returns unchanged text
    def fake_sanitize_with_locks(text, locks, ctx):
        from app.services.prompt_safety import SanitizedPrompt
        return SanitizedPrompt(text=text, changed=False, matches=[], metadata={})

    monkeypatch.setattr(img_module, "sanitize_with_locks", fake_sanitize_with_locks)

    # Force sensitive detection True and rewrite to a known string
    monkeypatch.setattr(img_module, "ps_is_sensitive_error", lambda err: True)
    async def fake_rewrite(prompt, locks, **kw):
        return "REWRITTEN_IMAGE_PROMPT", {"tokens": 5}

    monkeypatch.setattr(img_module, "ps_rewrite_preserving_locks", fake_rewrite)

    tool = ImageGenerationTool()

    calls = {"count": 0}

    called_prompts = []

    async def fake_image_generation(self, **kwargs):
        called_prompts.append(kwargs.get("prompt"))
        calls["count"] += 1
        if calls["count"] == 1:
            raise ToolError("SensitiveContent detected", tool.metadata.name)
        return {"image_url": "https://img.example.com/ok.jpg", "model": "stub"}

    class FakeVLM:
        async def image_generation(self, **kwargs):
            return await fake_image_generation(self, **kwargs)

    tool._vlm_service = FakeVLM()

    params = {
        "prompt": "在古城战场中出现暴力和鲜血等敏感描写以验证安全兜底处理流程是否奏效",
        "size": "1024x1024",
        "scene_number": 1,
        # Optional locks (empty in this test)
        "locked_segments": [],
    }

    async def run_and_capture():
        res = await tool._generate_image(params)
        return res

    result = asyncio.run(run_and_capture())

    assert calls["count"] == 2  # first fail, second retry
    assert called_prompts[-1] == "REWRITTEN_IMAGE_PROMPT"
    assert result.get("prompt_safety_rewrite", {}).get("applied") is True


def test_image_no_advisory_injection(monkeypatch):
    # Sanitize replaces text without injecting advisory
    def fake_sanitize_with_locks(text, locks, ctx):
        from app.services.prompt_safety import SanitizedPrompt
        # Simulate replacement but not advisory injection
        return SanitizedPrompt(text=text.replace("鲜血", "墨色光芒"), changed=True, matches=[{"rule": "violence"}], metadata={})

    monkeypatch.setattr(img_module, "sanitize_with_locks", fake_sanitize_with_locks)
    tool = ImageGenerationTool()

    captured_prompts = []

    class FakeVLM:
        async def image_generation(self, **kwargs):
            captured_prompts.append(kwargs.get("prompt"))
            return {"image_url": "https://img.example.com/sanitized.jpg"}

    tool._vlm_service = FakeVLM()

    original_prompt = "这段提示词描述鲜血四溅的激烈战斗场景以测试过滤逻辑能否正确触发"
    res = asyncio.run(
        tool._generate_image({
            "prompt": original_prompt,
            "size": "1024x1024",
        })
    )
    sanitized_prompt = original_prompt.replace("鲜血", "墨色光芒")
    assert captured_prompts and captured_prompts[0] == sanitized_prompt
    assert res.get("generated_prompt") == sanitized_prompt
    assert "PG-13" not in res.get("generated_prompt", "")
