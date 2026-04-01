from __future__ import annotations

import json
from pathlib import Path

from app.agents.utils.plan_context import build_plan_context


def _write_scene_info_ref(tmp_path: Path) -> str:
    ref_path = tmp_path / "scene_info.json"
    ref_path.write_text(
        json.dumps(
            {
                "task_type": "batch_image_generation",
                "workflow_state_id": "wf-progress-read-model",
                "scenes_to_generate": [
                    {"scene_number": 1},
                    {"scene_number": 2},
                    {"scene_number": 3},
                ],
                "scenes_to_skip": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return str(ref_path)


def test_build_plan_context_adds_progress_read_model_from_scene_info_ref_and_obs_receipts(tmp_path):
    scene_info_ref = _write_scene_info_ref(tmp_path)

    ctx = build_plan_context(
        input_data={
            "static_context": {
                "scene_info_ref": scene_info_ref,
                "scenes_to_generate": [{"scene_number": 1}, {"scene_number": 2}, {"scene_number": 3}],
            }
        },
        iteration_context={
            "obs_records": [
                {
                    "iteration": 0,
                    "action_result": {
                        "act_log": [
                            {"scene_number": 1, "success": True},
                            {"scene_number": 2, "success": False, "error_type": "provider_error"},
                        ]
                    },
                }
            ]
        },
    )

    progress = ctx["progress_read_model"]
    assert progress["planned_scene_numbers"] == [1, 2, 3]
    assert progress["successful_scene_numbers"] == [1]
    assert progress["remaining_scene_numbers"] == [2, 3]
    assert progress["recent_execution_receipts"] == [
        {"iteration": 0, "scene_number": 1, "status": "succeeded"},
        {
            "iteration": 0,
            "scene_number": 2,
            "status": "failed",
            "error_type": "provider_error",
        },
    ]


def test_build_plan_context_falls_back_to_executed_calls_when_act_log_is_absent(tmp_path):
    scene_info_ref = _write_scene_info_ref(tmp_path)

    ctx = build_plan_context(
        input_data={"static_context": {"scene_info_ref": scene_info_ref}},
        iteration_context={
            "obs_records": [
                {
                    "iteration": 1,
                    "action_result": {
                        "executed_calls": [
                            {
                                "tool": "image_prompt_composer.generate",
                                "success": True,
                                "args": {"scene_number": 3},
                            }
                        ]
                    },
                }
            ]
        },
    )

    progress = ctx["progress_read_model"]
    assert progress["planned_scene_numbers"] == [1, 2, 3]
    assert progress["successful_scene_numbers"] == [3]
    assert progress["remaining_scene_numbers"] == [1, 2]
    assert progress["recent_execution_receipts"] == [
        {"iteration": 1, "scene_number": 3, "status": "succeeded"}
    ]


def test_build_plan_context_keeps_explicit_diagnostics_when_progress_projection_cannot_be_built(tmp_path):
    missing_ref = str(tmp_path / "missing-scene-info.json")

    ctx = build_plan_context(
        input_data={"static_context": {"scene_info_ref": missing_ref}},
        iteration_context={"obs_records": []},
    )

    assert "progress_read_model" not in ctx
    diagnostics = ctx["plan_context_diagnostics"]["progress_read_model"]
    assert diagnostics["status"] == "degraded"
    assert diagnostics["reason"] == "scene_info_ref_load_failed"
    assert diagnostics["detail"] == "SceneInfoReferenceResolutionError"
