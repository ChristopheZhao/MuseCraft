"""
Explicit stage runner for post-script media stages.
"""
from __future__ import annotations

import os
from typing import Any, Dict

from sqlalchemy.orm import Session

from ..agents import (
    ImageGeneratorAgent,
    VideoComposerAgent,
    VideoGeneratorAgent,
    QualityCheckerAgent,
)
from ..agents.adapters.memory_views import (
    build_image_generation_context,
    build_video_composer_context,
    build_video_generation_context,
)
from ..agents.utils.llm_policy import LLMPolicyManager
from ..agents.utils.memory_helpers import agent_scope, get_mas_working_memory, mas_scope
from ..models import AgentType, Task
from .memory_provider import MemoryServices, build_memory_services
from .scene_info_reference_service import persist_scene_info_ref
from .video_composer_execution_contract import build_video_composer_execution_contract
from .video_execution_contract import build_video_generation_execution_contract


class PostScriptStageRunner:
    """Runs post-script stages outside orchestrator ownership."""

    _FAILED_COMPLETION_STATES = {"partial", "blocked", "error", "failed", "max_iter_reached"}
    _SUCCESS_COMPLETION_STATES = {"complete", "completed"}
    _QUALITY_SUCCESS_STATUSES = {"approved", "conditional"}
    _QUALITY_FAILED_STATUSES = {"needs_revision", "rejected"}

    def __init__(self, memory_services: MemoryServices | None = None):
        self._memory_services = memory_services or build_memory_services()
        policy_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "llm_policies.yaml")
        self._llm_policy = LLMPolicyManager(policy_file)
        self._image_generator = ImageGeneratorAgent(
            llms=self._llm_policy.build_llms_for_agent("image_generator"),
            memory_services=self._memory_services,
        )
        self._video_generator = VideoGeneratorAgent(
            llms=self._llm_policy.build_llms_for_agent("video_generator"),
            memory_services=self._memory_services,
        )
        self._video_composer = VideoComposerAgent(
            llms=self._llm_policy.build_llms_for_agent("video_composer"),
            memory_services=self._memory_services,
        )
        self._quality_checker = QualityCheckerAgent(
            llms=self._llm_policy.build_llms_for_agent("quality_checker"),
            memory_services=self._memory_services,
        )

    def _ensure_mas_memory(self, workflow_id: str) -> None:
        self._memory_services.short_term.create_or_get(workflow_id, mas_scope(workflow_id))

    def _ensure_agent_memory(self, workflow_id: str, agent_name: str) -> None:
        shared_view = get_mas_working_memory(workflow_id, service=self._memory_services.short_term)
        scope = agent_scope(workflow_id, agent_name)
        try:
            self._memory_services.short_term.reset(scope, workflow_id)
        except Exception:
            pass
        self._memory_services.short_term.create_or_get(
            workflow_id,
            scope,
            owner_agent=agent_name,
            shared_view=shared_view,
        )

    def _build_stage_input(
        self,
        *,
        task: Task,
        session_input_payload: Dict[str, Any],
        workflow_id: str,
    ) -> Dict[str, Any]:
        merged = dict(task.input_parameters or {})
        for key, value in dict(session_input_payload or {}).items():
            if key == "runtime_contracts":
                continue
            merged[key] = value
        merged["workflow_state_id"] = workflow_id
        return merged

    def _build_image_input(
        self,
        *,
        task: Task,
        workflow_id: str,
        session_input_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        stage_input = self._build_stage_input(
            task=task,
            session_input_payload=session_input_payload,
            workflow_id=workflow_id,
        )
        image_ctx = build_image_generation_context(workflow_id, service=self._memory_services.short_term)
        context_payload = dict(image_ctx.get("context") or {})
        scene_info_payload = image_ctx.get("scene_info_payload") or {}
        payload_for_ref = scene_info_payload or context_payload
        ref_path = persist_scene_info_ref(
            workflow_id=workflow_id,
            agent_type=AgentType.IMAGE_GENERATOR,
            payload=payload_for_ref,
        )
        if ref_path:
            context_payload["scene_info_ref"] = ref_path
        elif scene_info_payload:
            context_payload["scene_info_payload"] = scene_info_payload
        if context_payload:
            stage_input["static_context"] = context_payload
        return stage_input

    def _build_video_input(
        self,
        *,
        task: Task,
        workflow_id: str,
        session_input_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        stage_input = self._build_stage_input(
            task=task,
            session_input_payload=session_input_payload,
            workflow_id=workflow_id,
        )
        video_ctx = build_video_generation_context(workflow_id, service=self._memory_services.short_term)
        context_payload = dict(video_ctx.get("context") or {})
        scene_info_payload = video_ctx.get("scene_info_payload") or {}
        ref_path = persist_scene_info_ref(
            workflow_id=workflow_id,
            agent_type=AgentType.VIDEO_GENERATOR,
            payload=scene_info_payload,
        )
        if ref_path:
            context_payload["scene_info_ref"] = ref_path
            key_illustration = dict(context_payload.get("key_illustration") or {})
            key_illustration.setdefault("task_overview", "全局故事与风格/角色概览，仅用于规划")
            key_illustration.setdefault("scene_dependency_graph", "场景依赖关系，表示生成顺序")
            key_illustration["scene_info_ref"] = "场景详细信息的引用地址（包含所有场景的具体规划数据）"
            context_payload["key_illustration"] = key_illustration
        elif scene_info_payload:
            context_payload["scene_info_payload"] = scene_info_payload

        if context_payload:
            stage_input["static_context"] = context_payload
        stage_input["execution_contract"] = build_video_generation_execution_contract(
            workflow_state_id=workflow_id,
        )
        return stage_input

    def _build_compose_input(
        self,
        *,
        task: Task,
        workflow_id: str,
        session_input_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        stage_input = self._build_stage_input(
            task=task,
            session_input_payload=session_input_payload,
            workflow_id=workflow_id,
        )
        composer_ctx = build_video_composer_context(
            workflow_id,
            service=self._memory_services.short_term,
            requests=None,
        )
        if composer_ctx:
            stage_input["static_context"] = composer_ctx
        stage_input["execution_contract"] = build_video_composer_execution_contract(
            workflow_state_id=workflow_id,
            compose_mode="compose",
        )
        return stage_input

    def _build_quality_input(
        self,
        *,
        task: Task,
        workflow_id: str,
        session_input_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        return self._build_stage_input(
            task=task,
            session_input_payload=session_input_payload,
            workflow_id=workflow_id,
        )

    @staticmethod
    def _count_successful_items(output: Dict[str, Any]) -> int:
        for key in ("final_completed_scenes", "generation_results"):
            items = output.get(key)
            if isinstance(items, list):
                return sum(1 for item in items if isinstance(item, dict) and item.get("success", True))
        return 0

    @classmethod
    def _normalize_stage_contract(
        cls,
        *,
        stage_name: str,
        agent_output: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not isinstance(agent_output, dict):
            raise ValueError(f"{stage_name} stage output must be a dict")

        explicit_success = agent_output.get("success")
        subtask_state = str(agent_output.get("subtask_state") or "").strip().lower()
        if not subtask_state:
            subtask_state = ""

        if stage_name == "quality":
            approval_status = str(agent_output.get("approval_status") or "").strip().lower()
            if approval_status in cls._QUALITY_SUCCESS_STATUSES:
                return {"success": True, "subtask_state": subtask_state or "complete", "diagnostics": []}
            if approval_status in cls._QUALITY_FAILED_STATUSES:
                return {
                    "success": False,
                    "subtask_state": subtask_state or "partial",
                    "diagnostics": [
                        {
                            "code": "quality_gate_not_approved",
                            "stage": stage_name,
                            "approval_status": approval_status,
                            "message": f"{stage_name} stage did not pass quality review (approval_status={approval_status})",
                        }
                    ],
                }

        if isinstance(explicit_success, bool):
            diagnostics = []
            if not explicit_success:
                diagnostics = [
                    {
                        "code": "stage_output_unsuccessful",
                        "stage": stage_name,
                        "subtask_state": subtask_state or "partial",
                        "message": (
                            str(agent_output.get("completed_reason") or "")
                            or str(agent_output.get("loop_end_reason") or "")
                            or str(agent_output.get("error") or "")
                            or f"{stage_name} stage returned success=false"
                        ),
                    }
                ]
            return {
                "success": explicit_success,
                "subtask_state": subtask_state or ("complete" if explicit_success else "partial"),
                "diagnostics": diagnostics,
            }

        report = agent_output.get("orchestration_report")
        if isinstance(report, dict):
            report_status = str(report.get("status") or "").strip().lower()
            reflection = report.get("reflection") if isinstance(report.get("reflection"), dict) else {}
            completion_state = str(reflection.get("completion_state") or "").strip().lower()
            if completion_state in cls._FAILED_COMPLETION_STATES or report_status == "partial":
                return {
                    "success": False,
                    "subtask_state": completion_state or subtask_state or "partial",
                    "diagnostics": [
                        {
                            "code": "stage_output_partial",
                            "stage": stage_name,
                            "completion_state": completion_state or subtask_state or "partial",
                            "message": f"{stage_name} stage reported partial completion",
                        }
                    ],
                }
            if completion_state in cls._SUCCESS_COMPLETION_STATES or report_status == "completed":
                return {
                    "success": True,
                    "subtask_state": completion_state or subtask_state or "complete",
                    "diagnostics": [],
                }

        raise ValueError(f"{stage_name} stage output missing explicit success contract")

    async def run_storyboard(
        self,
        *,
        task: Task,
        workflow_id: str,
        session_input_payload: Dict[str, Any],
        db: Session,
    ) -> Dict[str, Any]:
        self._ensure_mas_memory(workflow_id)
        self._ensure_agent_memory(workflow_id, self._image_generator.agent_name)
        image_input = self._build_image_input(
            task=task,
            workflow_id=workflow_id,
            session_input_payload=session_input_payload,
        )
        image_output = await self._image_generator.execute(
            task=task,
            input_data=image_input,
            db=db,
            execution_order=3,
        )
        contract = self._normalize_stage_contract(
            stage_name="storyboard",
            agent_output=image_output,
        )
        return {
            "success": contract["success"],
            "subtask_state": contract["subtask_state"],
            "diagnostics": contract["diagnostics"],
            "image_output": image_output,
            "artifacts": [{"type": "shared_fact", "ref": "scene_outputs.image"}],
            "metrics": {
                "images_generated": self._count_successful_items(image_output or {}),
            },
        }

    async def run_scene_video(
        self,
        *,
        task: Task,
        workflow_id: str,
        session_input_payload: Dict[str, Any],
        db: Session,
    ) -> Dict[str, Any]:
        self._ensure_mas_memory(workflow_id)
        self._ensure_agent_memory(workflow_id, self._video_generator.agent_name)
        video_input = self._build_video_input(
            task=task,
            workflow_id=workflow_id,
            session_input_payload=session_input_payload,
        )
        video_output = await self._video_generator.execute(
            task=task,
            input_data=video_input,
            db=db,
            execution_order=4,
        )
        contract = self._normalize_stage_contract(
            stage_name="scene_video",
            agent_output=video_output,
        )
        return {
            "success": contract["success"],
            "subtask_state": contract["subtask_state"],
            "diagnostics": contract["diagnostics"],
            "video_output": video_output,
            "artifacts": [{"type": "shared_fact", "ref": "scene_outputs.video"}],
            "metrics": {
                "videos_generated": self._count_successful_items(video_output or {}),
            },
        }

    async def run_compose(
        self,
        *,
        task: Task,
        workflow_id: str,
        session_input_payload: Dict[str, Any],
        db: Session,
    ) -> Dict[str, Any]:
        self._ensure_mas_memory(workflow_id)
        self._ensure_agent_memory(workflow_id, self._video_composer.agent_name)
        compose_input = self._build_compose_input(
            task=task,
            workflow_id=workflow_id,
            session_input_payload=session_input_payload,
        )
        compose_output = await self._video_composer.execute(
            task=task,
            input_data=compose_input,
            db=db,
            execution_order=5,
        )
        contract = self._normalize_stage_contract(
            stage_name="compose",
            agent_output=compose_output,
        )
        mix_receipt = compose_output.get("mix_receipt") if isinstance(compose_output, dict) else {}
        mix_type = mix_receipt.get("mix_type") if isinstance(mix_receipt, dict) else None
        return {
            "success": contract["success"],
            "subtask_state": contract["subtask_state"],
            "diagnostics": contract["diagnostics"],
            "compose_output": compose_output,
            "artifacts": [
                {"type": "shared_fact", "ref": "project.final_video"},
                {"type": "shared_fact", "ref": "project.final_video_mix"},
            ],
            "metrics": {
                "final_video_url": compose_output.get("final_video_url"),
                "mix_type": mix_type,
            },
        }

    async def run_quality(
        self,
        *,
        task: Task,
        workflow_id: str,
        session_input_payload: Dict[str, Any],
        db: Session,
    ) -> Dict[str, Any]:
        self._ensure_mas_memory(workflow_id)
        self._ensure_agent_memory(workflow_id, self._quality_checker.agent_name)
        quality_input = self._build_quality_input(
            task=task,
            workflow_id=workflow_id,
            session_input_payload=session_input_payload,
        )
        quality_output = await self._quality_checker.execute(
            task=task,
            input_data=quality_input,
            db=db,
            execution_order=6,
        )
        contract = self._normalize_stage_contract(
            stage_name="quality",
            agent_output=quality_output,
        )
        return {
            "success": contract["success"],
            "subtask_state": contract["subtask_state"],
            "diagnostics": contract["diagnostics"],
            "quality_output": quality_output,
            "artifacts": [{"type": "shared_fact", "ref": "project.final_video"}],
            "metrics": {
                "quality_score": quality_output.get("quality_score"),
                "approval_status": quality_output.get("approval_status"),
            },
        }
