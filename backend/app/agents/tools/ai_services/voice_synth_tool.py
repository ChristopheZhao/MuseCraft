"""Voice synthesis tool bridging MAS agents with the voice service router."""
from typing import Any, Dict, List, Optional

from ..base_tool import AsyncTool, ToolMetadata, ToolType, ToolInput, ToolError
from ..tool_registry import get_tool_registry
from ....services.voice_service import voice_service, VoiceSynthesisRequest, VoiceServiceError
from ....core.config import settings


class VoiceSynthesisTool(AsyncTool):
    """Expose supplier-agnostic voice synthesis actions via FC schema."""

    @classmethod
    def get_metadata(cls) -> ToolMetadata:
        return ToolMetadata(
            name="voice_synth_tool",
            version="1.0.0",
            description="Supplier-agnostic voice synthesis tool",
            tool_type=ToolType.AI_SERVICE,
            author="system",
            tags=["voice", "tts", "speech", "audio"],
            capabilities=["text_to_speech", "voice_over_generation"],
            limitations=["requires_configured_provider", "text_length_limited"],
        )

    def _initialize(self) -> None:
        self.logger.info("VoiceSynthesisTool ready (router based)")

    def get_available_actions(self) -> List[str]:
        return ["synthesize_voice", "synthesize_voice_aligned", "list_voices"]

    def get_fc_visibility(self) -> Dict[str, Any]:
        return {"expose": True, "allowed_actions": ["synthesize_voice", "synthesize_voice_aligned"]}

    def get_action_schema(self, action: str) -> Dict[str, Any]:
        if action == "synthesize_voice":
            voice_enum, voice_enum_names = self._build_voice_enums()
            return {
                "type": "object",
                "properties": {
                    "scene_number": {"type": "integer", "description": "场景编号（用于归档/去重）"},
                    "text": {"type": "string", "description": "待合成的配音文本"},
                    "voice_id": {
                        "type": "string",
                        "description": "目标音色ID",
                        "enum": voice_enum or None,
                        "enumNames": voice_enum_names or None,
                    },
                    "language": {"type": "string", "description": "语言代码，如 zh-CN"},
                    "speed": {
                        "type": "number",
                        "minimum": 0.5,
                        "maximum": 1.5,
                        "description": "语速比例，1.0 为默认语速",
                    },
                    "pitch": {
                        "type": "number",
                        "minimum": 0.5,
                        "maximum": 1.5,
                        "description": "音调比例，1.0 为默认音调",
                    },
                    "style": {"type": "string", "description": "供应商定义的风格标签"},
                    "sample_rate": {"type": "integer", "description": "采样率（Hz）"},
                    "audio_format": {
                        "type": "string",
                        "enum": ["wav", "mp3", "pcm"],
                        "description": "输出格式",
                    },
                    "reference_id": {"type": "string", "description": "场景/任务参考ID"},
                    "metadata": {
                        "type": "object",
                        "description": "附加元数据，将透传到结果中",
                    },
                },
                "required": ["scene_number", "text", "voice_id"],
            }
        if action == "synthesize_voice_aligned":
            voice_enum, voice_enum_names = self._build_voice_enums()
            return {
                "type": "object",
                "properties": {
                    "scene_number": {"type": "integer", "description": "场景编号（用于归档/去重）"},
                    "text": {"type": "string", "description": "待合成的配音文本"},
                    "voice_id": {
                        "type": "string",
                        "description": "目标音色ID",
                        "enum": voice_enum or None,
                        "enumNames": voice_enum_names or None,
                    },
                    "language": {"type": "string", "description": "语言代码，如 zh-CN"},
                    "speed": {
                        "type": "number",
                        "minimum": 0.5,
                        "maximum": 1.5,
                        "description": "语速比例，1.0 为默认语速",
                    },
                    "pitch": {
                        "type": "number",
                        "minimum": 0.5,
                        "maximum": 1.5,
                        "description": "音调比例，1.0 为默认音调",
                    },
                    "style": {"type": "string", "description": "供应商定义的风格标签"},
                    "sample_rate": {"type": "integer", "description": "采样率（Hz）"},
                    "audio_format": {
                        "type": "string",
                        "enum": ["wav", "mp3", "pcm"],
                        "description": "输出格式",
                    },
                    "target_duration": {"type": "number", "description": "目标时长（秒）"},
                    "reference_id": {"type": "string", "description": "场景/任务参考ID"},
                    "metadata": {
                        "type": "object",
                        "description": "附加元数据，将透传到结果中",
                    },
                },
                "required": ["scene_number", "text", "voice_id", "target_duration"],
            }
        if action == "list_voices":
            return {
                "type": "object",
                "properties": {},
            }
        return {}

    async def _execute_impl(self, tool_input: ToolInput) -> Any:
        action = tool_input.action
        params = tool_input.parameters or {}

        if action == "synthesize_voice":
            request = self._build_request(params)
            try:
                result = await voice_service.synthesize(request)
            except VoiceServiceError as exc:
                raise ToolError(str(exc), self.metadata.name)

            return {
                "audio_path": result.local_path,
                "provider": result.provider,
                "voice_id": result.voice_id,
                "sample_rate": result.sample_rate,
                "audio_format": result.audio_format,
                "duration": result.duration,
                # omit raw_audio bytes to avoid flooding logs; consumers rely on file path
                "metadata": result.metadata,
            }
        if action == "synthesize_voice_aligned":
            request = self._build_request(params)
            target_duration = params.get("target_duration")
            if target_duration is None:
                raise ToolError("target_duration is required", self.metadata.name)
            try:
                target_duration = float(target_duration)
            except (TypeError, ValueError):
                raise ToolError("target_duration must be numeric", self.metadata.name)
            if target_duration <= 0:
                raise ToolError("target_duration must be greater than 0", self.metadata.name)

            try:
                result = await voice_service.synthesize(request)
            except VoiceServiceError as exc:
                raise ToolError(str(exc), self.metadata.name)

            audio_path = result.local_path
            audio_tool = get_tool_registry().get_tool("audio_processor")
            align_input = ToolInput(
                action="ensure_duration",
                parameters={
                    "input_path": audio_path,
                    "target_duration": target_duration,
                    "sample_rate": result.sample_rate,
                    "audio_format": result.audio_format,
                    "fade_out": float(getattr(settings, "AUDIO_FADE_OUT_DURATION", 0.5)),
                },
                context=tool_input.context or {},
            )
            try:
                align_result = await audio_tool.execute(align_input)
            except Exception as exc:
                raise ToolError(f"ensure_duration failed: {exc}", self.metadata.name)

            payload = align_result.result if hasattr(align_result, "result") else None
            if not isinstance(payload, dict):
                raise ToolError("ensure_duration returned empty payload", self.metadata.name)
            aligned_path = payload.get("output_path") or audio_path
            final_duration = payload.get("final_duration") or payload.get("target_duration") or result.duration

            metadata = dict(result.metadata or {})
            metadata.setdefault("alignment", {})
            if isinstance(metadata.get("alignment"), dict):
                metadata["alignment"].update(
                    {
                        "target_duration": target_duration,
                        "adjusted": bool(payload.get("adjusted")),
                    }
                )

            return {
                "audio_path": aligned_path,
                "provider": result.provider,
                "voice_id": result.voice_id,
                "sample_rate": result.sample_rate,
                "audio_format": result.audio_format,
                "duration": final_duration,
                "original_duration": result.duration,
                "metadata": metadata,
            }

        if action == "list_voices":
            catalog = await voice_service.list_voices()
            return {"catalog": catalog}

        raise ToolError(f"Unsupported action: {action}", self.metadata.name)

    def _build_request(self, params: Dict[str, Any]) -> VoiceSynthesisRequest:
        text = str(params.get("text", "")).strip()
        if not text:
            raise ToolError("text payload is required", self.metadata.name)

        voice_id = str(params.get("voice_id") or settings.VOICE_DEFAULT_VOICE_ID or "").strip()
        if not voice_id:
            raise ToolError("voice_id is required", self.metadata.name)
        if not self._is_voice_allowed(voice_id):
            raise ToolError(f"voice_id {voice_id} is not allowed", self.metadata.name)

        scene_number = params.get("scene_number")
        language = str(params.get("language") or "zh-CN")
        speed = float(params.get("speed", 1.0))
        pitch = float(params.get("pitch", 1.0))
        style = params.get("style")
        sample_rate = int(params.get("sample_rate", settings.VOICE_DEFAULT_SAMPLE_RATE))
        audio_format = str(params.get("audio_format", settings.VOICE_DEFAULT_FORMAT))
        reference_id = params.get("reference_id")
        metadata = params.get("metadata") or {}
        if scene_number is not None and isinstance(metadata, dict):
            metadata = dict(metadata)
            metadata.setdefault("scene_number", scene_number)
        if reference_id and isinstance(metadata, dict):
            metadata = dict(metadata)
            metadata.setdefault("reference_id", reference_id)

        return VoiceSynthesisRequest(
            text=text,
            voice_id=voice_id,
            language=language,
            speed=speed,
            pitch=pitch,
            style=style,
            sample_rate=sample_rate,
            audio_format=audio_format,
            reference_id=reference_id,
            metadata=metadata,
        )

    def _build_voice_enums(self) -> tuple[list[str], list[str]]:
        manifest = voice_service.voice_manifest
        voices = manifest if isinstance(manifest, list) else manifest.get("voices") if isinstance(manifest, dict) else []
        enum = []
        names = []
        for item in voices or []:
            voice_id = item.get("id")
            label = item.get("label") or voice_id
            if voice_id:
                enum.append(str(voice_id))
                names.append(str(label))
        return enum, names

    def _is_voice_allowed(self, voice_id: str) -> bool:
        enum, _ = self._build_voice_enums()
        if not enum:
            return True
        if voice_id in enum:
            return True

        default_voice = str(getattr(settings, "VOICE_DEFAULT_VOICE_ID", "") or "").strip()
        if default_voice and voice_id == default_voice:
            # 兼容旧配置：当默认音色未出现在目录中时仍允许使用，防止开箱即用的配置失效。
            self.logger.warning(
                "VOICE_CATALOG_MISS: allowing default voice_id %s not present in catalog",
                voice_id,
            )
            return True

        return False
