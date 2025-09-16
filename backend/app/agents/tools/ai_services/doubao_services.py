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

from .service_interfaces import VideoModelServiceInterface, VLMServiceInterface, ServiceProvider


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

        # Supported models (align with latest product names if different in your tenant)
        # 推荐：
        # - 文/图（首帧）生视频：doubao-seedance-1-0-pro-250528
        # - 图生视频（首/尾帧/参考图）：doubao-seedance-1-0-lite-i2v-250428
        # - 文生视频（Lite）：doubao-seedance-1-0-lite-t2v-250428
        self.supported_models = [
            "doubao-seedance-1-0-pro-250528",
            "doubao-seedance-1-0-lite-i2v-250428",
            "doubao-seedance-1-0-lite-t2v-250428",
        ]

    # Interface impl
    def is_available(self) -> bool:
        return bool(self.api_key and self.base_url)

    def get_provider_name(self) -> str:
        return ServiceProvider.ZHIPU.value if False else "doubao"  # keep literal to avoid enum drift

    def get_supported_models(self) -> List[str]:
        return list(self.supported_models)

    def get_duration_capabilities(self) -> List[int]:
        try:
            from ....core.video_config_manager import get_video_config
            return list(get_video_config().get_current_provider_config().duration_capabilities)
        except Exception:
            return [5, 10]

    def supports_first_last_frame(self) -> bool:
        # Seedance supports FLF via dedicated model (wan2-1-14b-flf2v)
        return True

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

        # Choose model based on inputs if caller doesn't specify an explicit one
        chosen_model = (model or "doubao-seedance-pro").strip()
        generation_mode = "text_to_video"
        images_payload: List[Dict[str, str]] | None = None

        # 成本策略：
        # - 首尾帧：用 lite-i2v（支持FLF，成本低于 wan2-*）
        # - 单图：用 pronew/pro（首帧I2V更便宜）；默认 pronew，可通过 env 覆盖
        # - 纯文本：用 pro
        iv2_flf_model = self.config.get("i2v_flf_model") or _get_env(
            "DOUBAO_I2V_FLF_MODEL", "doubao-seedance-1-0-lite-i2v-250428"
        )
        iv2_single_model = self.config.get("i2v_single_model") or _get_env(
            "DOUBAO_I2V_SINGLE_MODEL", "doubao-seedance-1-0-pro-250528"
        )
        # 可选：单图 I2V 替代模型（用于超时回退）
        iv2_single_alt_model = self.config.get("i2v_single_alter_model") or _get_env(
            "DOUBAO_I2V_SINGLE_ALTER_MODEL", "doubao-seedance-1-0-lite-i2v-250428"
        )
        t2v_model = self.config.get("t2v_model") or _get_env(
            "DOUBAO_T2V_MODEL", "doubao-seedance-1-0-pro-250528"
        )

        if first_frame_image and last_frame_image:
            generation_mode = "first_last_frame"
            if model is None:
                chosen_model = iv2_flf_model
            images_payload = [
                {"url": first_frame_image, "role": "first_frame"},
                {"url": last_frame_image, "role": "last_frame"},
            ]
        else:
            ref_image = first_frame_image or image_url
            if ref_image:
                generation_mode = "image_to_video"
                if model is None:
                    chosen_model = iv2_single_model
                images_payload = [{"url": ref_image, "role": "image"}]
            else:
                # 纯文本
                generation_mode = "text_to_video"
                if model is None:
                    chosen_model = t2v_model

        requested_resolution = kwargs.get("resolution") or kwargs.get("rs")
        resolution_for_api: Optional[str] = None
        resolution_canonical: Optional[str] = None
        if isinstance(requested_resolution, (list, tuple, dict)):
            requested_resolution = str(requested_resolution)
        if isinstance(requested_resolution, str):
            requested_resolution = requested_resolution.strip()
        else:
            requested_resolution = None
        if requested_resolution:
            resolution_canonical = requested_resolution
            alias_to_canonical = {
                "480p": "720x480",
                "720p": "1280x720",
                "1080p": "1920x1080"
            }
            canonical_to_alias = {v: k for k, v in alias_to_canonical.items()}
            if requested_resolution in alias_to_canonical:
                resolution_canonical = alias_to_canonical[requested_resolution]
                resolution_for_api = requested_resolution
            elif requested_resolution in canonical_to_alias:
                resolution_canonical = requested_resolution
                resolution_for_api = canonical_to_alias[requested_resolution]
            else:
                resolution_for_api = requested_resolution
            try:
                from ....core.video_config_manager import get_video_config
                allowed_resolutions = list(get_video_config().get_current_provider_config().resolution_options or [])
            except Exception:
                allowed_resolutions = []
            if allowed_resolutions and resolution_canonical not in allowed_resolutions:
                try:
                    self.logger.warning(
                        f"resolution {requested_resolution} not supported; falling back to {allowed_resolutions[0]}"
                    )
                except Exception:
                    pass
                resolution_canonical = allowed_resolutions[0]
                resolution_for_api = canonical_to_alias.get(resolution_canonical, resolution_for_api or resolution_canonical)
        
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
                if duration and duration not in (None, ""):
                    text_prompt = f"{text_prompt} --dur {int(duration)}".strip()
                if resolution_for_api:
                    text_prompt = f"{text_prompt} --rs {resolution_for_api}".strip()
                if text_prompt:
                    content_items.append({"type": "text", "text": text_prompt})
                if images_payload:
                    for it in images_payload:
                        url = it.get("url")
                        if not url:
                            continue
                        content_items.append({"type": "image_url", "image_url": {"url": url}})
                return {"model": model_name, "content": content_items}
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
            return pay

        async def _create_and_poll(model_name: str) -> Dict[str, Any]:
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
            video_url_local = await self._poll_video_result(task_id_local, headers)
            return {"task_id": task_id_local, "video_url": video_url_local}

        # 第一次尝试（按自动/显式选择的模型）
        first = await _create_and_poll(chosen_model)
        task_id = first["task_id"]
        video_url = first["video_url"]
        status = "completed" if video_url else "timeout"

        fallback_applied = False
        fallback_reason: Optional[str] = None
        first_attempt_model = chosen_model
        first_attempt_task_id = task_id

        # 超时且为单图 I2V 且配置了备用模型 → 回退一次
        if (not video_url) and generation_mode == "image_to_video" and (first_attempt_model == iv2_single_model):
            if iv2_single_alt_model and iv2_single_alt_model != first_attempt_model:
                try:
                    self.logger.info(
                        f"FALLBACK: i2v single returned no url/timeout; retrying with alternative model: {iv2_single_alt_model}"
                    )
                except Exception:
                    pass
                second = await _create_and_poll(iv2_single_alt_model)
                if second.get("video_url"):
                    video_url = second["video_url"]
                    task_id = second["task_id"]
                    chosen_model = iv2_single_alt_model
                    status = "completed"
                    fallback_applied = True
                    fallback_reason = "provider_timeout"
                else:
                    # 保持第一次的任务ID与模型，按 timeout 返回
                    fallback_applied = True
                    fallback_reason = "provider_timeout_no_alternative_result"

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
        }
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

    async def _poll_video_result(self, task_id: str, headers: Dict[str, str]) -> str:
        # Poll up to ~3 minutes by default
        max_attempts = int(getattr(self, 'poll_attempts', 36))
        interval = int(getattr(self, 'poll_interval', 5))
        query_url = f"{self.base_url.rstrip('/')}{self.query_path_tpl.format(task_id=task_id)}"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            success_status = {"SUCCESS", "SUCCEEDED", "COMPLETED", "DONE"}
            failed_status = {"FAIL", "FAILED", "ERROR", "CANCELLED", "CANCELED"}
            for attempt in range(max_attempts):
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
                        if video_url:
                            return video_url
                        # Success but no url; break
                        return ""
                    if status_upper in failed_status:
                        self.logger.error(f"Doubao task failed: {js}")
                        return ""
                except Exception as e:
                    self.logger.warning(f"Doubao poll error: {e}")
                await asyncio.sleep(interval)
        return ""


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
        self.model_generation = self.config.get("image_model") or _get_env("DOUBAO_IMAGE_MODEL", "doubao-seedream-4-0-250828")

    def is_available(self) -> bool:
        return bool(self.api_key and self.base_url)

    def get_provider_name(self) -> str:
        return "doubao"

    def get_supported_models(self) -> Dict[str, List[str]]:
        return {"generation": [self.model_generation], "vision": []}

    async def image_understanding(self, image_input: Union[str, bytes], prompt: str, model: str | None = None, **kwargs) -> Dict[str, Any]:
        raise NotImplementedError("Doubao image understanding not implemented")

    async def image_generation(self, prompt: str, model: str | None = None, size: str = "1024x1024", style: str = "vivid", quality: str = "standard", **kwargs) -> Dict[str, Any]:
        if not self.is_available():
            raise RuntimeError("DoubaoVLMService not available - API key/base_url missing")

        chosen_model = (model or self.model_generation).strip()
        payload: Dict[str, Any] = {
            "model": chosen_model,
            "prompt": prompt,
            # 接口允许尺寸枚举，如 '2K'/'1K' 或具体分辨率；此处直接透传 size
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
