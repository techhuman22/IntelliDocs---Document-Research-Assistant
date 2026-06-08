"""
Generic async repository base class.

Provides standard CRUD operations for any SQLAlchemy ORM model.
Concrete repositories extend this and add domain-specific query methods.

Pattern: Repository isolates all database I/O from the service layer.
  Service  → knows business rules, calls repository methods
  Repository → knows SQL/ORM, knows nothing about HTTP or business rules

This clean separation means:
  - Services are testable without a database (mock the repository)
  - Repositories are testable without FastAPI (pass a test session)
  - Swapping PostgreSQL for another DB only requires changing repositories
"""

from typing import Any, Generic, Optional, Type, TypeVar
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """
    Async CRUD repository for a single SQLAlchemy model type.

    Usage:
        class UserRepository(BaseRepository[User]):
            model = User

        async def get_by_id(db, user_id):
            repo = UserRepository(db)
            return await repo.get(user_id)
    """

    model: Type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, id: UUID) -> Optional[ModelT]:
        """Fetch a single record by primary key. Returns None if not found."""
        return await self._session.get(self.model, id)

    async def get_or_raise(self, id: UUID, not_found_exc: Exception) -> ModelT:
        """Fetch a record by PK. Raises the provided exception if not found."""
        obj = await self._session.get(self.model, id)
        if obj is None:
            raise not_found_exc
        return obj

    async def create(self, **kwargs: Any) -> ModelT:
        """
        Create a new record. Flushes to DB to populate server-side defaults
        (id, created_at) without committing the transaction.
        """
        obj = self.model(**kwargs)
        self._session.add(obj)
        await self._session.flush()
        await self._session.refresh(obj)
        return obj

    async def update(self, obj: ModelT, **kwargs: Any) -> ModelT:
        """Update fields on an existing ORM instance and flush."""
        for field, value in kwargs.items():
            setattr(obj, field, value)
        self._session.add(obj)
        await self._session.flush()
        await self._session.refresh(obj)
        return obj

    async def delete(self, obj: ModelT) -> None:
        """Soft or hard delete — this base implementation does a hard delete."""
        await self._session.delete(obj)
        await self._session.flush()

    async def save(self, obj: ModelT) -> ModelT:
        """Persist an already-modified ORM object and refresh it."""
        self._session.add(obj)
        await self._session.flush()
        await self._session.refresh(obj)
        return obj
