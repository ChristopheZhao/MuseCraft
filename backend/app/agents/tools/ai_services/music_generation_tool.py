"""Supplier-neutral music generation tool with configured provider adapters."""

from __future__ import annotations

from typing import Any, Dict, List

from ....core.config import settings
from ..base_tool import AsyncTool, ToolError, ToolInput, ToolMetadata, ToolType


class MusicGenerationTool(AsyncTool):
    @classmethod
    def get_metadata(cls) -> ToolMetadata:
        return ToolMetadata(
            name="music_generation",
            version="1.0.0",
            description="Generate background music through the configured music provider",
            tool_type=ToolType.AI_SERVICE,
            author="system",
            tags=["music", "audio", "background-music", "soundtrack"],
            capabilities=[
                "background_music_generation",
                "instrumental_music",
                "mood_based_generation",
                "style_control",
            ],
            limitations=[
                "provider_configuration_required",
                "duration_is_a_generation_hint",
                "post_processing_required_for_exact_duration",
            ],
        )

    def __init__(
        self,
        metadata: ToolMetadata | None = None,
        config: Dict[str, Any] | None = None,
    ) -> None:
        super().__init__(metadata or self.get_metadata(), config)

    def _initialize(self) -> None:
        provider_name = (
            str(
                self.config.get("provider")
                or getattr(settings, "MUSIC_GENERATION_PROVIDER", "suno")
            )
            .strip()
            .lower()
        )
        self._provider_name = provider_name
        self._provider = self._build_provider(provider_name)
        self._functional = bool(getattr(self._provider, "_functional", True))

    def _build_provider(self, provider_name: str):
        if provider_name == "suno":
            from .suno_client import SunoClientTool

            provider_config = dict(self.config.get("provider_config") or {})
            return SunoClientTool(config=provider_config)
        raise ToolError(
            f"Unsupported music generation provider: {provider_name}",
            self.metadata.name,
            error_code="unsupported_music_provider",
        )

    def get_available_actions(self) -> List[str]:
        return ["generate_background_music"]

    def get_fc_visibility(self) -> Dict[str, Any]:
        return {"expose": True, "allowed_actions": ["generate_background_music"]}

    def get_action_schema(self, action: str) -> Dict[str, Any]:
        if action != "generate_background_music":
            return {}
        return {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "Musical qualities, arrangement, and intended video role",
                },
                "mood": {"type": "string", "description": "Desired musical mood"},
                "style": {"type": "string", "description": "Desired genre or style"},
                "duration": {
                    "type": "integer",
                    "description": "Target duration hint in seconds",
                },
                "instrumental": {
                    "type": "boolean",
                    "description": "Whether vocals should be omitted",
                    "default": True,
                },
                "title": {"type": "string", "description": "Optional working title"},
            },
            "required": ["description"],
        }

    async def _execute_impl(self, tool_input: ToolInput) -> Any:
        if not self._functional:
            raise ToolError(
                "Configured music generation provider is unavailable",
                self.metadata.name,
                error_code="music_provider_unavailable",
            )
        provider_output = await self._provider.execute(tool_input)
        if not provider_output.success:
            raise ToolError(
                provider_output.error or "Configured music provider failed",
                self.metadata.name,
                error_code="music_provider_execution_failed",
                details={"provider": self._provider_name},
            )
        result = provider_output.result
        if isinstance(result, dict):
            normalized = dict(result)
            normalized.setdefault("provider", self._provider_name)
            return normalized
        return result
