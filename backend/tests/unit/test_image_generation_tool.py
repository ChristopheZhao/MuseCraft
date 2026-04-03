import asyncio
from types import SimpleNamespace

import pytest

from app.agents.tools.ai_services import image_generation_tool as img_module
from app.agents.tools.ai_services.image_generation_tool import ImageGenerationTool
from app.agents.tools.ai_services.service_interfaces import EnumCapability, ImageGenerationCapabilities
from app.agents.tools.base_tool import ToolError
from app.core.consistency_policy import ConsistencyPolicy, PromptSafetyPolicy


def _patch_noop_prompt_safety(monkeypatch):
    monkeypatch.setattr(
        img_module,
        "apply_prompt_safety",
        lambda prompt, *_args, **_kwargs: (prompt, SimpleNamespace(metadata={})),
    )

    def fake_sanitize_with_locks(text, locks, ctx):
        from app.services.prompt_safety import SanitizedPrompt

        return SanitizedPrompt(text=text, changed=False, matches=[], metadata={})

    monkeypatch.setattr(img_module, "sanitize_with_locks", fake_sanitize_with_locks)


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


def test_image_sensitive_runtime_error_is_normalized_and_rewritten(monkeypatch):
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
    _patch_noop_prompt_safety(monkeypatch)

    async def fake_rewrite(prompt, locks, **_kw):
        return "SAFE_REWRITE_PROMPT", {"tokens": 7, "model": "glm-4.5-air", "result": "rewritten"}

    monkeypatch.setattr(img_module, "ps_rewrite_preserving_locks", fake_rewrite)

    tool = ImageGenerationTool()
    calls = {"count": 0}
    prompts = []

    class FakeVLM:
        def get_provider_name(self):
            return "doubao"

        async def image_generation(self, **kwargs):
            prompts.append(kwargs.get("prompt"))
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError(
                    'image_generation failed: 400 {"error":{"code":"InputTextSensitiveContentDetected","message":"rejected by provider"}}'
                )
            return {"image_url": "https://img.example.com/runtime-rewrite.jpg"}

    tool._vlm_service = FakeVLM()

    result = asyncio.run(
        tool._generate_image(
            {
                "prompt": "动态水墨奇幻风格的青袍青年立于古朴村落前景，背景保留水墨晕染与金色光芒，画面主体清晰稳定，同时出现多场景快速切换与标题文字闪现",
                "size": "1024x1024",
                "scene_number": 5,
                "locked_segments": ["青袍青年", "水墨风格"],
            }
        )
    )

    assert calls["count"] == 2
    assert prompts[-1] == "SAFE_REWRITE_PROMPT"
    assert result["prompt_safety_rewrite"]["provider_error_code"] == "InputTextSensitiveContentDetected"
    assert result["prompt_safety_rewrite"]["retry_outcome"] == "success"


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


def test_generate_image_uses_provider_default_size_when_missing(monkeypatch):
    _patch_noop_prompt_safety(monkeypatch)
    tool = ImageGenerationTool()
    calls = []

    class FakeVLM:
        def get_provider_name(self):
            return "doubao"

        def get_capabilities(self):
            return ImageGenerationCapabilities(
                size=EnumCapability(
                    options=["2K"],
                    aliases={"1024x1024": "2K", "1024x1792": "2K", "1792x1024": "2K"},
                )
            )

        async def image_generation(self, **kwargs):
            calls.append(kwargs)
            return {"image_url": "https://img.example.com/default-size.jpg"}

    tool._vlm_service = FakeVLM()

    result = asyncio.run(
        tool._generate_image(
            {
                "prompt": "东方玄幻史诗动画风格的韩立站在晨雾山村中，手持古籍，光影细节充足，构图清晰稳定。",
            }
        )
    )

    assert calls and calls[0]["size"] == "2K"
    assert result["size"] == "2K"


def test_generate_image_normalizes_alias_size_before_provider_call(monkeypatch):
    _patch_noop_prompt_safety(monkeypatch)
    tool = ImageGenerationTool()
    calls = []

    class FakeVLM:
        def get_provider_name(self):
            return "doubao"

        def get_capabilities(self):
            return ImageGenerationCapabilities(
                size=EnumCapability(
                    options=["2K"],
                    aliases={"1024x1024": "2K", "1024x1792": "2K", "1792x1024": "2K"},
                )
            )

        async def image_generation(self, **kwargs):
            calls.append(kwargs)
            return {"image_url": "https://img.example.com/normalized-size.jpg"}

    tool._vlm_service = FakeVLM()

    result = asyncio.run(
        tool._generate_image(
            {
                "prompt": "东方玄幻史诗动画风格的韩立站在晨雾山村中，手持古籍，光影细节充足，构图清晰稳定。",
                "size": "1024x1024",
            }
        )
    )

    assert calls and calls[0]["size"] == "2K"
    assert result["size"] == "2K"


def test_generate_image_rejects_unsupported_size_before_provider_call(monkeypatch):
    _patch_noop_prompt_safety(monkeypatch)
    tool = ImageGenerationTool()
    calls = []

    class FakeVLM:
        def get_provider_name(self):
            return "doubao"

        def get_capabilities(self):
            return ImageGenerationCapabilities(
                size=EnumCapability(
                    options=["2K"],
                    aliases={"1024x1024": "2K", "1024x1792": "2K", "1792x1024": "2K"},
                )
            )

        async def image_generation(self, **kwargs):
            calls.append(kwargs)
            return {"image_url": "https://img.example.com/should-not-run.jpg"}

    tool._vlm_service = FakeVLM()

    with pytest.raises(ToolError) as exc:
        asyncio.run(
            tool._generate_image(
                {
                    "prompt": "东方玄幻史诗动画风格的韩立站在晨雾山村中，手持古籍，光影细节充足，构图清晰稳定。",
                    "size": "1920x1924",
                }
            )
        )

    assert exc.value.error_code == "invalid_image_size"
    assert exc.value.details["allowed_sizes"] == ["2K"]
    assert calls == []


def test_image_generation_tool_exposes_execution_only_actions():
    tool = ImageGenerationTool()

    assert tool.get_available_actions() == [
        "generate_image",
        "analyze_image_style",
        "extract_visual_features",
    ]
    assert tool.get_fc_visibility()["allowed_actions"] == ["generate_image"]


def test_create_image_prompt_from_scene_is_removed():
    tool = ImageGenerationTool()

    with pytest.raises(ToolError) as exc:
        asyncio.run(
            tool._create_image_prompt_from_scene(
                {"scene_number": 2, "title": "秘境探险"},
                "动态水墨奇幻",
                {"style_name": "动态水墨奇幻"},
            )
        )

    assert exc.value.error_code == "action_removed"


def test_generate_with_autoprompt_action_is_removed():
    tool = ImageGenerationTool()

    with pytest.raises(ToolError) as exc:
        asyncio.run(
            tool._execute_impl(
                SimpleNamespace(
                    action="generate_with_autoprompt",
                    parameters={"scene_number": 1},
                )
            )
        )

    assert exc.value.error_code == "action_removed"


def test_gen_image_prompt_action_is_removed():
    tool = ImageGenerationTool()

    with pytest.raises(ToolError) as exc:
        asyncio.run(
            tool._execute_impl(
                SimpleNamespace(
                    action="gen_image_prompt",
                    parameters={"scene_number": 1},
                )
            )
        )

    assert exc.value.error_code == "action_removed"
