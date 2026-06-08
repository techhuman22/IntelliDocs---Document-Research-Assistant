"""
Shared FastAPI dependencies.

Injected via Depends() into route handlers throughout the API.
This module is the composition root for dependency injection:
  - Database sessions
  - Redis connections
  - Service instances
  - Authenticated user

Dependency graph:
  get_db      ─┐
  get_redis   ─┼─▶ get_auth_service ─▶ get_current_user ─▶ get_current_active_user
               └─▶ get_user_service

Usage in a route:
    async def my_route(user: User = Depends(get_current_active_user)):
        ...
"""

from typing import AsyncGenerator, Optional

import redis.asyncio as aioredis
from fastapi import Cookie, Depends, Header, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.core.exceptions import InvalidTokenException, UnauthorizedException
from app.core.logging import get_logger, user_id_var
from app.db.base import get_db
from app.db.models import User
from app.services.auth_service import AuthService
from app.services.chat_service import ChatService
from app.services.document_service import DocumentService
from app.services.embedding_service import EmbeddingService
from app.services.retrieval_service import RetrievalService
from app.services.storage_service import StorageService
from app.services.user_service import UserService
from app.db.repositories.vector_repository import VectorRepository

logger = get_logger(__name__)

# HTTPBearer extracts the token from "Authorization: Bearer <token>"
# auto_error=False lets us return our own custom exception instead of the default 403
_bearer_scheme = HTTPBearer(auto_error=False)


# ── Redis Connection Pool ─────────────────────────────────────────────────────

_redis_pool: Optional[aioredis.ConnectionPool] = None


def _get_redis_pool() -> aioredis.ConnectionPool:
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = aioredis.ConnectionPool.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            max_connections=20,
        )
    return _redis_pool


async def get_redis() -> AsyncGenerator[aioredis.Redis, None]:
    """
    Dependency: yields a Redis client from the shared connection pool.

    The client is returned to the pool (not closed) after each request.
    """
    pool = _get_redis_pool()
    client = aioredis.Redis(connection_pool=pool)
    try:
        yield client
    finally:
        await client.aclose()


# ── Service Factories ─────────────────────────────────────────────────────────

async def get_auth_service(
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> AuthService:
    """
    Dependency: yields a fully-constructed AuthService.

    Both db and redis are injected by FastAPI's dependency system,
    which means they use the same session as the rest of the request.
    """
    return AuthService(session=db, redis=redis)


async def get_user_service(
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> UserService:
    """Dependency: yields a fully-constructed UserService."""
    return UserService(session=db, redis=redis)


# ── Authentication Dependencies ───────────────────────────────────────────────

def _extract_token(
    credentials: Optional[HTTPAuthorizationCredentials],
) -> str:
    """
    Extract the bearer token string from the Authorization header.

    Raises UnauthorizedException if no token is present.
    """
    if credentials is None or not credentials.credentials:
        raise UnauthorizedException(
            "Authentication required. Provide a Bearer token in the Authorization header."
        )
    return credentials.credentials


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    auth_service: AuthService = Depends(get_auth_service),
) -> User:
    """
    Core authentication dependency.

    Extracts the Bearer token, validates it (signature + expiry),
    loads and returns the corresponding User from the database.

    Raises UnauthorizedException / InvalidTokenException on any failure.

    Sets the user_id ContextVar so all log events within this request
    automatically include the authenticated user's ID.
    """
    token = _extract_token(credentials)

    user = await auth_service.get_user_from_access_token(token)

    # Inject user_id into logging context for this request
    user_id_var.set(str(user.id))

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Extends get_current_user with an explicit is_active check.

    AuthService.get_user_from_access_token already checks is_active,
    so this is a belt-and-suspenders guard for routes where you want
    the check to be very explicit in the route signature.
    """
    if not current_user.is_active:
        raise UnauthorizedException("Account is deactivated.")
    return current_user


async def get_storage_service() -> StorageService:
    """Dependency: yields a StorageService (stateless, no session needed)."""
    return StorageService()


async def get_document_service(
    db: AsyncSession = Depends(get_db),
    storage_service: StorageService = Depends(get_storage_service),
) -> DocumentService:
    """Dependency: yields a fully-constructed DocumentService."""
    return DocumentService(session=db, storage_service=storage_service)


async def get_embedding_service() -> EmbeddingService:
    """Dependency: yields a stateless EmbeddingService (Gemini client)."""
    return EmbeddingService()


async def get_vector_repository(
    db: AsyncSession = Depends(get_db),
) -> VectorRepository:
    """Dependency: yields a VectorRepository bound to the current request session."""
    return VectorRepository(db)


async def get_retrieval_service(
    db: AsyncSession = Depends(get_db),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
) -> RetrievalService:
    """Dependency: yields a RetrievalService (embed + pgvector search)."""
    return RetrievalService(session=db, embedding_service=embedding_service)


async def get_chat_service(
    db: AsyncSession = Depends(get_db),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
) -> ChatService:
    """Dependency: yields a ChatService with retrieval injected."""
    retrieval_svc = RetrievalService(session=db, embedding_service=embedding_service)
    return ChatService(session=db, retrieval_service=retrieval_svc)


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    auth_service: AuthService = Depends(get_auth_service),
) -> Optional[User]:
    """
    Dependency for routes that work for both authenticated and anonymous users.

    Returns the User if a valid token is present, None otherwise.
    Never raises — callers must handle the None case.
    """
    if credentials is None or not credentials.credentials:
        return None
    try:
        return await auth_service.get_user_from_access_token(credentials.credentials)
    except Exception:
        return None
