import pytest

from app.agents.tools.ai_services import doubao_services as doubao_module
from app.agents.tools.ai_services.doubao_services import DoubaoVideoService


class _FakeHTTPResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self):
        return self._payload


def _patch_async_client(monkeypatch, post_payloads):
    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers=None, json=None):
            post_payloads.append({"url": url, "headers": headers, "json": json})
            return _FakeHTTPResponse({"id": "task-1"})

    monkeypatch.setattr(doubao_module.httpx, "AsyncClient", _FakeAsyncClient)


@pytest.mark.asyncio
async def test_generate_video_i2v_does_not_require_t2v_or_fallback_model(monkeypatch):
    post_payloads = []
    _patch_async_client(monkeypatch, post_payloads)

    service = DoubaoVideoService(config={"api_key": "k", "base_url": "https://unit.test"})
    resolve_calls = []

    def _resolve_mode_model(*, mode, config_key, env_name, explicit_model=None):
        resolve_calls.append(mode)
        if mode == "text_to_video":
            raise RuntimeError("t2v should not be resolved for i2v")
        if mode == "image_to_video":
            return "i2v-main-model"
        if mode == "image_to_video_fallback":
            raise RuntimeError("fallback model is intentionally unset")
        raise AssertionError(f"unexpected mode: {mode}")

    async def _poll_video_result(_task_id, _headers):
        return {"video_url": "https://unit.test/video.mp4", "status": "SUCCESS", "provider_error": None}

    monkeypatch.setattr(service, "_resolve_mode_model", _resolve_mode_model)
    monkeypatch.setattr(service, "_poll_video_result", _poll_video_result)

    result = await service.generate_video(
        prompt="test i2v",
        image_url="https://unit.test/image.jpg",
    )

    assert result["generation_mode"] == "image_to_video"
    assert result["model"] == "i2v-main-model"
    assert "text_to_video" not in resolve_calls
    assert len(post_payloads) == 1


@pytest.mark.asyncio
async def test_generate_video_i2v_explicit_model_skips_optional_fallback_resolution(monkeypatch):
    post_payloads = []
    _patch_async_client(monkeypatch, post_payloads)

    service = DoubaoVideoService(config={"api_key": "k", "base_url": "https://unit.test"})
    resolve_calls = []

    def _resolve_mode_model(*, mode, config_key, env_name, explicit_model=None):
        resolve_calls.append(mode)
        if mode == "image_to_video":
            return explicit_model or "i2v-main-model"
        if mode == "image_to_video_fallback":
            raise AssertionError("explicit model path should not resolve fallback mode")
        if mode == "text_to_video":
            raise AssertionError("explicit i2v request should not resolve text_to_video")
        raise AssertionError(f"unexpected mode: {mode}")

    async def _poll_video_result(_task_id, _headers):
        return {"video_url": "https://unit.test/video.mp4", "status": "SUCCESS", "provider_error": None}

    monkeypatch.setattr(service, "_resolve_mode_model", _resolve_mode_model)
    monkeypatch.setattr(service, "_poll_video_result", _poll_video_result)

    result = await service.generate_video(
        prompt="test i2v explicit model",
        model="doubao-i2v-explicit",
        image_url="https://unit.test/image.jpg",
    )

    assert result["generation_mode"] == "image_to_video"
    assert result["model"] == "doubao-i2v-explicit"
    assert resolve_calls == ["image_to_video"]
    assert len(post_payloads) == 1
