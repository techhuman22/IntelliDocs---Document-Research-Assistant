"""
User service — business logic for user profile management.

Handles CRUD operations on the authenticated user's own account.
Admin operations on other users are out of scope for Phase 2.
"""

from typing import Optional
from uuid import UUID

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenException, UserNotFoundException
from app.core.logging import get_logger
from app.core.security import hash_password, verify_password
from app.db.models import User
from app.db.repositories.token_repository import TokenRepository
from app.db.repositories.user_repository import UserRepository

logger = get_logger(__name__)


class UserService:
    """
    User profile management service.

    Keeps profile operations separate from authentication operations
    so each service has a single clear responsibility.
    """

    def __init__(self, session: AsyncSession, redis: aioredis.Redis) -> None:
        self._session = session
        self._redis = redis
        self._user_repo = UserRepository(session)
        self._token_repo = TokenRepository(session)

    # ── Read ──────────────────────────────────────────────────────────────────

    async def get_by_id(self, user_id: UUID) -> User:
        """
        Fetch a user by UUID. Raises UserNotFoundException if not found.
        Used by routes that need to re-fetch the user after a mutation.
        """
        user = await self._user_repo.get_by_id(user_id)
        if user is None:
            raise UserNotFoundException(user_id)
        return user

    # ── Update ────────────────────────────────────────────────────────────────

    async def update_profile(
        self,
        *,
        user: User,
        full_name: Optional[str] = None,
    ) -> User:
        """
        Update mutable profile fields for a user.

        Only fields explicitly passed (non-None) are updated.
        Returns the updated ORM instance.
        """
        updates: dict = {}

        if full_name is not None:
            updates["full_name"] = full_name

        if not updates:
            # Nothing to update — return the user unchanged
            return user

        updated_user = await self._user_repo.update_user(user, **updates)
        logger.info("user_profile_updated", user_id=str(user.id), fields=list(updates.keys()))
        return updated_user

    # ── Password Change ───────────────────────────────────────────────────────

    async def change_password(
        self,
        *,
        user: User,
        current_password: str,
        new_password: str,
    ) -> None:
        """
        Change the user's password.

        Steps:
          1. Verify the current password matches the stored hash
          2. Hash the new password
          3. Update the record
          4. Revoke ALL existing refresh tokens (force re-login everywhere)

        Raises:
          ForbiddenException if current_password is wrong.
        """
        if not verify_password(current_password, user.password_hash):
            logger.warning("password_change_wrong_current", user_id=str(user.id))
            raise ForbiddenException("Current password is incorrect.")

        new_hash = hash_password(new_password)
        await self._user_repo.update_user(user, password_hash=new_hash)

        # Revoke all sessions — after a password change, all devices
        # should re-authenticate. This is a security best practice.
        revoked_count = await self._token_repo.revoke_all_for_user(user.id)

        logger.info(
            "password_changed",
            user_id=str(user.id),
            sessions_revoked=revoked_count,
        )

    # ── Delete Account ────────────────────────────────────────────────────────

    async def delete_account(self, *, user: User, password: str) -> None:
        """
        Permanently delete the user's account.

        Requires password confirmation to prevent CSRF-triggered deletions.
        All related data (documents, sessions, tokens) cascade-delete via FK.

        Raises:
          ForbiddenException if password is wrong.
        """
        if not verify_password(password, user.password_hash):
            logger.warning("account_delete_wrong_password", user_id=str(user.id))
            raise ForbiddenException("Password is incorrect. Account not deleted.")

        user_id = str(user.id)
        await self._user_repo.delete_user(user)
        logger.info("account_deleted", user_id=user_id)
