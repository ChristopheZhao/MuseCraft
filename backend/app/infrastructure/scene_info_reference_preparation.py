"""File-backed scene-reference preparation adapter."""

from __future__ import annotations

from typing import Any, Dict

from ..agents.adapters.memory_views import (
    build_image_generation_context,
    build_video_generation_context,
)
from ..domain import AgentType
from ..services.context_assembler import ContextContractAssembler
from ..services.context_reference_ports import SceneInfoReferencePreparationError
from ..services.memory_provider import MemoryServices
from ..services.scene_info_reference_service import (
    SceneInfoReferencePersistenceError,
    persist_scene_info_ref,
)


class FileSceneInfoReferencePreparationAdapter:
    def __init__(self, memory_services: MemoryServices) -> None:
        self._memory_services = memory_services
        self._assembler = ContextContractAssembler(memory_services)

    def prepare(
        self,
        *,
        workflow_state_id: str,
        agent_type: AgentType,
        runtime_input_payload: Dict[str, Any],
    ) -> str:
        if agent_type not in {AgentType.IMAGE_GENERATOR, AgentType.VIDEO_GENERATOR}:
            raise SceneInfoReferencePreparationError(
                reason_code="scene_info_reference_not_required",
                message=f"Scene info reference is not defined for {agent_type.value}",
            )
        resolution = self._assembler.resolve_published_stage_payload(
            workflow_state_id=workflow_state_id,
            node_key="script",
            prefer_approved=True,
            required=True,
            runtime_input_payload=runtime_input_payload,
        )
        published_payload = resolution.get("payload")
        if agent_type is AgentType.IMAGE_GENERATOR:
            context = build_image_generation_context(
                workflow_state_id,
                service=self._memory_services.short_term,
                published_payload=published_payload,
            )
        else:
            context = build_video_generation_context(
                workflow_state_id,
                service=self._memory_services.short_term,
                published_payload=published_payload,
            )
        payload = context.get("scene_info_payload") if isinstance(context, dict) else None
        if not isinstance(payload, dict) or not payload:
            raise SceneInfoReferencePreparationError(
                reason_code="scene_info_payload_missing",
                message=(
                    "Scene info payload is missing before reference preparation: "
                    f"workflow_id={workflow_state_id} agent_type={agent_type.value}"
                ),
            )
        try:
            ref = persist_scene_info_ref(
                workflow_id=workflow_state_id,
                agent_type=agent_type,
                payload=payload,
            )
        except SceneInfoReferencePersistenceError as exc:
            raise SceneInfoReferencePreparationError(
                reason_code="scene_info_reference_persistence_failed",
                message=str(exc),
            ) from exc
        if not str(ref or "").strip():
            raise SceneInfoReferencePreparationError(
                reason_code="scene_info_reference_empty",
                message="Scene info reference adapter returned an empty reference",
            )
        return str(ref)
