"""Typed database profile resolution and infrastructure composition."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from ipaddress import ip_address

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker

LOCAL_DEFAULT_DATABASE_URL = "postgresql://musecraft:musecraft@127.0.0.1:5432/short_video_maker"


class DatabaseProfile(str, Enum):
    LOCAL = "local"
    PRODUCTION = "production"
    TEST = "test"


class DatabaseBackend(str, Enum):
    POSTGRESQL = "postgresql"
    SQLITE = "sqlite"


class DatabaseRuntimeReason(str, Enum):
    INVALID_PROFILE = "invalid_database_profile"
    INVALID_URL = "invalid_database_url"
    MISSING_PRODUCTION_URL = "missing_production_database_url"
    MISSING_TEST_URL = "missing_test_database_url"
    UNSUPPORTED_BACKEND = "unsupported_database_backend"
    PROFILE_BACKEND_MISMATCH = "database_profile_backend_mismatch"
    PRODUCTION_LOCALHOST = "production_database_localhost_forbidden"
    PRODUCTION_UNSAFE_CREDENTIALS = "production_database_unsafe_credentials"
    CONNECTION_FAILED = "database_connection_failed"


class DatabaseRuntimeContractError(ValueError):
    """Typed configuration failure raised before engine construction."""

    def __init__(
        self,
        *,
        reason_code: DatabaseRuntimeReason,
        message: str,
        profile: str | None = None,
        backend: str | None = None,
    ) -> None:
        self.reason_code = reason_code
        self.profile = profile
        self.backend = backend
        super().__init__(f"{reason_code.value}: {message}")


@dataclass(frozen=True, slots=True)
class DatabaseAdapterSpec:
    backend: DatabaseBackend
    sync_driver: str
    async_driver: str
    accepted_profiles: tuple[DatabaseProfile, ...]


@dataclass(frozen=True, slots=True)
class DatabaseRuntimeConfig:
    profile: DatabaseProfile
    adapter: DatabaseAdapterSpec
    sync_url: URL = field(repr=False)
    async_url: URL = field(repr=False)
    migration_url: URL = field(repr=False)

    @property
    def backend(self) -> DatabaseBackend:
        return self.adapter.backend


@dataclass(frozen=True, slots=True)
class DatabasePreflightResult:
    accepted: bool
    profile: DatabaseProfile | None
    backend: DatabaseBackend | None
    backend_name: str | None = None
    reason_code: DatabaseRuntimeReason | None = None
    error_type: str | None = None


@dataclass(slots=True)
class DatabaseRuntime:
    config: DatabaseRuntimeConfig
    engine: Engine
    async_engine: AsyncEngine
    session_factory: sessionmaker[Session]
    async_session_factory: async_sessionmaker[AsyncSession]


_ADAPTERS = {
    DatabaseBackend.POSTGRESQL: DatabaseAdapterSpec(
        backend=DatabaseBackend.POSTGRESQL,
        sync_driver="postgresql+psycopg2",
        async_driver="postgresql+asyncpg",
        accepted_profiles=(
            DatabaseProfile.LOCAL,
            DatabaseProfile.PRODUCTION,
            DatabaseProfile.TEST,
        ),
    ),
    DatabaseBackend.SQLITE: DatabaseAdapterSpec(
        backend=DatabaseBackend.SQLITE,
        sync_driver="sqlite",
        async_driver="sqlite+aiosqlite",
        accepted_profiles=(DatabaseProfile.TEST,),
    ),
}
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
_UNSAFE_PRODUCTION_CREDENTIALS = {
    ("user", "password"),
    ("postgres", "postgres"),
    ("musecraft", "musecraft"),
}


def _profile(value: str) -> DatabaseProfile:
    normalized = str(value or "").strip().lower()
    try:
        return DatabaseProfile(normalized)
    except ValueError as exc:
        raise DatabaseRuntimeContractError(
            reason_code=DatabaseRuntimeReason.INVALID_PROFILE,
            profile=normalized or None,
            message="DATABASE_PROFILE must be local, production, or test",
        ) from exc


def _database_url(*, profile: DatabaseProfile, database_url: str | None) -> URL:
    normalized_url = str(database_url or "").strip()
    if not normalized_url:
        if profile is DatabaseProfile.LOCAL:
            normalized_url = LOCAL_DEFAULT_DATABASE_URL
        elif profile is DatabaseProfile.PRODUCTION:
            raise DatabaseRuntimeContractError(
                reason_code=DatabaseRuntimeReason.MISSING_PRODUCTION_URL,
                profile=profile.value,
                message="production requires an explicit DATABASE_URL",
            )
        else:
            raise DatabaseRuntimeContractError(
                reason_code=DatabaseRuntimeReason.MISSING_TEST_URL,
                profile=profile.value,
                message="test profile requires an explicit DATABASE_URL",
            )
    try:
        return make_url(normalized_url)
    except (ArgumentError, TypeError, ValueError) as exc:
        raise DatabaseRuntimeContractError(
            reason_code=DatabaseRuntimeReason.INVALID_URL,
            profile=profile.value,
            message="DATABASE_URL is not a valid SQLAlchemy URL",
        ) from exc


def _adapter(*, profile: DatabaseProfile, url: URL) -> DatabaseAdapterSpec:
    backend_name = url.get_backend_name().strip().lower()
    try:
        backend = DatabaseBackend(backend_name)
    except ValueError as exc:
        raise DatabaseRuntimeContractError(
            reason_code=DatabaseRuntimeReason.UNSUPPORTED_BACKEND,
            profile=profile.value,
            backend=backend_name or None,
            message="database backend has no registered runtime adapter",
        ) from exc
    adapter = _ADAPTERS[backend]
    if profile not in adapter.accepted_profiles:
        raise DatabaseRuntimeContractError(
            reason_code=DatabaseRuntimeReason.PROFILE_BACKEND_MISMATCH,
            profile=profile.value,
            backend=backend.value,
            message="database backend is not accepted by this profile",
        )
    return adapter


def _validate_production_url(url: URL) -> None:
    host = str(url.host or "").strip().lower()
    local_target = host in _LOCAL_HOSTS
    try:
        parsed_ip = ip_address(host)
        local_target = local_target or parsed_ip.is_loopback or parsed_ip.is_unspecified
    except ValueError:
        pass
    if local_target:
        raise DatabaseRuntimeContractError(
            reason_code=DatabaseRuntimeReason.PRODUCTION_LOCALHOST,
            profile=DatabaseProfile.PRODUCTION.value,
            backend=DatabaseBackend.POSTGRESQL.value,
            message="production DATABASE_URL must not target localhost",
        )
    credentials = (str(url.username or ""), str(url.password or ""))
    if credentials in _UNSAFE_PRODUCTION_CREDENTIALS:
        raise DatabaseRuntimeContractError(
            reason_code=DatabaseRuntimeReason.PRODUCTION_UNSAFE_CREDENTIALS,
            profile=DatabaseProfile.PRODUCTION.value,
            backend=DatabaseBackend.POSTGRESQL.value,
            message="production DATABASE_URL uses known development credentials",
        )


def resolve_database_runtime(
    *,
    profile: str,
    database_url: str | None,
) -> DatabaseRuntimeConfig:
    resolved_profile = _profile(profile)
    parsed_url = _database_url(profile=resolved_profile, database_url=database_url)
    adapter = _adapter(profile=resolved_profile, url=parsed_url)
    if resolved_profile is DatabaseProfile.PRODUCTION:
        _validate_production_url(parsed_url)
    return DatabaseRuntimeConfig(
        profile=resolved_profile,
        adapter=adapter,
        sync_url=parsed_url.set(drivername=adapter.sync_driver),
        async_url=parsed_url.set(drivername=adapter.async_driver),
        migration_url=parsed_url.set(drivername=adapter.async_driver),
    )


def compose_database_runtime(
    config: DatabaseRuntimeConfig,
    *,
    debug: bool,
) -> DatabaseRuntime:
    common_options: dict[str, object] = {
        "pool_pre_ping": True,
        "echo": bool(debug),
    }
    sync_options = dict(common_options)
    async_options = dict(common_options)
    if config.backend is DatabaseBackend.POSTGRESQL:
        pool_options = {
            "pool_recycle": 300,
            "pool_size": 20,
            "max_overflow": 0,
        }
        sync_options.update(pool_options)
        async_options.update(pool_options)
    engine = create_engine(config.sync_url, **sync_options)
    async_engine = create_async_engine(config.async_url, **async_options)
    return DatabaseRuntime(
        config=config,
        engine=engine,
        async_engine=async_engine,
        session_factory=sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=engine,
        ),
        async_session_factory=async_sessionmaker(
            async_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        ),
    )


def _default_connection_probe(url: URL) -> None:
    engine = create_engine(url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    finally:
        engine.dispose()


def _known_profile(value: str | None) -> DatabaseProfile | None:
    try:
        return DatabaseProfile(value) if value else None
    except ValueError:
        return None


def _known_backend(value: str | None) -> DatabaseBackend | None:
    try:
        return DatabaseBackend(value) if value else None
    except ValueError:
        return None


def preflight_database_runtime(
    *,
    profile: str,
    database_url: str | None,
    connection_probe: Callable[[URL], None] = _default_connection_probe,
) -> DatabasePreflightResult:
    try:
        config = resolve_database_runtime(profile=profile, database_url=database_url)
    except DatabaseRuntimeContractError as exc:
        return DatabasePreflightResult(
            accepted=False,
            profile=_known_profile(exc.profile),
            backend=_known_backend(exc.backend),
            backend_name=exc.backend,
            reason_code=exc.reason_code,
        )
    try:
        connection_probe(config.sync_url)
    except Exception as exc:
        return DatabasePreflightResult(
            accepted=False,
            profile=config.profile,
            backend=config.backend,
            backend_name=config.backend.value,
            reason_code=DatabaseRuntimeReason.CONNECTION_FAILED,
            error_type=type(exc).__name__,
        )
    return DatabasePreflightResult(
        accepted=True,
        profile=config.profile,
        backend=config.backend,
        backend_name=config.backend.value,
    )
