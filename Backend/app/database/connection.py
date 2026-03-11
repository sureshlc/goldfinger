"""
Database Connection Module
Async SQLAlchemy engine + session factory for PostgreSQL.
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.config import settings
import logging

logger = logging.getLogger(__name__)

# Global engine and session factory
_engine = None
_async_session_factory = None


async def init_db():
    """Initialize database engine and session factory."""
    global _engine, _async_session_factory

    _engine = create_async_engine(
        settings.database_url,
        echo=settings.environment == "development",
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
    )
    _async_session_factory = async_sessionmaker(
        _engine, class_=AsyncSession, expire_on_commit=False
    )
    logger.info("Database engine initialized")


async def close_db():
    """Dispose of the database engine."""
    global _engine, _async_session_factory
    if _engine:
        await _engine.dispose()
        _engine = None
        _async_session_factory = None
        logger.info("Database engine disposed")


async def get_db():
    """FastAPI dependency that yields a database session."""
    if _async_session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    async with _async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_session_factory():
    """Get the session factory for use outside of FastAPI dependencies."""
    if _async_session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _async_session_factory
