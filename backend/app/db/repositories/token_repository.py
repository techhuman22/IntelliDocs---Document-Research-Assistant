"""
Refresh token repository — all database operations for the refresh_tokens table.

Handles the persistent side of token management. Redis handles the fast-path
lookup; this table is the ground truth for audit, revocation, and cleanup.
"""

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import and_, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.db.models import RefreshToken
from app.db.repositories.base import BaseRepository


def hash_jti(jti: str) -> str:
    """
    SHA-256 hash of a JWT JTI claim.

    We store the hash, not the raw JTI, so a DB breach cannot be used
    to construct valid refresh tokens. The JTI is still in the JWT
    (which the client holds) — we just don't store the plaintext server-side.
    """
    return hashlib.sha256(jti.encode()).hexdigest()


class TokenRepository(BaseRepository[RefreshToken]):
    """Data access layer for the refresh_tokens table."""

    model = RefreshToken

    # ── Read ──────────────────────────────────────────────────────────────────

    async def get_by_jti(self, jti: str) -> Optional[RefreshToken]:
        """
        Fetch a refresh token record by its JTI claim.
        Hashes the JTI before querying — the DB only stores hashes.
        """
        jti_hash = hash_jti(jti)
        result = await self._session.execute(
            select(RefreshToken).where(RefreshToken.jti_hash == jti_hash)
        )
        return result.scalar_one_or_none()

    async def get_active_tokens_for_user(self, user_id: UUID) -> list[RefreshToken]:
        """List all non-revoked, non-expired tokens for a user (active sessions)."""
        now = datetime.now(tz=timezone.utc)
        result = await self._session.execute(
            select(RefreshToken).where(
                and_(
                    RefreshToken.user_id == user_id,
                    RefreshToken.is_revoked.is_(False),
                    RefreshToken.expires_at > now,
                )
            )
        )
        return list(result.scalars().all())

    # ── Write ─────────────────────────────────────────────────────────────────

    async def create_token(
        self,
        *,
        user_id: UUID,
        jti: str,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> RefreshToken:
        """
        Persist a new refresh token record.

        Args:
            user_id:    Owner of the token.
            jti:        Raw JTI from the signed JWT (will be hashed before storage).
            user_agent: HTTP User-Agent header (for session management UI).
            ip_address: Client IP (for suspicious activity detection).
        """
        expires_at = datetime.now(tz=timezone.utc) + timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS
        )
        return await self.create(
            user_id=user_id,
            jti_hash=hash_jti(jti),
            expires_at=expires_at,
            is_revoked=False,
            user_agent=user_agent,
            ip_address=ip_address,
        )

    async def revoke_token(self, token: RefreshToken) -> RefreshToken:
        """Mark a single token as revoked (logout from one session)."""
        return await self.update(
            token,
            is_revoked=True,
            revoked_at=datetime.now(tz=timezone.utc),
        )

    async def revoke_by_jti(self, jti: str) -> bool:
        """
        Revoke a token by JTI without loading the ORM object first.
        Returns True if a row was actually updated, False if the JTI was not found.
        """
        jti_hash = hash_jti(jti)
        now = datetime.now(tz=timezone.utc)
        result = await self._session.execute(
            update(RefreshToken)
            .where(
                and_(
                    RefreshToken.jti_hash == jti_hash,
                    RefreshToken.is_revoked.is_(False),
                )
            )
            .values(is_revoked=True, revoked_at=now)
        )
        await self._session.flush()
        return result.rowcount > 0  # type: ignore[return-value]

    async def revoke_all_for_user(self, user_id: UUID) -> int:
        """
        Revoke ALL active tokens for a user.
        Called on: password change, account deactivation, forced logout.
        Returns the number of tokens revoked.
        """
        now = datetime.now(tz=timezone.utc)
        result = await self._session.execute(
            update(RefreshToken)
            .where(
                and_(
                    RefreshToken.user_id == user_id,
                    RefreshToken.is_revoked.is_(False),
                )
            )
            .values(is_revoked=True, revoked_at=now)
        )
        await self._session.flush()
        return result.rowcount  # type: ignore[return-value]

    async def delete_expired_tokens(self) -> int:
        """
        Hard-delete all expired tokens across all users.

        Called periodically by a scheduled Celery task (Phase 5) to keep
        the table from growing unboundedly. Safe to run anytime.
        """
        now = datetime.now(tz=timezone.utc)
        result = await self._session.execute(
            delete(RefreshToken).where(RefreshToken.expires_at <= now)
        )
        await self._session.flush()
        return result.rowcount  # type: ignore[return-value]
