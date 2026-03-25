"""
Formal Context/Contract Assembler host for active single-episode harness paths.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from ..agents.adapters.memory_views import (
    build_script_stage_views,
    build_image_generation_context,
    build_media_agent_context,
    build_video_composer_context,
    build_video_generation_context,
    build_voice_synthesis_context,
)
from ..agents.base import AgentError
from ..agents.utils.memory_helpers import read_shared_fact
from ..core.config import settings
from ..models import AgentType
from .memory_provider import MemoryServices
from .published_deliverable_adapter import (
    build_script_deliverable_payload,
    project_payload_deliverables_to_shared_wm,
)
from .published_deliverable_service import (
    PublishedDeliverableService,
    build_deliverable_ref,
    get_published_deliverable_ref,
    get_published_deliverables,
    load_published_payload,
)
from .scene_info_reference_service import persist_scene_info_ref
from .script_review_contract import build_script_preview_text
from .video_composer_execution_contract import (
    build_video_composer_execution_contract,
)
from .video_execution_contract import build_video_generation_execution_contract


class ContextContractAssembler:
    """Builds stage-boundary inputs and leaf-facing execution contracts."""

    def __init__(self, memory_services: MemoryServices):
        self._memory_services = memory_services

    def _persist_scene_info_ref(
        self,
        *,
        workflow_state_id: str,
        agent_type: AgentType,
        payload: Dict[str, Any],
    ) -> Optional[str]:
        ref = persist_scene_info_ref(
            workflow_id=workflow_state_id,
            agent_type=agent_type,
            payload=payload,
        )
        return ref or None

    def _build_scene_info_context(
        self,
        *,
        workflow_state_id: str,
        agent_type: AgentType,
        context_payload: Dict[str, Any],
        scene_info_payload: Dict[str, Any],
        payload_for_ref: Dict[str, Any],
        key_illustration_defaults: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        ref_path = self._persist_scene_info_ref(
            workflow_state_id=workflow_state_id,
            agent_type=agent_type,
            payload=payload_for_ref,
        )
        if ref_path:
            context = dict(context_payload or {})
            context["scene_info_ref"] = ref_path
            if isinstance(key_illustration_defaults, dict) and key_illustration_defaults:
                key_illustration = dict(context.get("key_illustration") or {})
                for key, value in key_illustration_defaults.items():
                    key_illustration.setdefault(key, value)
                context["key_illustration"] = key_illustration
            return context

        fallback_context = dict(context_payload or {})
        if scene_info_payload:
            fallback_context["scene_info_payload"] = scene_info_payload
        return fallback_context

    @staticmethod
    def _compact_resolution_receipt(receipt: Dict[str, Any]) -> Dict[str, Any]:
        compact = {
            "node_key": receipt.get("node_key"),
            "prefer_approved": bool(receipt.get("prefer_approved")),
            "required": bool(receipt.get("required")),
            "status": receipt.get("status"),
        }
        source = str(receipt.get("source") or "").strip()
        if source:
            compact["source"] = source
        fallback_reason = str(receipt.get("fallback_reason") or "").strip()
        if fallback_reason:
            compact["fallback_reason"] = fallback_reason
        ref = receipt.get("ref")
        if isinstance(ref, dict):
            compact["deliverable_id"] = ref.get("deliverable_id")
            compact["payload_ref"] = ref.get("payload_ref")
            compact["approved"] = bool(ref.get("is_approved"))
        return compact

    def _resolve_payload_from_ref(
        self,
        *,
        workflow_state_id: str,
        node_key: str,
        prefer_approved: bool,
        required: bool,
        ref: Dict[str, Any],
        source: str,
        fallback_reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        receipt: Dict[str, Any] = {
            "workflow_state_id": workflow_state_id,
            "node_key": node_key,
            "prefer_approved": bool(prefer_approved),
            "required": bool(required),
            "status": "ref_resolved",
            "source": source,
            "ref": dict(ref),
        }
        if fallback_reason:
            receipt["fallback_reason"] = fallback_reason

        payload_ref = str(ref.get("payload_ref") or "").strip()
        if not payload_ref:
            receipt["status"] = "missing_payload_ref"
            if required:
                raise AgentError(
                    "Published deliverable ref missing payload_ref: "
                    f"workflow_id={workflow_state_id} node_key={node_key} "
                    f"source={source} status=missing_payload_ref"
                )
            return receipt

        payload = load_published_payload(payload_ref)
        if not isinstance(payload, dict):
            receipt["status"] = "payload_unavailable"
            if required:
                raise AgentError(
                    "Published deliverable payload unavailable: "
                    f"workflow_id={workflow_state_id} node_key={node_key} "
                    f"payload_ref={payload_ref} source={source} status=payload_unavailable"
                )
            return receipt

        receipt["status"] = "resolved"
        receipt["payload"] = payload
        return receipt

    def resolve_published_stage_payload(
        self,
        *,
        workflow_state_id: str,
        node_key: str,
        prefer_approved: bool = True,
        required: bool = False,
        runtime_input_payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        runtime_ref = get_published_deliverable_ref(
            runtime_input_payload,
            node_key=node_key,
        )
        if isinstance(runtime_ref, dict):
            return self._resolve_payload_from_ref(
                workflow_state_id=workflow_state_id,
                node_key=node_key,
                prefer_approved=prefer_approved,
                required=required,
                ref=runtime_ref,
                source="runtime_input",
            )

        receipt: Dict[str, Any] = {
            "workflow_state_id": workflow_state_id,
            "node_key": node_key,
            "prefer_approved": bool(prefer_approved),
            "required": bool(required),
            "status": "missing_runtime_input_ref",
            "source": "runtime_input",
        }
        if required:
            raise AgentError(
                "Missing runtime-input published deliverable ref: "
                f"workflow_id={workflow_state_id} node_key={node_key} "
                f"prefer_approved={prefer_approved} status=missing_runtime_input_ref"
            )
        return receipt

    def assemble_agent_context(
        self,
        *,
        agent_type: AgentType,
        workflow_state_id: str,
        workflow_data: Optional[Dict[str, Any]] = None,
        runtime_input_payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        workflow_payload = dict(workflow_data or {})
        runtime_payload = dict(runtime_input_payload or {})
        assembled: Dict[str, Any] = {}
        static_context: Dict[str, Any] = {}
        assembler_diagnostics: Dict[str, Any] = {}
        script_stage_resolution: Optional[Dict[str, Any]] = None

        if agent_type in {
            AgentType.AUDIO_GENERATOR,
            AgentType.IMAGE_GENERATOR,
            AgentType.VIDEO_GENERATOR,
            AgentType.VOICE_SYNTHESIZER,
        }:
            script_stage_resolution = self.resolve_published_stage_payload(
                workflow_state_id=workflow_state_id,
                node_key="script",
                prefer_approved=True,
                required=agent_type in {
                    AgentType.AUDIO_GENERATOR,
                    AgentType.IMAGE_GENERATOR,
                    AgentType.VIDEO_GENERATOR,
                    AgentType.VOICE_SYNTHESIZER,
                },
                runtime_input_payload=runtime_payload,
            )
            assembler_diagnostics["script_stage_payload"] = self._compact_resolution_receipt(
                script_stage_resolution
            )

        if agent_type == AgentType.AUDIO_GENERATOR:
            audio_req = workflow_payload.get("audio_requirements")
            sfx_override = None
            if isinstance(audio_req, dict) and audio_req.get("sfx_required") is not None:
                sfx_override = bool(audio_req.get("sfx_required"))
            elif workflow_payload.get("sfx_required") is not None:
                sfx_override = bool(workflow_payload.get("sfx_required"))

            context_bundle = build_media_agent_context(
                workflow_state_id,
                service=self._memory_services.short_term,
                include_scripts=True,
                include_roles=False,
                include_audio_requirements=True,
                sfx_required_default=getattr(settings, "AUDIO_SFX_REQUIRED_DEFAULT", False),
                sfx_required_override=sfx_override,
                script_stage_views=build_script_stage_views(
                    workflow_state_id,
                    service=self._memory_services.short_term,
                    published_payload=(script_stage_resolution or {}).get("payload"),
                ),
            )
            for key, value in context_bundle.items():
                if value:
                    assembled[key] = value
                    static_context[key] = value

            if isinstance(audio_req, dict) and audio_req:
                merged_req = dict(static_context.get("audio_requirements") or {})
                merged_req.update(audio_req)
                static_context["audio_requirements"] = merged_req
                assembled["audio_requirements"] = merged_req

        elif agent_type == AgentType.VIDEO_COMPOSER:
            composer_ctx = build_video_composer_context(
                workflow_state_id,
                service=self._memory_services.short_term,
                requests=None,
            )
            if composer_ctx:
                static_context.update(composer_ctx)

        elif agent_type == AgentType.IMAGE_GENERATOR:
            image_ctx = build_image_generation_context(
                workflow_state_id,
                service=self._memory_services.short_term,
                published_payload=(script_stage_resolution or {}).get("payload"),
            )
            if isinstance(image_ctx, dict) and image_ctx.get("context"):
                context_payload = dict(image_ctx.get("context") or {})
                scene_info_payload = image_ctx.get("scene_info_payload") or {}
                static_context.update(
                    self._build_scene_info_context(
                        workflow_state_id=workflow_state_id,
                        agent_type=agent_type,
                        context_payload=context_payload,
                        scene_info_payload=scene_info_payload,
                        payload_for_ref=scene_info_payload or context_payload,
                    )
                )

        elif agent_type == AgentType.VIDEO_GENERATOR:
            video_ctx = build_video_generation_context(
                workflow_state_id,
                service=self._memory_services.short_term,
                published_payload=(script_stage_resolution or {}).get("payload"),
            )
            if isinstance(video_ctx, dict) and video_ctx.get("context"):
                context_payload = dict(video_ctx.get("context") or {})
                scene_info_payload = video_ctx.get("scene_info_payload") or {}
                static_context.update(
                    self._build_scene_info_context(
                        workflow_state_id=workflow_state_id,
                        agent_type=agent_type,
                        context_payload=context_payload,
                        scene_info_payload=scene_info_payload,
                        payload_for_ref=scene_info_payload,
                        key_illustration_defaults={
                            "task_overview": "全局故事与风格/角色概览，仅用于规划",
                            "scene_dependency_graph": "场景依赖关系，表示生成顺序",
                            "scene_info_ref": "场景详细信息的引用地址（包含所有场景的具体规划数据）",
                        },
                    )
                )

        elif agent_type == AgentType.VOICE_SYNTHESIZER:
            voice_ctx = build_voice_synthesis_context(
                workflow_state_id,
                service=self._memory_services.short_term,
                script_stage_views=build_script_stage_views(
                    workflow_state_id,
                    service=self._memory_services.short_term,
                    published_payload=(script_stage_resolution or {}).get("payload"),
                ),
            )
            if isinstance(voice_ctx, dict) and voice_ctx.get("context"):
                static_context.update(voice_ctx.get("context") or {})

        if static_context:
            assembled["static_context"] = static_context
        if assembler_diagnostics:
            assembled["_assembler_diagnostics"] = assembler_diagnostics
        return assembled

    def resolve_runtime_hints(
        self,
        *,
        workflow_state_id: str,
        agent_type: AgentType,
    ) -> Dict[str, Any]:
        task_specs = read_shared_fact(
            workflow_state_id,
            "workflow.task_specs",
            {},
            service=self._memory_services.short_term,
        ) or {}
        if not isinstance(task_specs, dict):
            return {}
        spec = task_specs.get(agent_type.value)
        if not isinstance(spec, dict):
            return {}
        params = spec.get("runtime_hints")
        return dict(params) if isinstance(params, dict) else {}

    def build_execution_contract(
        self,
        *,
        agent_type: AgentType,
        workflow_state_id: str,
        runtime_hints: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if agent_type == AgentType.VIDEO_GENERATOR:
            generate_audio = None
            if isinstance(runtime_hints, dict):
                candidate = runtime_hints.get("generate_audio")
                if isinstance(candidate, bool):
                    generate_audio = bool(candidate)
            return build_video_generation_execution_contract(
                workflow_state_id=workflow_state_id,
                generate_audio=generate_audio,
            )

        if agent_type == AgentType.VIDEO_COMPOSER:
            try:
                if isinstance(runtime_hints, dict):
                    legacy_keys = [
                        key for key in ("add_bgm", "add_voiceover", "compose_requested")
                        if runtime_hints.get(key) is not None
                    ]
                    if legacy_keys:
                        raise AgentError(
                            "Legacy video_composer runtime overrides are no longer supported; "
                            f"use compose_mode instead (got: {', '.join(legacy_keys)})"
                        )
                compose_mode = "compose"
                if isinstance(runtime_hints, dict) and runtime_hints.get("compose_mode") is not None:
                    compose_mode = str(runtime_hints.get("compose_mode"))
                return build_video_composer_execution_contract(
                    workflow_state_id=workflow_state_id,
                    compose_mode=compose_mode,
                )
            except ValueError as exc:
                raise AgentError(f"Invalid video_composer execution boundary: {exc}") from exc

        return {}

    def apply_execution_boundary(
        self,
        *,
        agent_type: AgentType,
        agent_input: Dict[str, Any],
        execution_contract: Dict[str, Any],
    ) -> Dict[str, Any]:
        if agent_type != AgentType.VIDEO_COMPOSER or not isinstance(agent_input, dict):
            return agent_input

        normalized = dict(agent_input)
        normalized.pop("add_bgm", None)
        normalized.pop("add_voiceover", None)
        normalized.pop("compose_requested", None)
        static_context = normalized.get("static_context")
        if isinstance(static_context, dict) and "requests" in static_context:
            static_context = dict(static_context)
            static_context.pop("requests", None)
            normalized["static_context"] = static_context
        return normalized

    def publish_script_review_boundary_sync(
        self,
        *,
        db: Session,
        session: Any,
        workflow_state_id: str,
        attempt_id: int,
        script_output: Dict[str, Any],
    ) -> Dict[str, Any]:
        scene_scripts = read_shared_fact(
            workflow_state_id,
            "project.scene_scripts",
            {},
            service=self._memory_services.short_term,
        ) or {}
        script_preview_text = build_script_preview_text(
            scene_scripts,
            script_output=script_output,
        )
        deliverable = PublishedDeliverableService.publish_script_deliverable_sync(
            db,
            session=session,
            workflow_id=workflow_state_id,
            attempt_id=attempt_id,
            payload=build_script_deliverable_payload(
                workflow_state_id,
                service=self._memory_services.short_term,
            ),
            summary={
                "script_preview_text": script_preview_text,
                "scenes_generated": script_output.get("scenes_generated"),
                "total_scenes": script_output.get("total_scenes"),
            },
        )
        artifact_ref = build_deliverable_ref(deliverable)
        return {
            "artifact_ref": artifact_ref,
            "artifact_refs": [artifact_ref],
            "script_preview_text": script_preview_text,
        }

    def project_runtime_payload_deliverables(
        self,
        *,
        workflow_state_id: str,
        runtime_input_payload: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Compatibility-only bridge for explicitly projecting runtime carrier refs to shared WM."""
        payload = dict(runtime_input_payload or {})
        deliverables = get_published_deliverables(payload)
        if not deliverables:
            return {
                "projected_count": 0,
                "projected_nodes": [],
            }
        project_payload_deliverables_to_shared_wm(
            workflow_state_id,
            payload,
            service=self._memory_services.short_term,
        )
        return {
            "projected_count": len(deliverables),
            "projected_nodes": sorted(deliverables.keys()),
        }


context_assembler: Optional[ContextContractAssembler] = None

__all__ = ["ContextContractAssembler", "context_assembler"]
