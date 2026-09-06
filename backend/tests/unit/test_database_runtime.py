"""Database composition contract tests."""

from __future__ import annotations

from sqlalchemy import text

from app.infrastructure.database_runtime import (
    LOCAL_DEFAULT_DATABASE_URL,
    DatabaseBackend,
    DatabaseProfile,
    DatabaseRuntimeReason,
    compose_database_runtime,
    preflight_database_runtime,
    resolve_database_runtime,
)


def test_local_profile_uses_documented_postgresql_default() -> None:
    config = resolve_database_runtime(profile="local", database_url=None)

    assert config.profile is DatabaseProfile.LOCAL
    assert config.backend is DatabaseBackend.POSTGRESQL
    assert config.sync_url.render_as_string(
        hide_password=False
    ) == LOCAL_DEFAULT_DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)
    assert config.async_url.drivername == "postgresql+asyncpg"


def test_postgresql_driver_inputs_normalize_to_registered_runtime_drivers() -> None:
    config = resolve_database_runtime(
        profile="local",
        database_url="postgresql+asyncpg://dev:secret@db.example/musecraft",
    )

    assert config.sync_url.drivername == "postgresql+psycopg2"
    assert config.async_url.drivername == "postgresql+asyncpg"
    assert config.migration_url == config.async_url


def test_production_requires_explicit_non_local_non_example_configuration() -> None:
    cases = (
        (None, DatabaseRuntimeReason.MISSING_PRODUCTION_URL),
        (
            "postgresql://service:secret@localhost/musecraft",
            DatabaseRuntimeReason.PRODUCTION_LOCALHOST,
        ),
        (
            "postgresql://service:secret@0.0.0.0/musecraft",
            DatabaseRuntimeReason.PRODUCTION_LOCALHOST,
        ),
        (
            "postgresql://user:password@db.example/musecraft",
            DatabaseRuntimeReason.PRODUCTION_UNSAFE_CREDENTIALS,
        ),
    )

    for database_url, reason_code in cases:
        result = preflight_database_runtime(
            profile="production",
            database_url=database_url,
            connection_probe=lambda _url: None,
        )
        assert result.accepted is False
        assert result.reason_code is reason_code


def test_production_accepts_explicit_remote_postgresql_configuration() -> None:
    seen = []
    result = preflight_database_runtime(
        profile="production",
        database_url="postgresql://service:strong-secret@db.example/musecraft",
        connection_probe=seen.append,
    )

    assert result.accepted is True
    assert result.profile is DatabaseProfile.PRODUCTION
    assert result.backend is DatabaseBackend.POSTGRESQL
    assert seen[0].drivername == "postgresql+psycopg2"


def test_mysql_is_rejected_before_connection_probe() -> None:
    probe_calls = []
    result = preflight_database_runtime(
        profile="local",
        database_url="mysql://user:password@localhost/musecraft",
        connection_probe=probe_calls.append,
    )

    assert result.accepted is False
    assert result.backend is None
    assert result.backend_name == "mysql"
    assert result.reason_code is DatabaseRuntimeReason.UNSUPPORTED_BACKEND
    assert probe_calls == []


def test_sqlite_is_accepted_only_for_explicit_test_profile() -> None:
    accepted = resolve_database_runtime(
        profile="test",
        database_url="sqlite+aiosqlite:///:memory:",
    )
    rejected = preflight_database_runtime(
        profile="local",
        database_url="sqlite:///:memory:",
        connection_probe=lambda _url: None,
    )

    assert accepted.sync_url.drivername == "sqlite"
    assert accepted.async_url.drivername == "sqlite+aiosqlite"
    assert rejected.reason_code is DatabaseRuntimeReason.PROFILE_BACKEND_MISMATCH


def test_invalid_profile_and_url_return_distinct_reason_codes() -> None:
    invalid_profile = preflight_database_runtime(
        profile="staging",
        database_url="postgresql://service:secret@db.example/musecraft",
    )
    invalid_url = preflight_database_runtime(
        profile="local",
        database_url="not a database url",
    )

    assert invalid_profile.reason_code is DatabaseRuntimeReason.INVALID_PROFILE
    assert invalid_url.reason_code is DatabaseRuntimeReason.INVALID_URL


def test_connection_failure_is_typed_without_connection_details() -> None:
    def _fail(_url) -> None:
        raise OSError("postgresql://service:secret@db.example/musecraft")

    result = preflight_database_runtime(
        profile="production",
        database_url="postgresql://service:strong-secret@db.example/musecraft",
        connection_probe=_fail,
    )

    assert result.accepted is False
    assert result.reason_code is DatabaseRuntimeReason.CONNECTION_FAILED
    assert result.error_type == "OSError"
    assert "secret" not in repr(result)


def test_resolved_runtime_repr_does_not_expose_database_url() -> None:
    config = resolve_database_runtime(
        profile="production",
        database_url="postgresql://service:strong-secret@db.example/musecraft",
    )

    assert "strong-secret" not in repr(config)
    assert "db.example" not in repr(config)


def test_composed_test_runtime_provides_working_sync_session_factory() -> None:
    config = resolve_database_runtime(
        profile="test",
        database_url="sqlite+aiosqlite:///:memory:",
    )
    runtime = compose_database_runtime(config, debug=False)
    try:
        with runtime.session_factory() as session:
            assert session.execute(text("SELECT 1")).scalar_one() == 1
    finally:
        runtime.engine.dispose()
