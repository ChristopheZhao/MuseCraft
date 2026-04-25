import pytest

from app.agents.utils.artifacts import ensure_persisted_videos
from app.agents.video_generator import VideoGeneratorAgent


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
    agent = object.__new__(VideoGeneratorAgent)

    receipts = agent._build_delivery_receipts(
        [
            {
                "success": True,
                "scene_number": 1,
                "video_url": "https://example.com/scene-1.mp4",
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
    assert receipts[0]["storage_fallback_reason"] == "artifact_upload_failed"
    assert receipts[0]["fallback_reasons"] == ["artifact_upload_failed"]
    assert "accepted_at" not in receipts[0]


def test_video_delivery_receipt_accepts_only_persisted_local_artifact():
    agent = object.__new__(VideoGeneratorAgent)

    receipts = agent._build_delivery_receipts(
        [
            {
                "success": True,
                "scene_number": 1,
                "video_url": "https://example.com/scene-1.mp4",
                "video_path": "/tmp/scene-1.mp4",
            }
        ],
        workflow_state_id="wf-storage-diagnostics",
    )

    assert receipts[0]["status"] == "accepted"
    assert receipts[0]["delivery_ref"] == "scene_outputs.video.1"
    assert receipts[0]["accepted_at"]


def test_video_delivery_receipt_rejects_url_only_artifact():
    agent = object.__new__(VideoGeneratorAgent)

    receipts = agent._build_delivery_receipts(
        [
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
    assert receipts[0]["fallback_reasons"] == ["artifact_not_persisted"]
