import pytest
from pathlib import Path

from app.agents.memory.storage.slot import SlotRegistry, SlotScope, SlotDefinitionError


def test_slot_registry_loads_config():
    import os
    print('current working directory:', os.getcwd())
    path = Path("app/agents/memory/config/memory_slots.yaml")
    registry = SlotRegistry.from_config(path)
    schema = registry.get("project.concept_plan")
    assert schema.scope == SlotScope.WORKFLOW
    assert schema.value_type is dict
    assert schema.reducer is not None


def test_slot_acl_defaults():
    path = Path("app/agents/memory/config/memory_slots.yaml")
    registry = SlotRegistry.from_config(path)
    concept = registry.get("project.concept_plan")
    assert concept.scope == SlotScope.WORKFLOW


def test_invalid_scope_raises(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "slots:\n  - slot_id: bad.slot\n    scope: unknown\n    value_type: dict\n"
    )
    with pytest.raises(SlotDefinitionError):
        SlotRegistry.from_config(bad)
