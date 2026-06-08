"""
Pytest configuration and shared fixtures.

Test database strategy:
  - A separate test database is used (POSTGRES_DB=agentflow_test).
  - Each test runs inside a transaction that is rolled back at the end —
    no data leaks between tests and no need to truncate tables.
  - The schema is created once per test session by running Alembic migrations.

Fixture hierarchy:
  event_loop     (session scope)  — single asyncio event loop for all tests
  engine         (session scope)  — one engine for the test session
  db_session     (function scope) — per-test transaction, always rolled back
  client         (function scope) — ASGI test client with overridden db dep
"""

import asyncio
from typing import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config.settings import settings
from app.db.base import Base, get_db
from app.main import create_application

# ── Test Database URL ─────────────────────────────────────────────────────────
# Use a separate test database to avoid polluting development data.
TEST_DATABASE_URL = settings.DATABASE_URL.replace(
    f"/{settings.POSTGRES_DB}",
    f"/{settings.POSTGRES_DB}_test",
)


# ── Event Loop ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Single event loop shared across all async tests in the session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ── Test Engine ───────────────────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="session")
async def test_engine():
    """Create test engine and run schema migrations once per test session."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


# ── Per-test Database Session (with rollback) ─────────────────────────────────

@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """
    Provide a per-test database session that rolls back after each test.

    Uses nested transactions (SAVEPOINTs) so that code under test can
    call session.commit() without actually persisting data.
    """
    async with test_engine.connect() as connection:
        await connection.begin()

        session_factory = async_sessionmaker(
            bind=connection,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )

        async with session_factory() as session:
            await session.begin_nested()   # SAVEPOINT

            yield session

            await session.rollback()       # always roll back to SAVEPOINT

        await connection.rollback()        # roll back the outer transaction


# ── ASGI Test Client ──────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    Provide an async test client with the database dependency overridden
    to use the per-test rolled-back session.
    """
    app = create_application()

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()
