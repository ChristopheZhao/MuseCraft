from app.agents.video_generator import VideoGeneratorAgent


def test_extract_pending_image_regen_sanitizes_entries():
    agent = object.__new__(VideoGeneratorAgent)

    workflow_state = {
        "pending_image_regen": {
            1: {
                "status": "waiting",
                "reason": "input_image_sensitive",
                "attempts": 2,
                "blocked_image_url": "https://example.com/flagged.jpg",
            }
        }
    }

    sanitized, blocked = agent._extract_pending_image_regen(workflow_state, sanitize=True)

    assert 1 in sanitized
    assert sanitized[1]["status"] == "waiting"
    assert "blocked_image_url" not in sanitized[1]
    assert 1 in blocked
