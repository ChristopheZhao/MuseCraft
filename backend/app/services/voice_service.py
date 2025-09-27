"""Voice synthesis service router and provider adapters."""
import asyncio
import json
import base64
import hashlib
import hmac
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlencode

import httpx

from ..core.config import settings


class VoiceServiceError(Exception):
    """Base exception for voice service errors."""


class VoiceProviderUnavailableError(VoiceServiceError):
    """Raised when a provider is not properly configured or reachable."""


class VoiceProviderResponseError(VoiceServiceError):
    """Raised when a provider returns an unexpected response."""


@dataclass
class VoiceSynthesisRequest:
    """Canonical request payload for voice synthesis providers."""

    text: str
    voice_id: str
    language: str = "zh-CN"
    speed: float = 1.0
    pitch: float = 1.0
    style: Optional[str] = None
    sample_rate: int = 16000
    audio_format: str = "wav"
    reference_id: Optional[str] = None
    output_path: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VoiceSynthesisResult:
    """Normalized voice synthesis result returned to agents/tools."""

    local_path: str
    provider: str
    voice_id: str
    sample_rate: int
    audio_format: str
    duration: float
    raw_audio: bytes
    metadata: Dict[str, Any] = field(default_factory=dict)
    fallback_reason: Optional[str] = None


class BaseVoiceAdapter:
    """Abstract base class for voice provider adapters."""

    provider_name: str = "base"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.logger = logging.getLogger(f"voice_provider.{self.provider_name}")
        self._initialize()

    def _initialize(self) -> None:
        """Perform provider specific initialization."""

    def is_available(self) -> bool:
        """Whether the provider is ready for use."""
        return True

    async def synthesize(self, request: VoiceSynthesisRequest) -> VoiceSynthesisResult:
        raise NotImplementedError

    async def list_voices(self) -> List[Dict[str, Any]]:
        """Return provider specific voice manifest, if available."""
        return []


class AliyunTTSAdapter(BaseVoiceAdapter):
    """Adapter for Aliyun Intelligent Speech Interaction TTS API."""

    provider_name = "aliyun"

    def _initialize(self) -> None:
        self.app_key = self.config.get("app_key") or getattr(settings, "ALIYUN_TTS_APP_KEY", None)
        self.access_key_id = self.config.get("access_key_id") or getattr(settings, "ALIYUN_TTS_ACCESS_KEY_ID", None)
        self.access_key_secret = (
            self.config.get("access_key_secret") or getattr(settings, "ALIYUN_TTS_ACCESS_KEY_SECRET", None)
        )
        self.region = self.config.get("region") or getattr(settings, "ALIYUN_TTS_REGION", "cn-shanghai")
        self.token_endpoint = self.config.get(
            "token_endpoint",
            f"https://nls-meta.{self.region}.aliyuncs.com/v1/token",
        )
        self.gateway_endpoint = self.config.get(
            "gateway_endpoint",
            f"https://nls-gateway-{self.region}.aliyuncs.com/stream/v1/tts",
        )
        self.voice_manifest = self._load_voice_manifest()
        self.timeout = int(self.config.get("timeout", getattr(settings, "VOICE_HTTP_TIMEOUT", 30)))
        self.output_dir = Path(getattr(settings, "VOICE_OUTPUT_DIR", "./storage/generated/voices"))
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self._token: Optional[str] = None
        self._token_expire: float = 0.0
        self._token_lock = asyncio.Lock()

        if not all([self.app_key, self.access_key_id, self.access_key_secret]):
            self.logger.warning("Aliyun TTS missing credentials; provider disabled")

    def _load_voice_manifest(self) -> List[Dict[str, Any]]:
        manifest = []
        try:
            catalog_path = getattr(settings, "VOICE_CATALOG_PATH", None)
            if catalog_path and Path(catalog_path).exists():
                with open(catalog_path, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
                if isinstance(data, dict):
                    manifest = data.get("voices", [])
                elif isinstance(data, list):
                    manifest = data
        except Exception as exc:
            self.logger.warning(f"Failed to load voice manifest: {exc}")
        return manifest

    def is_available(self) -> bool:
        return all([self.app_key, self.access_key_id, self.access_key_secret])

    async def synthesize(self, request: VoiceSynthesisRequest) -> VoiceSynthesisResult:
        if not self.is_available():
            raise VoiceProviderUnavailableError("Aliyun TTS credentials missing")

        if not request.text.strip():
            raise VoiceServiceError("Voice synthesis text payload is empty")

        token = await self._ensure_token()
        speech_rate = self._normalize_rate(request.speed)
        pitch_rate = self._normalize_rate(request.pitch)

        params = {
            "appkey": self.app_key,
            "token": token,
            "voice": request.voice_id,
            "format": request.audio_format,
            "sample_rate": str(request.sample_rate),
            "speech_rate": str(speech_rate),
            "pitch_rate": str(pitch_rate),
            "text": request.text,
            "volume": "50",
            "enable_subtitle": "false",
        }

        if request.style:
            params["style"] = request.style

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                self.gateway_endpoint,
                params=params,
            )

        if response.status_code != 200:
            raise VoiceProviderResponseError(
                f"Aliyun TTS request failed: {response.status_code} {response.text}"
            )

        content_type = response.headers.get("content-type", "")
        if "audio" not in content_type:
            raise VoiceProviderResponseError(
                f"Unexpected Aliyun TTS response type: {content_type} {response.text}"
            )

        audio_bytes = response.content
        output_path = self._resolve_output_path(request)
        await asyncio.to_thread(self._write_file, output_path, audio_bytes)

        duration = self._estimate_duration(audio_bytes, request.sample_rate, request.audio_format)
        metadata = {
            "provider": self.provider_name,
            "speech_rate": speech_rate,
            "pitch_rate": pitch_rate,
            "style": request.style,
            "reference_id": request.reference_id,
        }

        return VoiceSynthesisResult(
            local_path=str(output_path),
            provider=self.provider_name,
            voice_id=request.voice_id,
            sample_rate=request.sample_rate,
            audio_format=request.audio_format,
            duration=duration,
            raw_audio=audio_bytes,
            metadata=metadata,
        )

    async def list_voices(self) -> List[Dict[str, Any]]:
        return self.voice_manifest

    async def _ensure_token(self) -> str:
        async with self._token_lock:
            now = time.time()
            if self._token and now < self._token_expire - 30:
                return self._token

            token, expire_ts = await self._request_federated_token()

            self._token = token
            self._token_expire = expire_ts
            return token

    async def _request_federated_token(self) -> tuple[str, float]:
        params = {
            "AccessKeyId": self.access_key_id,
            "Action": "CreateToken",
            "Format": "JSON",
            "RegionId": self.region,
            "SignatureMethod": "HMAC-SHA1",
            "SignatureNonce": uuid.uuid4().hex,
            "SignatureVersion": "1.0",
            "Timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "Version": "2019-02-28",
        }

        canonical_query = self._encode_dict(params)
        string_to_sign = "GET&%2F&" + self._encode_text(canonical_query)
        signing_key = f"{self.access_key_secret}&"
        signature = base64.b64encode(
            hmac.new(signing_key.encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha1).digest()
        ).decode("utf-8")
        encoded_signature = self._encode_text(signature)
        token_url = f"https://nls-meta.{self.region}.aliyuncs.com/?Signature={encoded_signature}&{canonical_query}"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(token_url)

        if response.status_code != 200:
            raise VoiceProviderResponseError(
                f"Aliyun token request failed: {response.status_code} {response.text}"
            )

        try:
            data = response.json()
            token_info = data.get("Token") or {}
            token = token_info.get("Id")
            expire_time = token_info.get("ExpireTime")
            expire_ms = token_info.get("ExpireTimeMillis")
        except Exception as exc:
            raise VoiceProviderResponseError(f"Invalid token response: {exc}") from exc

        if not token:
            raise VoiceProviderResponseError(f"Token not present in response: {response.text}")

        if expire_ms:
            expire_ts = float(expire_ms) / 1000.0
        elif expire_time:
            expire_ts = self._parse_expire_time(expire_time)
        else:
            expire_ts = time.time() + 300

        return token, expire_ts

    @staticmethod
    def _encode_text(text: str) -> str:
        encoded = quote(text, safe="~")
        return encoded

    @classmethod
    def _encode_dict(cls, data: Dict[str, Any]) -> str:
        sorted_items = [(key, data[key]) for key in sorted(data.keys())]
        encoded = urlencode(sorted_items)
        encoded = encoded.replace("+", "%20").replace("*", "%2A").replace("%7E", "~")
        return encoded

    def _resolve_output_path(self, request: VoiceSynthesisRequest) -> Path:
        if request.output_path:
            output_path = Path(request.output_path)
        else:
            filename = f"voice_{uuid.uuid4().hex}.{request.audio_format}"
            output_path = self.output_dir / filename
        output_path.parent.mkdir(parents=True, exist_ok=True)
        return output_path

    @staticmethod
    def _write_file(path: Path, data: bytes) -> None:
        with open(path, "wb") as handle:
            handle.write(data)

    @staticmethod
    def _normalize_rate(value: float) -> int:
        try:
            multiplier = float(value)
        except (TypeError, ValueError):
            return 0

        if multiplier <= 0:
            return -500

        if abs(multiplier - 1.0) < 0.01:
            return 0

        if multiplier < 1.0:
            rate = (1 - (1 / multiplier)) / 0.002
        else:
            rate = (1 - (1 / multiplier)) / 0.001

        rate = int(round(rate))
        return max(-500, min(500, rate))

    @staticmethod
    def _estimate_duration(audio_bytes: bytes, sample_rate: int, audio_format: str) -> float:
        if audio_format.lower() == "wav" and sample_rate:
            # Rough estimate: assume 16-bit mono (2 bytes per sample)
            return max(0.0, len(audio_bytes) / (sample_rate * 2))
        return 0.0

    @staticmethod
    def _parse_expire_time(expire_time: str) -> float:
        try:
            # Example format: "2024-01-01 12:34:56"
            from datetime import datetime

            dt = datetime.strptime(expire_time, "%Y-%m-%d %H:%M:%S")
            return dt.timestamp()
        except Exception:
            return time.time() + 300


class VoiceServiceRouter:
    """Service router orchestrating supplier selection and fallback."""

    def __init__(self):
        self.logger = logging.getLogger("voice_service")
        self._adapters: Dict[str, BaseVoiceAdapter] = {}
        self._provider_order = self._build_provider_order()
        self._voice_manifest: List[Dict[str, Any]] = []
        self._register_providers()

    def _build_provider_order(self) -> List[str]:
        primary = getattr(settings, "VOICE_PRIMARY_PROVIDER", "aliyun") or "aliyun"
        fallbacks = getattr(settings, "VOICE_PROVIDER_FALLBACKS", []) or []
        if isinstance(fallbacks, str):
            fallbacks = [p.strip() for p in fallbacks.split(",") if p.strip()]
        order = [primary]
        for candidate in fallbacks:
            if candidate not in order:
                order.append(candidate)
        return order

    def _register_providers(self) -> None:
        providers_config = getattr(settings, "VOICE_PROVIDER_CONFIG", {}) or {}
        aliyun_cfg = providers_config.get("aliyun", {})
        adapter = AliyunTTSAdapter(aliyun_cfg)
        self._adapters[adapter.provider_name] = adapter
        if adapter.voice_manifest:
            self._voice_manifest.extend(adapter.voice_manifest)

    async def synthesize(self, request: VoiceSynthesisRequest) -> VoiceSynthesisResult:
        errors: List[str] = []
        for provider_name in self._provider_order:
            adapter = self._adapters.get(provider_name)
            if not adapter:
                errors.append(f"provider={provider_name} not registered")
                continue
            if not adapter.is_available():
                errors.append(f"provider={provider_name} unavailable")
                continue
            try:
                result = await adapter.synthesize(request)
                return result
            except VoiceServiceError as exc:
                self.logger.warning(
                    "Voice synthesis failed on provider %s: %s", provider_name, exc
                )
                errors.append(f"{provider_name}: {exc}")
                continue
            except Exception as exc:  # noqa: BLE001 - ensure fallbacks still run
                wrapped = VoiceServiceError(str(exc))
                self.logger.warning(
                    "Voice synthesis unexpected error on provider %s: %s", provider_name, exc,
                    exc_info=exc,
                )
                errors.append(f"{provider_name}: {wrapped}")
                continue
        raise VoiceServiceError(f"All voice providers failed: {'; '.join(errors)}")

    async def list_voices(self) -> Dict[str, List[Dict[str, Any]]]:
        catalog: Dict[str, List[Dict[str, Any]]] = {}
        for name, adapter in self._adapters.items():
            try:
                catalog[name] = await adapter.list_voices()
            except Exception as exc:
                self.logger.warning("List voices failed for %s: %s", name, exc)
        if not self._voice_manifest:
            combined: List[Dict[str, Any]] = []
            for voices in catalog.values():
                if voices:
                    combined.extend(voices)
            self._voice_manifest = combined
        return catalog

    @property
    def voice_manifest(self) -> List[Dict[str, Any]]:
        return self._voice_manifest


voice_service = VoiceServiceRouter()
