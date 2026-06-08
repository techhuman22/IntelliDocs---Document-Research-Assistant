"""
User repository — all database operations for the users table.

The repository is the only layer that writes SQL (via SQLAlchemy ORM).
Service methods call repository methods; routes call service methods.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.db.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    """Data access layer for the users table."""

    model = User

    # ── Read operations ───────────────────────────────────────────────────────

    async def get_by_email(self, email: str) -> Optional[User]:
        """
        Fetch a user by email address (case-insensitive).

        We store emails lowercased at write time, so a straight equality
        comparison is sufficient. This query uses the ix_users_email index.
        """
        result = await self._session.execute(
            select(User).where(User.email == email.lower())
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: UUID) -> Optional[User]:
        """Fetch a user by UUID primary key."""
        return await self._session.get(User, user_id)

    async def email_exists(self, email: str) -> bool:
        """
        Check whether an email is already registered without loading the full row.
        Used during registration to fail fast before hashing the password.
        """
        result = await self._session.execute(
            select(User.id).where(User.email == email.lower()).limit(1)
        )
        return result.scalar_one_or_none() is not None

    # ── Write operations ──────────────────────────────────────────────────────

    async def create_user(
        self,
        *,
        email: str,
        password_hash: str,
        full_name: Optional[str] = None,
    ) -> User:
        """
        Create a new user record.

        Flushes to get the DB-generated UUID and timestamps without committing
        the parent transaction — the caller (service) decides when to commit.
        """
        return await self.create(
            email=email.lower(),
            password_hash=password_hash,
            full_name=full_name,
            is_active=True,
            is_verified=False,
            plan_tier="free",
        )

    async def update_user(self, user: User, **fields) -> User:
        """
        Update allowed profile fields. The caller must pass only
        validated, allowlisted fields — never pass raw request data directly.
        """
        allowed_fields = {"full_name", "is_active", "is_verified", "plan_tier", "password_hash"}
        filtered = {k: v for k, v in fields.items() if k in allowed_fields}
        return await self.update(user, **filtered)

    async def delete_user(self, user: User) -> None:
        """Hard-delete a user. Cascades to all related rows per FK constraints."""
        await self.delete(user)

    async def mark_verified(self, user: User) -> User:
        """Mark the user's email as verified."""
        return await self.update(user, is_verified=True)

    async def deactivate(self, user: User) -> User:
        """Soft-disable a user without deleting their data."""
        return await self.update(user, is_active=False)
