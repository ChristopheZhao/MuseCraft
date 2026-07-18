"""Architecture ratchet for Slice D runtime-store separation."""

from __future__ import annotations

import ast
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
SERVICES_ROOT = BACKEND_ROOT / "app" / "services"
DOMAIN_CONTRACT = BACKEND_ROOT / "app" / "domain" / "runtime_store.py"
RUNTIME_READ_MODEL_SERVICE = BACKEND_ROOT / "app" / "services" / "runtime_read_model_service.py"
RUNTIME_SESSION_CONTROL_PLANE = (
    BACKEND_ROOT / "app" / "services" / "runtime_session_control_plane.py"
)
RUNTIME_RECONCILER = BACKEND_ROOT / "app" / "services" / "runtime_reconciler.py"
CONTEXT_ASSEMBLER = BACKEND_ROOT / "app" / "services" / "context_assembler.py"
PUBLISHED_DELIVERABLE_SERVICE = (
    BACKEND_ROOT / "app" / "services" / "published_deliverable_service.py"
)
RUNTIME_PUBLISHED_DELIVERABLE_CONTROL_PLANE = (
    BACKEND_ROOT / "app" / "services" / "runtime_published_deliverable_control_plane.py"
)
RUNTIME_RESUME_CONTROL_PLANE = BACKEND_ROOT / "app" / "services" / "runtime_resume_control_plane.py"
RUNTIME_SESSION_BOOTSTRAP_CONTROL_PLANE = (
    BACKEND_ROOT / "app" / "services" / "runtime_session_bootstrap_control_plane.py"
)

EXPECTED_TRANSITIONAL_RUNTIME_PERSISTENCE_DEBT: set[str] = set()
RUNTIME_ORM_SYMBOLS = {
    "WorkflowSession",
    "WorkflowNodeAttempt",
    "WorkflowNodeState",
    "WorkflowGate",
    "WorkflowGateDecision",
    "WorkflowPublishedDeliverable",
}


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


def _imported_names(path: Path, *, modules: set[str]) -> set[str]:
    imported: set[str] = set()
    tree = ast.parse(_source(path), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in modules:
            imported.update(alias.name for alias in node.names)
    return imported


def test_runtime_store_domain_contract_has_no_persistence_or_untyped_escape_hatch():
    source = _source(DOMAIN_CONTRACT)
    imports = _imports(DOMAIN_CONTRACT)

    assert not any(module == "sqlalchemy" or module.startswith("sqlalchemy.") for module in imports)
    assert not any(module == "models" or module.endswith(".models") for module in imports)
    assert "sqlalchemy.orm import Session" not in source
    assert "Any" not in source
    assert "dict[str," not in source


def test_runtime_projection_and_session_policy_are_database_independent():
    for path in {
        RUNTIME_READ_MODEL_SERVICE,
        RUNTIME_SESSION_CONTROL_PLANE,
        RUNTIME_RECONCILER,
        CONTEXT_ASSEMBLER,
        PUBLISHED_DELIVERABLE_SERVICE,
        RUNTIME_PUBLISHED_DELIVERABLE_CONTROL_PLANE,
        RUNTIME_RESUME_CONTROL_PLANE,
        RUNTIME_SESSION_BOOTSTRAP_CONTROL_PLANE,
    }:
        imports = _imports(path)
        source = _source(path)
        assert not any(
            module == "sqlalchemy" or module.startswith("sqlalchemy.") for module in imports
        )
        assert not any(module == "models" or module.endswith(".models") for module in imports)
        assert "RuntimeSessionService" not in source


def test_runtime_control_plane_sql_debt_matches_exact_slice_d_ratchet():
    observed: set[str] = set()
    for path in SERVICES_ROOT.glob("*.py"):
        source = _source(path)
        imports = _imports(path)
        imports_sqlalchemy = any(
            module == "sqlalchemy" or module.startswith("sqlalchemy.") for module in imports
        )
        imports_runtime_models = bool(
            _imported_names(path, modules={"app.models", "models"}) & RUNTIME_ORM_SYMBOLS
        )
        uses_legacy_runtime_service = "RuntimeSessionService" in source
        if imports_sqlalchemy and (imports_runtime_models or uses_legacy_runtime_service):
            observed.add(path.name)

    assert observed == EXPECTED_TRANSITIONAL_RUNTIME_PERSISTENCE_DEBT


def test_production_runtime_callers_do_not_reference_legacy_session_service():
    violations: list[str] = []
    for root in (BACKEND_ROOT / "app" / "api", BACKEND_ROOT / "app" / "services"):
        for path in root.rglob("*.py"):
            imports = _imports(path)
            imports_legacy_service = any(
                module == "runtime_session_service" or module.endswith(".runtime_session_service")
                for module in imports
            )
            if imports_legacy_service or "RuntimeSessionService" in _source(path):
                violations.append(str(path.relative_to(BACKEND_ROOT)))
    for path in (BACKEND_ROOT / "scripts").rglob("*.py"):
        source = _source(path)
        if "runtime_session_service" in source or "RuntimeSessionService" in source:
            violations.append(str(path.relative_to(BACKEND_ROOT)))

    assert violations == []


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
        "clear_node_diagnostics",
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

    read_store = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "RuntimeReadStore"
    )
    read_store_methods = {
        node.name
        for node in read_store.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert read_store_methods == {
        "load_session",
        "load_latest_session_for_task",
        "load_nodes",
        "load_attempt",
        "load_latest_gate",
        "load_latest_gate_decision",
    }

    session_store = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "RuntimeSessionStore"
    )
    session_store_methods = {
        node.name
        for node in session_store.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert session_store_methods == {"transition_session"}

    bootstrap_store = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "RuntimeSessionBootstrapStore"
    )
    bootstrap_store_methods = {
        node.name
        for node in bootstrap_store.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert bootstrap_store_methods == {"create_session"}

    resume_store = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "RuntimeResumeStore"
    )
    resume_store_methods = {
        node.name
        for node in resume_store.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert resume_store_methods == {
        "load_node",
        "load_published_deliverable",
        "clear_node_diagnostics",
    }

    maintenance_store = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "RuntimeMaintenanceStore"
    )
    maintenance_store_methods = {
        node.name
        for node in maintenance_store.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert maintenance_store_methods == {"load_reconcilable_sessions"}


def test_production_runtime_callers_do_not_use_legacy_projection_or_terminal_mutators():
    forbidden_calls = {
        "build_runtime_view_for_task",
        "build_runtime_view_for_task_sync",
        "get_resume_control_sync",
        "mark_session_running_sync",
        "mark_session_resuming_sync",
        "mark_session_completed_sync",
        "mark_session_failed_sync",
        "mark_session_cancelled_sync",
        "mark_session_cancelled_for_task",
        "reconcile_irrecoverable_quick_runtime_sync",
        "reconcile_irrecoverable_quick_runtimes_sync",
    }
    production_roots = [BACKEND_ROOT / "app" / "api", BACKEND_ROOT / "app" / "services"]
    violations: list[str] = []
    for root in production_roots:
        for path in root.rglob("*.py"):
            tree = ast.parse(_source(path), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    if node.func.attr in forbidden_calls:
                        violations.append(
                            f"{path.relative_to(BACKEND_ROOT)}:{node.lineno}:{node.func.attr}"
                        )
    for path in (BACKEND_ROOT / "scripts").rglob("*.py"):
        source = _source(path)
        for forbidden_call in forbidden_calls:
            if f".{forbidden_call}(" in source:
                violations.append(f"{path.relative_to(BACKEND_ROOT)}:{forbidden_call}")
    assert violations == []


def test_runtime_store_keeps_attempt_and_gate_capability_ports_narrow():
    tree = ast.parse(_source(DOMAIN_CONTRACT), filename=str(DOMAIN_CONTRACT))
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
        "clear_node_diagnostics",
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

    deliverable_protocol = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "RuntimePublishedDeliverableStore"
    )
    deliverable_methods = {
        node.name
        for node in deliverable_protocol.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert deliverable_methods == {
        "load_session",
        "load_node",
        "load_attempt",
        "load_published_deliverable",
        "publish_deliverable",
        "approve_deliverable",
    }
