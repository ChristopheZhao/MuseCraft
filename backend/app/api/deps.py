"""
API dependencies
"""
from typing import Generator
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db


async def get_database() -> AsyncSession:
    """Get database session dependency"""
    async for session in get_db():
        yield session