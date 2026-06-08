"""
SQLAlchemy async engine, session factory, and declarative Base.

Import Base into every model file so Alembic's autogenerate can
discover all tables via: from app.db.base import Base
"""

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, MappedColumn
from sqlalchemy.pool import NullPool

from app.config.settings import settings


# ── Declarative Base ──────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    """
    Base class for all ORM models.

    Subclass this in every model. Alembic's env.py imports this Base
    so that autogenerate can detect all table definitions.
    """
    pass


# ── Engine Factory ────────────────────────────────────────────────────────────

def _build_engine() -> AsyncEngine:
    """
    Construct the async SQLAlchemy engine with production-safe connection
    pool settings and pgvector support.
    """
    engine_kwargs: dict = {
        "echo": settings.DB_ECHO,
        "pool_pre_ping": True,          # verify connections before use
        "pool_size": settings.DB_POOL_SIZE,
        "max_overflow": settings.DB_MAX_OVERFLOW,
        "pool_timeout": settings.DB_POOL_TIMEOUT,
        "pool_recycle": settings.DB_POOL_RECYCLE,
    }

    # NullPool disables connection pooling — required for Celery workers and
    # scripts that fork processes (each child needs its own connections).
    if settings.ENVIRONMENT == "production":
        # In production behind a PgBouncer, disable SQLAlchemy's pool so
        # PgBouncer handles pooling. Uncomment the line below if using PgBouncer.
        # engine_kwargs = {"echo": False, "poolclass": NullPool}
        pass

    return create_async_engine(settings.DATABASE_URL, **engine_kwargs)


# Module-level engine — one per process
engine: AsyncEngine = _build_engine()


# ── Session Factory ───────────────────────────────────────────────────────────

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,     # prevent lazy-load errors after commit
    autocommit=False,
    autoflush=False,
)


# ── Dependency ────────────────────────────────────────────────────────────────

async def get_db() -> AsyncSession:  # type: ignore[return]
    """
    FastAPI dependency that yields an async database session.

    Usage in a route:
        async def my_route(db: AsyncSession = Depends(get_db)):
            ...

    The session is always closed (and rolled back on error) after the
    request completes, even if an exception is raised.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ── Startup / Shutdown Helpers ────────────────────────────────────────────────

async def init_db() -> None:
    """
    Called at application startup.

    - Verifies the database connection is reachable.
    - Ensures the pgvector extension is installed.
    - Does NOT create tables (that is Alembic's job).
    """
    async with engine.begin() as conn:
        # Verify connectivity
        await conn.execute(text("SELECT 1"))

        # Install pgvector extension if not already present
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    from app.core.logging import get_logger
    logger = get_logger(__name__)
    logger.info("database_ready", url=settings.POSTGRES_HOST, db=settings.POSTGRES_DB)


async def close_db() -> None:
    """Called at application shutdown to release all connections."""
    await engine.dispose()
