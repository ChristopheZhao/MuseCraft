"""
Audio delivery gate evaluator.

Owns runtime probing and normalized gate results for workflow-level video audio delivery.
"""
from __future__ import annotations

import os
import subprocess
from typing import Any, Dict, Optional

from .memory_provider import MemoryServices, build_memory_services
from ..agents.utils.memory_helpers import get_mas_working_memory
from ..agents.adapters.state.agent_outputs import (
    assess_composer_bgm_prereq,
    assess_composer_mix_delivery,
)


class AudioDeliveryGateEvaluator:
    """Evaluate runtime video-audio delivery facts outside the orchestrator."""

    def __init__(self, memory_services: Optional[MemoryServices] = None):
        self._memory_services = memory_services or build_memory_services()

    def evaluate_workflow_video_audio(self, workflow_state_id: str) -> Dict[str, Any]:
        facts = self._collect_runtime_video_audio_facts(workflow_state_id)
        result = "fail"
        recommended_action = "inspect_runtime_gap"
        if bool(facts.get("all_have_audio")):
            result = "pass"
            recommended_action = "continue"
        elif str(facts.get("reason") or "").strip() in {
            "workflow_id_missing",
            "video_outputs_missing",
        } or int(facts.get("unknown") or 0) > 0:
            result = "inconclusive"

        return {
            "contract_version": "v1",
            "gate_name": "workflow_video_audio_delivery",
            "gate_type": "system_evaluator",
            "scope": {
                "scope_type": "workflow",
                "scope_ref": str(workflow_state_id or ""),
            },
            "artifact_refs": [
                {
                    "kind": "shared_fact",
                    "ref": "scene_outputs.video",
                }
            ],
            "facts": facts,
            "result": result,
            "reason_code": str(facts.get("reason") or "unknown"),
            "diagnostics": [],
            "allowed_actions": [],
            "recommended_action": recommended_action,
        }

    def build_observation_signal(
        self,
        workflow_state_id: str,
        *,
        route_payload: Dict[str, Any],
        gate_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        facts = gate_result.get("facts") if isinstance(gate_result, dict) else {}
        if not isinstance(facts, dict):
            facts = {}
        return {
            "source": "audio_delivery_gate",
            "workflow_state_id": str(workflow_state_id or ""),
            "route_id": route_payload.get("route_id"),
            "route_source": route_payload.get("route_source"),
            "policy": route_payload.get("policy"),
            "execution_id": route_payload.get("execution_id"),
            "gate_name": gate_result.get("gate_name") if isinstance(gate_result, dict) else "",
            "gate_result": gate_result.get("result") if isinstance(gate_result, dict) else "",
            "gate_reason_code": gate_result.get("reason_code") if isinstance(gate_result, dict) else "",
            "facts": {
                "records": facts.get("records"),
                "checked": facts.get("checked"),
                "with_audio": facts.get("with_audio"),
                "without_audio": facts.get("without_audio"),
                "unknown": facts.get("unknown"),
                "all_have_audio": facts.get("all_have_audio"),
                "reason": facts.get("reason"),
            },
            "gate_scope": "observation_only",
        }

    def evaluate_global_bgm_mix_delivery(self, workflow_state_id: str) -> Dict[str, Any]:
        prereq = assess_composer_bgm_prereq(
            workflow_state_id,
            service=self._memory_services.short_term,
        ) or {}
        delivery = assess_composer_mix_delivery(
            workflow_state_id,
            mix_type="bgm",
            service=self._memory_services.short_term,
        ) or {}

        eligible = bool(prereq.get("eligible"))
        delivery_state = str(delivery.get("subtask_state") or "").strip().lower()
        delivery_complete = delivery_state == "complete"

        result = "fail"
        recommended_action = "activate_bgm_mix"
        if eligible and delivery_complete:
            result = "pass"
            recommended_action = "continue"
        elif not eligible:
            result = "inconclusive"
            recommended_action = "inspect_prereq"

        reason_code = (
            str(delivery.get("reason") or "").strip()
            or str(prereq.get("reason") or "").strip()
            or "unknown"
        )

        return {
            "contract_version": "v1",
            "gate_name": "workflow_global_bgm_mix_delivery",
            "gate_type": "system_evaluator",
            "scope": {
                "scope_type": "workflow",
                "scope_ref": str(workflow_state_id or ""),
            },
            "artifact_refs": [
                {"kind": "shared_fact", "ref": "project.background_music"},
                {"kind": "shared_fact", "ref": "project.final_video"},
                {"kind": "shared_fact", "ref": "project.final_video_mix"},
            ],
            "facts": {
                "bgm_prereq": prereq,
                "bgm_delivery": delivery,
                "eligible": eligible,
                "delivery_complete": delivery_complete,
            },
            "result": result,
            "reason_code": reason_code,
            "diagnostics": [],
            "allowed_actions": [],
            "recommended_action": recommended_action,
        }

    def _collect_runtime_video_audio_facts(self, workflow_state_id: str) -> Dict[str, Any]:
        """Collect runtime audio facts from scene_outputs.video."""
        wf_id = str(workflow_state_id or "").strip()
        if not wf_id:
            return {
                "total_scenes": 0,
                "records": 0,
                "checked": 0,
                "with_audio": 0,
                "without_audio": 0,
                "unknown": 0,
                "all_have_audio": False,
                "reason": "workflow_id_missing",
            }

        try:
            wm = get_mas_working_memory(wf_id, service=self._memory_services.short_term)
        except Exception:
            wm = None

        overview = wm.get("scene_overview", {}) if wm is not None else {}
        raw_scenes = overview.get("scenes") if isinstance(overview, dict) else []
        total_scenes = len(raw_scenes) if isinstance(raw_scenes, list) else 0

        video_bucket = wm.get("scene_outputs.video", {}) if wm is not None else {}
        if not isinstance(video_bucket, dict):
            video_bucket = {}

        records = 0
        checked = 0
        with_audio = 0
        without_audio = 0
        unknown = 0

        for rec in video_bucket.values():
            if not isinstance(rec, dict):
                continue
            records += 1
            video_path = (
                rec.get("video_path")
                or rec.get("path")
                or rec.get("file_path")
                or ""
            )
            if not isinstance(video_path, str) or not video_path.strip():
                unknown += 1
                continue
            normalized = video_path.strip()
            if normalized.startswith("file://"):
                normalized = normalized[7:]
            if not os.path.exists(normalized):
                unknown += 1
                continue
            has_audio = self._probe_video_audio_stream(normalized)
            if has_audio is None:
                unknown += 1
                continue
            checked += 1
            if has_audio:
                with_audio += 1
            else:
                without_audio += 1

        expected = total_scenes or records
        all_have_audio = bool(
            expected > 0
            and checked >= expected
            and without_audio == 0
            and unknown == 0
        )
        reason = "all_have_audio" if all_have_audio else "audio_missing_or_unknown"
        if records == 0:
            reason = "video_outputs_missing"

        return {
            "total_scenes": total_scenes,
            "records": records,
            "checked": checked,
            "with_audio": with_audio,
            "without_audio": without_audio,
            "unknown": unknown,
            "all_have_audio": all_have_audio,
            "reason": reason,
        }

    @staticmethod
    def _probe_video_audio_stream(video_path: str) -> Optional[bool]:
        """Probe local video audio stream presence via ffprobe."""
        try:
            probe = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    "a:0",
                    "-show_entries",
                    "stream=index",
                    "-of",
                    "csv=p=0",
                    video_path,
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if probe.returncode != 0:
                return None
            return bool((probe.stdout or "").strip())
        except Exception:
            return None
