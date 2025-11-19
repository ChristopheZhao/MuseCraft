from pathlib import Path

import pytest

from app.services.memory_provider import build_memory_services, set_memory_services


def test_memory_coordinator_basic_flow():
    services = build_memory_services()
    set_memory_services(services)
    wf_id = "wf-unit"
    coord = services.coordinator

    # workflow scope slot - concept_plan
    coord.set_memory(wf_id, "project.concept_plan", {"overview": "unit"}, agent="concept_planner")
    plan = coord.get_memory(wf_id, "project.concept_plan", agent="image_generator")
    assert plan["overview"] == "unit"

    # ACL enforcement on write: image_generator 不在 concept_plan 的 write 列表中
    with pytest.raises(Exception):
        coord.set_memory(wf_id, "project.concept_plan", {"overview": "bad"}, agent="image_generator")
