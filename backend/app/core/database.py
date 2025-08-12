"""
Database configuration and session management
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from .config import settings

# Synchronous database engine
# Support both PostgreSQL and MySQL
sync_database_url = settings.DATABASE_URL
if settings.DATABASE_URL.startswith("mysql://"):
    sync_database_url = settings.DATABASE_URL.replace("mysql://", "mysql+pymysql://")

engine = create_engine(
    sync_database_url,
    pool_pre_ping=True,
    pool_recycle=300,
    pool_size=20,
    max_overflow=0,
    echo=settings.DEBUG
)

# Asynchronous database engine  
# Support both PostgreSQL and MySQL
async_database_url = settings.DATABASE_URL
if settings.DATABASE_URL.startswith("postgresql://"):
    async_database_url = settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
elif settings.DATABASE_URL.startswith("mysql://"):
    async_database_url = settings.DATABASE_URL.replace("mysql://", "mysql+aiomysql://")

async_engine = create_async_engine(
    async_database_url,
    pool_pre_ping=True,
    pool_recycle=300,
    pool_size=20,
    max_overflow=0,
    echo=settings.DEBUG
)

# Session makers
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
AsyncSessionLocal = async_sessionmaker(
    async_engine, class_=AsyncSession, expire_on_commit=False
)

# Import Base from models to avoid circular imports
# This will be set after models are imported
Base = None


# Dependency to get database session
async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


# Dependency to get sync database session (for Celery tasks)
def get_sync_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()