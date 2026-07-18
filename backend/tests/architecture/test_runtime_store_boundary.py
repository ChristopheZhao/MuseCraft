"""Architecture ratchet for Slice D runtime-store separation."""

from __future__ import annotations

import ast
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
SERVICES_ROOT = BACKEND_ROOT / "app" / "services"
DOMAIN_CONTRACT = BACKEND_ROOT / "app" / "domain" / "runtime_store.py"

EXPECTED_TRANSITIONAL_RUNTIME_PERSISTENCE_DEBT = {
    "context_assembler.py",
    "orchestration_runtime_resume_bootstrap_facade.py",
    "orchestration_runtime_transition_facade.py",
    "published_deliverable_service.py",
    "runtime_session_service.py",
}

RUNTIME_OWNERSHIP_MARKERS = (
    "RuntimeSessionService",
    "PublishedDeliverableService",
    "publish_script_review_boundary_sync",
    "WorkflowSession",
    "WorkflowNodeAttempt",
    "WorkflowNodeState",
    "WorkflowGate",
    "WorkflowPublishedDeliverable",
)


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _imports(path: Path) -> set[str]:
    imported: set[str] = set()
    tree = ast.parse(_source(path), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    return imported


def test_runtime_store_domain_contract_has_no_persistence_or_untyped_escape_hatch():
    source = _source(DOMAIN_CONTRACT)
    imports = _imports(DOMAIN_CONTRACT)

    assert not any(module == "sqlalchemy" or module.startswith("sqlalchemy.") for module in imports)
    assert not any(module == "models" or module.endswith(".models") for module in imports)
    assert "sqlalchemy.orm import Session" not in source
    assert "Any" not in source
    assert "dict[str," not in source


def test_runtime_control_plane_sql_debt_matches_exact_slice_d_ratchet():
    observed: set[str] = set()
    for path in SERVICES_ROOT.glob("*.py"):
        source = _source(path)
        imports = _imports(path)
        imports_sqlalchemy = any(
            module == "sqlalchemy" or module.startswith("sqlalchemy.") for module in imports
        )
        if imports_sqlalchemy and any(marker in source for marker in RUNTIME_OWNERSHIP_MARKERS):
            observed.add(path.name)

    assert observed == EXPECTED_TRANSITIONAL_RUNTIME_PERSISTENCE_DEBT


def test_runtime_store_exposes_required_atomic_capabilities():
    tree = ast.parse(_source(DOMAIN_CONTRACT), filename=str(DOMAIN_CONTRACT))
    protocol = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "RuntimeControlPlaneStore"
    )
    method_names = {
        node.name
        for node in protocol.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    required = {
        "load_session",
        "load_latest_session_for_task",
        "load_node",
        "load_nodes",
        "load_attempt",
        "load_latest_gate",
        "load_latest_gate_decision",
        "load_published_deliverable",
        "create_session",
        "transition_node",
        "start_attempt",
        "grant_attempt_lease",
        "heartbeat_attempt_lease",
        "release_attempt_lease",
        "bind_attempt_continuation",
        "complete_attempt",
        "fail_attempt",
        "open_gate",
        "create_gate_decision",
        "apply_gate_decision",
        "transition_session",
        "publish_deliverable",
        "approve_deliverable",
        "upsert_node_diagnostic",
    }
    assert method_names == required

    query_protocol = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "RuntimeReadModelQuery"
    )
    query_methods = {
        node.name
        for node in query_protocol.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert query_methods == {"load_for_task"}

    attempt_protocol = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "RuntimeAttemptStore"
    )
    attempt_methods = {
        node.name
        for node in attempt_protocol.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert attempt_methods == {
        "load_session",
        "load_node",
        "load_attempt",
        "start_attempt",
        "grant_attempt_lease",
        "heartbeat_attempt_lease",
        "release_attempt_lease",
        "bind_attempt_continuation",
        "complete_attempt",
        "fail_attempt",
        "upsert_node_diagnostic",
    }

    gate_protocol = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "RuntimeGateStore"
    )
    gate_methods = {
        node.name
        for node in gate_protocol.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert gate_methods == {
        "load_session",
        "load_node",
        "load_attempt",
        "load_latest_gate",
        "load_published_deliverable",
        "open_gate",
        "create_gate_decision",
        "apply_gate_decision",
    }
