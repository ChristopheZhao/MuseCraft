"""Architecture ratchet for Slice E database composition ownership."""

from __future__ import annotations

from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_ENTRYPOINTS = {
    BACKEND_ROOT / "app" / "core" / "config.py",
    BACKEND_ROOT / "app" / "core" / "database.py",
    BACKEND_ROOT / "alembic" / "env.py",
    BACKEND_ROOT / "scripts" / "start_dev.py",
    BACKEND_ROOT / "scripts" / "start_dev_uv.py",
}
EXPECTED_TRANSITIONAL_DATABASE_POLICY_DEBT = {
    "alembic/env.py",
    "app/core/config.py",
    "app/core/database.py",
    "scripts/start_dev.py",
    "scripts/start_dev_uv.py",
}
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


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_database_policy_debt_matches_exact_slice_e_ratchet() -> None:
    observed = {
        path.relative_to(BACKEND_ROOT).as_posix()
        for path in RUNTIME_ENTRYPOINTS
        if any(marker in _source(path) for marker in POLICY_MARKERS)
    }

    assert observed == EXPECTED_TRANSITIONAL_DATABASE_POLICY_DEBT


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


def test_uv_launcher_currently_owns_transitional_database_policy_only_once() -> None:
    source = _source(BACKEND_ROOT / "scripts" / "start_dev_uv.py")

    assert source.count("def _inspect_database_runtime_contract") == 1
    assert source.count("def _check_database_dependency") == 1
