"""Tests for database contract consumption in the system validator."""

from __future__ import annotations

from app.infrastructure.database_runtime import (
    DatabaseBackend,
    DatabasePreflightResult,
    DatabaseProfile,
    DatabaseRuntimeReason,
)
from scripts import validate_system


def _configure_valid_non_database_settings(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(validate_system.settings, "REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setattr(validate_system.settings, "SECRET_KEY", "test-secret")
    monkeypatch.setattr(validate_system.settings, "UPLOAD_PATH", str(tmp_path / "uploads"))
    monkeypatch.setattr(
        validate_system.settings,
        "GENERATED_PATH",
        str(tmp_path / "generated"),
    )
    monkeypatch.setattr(validate_system.settings, "TEMP_PATH", str(tmp_path / "temp"))


def test_configuration_accepts_local_profile_without_database_url(
    monkeypatch,
    tmp_path,
) -> None:
    _configure_valid_non_database_settings(monkeypatch, tmp_path)
    monkeypatch.setattr(validate_system.settings, "DATABASE_PROFILE", "local")
    monkeypatch.setattr(validate_system.settings, "DATABASE_URL", None)

    result = validate_system.SystemValidator()._validate_configuration()

    assert not any("DATABASE_URL" in issue for issue in result["issues"])
    assert not any("Database runtime rejected" in issue for issue in result["issues"])


def test_configuration_reports_typed_production_database_rejection(
    monkeypatch,
    tmp_path,
) -> None:
    _configure_valid_non_database_settings(monkeypatch, tmp_path)
    monkeypatch.setattr(validate_system.settings, "DATABASE_PROFILE", "production")
    monkeypatch.setattr(validate_system.settings, "DATABASE_URL", None)

    result = validate_system.SystemValidator()._validate_configuration()

    assert result["status"] == "CRITICAL"
    assert "Database runtime rejected: missing_production_database_url" in result["issues"]


def test_database_validation_reports_sanitized_typed_preflight_failure(
    monkeypatch,
) -> None:
    secret = "do-not-log-this-password"
    monkeypatch.setattr(validate_system.settings, "DATABASE_PROFILE", "local")
    monkeypatch.setattr(
        validate_system.settings,
        "DATABASE_URL",
        f"postgresql://musecraft:{secret}@localhost:5432/short_video_maker",
    )
    monkeypatch.setattr(
        validate_system,
        "preflight_database_runtime",
        lambda **_: DatabasePreflightResult(
            accepted=False,
            profile=DatabaseProfile.LOCAL,
            backend=DatabaseBackend.POSTGRESQL,
            backend_name=DatabaseBackend.POSTGRESQL.value,
            reason_code=DatabaseRuntimeReason.CONNECTION_FAILED,
            error_type="OperationalError",
        ),
    )

    result = validate_system.SystemValidator()._validate_database_setup()

    assert result["status"] == "CRITICAL"
    assert result["details"]["connection_test"] == "FAIL"
    assert result["issues"] == [
        "Database preflight rejected: "
        "reason_code=database_connection_failed, profile=local, "
        "backend=postgresql, error_type=OperationalError"
    ]
    assert secret not in str(result)
