from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.agents.utils.memory_helpers import ensure_mas_working_memory
from app.agents.utils.plan_context import build_plan_context
from app.services.memory_provider import build_memory_services


@pytest.fixture(autouse=True)
def _use_in_memory_long_term_store(monkeypatch):
    monkeypatch.setenv("MEMORY_BACKEND", "dict")


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


def test_build_plan_context_adds_progress_read_model_from_delivery_receipts(tmp_path):
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
                        "delivery_receipts": [
                            {
                                "scene_number": 1,
                                "status": "accepted",
                                "delivery_surface": "scene_outputs.image",
                                "delivery_ref": "scene_outputs.image.1",
                            },
                            {
                                "scene_number": 2,
                                "status": "failed",
                                "delivery_surface": "scene_outputs.image",
                                "delivery_ref": "scene_outputs.image.2",
                            },
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
    assert progress["recent_delivery_receipts"] == [
        {
            "iteration": 0,
            "scene_number": 1,
            "status": "accepted",
            "delivery_surface": "scene_outputs.image",
            "delivery_ref": "scene_outputs.image.1",
        }
    ]
    assert progress["derived_from"] == ["obs_records.delivery_receipts"]
    assert progress["last_receipt_watermark"] == "scene_outputs.image.1"
    assert progress["max_staleness_seconds"] > 0


def test_build_plan_context_prefers_authoritative_scene_outputs_over_observation_receipts(tmp_path):
    scene_info_ref = _write_scene_info_ref(tmp_path)
    services = build_memory_services()
    shared = ensure_mas_working_memory("wf-progress-read-model", service=services.short_term)
    shared.put(
        "scene_outputs.image",
        {
            2: {"scene_number": 2, "image_path": "/tmp/scene-2.png"},
            3: {"scene_number": 3, "image_url": "https://example.com/scene-3.png"},
        },
    )

    ctx = build_plan_context(
        input_data={
            "workflow_state_id": "wf-progress-read-model",
            "static_context": {"scene_info_ref": scene_info_ref},
        },
        iteration_context={
            "obs_records": [
                {
                    "iteration": 1,
                    "action_result": {
                        "delivery_receipts": [
                            {
                                "scene_number": 1,
                                "status": "accepted",
                                "delivery_surface": "scene_outputs.image",
                                "delivery_ref": "scene_outputs.image.1",
                            }
                        ]
                    },
                }
            ]
        },
        workflow_state_id="wf-progress-read-model",
        service=services.short_term,
        progress_kind="image",
    )

    progress = ctx["progress_read_model"]
    assert progress["planned_scene_numbers"] == [1, 2, 3]
    assert progress["successful_scene_numbers"] == [2, 3]
    assert progress["remaining_scene_numbers"] == [1]
    assert progress["recent_delivery_receipts"] == [
        {
            "scene_number": 2,
            "status": "accepted",
            "delivery_surface": "scene_outputs.image",
            "delivery_ref": "scene_outputs.image.2",
        },
        {
            "scene_number": 3,
            "status": "accepted",
            "delivery_surface": "scene_outputs.image",
            "delivery_ref": "scene_outputs.image.3",
        },
    ]
    assert progress["derived_from"] == ["scene_outputs.image"]
    assert progress["last_receipt_watermark"] == "scene_outputs.image.3"


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
