"""
Doubao (Volcengine) services – Video (Seedance) and optional Image (Seedream)

Notes
- Video create/query follow asynchronous task pattern.
- Seedance supports first/last-frame I2V when providing two image_url entries with role=first_frame/last_frame.
- Keep supplier-agnostic surface via VideoModelServiceInterface; map inputs internally.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional, Union
import logging

import httpx

from ....services.execution_host_lease import ExecutionHostKeepaliveLostError
from .service_interfaces import (
    VideoModelServiceInterface,
    VLMServiceInterface,
    ServiceProvider,
    VideoCapabilities,
    ImageGenerationCapabilities,
    EnumCapability,
    PromptCapability,
)


def _get_env(name: str, default: Optional[str] = None) -> Optional[str]:
    try:
        from ....core.config import settings  # type: ignore
        val = getattr(settings, name, None)
        if isinstance(val, str) and val:
            return val
    except Exception:
        pass
    return default


class DoubaoVideoService(VideoModelServiceInterface):
    """Volcengine Doubao Seedance video generation service."""

    def __init__(self, config: Dict[str, Any] | None = None):
        self.config = config or {}
        self.logger = logging.getLogger(self.__class__.__name__)

        # env/config
        self.api_key = self.config.get("api_key") or _get_env("DOUBAO_API_KEY")
        # Ark base url (e.g. https://ark.cn-beijing.volces.com)
        self.base_url = self.config.get("base_url") or _get_env("DOUBAO_BASE_URL", "https://ark.cn-beijing.volces.com")
        # Endpoints (allow override via config if product evolves)
        # 支持通过 env 覆盖视频创建/查询路径，兼容不同租户网关（如 contents/generations）
        self.create_path = (
            self.config.get("video_create_path")
            # Correct Doubao Seedance endpoint is "/api/v3/videos/generations" (plural)
            or _get_env("DOUBAO_VIDEO_CREATE_PATH", "/api/v3/videos/generations")
        )
        self.query_path_tpl = (
            self.config.get("video_query_path_tpl")
            # Corresponding task query endpoint is also under "/api/v3/videos/…"
            or _get_env("DOUBAO_VIDEO_QUERY_PATH", "/api/v3/videos/generations/{task_id}")
        )
        # default timeout
        self.timeout = int(self.config.get("timeout") or _get_env("AI_SERVICE_TIMEOUT", 300) or 300)
        # polling controls (allow env override)
        try:
            self.poll_attempts = int(self.config.get("poll_attempts") or _get_env("DOUBAO_POLL_ATTEMPTS", 36) or 36)
        except Exception:
            self.poll_attempts = 36
        try:
            self.poll_interval = int(self.config.get("poll_interval") or _get_env("DOUBAO_POLL_INTERVAL", 5) or 5)
        except Exception:
            self.poll_interval = 5
        provider_key = self.config.get("provider_key") or _get_env("DOUBAO_VIDEO_PROVIDER_KEY", "doubao")
        self.provider_key = str(provider_key).strip() or "doubao"

    # Interface impl
    def is_available(self) -> bool:
        return bool(self.api_key and self.base_url)

    def get_provider_name(self) -> str:
        return ServiceProvider.ZHIPU.value if False else "doubao"  # keep literal to avoid enum drift

    def get_supported_models(self) -> List[str]:
        try:
            from ....core.video_config_manager import get_video_config

            models = get_video_config().get_provider_supported_models(self.provider_key)
            if models:
                return models
        except Exception:
            pass

        # fallback: keep legacy env-driven behaviour
        models: List[str] = []
        seen = set()
        for env_name in (
            "DOUBAO_T2V_MODEL",
            "DOUBAO_I2V_SINGLE_MODEL",
            "DOUBAO_I2V_SINGLE_ALTER_MODEL",
            "DOUBAO_I2V_FLF_MODEL",
        ):
            value = _get_env(env_name, None)
            if not isinstance(value, str):
                continue
            model = value.strip()
            if not model or model in seen:
                continue
            seen.add(model)
            models.append(model)
        provider_cfg = self._get_provider_config()
        if provider_cfg:
            for candidate in [provider_cfg.model_name] + list((provider_cfg.mode_model_mapping or {}).values()):
                if not isinstance(candidate, str):
                    continue
                model = candidate.strip()
                if not model or model in seen:
                    continue
                seen.add(model)
                models.append(model)
        return models

    def get_duration_capabilities(self) -> List[int]:
        try:
            from ....core.video_config_manager import get_video_config
            return list(get_video_config().get_current_provider_config().duration_capabilities)
        except Exception:
            return [5, 10]

    def supports_first_last_frame(self) -> bool:
        # Seedance supports FLF via dedicated model (wan2-1-14b-flf2v)
        return True

    def _get_provider_config(self):
        try:
            from ....core.video_config_manager import get_video_config
            cfg = None
            if self.provider_key:
                cfg = get_video_config().get_provider_config(self.provider_key)
            if cfg is None:
                cfg = get_video_config().get_current_provider_config()
            return cfg
        except Exception:
            return None

    def _resolve_mode_model(
        self,
        *,
        mode: str,
        config_key: str,
        env_name: str,
        explicit_model: Optional[str] = None,
    ) -> str:
        """Resolve model name by provider+mode with clear precedence."""
        if isinstance(explicit_model, str) and explicit_model.strip():
            return explicit_model.strip()

        override_model = self.config.get(config_key)
        if isinstance(override_model, str) and override_model.strip():
            return override_model.strip()

        try:
            from ....core.video_config_manager import get_video_config

            resolved = get_video_config().resolve_model_for_mode(
                self.provider_key,
                mode=mode,
                explicit_model=None,
                default_model=None,
            )
            if isinstance(resolved, str) and resolved.strip():
                return resolved.strip()
        except Exception:
            pass

        fallback = _get_env(env_name, None)
        if isinstance(fallback, str) and fallback.strip():
            return fallback.strip()

        provider_cfg = self._get_provider_config()
        if provider_cfg:
            mode_key = str(mode or "").strip().lower()
            mapped = (provider_cfg.mode_model_mapping or {}).get(mode_key)
            if isinstance(mapped, str) and mapped.strip():
                return mapped.strip()
            if isinstance(provider_cfg.model_name, str) and provider_cfg.model_name.strip():
                return provider_cfg.model_name.strip()

        raise RuntimeError(
            f"Doubao model is not configured for mode={mode}; "
            f"set provider mode_model_mapping or env {env_name}"
        )

    def get_capabilities(self) -> VideoCapabilities:
        caps = VideoCapabilities()
        provider_cfg = self._get_provider_config()
        if not provider_cfg:
            return caps

        prompt_limits = provider_cfg.prompt_limits or {}
        if prompt_limits:
            caps.prompt = PromptCapability(
                max_bytes=prompt_limits.get("max_bytes"),
                approx_chinese_chars=prompt_limits.get("approx_chinese_chars"),
                approx_english_chars=prompt_limits.get("approx_english_chars"),
                description_suffix=prompt_limits.get("note"),
                enforce=bool(prompt_limits.get("enforce", False)),
                extra={
                    k: v
                    for k, v in prompt_limits.items()
                    if k not in {"approx_chinese_chars", "approx_english_chars", "note", "enforce"}
                },
            )

        if provider_cfg.resolution_options:
            caps.resolution = EnumCapability(
                options=list(provider_cfg.resolution_options),
                aliases=dict(provider_cfg.resolution_aliases or {}),
                description_suffix="支持的分辨率列表",
            )

        if provider_cfg.ratio_options:
            caps.ratio = EnumCapability(
                options=list(provider_cfg.ratio_options),
                aliases=dict(provider_cfg.ratio_aliases or {}),
                description_suffix="可选画幅比例",
            )

        return caps

    async def generate_video(
        self,
        prompt: str,
        model: str | None = None,
        duration: int = 5,
        image_url: str | None = None,
        first_frame_image: str | None = None,
        last_frame_image: str | None = None,
        **kwargs,
    ) -> Dict[str, Any]:
        if not self.is_available():
            raise RuntimeError("DoubaoVideoService not available - API key/base_url missing")

        generation_mode = "text_to_video"
        images_payload: List[Dict[str, str]] | None = None
        explicit_model = model.strip() if isinstance(model, str) and model.strip() else None
        iv2_single_alt_model: Optional[str] = None
        allow_i2v_timeout_fallback = False

        if first_frame_image and last_frame_image:
            generation_mode = "first_last_frame"
            images_payload = [
                {"url": first_frame_image, "role": "first_frame"},
                {"url": last_frame_image, "role": "last_frame"},
            ]
            chosen_model = self._resolve_mode_model(
                mode="first_last_frame",
                config_key="i2v_flf_model",
                env_name="DOUBAO_I2V_FLF_MODEL",
                explicit_model=explicit_model,
            )
        else:
            ref_image = first_frame_image or image_url
            if ref_image:
                generation_mode = "image_to_video"
                allow_i2v_timeout_fallback = explicit_model is None
                chosen_model = self._resolve_mode_model(
                    mode="image_to_video",
                    config_key="i2v_single_model",
                    env_name="DOUBAO_I2V_SINGLE_MODEL",
                    explicit_model=explicit_model,
                )
                images_payload = [{"url": ref_image, "role": "image"}]
                if allow_i2v_timeout_fallback:
                    try:
                        iv2_single_alt_model = self._resolve_mode_model(
                            mode="image_to_video_fallback",
                            config_key="i2v_single_alter_model",
                            env_name="DOUBAO_I2V_SINGLE_ALTER_MODEL",
                            explicit_model=None,
                        )
                    except Exception:
                        iv2_single_alt_model = None
            else:
                generation_mode = "text_to_video"
                chosen_model = self._resolve_mode_model(
                    mode="text_to_video",
                    config_key="t2v_model",
                    env_name="DOUBAO_T2V_MODEL",
                    explicit_model=explicit_model,
                )

        requested_resolution = kwargs.get("resolution") or kwargs.get("rs")
        if isinstance(requested_resolution, (list, tuple, dict)):
            requested_resolution = str(requested_resolution)
        if isinstance(requested_resolution, str):
            requested_resolution = requested_resolution.strip()
        else:
            requested_resolution = None

        provider_cfg = self._get_provider_config()
        resolution_aliases = dict(getattr(provider_cfg, "resolution_aliases", {}) or {})
        allowed_resolutions = list(getattr(provider_cfg, "resolution_options", []) or [])
        canonical_to_alias = {v: k for k, v in resolution_aliases.items()}

        resolution_for_api: Optional[str] = None
        resolution_canonical: Optional[str] = None

        if requested_resolution:
            resolution_canonical = resolution_aliases.get(requested_resolution, requested_resolution)
            if requested_resolution in resolution_aliases:
                # API 可以直接接受别名（rs=720p），保留原值
                resolution_for_api = requested_resolution
            else:
                resolution_for_api = canonical_to_alias.get(requested_resolution, requested_resolution)

            if allowed_resolutions and resolution_canonical not in allowed_resolutions:
                try:
                    self.logger.warning(
                        f"resolution {requested_resolution} not supported; falling back to {allowed_resolutions[0]}"
                    )
                except Exception:
                    pass
                resolution_canonical = allowed_resolutions[0]
                resolution_for_api = canonical_to_alias.get(resolution_canonical, resolution_canonical)

        requested_ratio = kwargs.get("ratio") or kwargs.get("rt")
        if isinstance(requested_ratio, (list, tuple, dict)):
            requested_ratio = str(requested_ratio)
        if isinstance(requested_ratio, str):
            requested_ratio = requested_ratio.strip()
        else:
            requested_ratio = None

        ratio_aliases = dict(getattr(provider_cfg, "ratio_aliases", {}) or {})
        allowed_ratios = list(getattr(provider_cfg, "ratio_options", []) or [])
        ratio_canonical: Optional[str] = None
        ratio_for_api: Optional[str] = None
        ratio_alias_inverse = {v: k for k, v in ratio_aliases.items()}

        if requested_ratio:
            ratio_canonical = ratio_aliases.get(requested_ratio, requested_ratio)
            if allowed_ratios and ratio_canonical not in allowed_ratios:
                try:
                    self.logger.warning(
                        f"ratio {requested_ratio} not supported; falling back to {allowed_ratios[0]}"
                    )
                except Exception:
                    pass
                ratio_canonical = allowed_ratios[0]
            if requested_ratio in ratio_aliases:
                ratio_for_api = requested_ratio
            else:
                ratio_for_api = ratio_alias_inverse.get(ratio_canonical, ratio_canonical)

        requested_generate_audio = kwargs.get("generate_audio")
        if isinstance(requested_generate_audio, str):
            lowered = requested_generate_audio.strip().lower()
            if lowered in {"true", "1", "yes", "on"}:
                requested_generate_audio = True
            elif lowered in {"false", "0", "no", "off"}:
                requested_generate_audio = False
            else:
                requested_generate_audio = None
        elif not isinstance(requested_generate_audio, bool):
            requested_generate_audio = None

        requested_frames = kwargs.get("frames")
        if isinstance(requested_frames, str):
            requested_frames = requested_frames.strip()
        try:
            requested_frames = int(requested_frames) if requested_frames not in (None, "") else None
        except Exception:
            requested_frames = None

        execution_liveness_probe = kwargs.get("execution_liveness_probe")

        # 组装请求头与URL
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        create_url = f"{self.base_url.rstrip('/')}{self.create_path}"

        async def _build_payload(model_name: str) -> Dict[str, Any]:
            """按当前网关构造请求 payload。"""
            if "contents/generations" in self.create_path:
                content_items: List[Dict[str, Any]] = []
                text_prompt = (prompt or "").strip()
                if text_prompt:
                    content_items.append({"type": "text", "text": text_prompt})
                if images_payload:
                    for it in images_payload:
                        url = it.get("url")
                        if not url:
                            continue
                        content_items.append({"type": "image_url", "image_url": {"url": url}})
                payload = {"model": model_name, "content": content_items}
                if requested_frames is not None:
                    payload["frames"] = requested_frames
                elif duration not in (None, ""):
                    payload["duration"] = int(duration)
                if resolution_for_api:
                    payload["resolution"] = resolution_for_api
                if ratio_for_api:
                    payload["ratio"] = ratio_for_api
                if isinstance(requested_generate_audio, bool):
                    payload["generate_audio"] = requested_generate_audio
                return payload
            # 旧版 /video/generations 风格
            pay: Dict[str, Any] = {
                "model": model_name,
                "prompt": prompt,
                "duration": int(duration),
            }
            if images_payload:
                pay["image_url"] = images_payload
            if resolution_for_api:
                pay["rs"] = resolution_for_api
                pay["resolution"] = resolution_for_api
            if ratio_for_api:
                pay["rt"] = ratio_for_api
                pay["ratio"] = ratio_for_api
            if isinstance(requested_generate_audio, bool):
                pay["generate_audio"] = requested_generate_audio
            return pay

        async def _create_and_poll(model_name: str) -> Dict[str, Any]:
            if callable(execution_liveness_probe):
                execution_liveness_probe()

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                payload = await _build_payload(model_name)
                resp = await client.post(create_url, headers=headers, json=payload)
                if resp.status_code >= 400:
                    raise RuntimeError(
                        f"Doubao create video failed: {resp.status_code} {resp.text} url={create_url}"
                    )
                data = resp.json()
            task_id_local = data.get("id") or data.get("task_id") or data.get("data", {}).get("task_id")
            if not task_id_local:
                raise RuntimeError(f"Doubao create video did not return task id: {data}")
            poll_res = await self._poll_video_result(
                task_id_local,
                headers,
                execution_liveness_probe=execution_liveness_probe,
            )
            return {
                "task_id": task_id_local,
                "video_url": poll_res.get("video_url"),
                "status": poll_res.get("status"),
                "provider_error": poll_res.get("provider_error"),
            }

        # 第一次尝试（按自动/显式选择的模型）
        first = await _create_and_poll(chosen_model)
        task_id = first.get("task_id")
        video_url = first.get("video_url")
        status = first.get("status", "UNKNOWN")
        provider_error = first.get("provider_error")

        fallback_applied = False
        fallback_reason: Optional[str] = None
        first_attempt_model = chosen_model
        first_attempt_task_id = task_id

        # 超时且为单图 I2V 且配置了备用模型 → 回退一次
        if (not video_url) and generation_mode == "image_to_video" and allow_i2v_timeout_fallback:
            if iv2_single_alt_model and iv2_single_alt_model != first_attempt_model:
                try:
                    self.logger.info(
                        f"FALLBACK: i2v single returned no url/timeout; retrying with alternative model: {iv2_single_alt_model}"
                    )
                except Exception:
                    pass
                second = await _create_and_poll(iv2_single_alt_model)
                if second.get("video_url"):
                    video_url = second.get("video_url")
                    task_id = second.get("task_id") or first_attempt_task_id
                    chosen_model = iv2_single_alt_model
                    status = second.get("status", "COMPLETED")
                    provider_error = second.get("provider_error")
                    fallback_applied = True
                    fallback_reason = "provider_timeout"
                else:
                    # 保持第一次的任务ID与模型，按 timeout 返回
                    fallback_applied = True
                    fallback_reason = "provider_timeout_no_alternative_result"
                    provider_error = provider_error or {"code": "provider_timeout", "message": "i2v fallback failed"}

        # 记录结果日志
        try:
            if video_url:
                self.logger.info(
                    f"✅ Doubao video generated: model={chosen_model} mode={generation_mode} url={str(video_url)[:96]}"
                )
            else:
                self.logger.warning(
                    f"Doubao video task completed without url or timed out: model={chosen_model} mode={generation_mode} task_id={task_id}"
                )
        except Exception:
            pass

        result: Dict[str, Any] = {
            "video_id": task_id,
            "status": status,
            "video_url": video_url,
            "model": chosen_model,
            "prompt": prompt,
            "generation_mode": generation_mode,
            "duration": duration,
            "provider": "doubao",
            "resolution": resolution_for_api or resolution_canonical,
            "requested_resolution": requested_resolution,
            "ratio": ratio_for_api or ratio_canonical,
            "requested_ratio": requested_ratio,
            "generate_audio": requested_generate_audio,
        }
        if provider_error:
            result["provider_error"] = provider_error
        if fallback_applied:
            result.update({
                "fallback_applied": True,
                "fallback_reason": fallback_reason,
                "initial_model": first_attempt_model,
                "initial_task_id": first_attempt_task_id,
                "final_model": chosen_model,
            })
        return result

    async def get_generation_status(self, task_id: str, **kwargs) -> Dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        query_url = f"{self.base_url.rstrip('/')}{self.query_path_tpl.format(task_id=task_id)}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(query_url, headers=headers)
            if resp.status_code >= 400:
                raise RuntimeError(f"Doubao query video failed: {resp.status_code} {resp.text} url={query_url}")
            js = resp.json()
        # Normalize
        task_status = js.get("status") or js.get("task_status") or js.get("data", {}).get("status")
        video_url = (
            js.get("video_url")
            or js.get("data", {}).get("video_url")
            or (js.get("data", {}).get("video_result", [{}]) or [{}])[0].get("url")
            or (js.get("content", {}) or {}).get("video_url")
        )
        return {"task_id": task_id, "status": task_status, "video_url": video_url}

    async def _poll_video_result(
        self,
        task_id: str,
        headers: Dict[str, str],
        *,
        execution_liveness_probe=None,
    ) -> Dict[str, Any]:
        # Poll up to ~3 minutes by default
        max_attempts = int(getattr(self, 'poll_attempts', 36))
        interval = int(getattr(self, 'poll_interval', 5))
        query_url = f"{self.base_url.rstrip('/')}{self.query_path_tpl.format(task_id=task_id)}"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            success_status = {"SUCCESS", "SUCCEEDED", "COMPLETED", "DONE"}
            failed_status = {"FAIL", "FAILED", "ERROR", "CANCELLED", "CANCELED"}
            for attempt in range(max_attempts):
                if callable(execution_liveness_probe):
                    execution_liveness_probe()
                try:
                    resp = await client.get(query_url, headers=headers)
                    if resp.status_code >= 400:
                        await asyncio.sleep(interval)
                        continue
                    js = resp.json()
                    status = js.get("status") or js.get("task_status") or js.get("data", {}).get("status")
                    status_upper = str(status).upper()
                    if status_upper in success_status:
                        video_url = (
                            js.get("video_url")
                            or js.get("data", {}).get("video_url")
                            or (js.get("data", {}).get("video_result", [{}]) or [{}])[0].get("url")
                            or (js.get("content", {}) or {}).get("video_url")
                        )
                        return {
                            "status": status_upper,
                            "video_url": video_url or "",
                            "provider_error": None,
                        }
                    if status_upper in failed_status:
                        self.logger.error(f"Doubao task failed: {js}")
                        provider_error = js.get("error") or {}
                        if not provider_error:
                            provider_error = {
                                "code": js.get("error_code") or status_upper.lower(),
                                "message": js.get("message") or str(js),
                            }
                        return {
                            "status": status_upper,
                            "video_url": "",
                            "provider_error": provider_error,
                        }
                except ExecutionHostKeepaliveLostError:
                    raise
                except Exception as e:
                    self.logger.warning(f"Doubao poll error: {e}")
                await asyncio.sleep(interval)
        return {
            "status": "TIMEOUT",
            "video_url": "",
            "provider_error": {"code": "provider_timeout", "message": "poll timeout"},
        }


class DoubaoVLMService(VLMServiceInterface):
    """Volcengine Doubao Seedream image generation service."""

    def __init__(self, config: Dict[str, Any] | None = None):
        self.config = config or {}
        self.logger = logging.getLogger(self.__class__.__name__)
        self.api_key = self.config.get("api_key") or _get_env("DOUBAO_API_KEY")
        self.base_url = self.config.get("base_url") or _get_env("DOUBAO_BASE_URL", "https://ark.cn-beijing.volces.com")
        # 允许通过环境变量覆盖路径，兼容不同租户的“contents/generations”网关配置
        self.create_path = (
            self.config.get("image_create_path")
            or _get_env("DOUBAO_IMAGE_CREATE_PATH", "/api/v3/images/generations")
        )
        self.timeout = int(self.config.get("timeout") or _get_env("AI_SERVICE_TIMEOUT", 120) or 120)
        model_cfg = self.config.get("image_model") or _get_env("DOUBAO_IMAGE_MODEL", None) or ""
        self.model_generation = str(model_cfg).strip()

    def is_available(self) -> bool:
        return bool(self.api_key and self.base_url and self.model_generation)

    def get_provider_name(self) -> str:
        return "doubao"

    def get_supported_models(self) -> Dict[str, List[str]]:
        generation = [self.model_generation] if self.model_generation else []
        return {"generation": generation, "vision": []}

    async def image_understanding(self, image_input: Union[str, bytes], prompt: str, model: str | None = None, **kwargs) -> Dict[str, Any]:
        raise NotImplementedError("Doubao image understanding not implemented")

    def get_capabilities(self) -> ImageGenerationCapabilities:
        return ImageGenerationCapabilities(
            size=EnumCapability(
                options=["2K"],
                aliases={
                    "1024x1024": "2K",
                    "1024x1792": "2K",
                    "1792x1024": "2K",
                    "1K": "2K",
                },
                description_suffix="当前 Doubao 图像生成仅暴露 provider-compatible canonical size",
                note="当前 provider 要求图像尺寸至少满足 3686400 像素，通用 1K/1024 尺寸将规范化到 2K。",
            )
        )

    async def image_generation(self, prompt: str, model: str | None = None, size: str | None = None, style: str = "vivid", quality: str = "standard", **kwargs) -> Dict[str, Any]:
        if not self.is_available():
            raise RuntimeError("DoubaoVLMService not available - API key/base_url/model missing")

        chosen_model = str(model or self.model_generation or "").strip()
        if not chosen_model:
            raise RuntimeError("Doubao image model is not configured; set DOUBAO_IMAGE_MODEL")
        payload: Dict[str, Any] = {
            "model": chosen_model,
            "prompt": prompt,
            # image_generation_tool 已负责 provider-aware 规范化；adapter 仅映射 payload
            "size": size,
            "sequential_image_generation": "disabled",
            "stream": False,
            "response_format": "url",
            "watermark": True,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self.base_url.rstrip('/')}{self.create_path}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code >= 400:
                raise RuntimeError(f"Doubao image generation failed: {resp.status_code} {resp.text}")
            js = resp.json()
        # Normalize url (兼容 data 为数组或对象的两种返回格式)
        image_url: Optional[str] = None
        if isinstance(js, dict):
            image_url = js.get("image_url") or js.get("url")
            if not image_url and "data" in js:
                data = js.get("data")
                if isinstance(data, list) and data:
                    first = data[0] if isinstance(data[0], dict) else {}
                    image_url = first.get("url") or first.get("image_url")
                elif isinstance(data, dict):
                    images = data.get("images") if isinstance(data.get("images"), list) else None
                    if images:
                        first = images[0] if isinstance(images[0], dict) else {}
                        image_url = first.get("url") or first.get("image_url")
                    else:
                        image_url = data.get("url") or data.get("image_url")
        try:
            if image_url:
                self.logger.info(
                    f"✅ Doubao image generated: model={chosen_model} url={str(image_url)[:96]}"
                )
            else:
                self.logger.warning(
                    f"Doubao image generation returned no url: model={chosen_model} resp_keys={list(js.keys())}"
                )
        except Exception:
            pass
        return {"image_url": image_url, "provider": "doubao", "model": chosen_model, "raw": js}

    async def image_editing(self, image_input: Union[str, bytes], prompt: str, model: str | None = None, **kwargs) -> Dict[str, Any]:
        raise NotImplementedError("Doubao image editing not implemented")
