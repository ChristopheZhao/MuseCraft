"""Application database sessions composed by the infrastructure boundary."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from ..infrastructure.database_runtime import compose_database_runtime, resolve_database_runtime
from ..models.base import BaseModel as Base
from .config import settings

database_runtime = compose_database_runtime(
    resolve_database_runtime(
        profile=settings.DATABASE_PROFILE,
        database_url=settings.DATABASE_URL,
    ),
    debug=settings.DEBUG,
)
engine = database_runtime.engine
async_engine = database_runtime.async_engine
SessionLocal = database_runtime.session_factory
AsyncSessionLocal = database_runtime.async_session_factory


async def get_db() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session


def get_sync_db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
