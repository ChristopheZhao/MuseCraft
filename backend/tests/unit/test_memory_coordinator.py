from app.services.memory_provider import build_memory_services


def test_memory_coordinator_basic_flow():
    services = build_memory_services()
    wf_id = "wf-unit"
    coord = services.global_service._memory_coordinator  # internal use for implementation test

    # workflow scope slot - concept_plan
    coord.set_memory(wf_id, "project.concept_plan", {"overview": "unit"}, agent="concept_planner")
    plan = coord.get_memory(wf_id, "project.concept_plan", agent="image_generator")
    assert plan["overview"] == "unit"

    # 无 ACL：后写覆盖
    coord.set_memory(wf_id, "project.concept_plan", {"overview": "updated"}, agent="image_generator")
    updated = coord.get_memory(wf_id, "project.concept_plan")
    assert updated["overview"] == "updated"
