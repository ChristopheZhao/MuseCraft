from app.agents.memory.short_term import WorkingMemory
from app.agents.utils.memory_helpers import agent_scope


def test_record_event_dedup_and_notes_trim():
    scope = agent_scope("wf-x", "test")
    wm = WorkingMemory(workflow_state_id="wf-x", scope=scope, goal_text="g", journal_max_events=5)

    wm.record_event(1, action="video_generation", success=False, error_type="timeout", dur_sec=1.2, ts=1.0)
    wm.record_event(1, action="video_generation", success=False, error_type="timeout", dur_sec=1.3, ts=2.0)

    evq = wm.event_streams.get("1")
    assert evq is not None
    assert len(evq) == 1, "duplicate events should be merged"
    last = evq[-1]
    assert last.get("count") == 2
    assert last.get("action") == "video_generation"
    assert last.get("error_type") == "timeout"
