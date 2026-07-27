import pytest

from app.agents.utils.artifacts import (
    ensure_persisted_videos,
    evaluate_scene_output_acceptance,
    issue_scene_output_acceptance_receipts,
    persist_scene_outputs,
)


class _SharedMemory(dict):
    def get(self, key, default=None):
        return super().get(key, default)

    def put(self, key, value):
        self[key] = value


@pytest.mark.asyncio
async def test_ensure_persisted_videos_reports_upload_failure():
    async def _failing_uploader(url, scene_number):
        raise RuntimeError("storage unavailable")

    results = await ensure_persisted_videos(
        [
            {
                "success": True,
                "scene_number": 1,
                "video_url": "https://example.com/scene-1.mp4",
                "metadata": {"provider": "stub"},
            }
        ],
        _failing_uploader,
    )

    assert results[0]["video_url"] == "https://example.com/scene-1.mp4"
    assert results[0].get("video_path", "") == ""
    assert results[0]["storage"]["status"] == "failed"
    assert results[0]["storage"]["fallback_reason"] == "artifact_upload_failed"
    assert results[0]["metadata"]["storage"]["fallback_reason"] == "artifact_upload_failed"
    assert "artifact_upload_failed" in results[0]["fallback_reasons"]


def test_video_delivery_receipt_rejects_storage_failure_diagnostic():
    _artifacts, receipts = issue_scene_output_acceptance_receipts(
        kind="video",
        artifacts=[
            {
                "success": True,
                "scene_number": 1,
                "video_url": "https://example.com/scene-1.mp4",
                "video_path": "/tmp/stale-scene-1.mp4",
                "metadata": {
                    "storage": {
                        "status": "failed",
                        "fallback_reason": "artifact_upload_failed",
                    }
                },
                "fallback_reasons": ["artifact_upload_failed"],
            }
        ],
        workflow_state_id="wf-storage-diagnostics",
    )

    assert receipts[0]["status"] == "failed"
    assert receipts[0]["failure_reason"] == "artifact_upload_failed"
    assert receipts[0]["storage_status"] == "failed"
    assert receipts[0]["accepted_at"] == ""


@pytest.mark.asyncio
async def test_existing_video_path_does_not_override_storage_failure():
    results = await ensure_persisted_videos(
        [
            {
                "success": True,
                "scene_number": 1,
                "video_path": "/tmp/stale-scene-1.mp4",
                "storage": {
                    "status": "failed",
                    "fallback_reason": "artifact_upload_failed",
                },
            }
        ],
        None,
    )

    assert results[0]["storage"]["status"] == "failed"
    assert results[0]["storage"]["fallback_reason"] == "artifact_upload_failed"


def test_video_delivery_receipt_accepts_only_persisted_local_artifact():
    artifacts, receipts = issue_scene_output_acceptance_receipts(
        kind="video",
        artifacts=[
            {
                "success": True,
                "scene_number": 1,
                "video_url": "https://example.com/scene-1.mp4",
                "video_path": "/tmp/scene-1.mp4",
                "metadata": {"storage": {"status": "persisted"}},
            }
        ],
        workflow_state_id="wf-storage-diagnostics",
    )

    assert receipts[0]["status"] == "accepted"
    assert receipts[0]["delivery_ref"] == "scene_outputs.video.1"
    assert receipts[0]["accepted_at"]
    assert receipts[0]["storage_status"] == "persisted"
    assert artifacts[0]["acceptance_receipt"] == receipts[0]


@pytest.mark.parametrize(
    ("receipt_update", "reason_code"),
    [
        ({"status": " Accepted "}, "scene_output_acceptance_receipt_invalid"),
        (
            {"producer_status": " Succeeded "},
            "scene_output_acceptance_receipt_invalid",
        ),
        ({"status": []}, "scene_output_acceptance_receipt_invalid"),
        ({"artifact_kind": {}}, "scene_output_acceptance_receipt_invalid"),
        ({"producer_status": []}, "scene_output_acceptance_receipt_invalid"),
        ({"scene_number": "1"}, "scene_output_acceptance_receipt_invalid"),
        ({"artifact_kind": " Image "}, "scene_output_acceptance_receipt_invalid"),
        (
            {"accepted_at": "2026-07-25T00:00:00"},
            "scene_output_acceptance_timestamp_invalid",
        ),
        (
            {"accepted_at": "not-a-timestamp"},
            "scene_output_acceptance_timestamp_invalid",
        ),
    ],
)
def test_scene_output_acceptance_rejects_noncanonical_receipt_values(
    receipt_update,
    reason_code,
):
    artifacts, _receipts = issue_scene_output_acceptance_receipts(
        kind="image",
        artifacts=[
            {
                "success": True,
                "scene_number": 1,
                "image_path": "/tmp/scene-1.png",
            }
        ],
        workflow_state_id="wf-canonical-receipt",
    )
    artifacts[0]["acceptance_receipt"].update(receipt_update)
    shared = _SharedMemory({"scene_outputs.image": {1: artifacts[0]}})

    result = evaluate_scene_output_acceptance(
        kind="image",
        workflow_id="wf-canonical-receipt",
        agent_memory=None,
        shared_memory=shared,
        expected_scene_numbers=[1],
    )

    assert result["accepted"] is False
    assert result["rejected_scene_outputs"][0]["reason_code"] == reason_code


def test_scene_output_receipt_issuer_does_not_coerce_string_scene_identity():
    artifacts, receipts = issue_scene_output_acceptance_receipts(
        kind="image",
        artifacts=[
            {
                "success": True,
                "scene_number": "1",
                "image_path": "/tmp/scene-1.png",
            }
        ],
        workflow_state_id="wf-source-identity",
    )

    assert receipts == []
    assert "acceptance_receipt" not in artifacts[0]


def test_video_acceptance_rejects_noncanonical_storage_status():
    artifacts, _receipts = issue_scene_output_acceptance_receipts(
        kind="video",
        artifacts=[
            {
                "success": True,
                "scene_number": 1,
                "video_path": "/tmp/scene-1.mp4",
                "storage": {"status": "persisted"},
            }
        ],
        workflow_state_id="wf-canonical-video-receipt",
    )
    artifacts[0]["acceptance_receipt"]["storage_status"] = " Persisted "
    shared = _SharedMemory({"scene_outputs.video": {1: artifacts[0]}})

    result = evaluate_scene_output_acceptance(
        kind="video",
        workflow_id="wf-canonical-video-receipt",
        agent_memory=None,
        shared_memory=shared,
        expected_scene_numbers=[1],
    )

    assert result["accepted"] is False
    assert (
        result["rejected_scene_outputs"][0]["reason_code"]
        == "scene_output_acceptance_receipt_invalid"
    )


def test_accepted_receipt_status_is_the_only_scene_acceptance_outcome():
    artifacts, _receipts = issue_scene_output_acceptance_receipts(
        kind="video",
        artifacts=[
            {
                "success": True,
                "scene_number": 1,
                "video_path": "/tmp/scene-1.mp4",
                "storage": {"status": "persisted"},
            }
        ],
        workflow_state_id="wf-single-receipt-outcome",
    )
    artifacts[0]["acceptance_receipt"]["producer_status"] = "failed"
    artifacts[0]["acceptance_receipt"]["storage_status"] = "failed"
    artifacts[0]["storage"] = {"status": "failed", "fallback_reason": "late_diagnostic"}
    shared = _SharedMemory({"scene_outputs.video": {1: artifacts[0]}})

    result = evaluate_scene_output_acceptance(
        kind="video",
        workflow_id="wf-single-receipt-outcome",
        agent_memory=None,
        shared_memory=shared,
        expected_scene_numbers=[1],
    )

    assert result["accepted"] is True
    assert result["accepted_scene_numbers"] == [1]


def test_video_delivery_receipt_rejects_url_only_artifact():
    _artifacts, receipts = issue_scene_output_acceptance_receipts(
        kind="video",
        artifacts=[
            {
                "success": True,
                "scene_number": 1,
                "video_url": "https://example.com/scene-1.mp4",
            }
        ],
        workflow_state_id="wf-storage-diagnostics",
    )

    assert receipts[0]["status"] == "failed"
    assert receipts[0]["failure_reason"] == "artifact_not_persisted"


@pytest.mark.asyncio
async def test_local_video_path_receives_persisted_storage_provenance():
    results = await ensure_persisted_videos(
        [
            {
                "success": True,
                "scene_number": 1,
                "video_path": "/tmp/scene-1.mp4",
            }
        ],
        None,
    )

    assert results[0]["storage"] == {
        "status": "persisted",
        "source": "producer_local_path",
    }
    assert results[0]["metadata"]["storage"] == results[0]["storage"]


@pytest.mark.asyncio
async def test_persist_scene_outputs_keeps_producer_acceptance_receipt():
    shared = _SharedMemory()
    artifacts, receipts = issue_scene_output_acceptance_receipts(
        kind="image",
        artifacts=[
            {
                "success": True,
                "scene_number": 1,
                "image_url": "https://example.com/scene-1.png",
            }
        ],
        workflow_state_id="wf-image-receipt",
    )

    await persist_scene_outputs(
        kind="image",
        shared_memory=shared,
        artifacts=artifacts,
    )

    assert shared["scene_outputs.image"][1]["acceptance_receipt"] == receipts[0]
