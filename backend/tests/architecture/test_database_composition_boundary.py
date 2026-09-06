"""Architecture ratchet for Slice E database composition ownership."""

from __future__ import annotations

import ast
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
PROJECT_METADATA = BACKEND_ROOT / "pyproject.toml"
DATABASE_COMPOSITION_OWNER = BACKEND_ROOT / "app" / "infrastructure" / "database_runtime.py"
RUNTIME_ENTRYPOINTS = {
    BACKEND_ROOT / "app" / "core" / "config.py",
    BACKEND_ROOT / "app" / "core" / "database.py",
    BACKEND_ROOT / "alembic" / "env.py",
    BACKEND_ROOT / "scripts" / "start_dev.py",
    BACKEND_ROOT / "scripts" / "start_dev_uv.py",
}
EXPECTED_TRANSITIONAL_DATABASE_POLICY_DEBT: set[str] = set()
POLICY_MARKERS = {
    "DATABASE_URL.startswith",
    "get_backend_name(",
    "make_url(",
    "mysql+pymysql",
    "mysql+aiomysql",
    "postgresql+asyncpg",
    "postgresql+psycopg2",
    'default="postgresql://',
}
ENGINE_CONSTRUCTION_CALLS = {
    "create_engine",
    "create_async_engine",
    "make_url",
}


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_database_policy_debt_matches_exact_slice_e_ratchet() -> None:
    observed = {
        path.relative_to(BACKEND_ROOT).as_posix()
        for path in RUNTIME_ENTRYPOINTS
        if any(marker in _source(path) for marker in POLICY_MARKERS)
    }

    assert observed == EXPECTED_TRANSITIONAL_DATABASE_POLICY_DEBT


def test_active_python_entrypoints_do_not_duplicate_database_policy() -> None:
    candidates = [
        *sorted((BACKEND_ROOT / "app").rglob("*.py")),
        *sorted((BACKEND_ROOT / "scripts").rglob("*.py")),
        BACKEND_ROOT / "alembic" / "env.py",
    ]
    provider_markers = {
        "DATABASE_URL.startswith",
        "get_backend_name(",
        "mysql+pymysql",
        "mysql+aiomysql",
        "postgresql+asyncpg",
        "postgresql+psycopg2",
    }
    violations: list[str] = []

    for path in candidates:
        if path == DATABASE_COMPOSITION_OWNER:
            continue
        source = _source(path)
        duplicate_policy = any(marker in source for marker in provider_markers)
        tree = ast.parse(source, filename=str(path))
        duplicate_construction = any(
            isinstance(node, ast.Call)
            and (
                isinstance(node.func, ast.Name)
                and node.func.id in ENGINE_CONSTRUCTION_CALLS
                or isinstance(node.func, ast.Attribute)
                and node.func.attr in ENGINE_CONSTRUCTION_CALLS
            )
            for node in ast.walk(tree)
        )
        if duplicate_policy or duplicate_construction:
            violations.append(path.relative_to(BACKEND_ROOT).as_posix())

    assert violations == []


def test_agents_control_plane_and_queue_do_not_own_database_composition() -> None:
    roots = (
        BACKEND_ROOT / "app" / "agents",
        BACKEND_ROOT / "app" / "services",
    )
    forbidden = (
        "create_engine(",
        "create_async_engine(",
        "make_url(",
        "DATABASE_URL.startswith",
        "mysql+pymysql",
        "mysql+aiomysql",
        "postgresql+asyncpg",
        "postgresql+psycopg2",
    )
    violations: list[str] = []
    for root in roots:
        for path in root.rglob("*.py"):
            source = _source(path)
            if any(marker in source for marker in forbidden):
                violations.append(str(path.relative_to(BACKEND_ROOT)))

    assert violations == []


def test_uv_launcher_delegates_database_preflight_to_composition_owner() -> None:
    source = _source(BACKEND_ROOT / "scripts" / "start_dev_uv.py")

    assert "from app.infrastructure.database_runtime import preflight_database_runtime" in source
    assert "def _inspect_database_runtime_contract" not in source
    assert source.count("def _check_database_dependency") == 1
    assert "create_engine" not in source
    assert "make_url" not in source


def test_system_validator_consumes_typed_database_preflight() -> None:
    source = _source(BACKEND_ROOT / "scripts" / "validate_system.py")

    assert "preflight_database_runtime(" in source
    assert "resolve_database_runtime(" in source
    assert "SessionLocal" not in source
    assert "create_engine" not in source
    assert 'execute("SELECT 1")' not in source
    assert "Database connection failed: {str(e)}" not in source


def test_project_dependencies_do_not_advertise_unregistered_database_drivers() -> None:
    source = _source(PROJECT_METADATA).lower()

    assert "pymysql" not in source
    assert "aiomysql" not in source
