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


def test_create_image_prompt_projects_montage_scene_to_single_still():
    tool = ImageGenerationTool()

    prompt = asyncio.run(
        tool._create_image_prompt_from_scene(
            {
                "scene_number": 5,
                "title": "终极预告",
                "visual_description": "场景以快速切换的剪辑呈现，最终定格于韩立特写镜头，标题与上映日期闪现。",
                "narrative_description": "作为预告片的收尾，本场景通过混剪强化前序情节的视觉记忆。",
                "opening_state": "韩立在古朴村落中沐浴神秘光芒",
                "action_phases": [
                    {
                        "phase": "极速混剪",
                        "observable_actions": "画面在韩立持剑战巨蟒、施法斗修仙者之间快速切换",
                    },
                    {
                        "phase": "水墨定格",
                        "observable_actions": "韩立特写镜头定格，背景化作动态水墨晕染，标题与上映日期闪现",
                    },
                ],
                "character_descriptions": [
                    "韩立：青灰色长袍，青竹剑，坚毅沉稳",
                    "快速切换场景中展现不同状态，最终以标题文字收尾",
                ],
                "mood_and_atmosphere": "高潮激昂，快速剪辑增强节奏感",
            },
            "动态水墨奇幻",
            {"style_name": "动态水墨奇幻", "visual_approach": "动画"},
        )
    )

    assert "韩立特写" in prompt
    assert "快速切换" not in prompt
    assert "混剪" not in prompt
    assert "标题" not in prompt
    assert "上映日期" not in prompt


def test_create_image_prompt_prefers_static_end_state_when_opening_is_high_risk():
    tool = ImageGenerationTool()

    prompt = asyncio.run(
        tool._create_image_prompt_from_scene(
            {
                "scene_number": 2,
                "title": "秘境探险",
                "opening_state": "蓝绿色幽光笼罩残垣，巨蟒张开巨口扑向镜头",
                "end_state": "青竹剑光映亮韩立坚毅面庞，巨蟒盘踞在后方阴影中",
                "action_phases": [
                    {"phase": "突袭", "observable_actions": "巨蟒从暗处窜出，韩立眼神骤紧"},
                    {"phase": "御敌", "observable_actions": "韩立身形灵动后撤，青竹剑挥出弧形剑气"},
                ],
                "character_descriptions": [
                    "韩立：青灰色长袍，青竹剑，坚毅沉稳",
                ],
            },
            "动态水墨奇幻",
            {"style_name": "动态水墨奇幻", "visual_approach": "动画"},
        )
    )

    assert "青竹剑光映亮韩立坚毅面庞" in prompt
    assert "扑向镜头" not in prompt
    assert "巨口" not in prompt


def test_create_image_prompt_compresses_role_card_character_descriptions():
    tool = ImageGenerationTool()

    prompt = asyncio.run(
        tool._create_image_prompt_from_scene(
            {
                "title": "终极预告",
                "opening_state": "韩立特写定格，背景化作动态水墨晕染",
                "character_descriptions": [
                    "韩立：原型：成长者；物种：人类；从凡人蜕变的修仙者，坚毅沉稳，成长型主角，手持法器，神秘气质；青灰色长袍，水墨线条勾勒，动态光影效果；青竹剑，储物袋；主角，展现从平凡到超凡的成长历程",
                    "快速切换场景中展现不同状态：从村落中的神秘光芒笼罩，到遗迹中的战斗姿态，再到与敌对修仙者的激战，最后是面对阴影人物的凝视。",
                    "阴影人物：原型：挑战者；物种：人类；神秘莫测，反派势力代表，阴影笼罩，未知威胁；深紫色调，模糊轮廓，低光环境；暗纹长袍；反派或神秘势力，制造悬念与冲突",
                ],
            },
            "动态水墨奇幻",
            {"style_name": "动态水墨奇幻", "visual_approach": "动画"},
        )
    )

    assert "成长历程" not in prompt
    assert "快速切换" not in prompt
    assert "激战" not in prompt
    assert "青灰色长袍" in prompt
    assert "青竹剑" in prompt
    assert "暗纹长袍" in prompt


def test_create_image_prompt_supports_character_reference_contract():
    tool = ImageGenerationTool()

    prompt = asyncio.run(
        tool._create_image_prompt_from_scene(
            {
                "title": "韩立",
                "image_purpose": "character_reference",
                "task_direction": "avatar",
                "characters_present": ["韩立"],
                "character_descriptions": [
                    "韩立：青灰色长袍，黑发束起，神情坚毅",
                    "作为故事开端的成长型主角，承担凡人逆袭叙事弧线",
                ],
                "narrative_description": "作为故事开端，建立韩立的成长主题。",
                "mood_and_atmosphere": "神秘而热血",
            },
            "动态水墨奇幻",
            {
                "style_name": "动态水墨奇幻",
                "style_description": "东方动画水墨质感",
                "visual_approach": "动画",
            },
        )
    )

    assert "角色头像参考图" in prompt
    assert "参考方向" in prompt
    assert "作为故事开端" not in prompt
    assert "光线与氛围" not in prompt
