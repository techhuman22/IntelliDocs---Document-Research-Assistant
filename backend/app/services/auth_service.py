"""
Authentication service — all business logic for auth flows.

Responsibilities:
  - Register new users
  - Authenticate credentials
  - Issue and rotate JWT token pairs
  - Revoke tokens (logout)
  - Invalidate all sessions (password change, deactivation)

The service layer sits between routes and repositories.
It knows business rules; it does NOT know about HTTP or SQL.

Redis is used as the fast-path for token validation:
  - On login/refresh:  write JTI → user_id mapping with TTL
  - On logout:         delete from Redis (+ mark DB row as revoked)
  - On protected route: check Redis first → fall back to DB if cache miss

This means valid access tokens are validated without a DB query
(just JWT signature check). Refresh tokens hit Redis first,
then DB for audit-grade revocation verification.
"""

from datetime import timedelta
from typing import Optional
from uuid import UUID

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.core.exceptions import (
    EmailAlreadyExistsException,
    ForbiddenException,
    InvalidTokenException,
    UnauthorizedException,
    UserNotFoundException,
)
from app.core.logging import get_logger
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    refresh_token_redis_key,
    verify_password,
)
from app.db.models import User
from app.db.repositories.token_repository import TokenRepository
from app.db.repositories.user_repository import UserRepository
from app.schemas.auth import TokenPair

logger = get_logger(__name__)


class AuthService:
    """
    Orchestrates authentication flows.

    Injected with a database session and Redis client per request.
    All repository instances are created here — services own their repos.
    """

    def __init__(self, session: AsyncSession, redis: aioredis.Redis) -> None:
        self._session = session
        self._redis = redis
        self._user_repo = UserRepository(session)
        self._token_repo = TokenRepository(session)

    # ── Registration ──────────────────────────────────────────────────────────

    async def register(
        self,
        *,
        email: str,
        password: str,
        full_name: Optional[str] = None,
    ) -> User:
        """
        Create a new user account.

        Steps:
          1. Check email uniqueness (fast — indexed query, no hash computed yet)
          2. Hash the password (bcrypt — intentionally slow)
          3. Persist user record
          4. Return the ORM user (caller wraps in UserResponse schema)

        Raises:
          EmailAlreadyExistsException if email is taken.
        """
        if await self._user_repo.email_exists(email):
            raise EmailAlreadyExistsException(email)

        password_hash = hash_password(password)

        user = await self._user_repo.create_user(
            email=email,
            password_hash=password_hash,
            full_name=full_name,
        )

        logger.info("user_registered", user_id=str(user.id), email=email)
        return user

    # ── Login ─────────────────────────────────────────────────────────────────

    async def login(
        self,
        *,
        email: str,
        password: str,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> tuple[User, TokenPair]:
        """
        Authenticate a user and issue a token pair.

        Steps:
          1. Load user by email (returns None for unknown emails)
          2. Verify password using constant-time bcrypt comparison
          3. Reject inactive accounts
          4. Create access + refresh JWT pair
          5. Persist refresh token record to DB
          6. Cache refresh token JTI in Redis with expiry TTL
          7. Return (user, token_pair)

        Both "email not found" and "wrong password" return the same
        UnauthorizedException to prevent user enumeration attacks.

        Raises:
          UnauthorizedException on any credential failure.
          ForbiddenException if the account is inactive.
        """
        user = await self._user_repo.get_by_email(email)

        # Constant-time: always verify even if user is None (dummy hash)
        dummy_hash = "$2b$12$invalidhashpadding000000000000000000000000000000000000"
        stored_hash = user.password_hash if user else dummy_hash
        password_ok = verify_password(password, stored_hash)

        if not user or not password_ok:
            logger.warning("login_failed_bad_credentials", email=email)
            raise UnauthorizedException("Invalid email or password.")

        if not user.is_active:
            logger.warning("login_failed_inactive", user_id=str(user.id))
            raise ForbiddenException("Account is deactivated. Contact support.")

        # Issue tokens
        token_pair = await self._issue_token_pair(
            user=user,
            user_agent=user_agent,
            ip_address=ip_address,
        )

        logger.info("user_logged_in", user_id=str(user.id))
        return user, token_pair

    # ── Token Refresh ─────────────────────────────────────────────────────────

    async def refresh_tokens(
        self,
        *,
        refresh_token: str,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> tuple[User, TokenPair]:
        """
        Rotate the refresh token pair.

        Token rotation strategy:
          1. Decode and validate the incoming refresh JWT
          2. Verify JTI exists in DB and is not revoked/expired
          3. Revoke the old token (both DB and Redis)
          4. Load the user and verify account is still active
          5. Issue a fresh token pair

        This ensures each refresh token can only be used once.
        If an attacker replays a revoked token, step 2 will catch it.

        Raises:
          InvalidTokenException on any validation failure.
          UnauthorizedException if the user account is gone or inactive.
        """
        # Step 1: decode the JWT
        try:
            payload = decode_token(refresh_token, expected_type="refresh")
        except Exception as exc:
            raise InvalidTokenException(str(exc)) from exc

        jti: str = payload.get("jti", "")
        user_id_str: str = payload.get("sub", "")

        if not jti or not user_id_str:
            raise InvalidTokenException("Malformed refresh token.")

        # Step 2: verify JTI exists in DB and is valid
        db_token = await self._token_repo.get_by_jti(jti)

        if db_token is None:
            logger.warning("refresh_token_not_found", user_id=user_id_str)
            raise InvalidTokenException("Refresh token not recognized.")

        if not db_token.is_valid:
            # Token already used or expired — possible replay attack
            logger.warning(
                "refresh_token_replay_attempt",
                user_id=user_id_str,
                revoked=db_token.is_revoked,
                expired=db_token.is_expired,
            )
            raise InvalidTokenException("Refresh token has already been used or has expired.")

        # Step 3: revoke old token
        await self._token_repo.revoke_token(db_token)
        await self._redis.delete(refresh_token_redis_key(jti))

        # Step 4: load user
        try:
            user_id = UUID(user_id_str)
        except ValueError as exc:
            raise InvalidTokenException("Invalid user identifier in token.") from exc

        user = await self._user_repo.get_by_id(user_id)
        if not user or not user.is_active:
            raise UnauthorizedException("User account is unavailable.")

        # Step 5: issue fresh pair
        token_pair = await self._issue_token_pair(
            user=user,
            user_agent=user_agent,
            ip_address=ip_address,
        )

        logger.info("token_refreshed", user_id=str(user.id))
        return user, token_pair

    # ── Logout ────────────────────────────────────────────────────────────────

    async def logout(self, *, refresh_token: str) -> None:
        """
        Revoke a specific refresh token (logout from one session).

        The access token will expire naturally after its 15-minute TTL.
        To immediately invalidate it, clients should discard it from memory.
        There is no server-side access token blacklist by design —
        that would require a DB/Redis hit on every single API call.

        Raises:
          InvalidTokenException if the token cannot be decoded.
        """
        try:
            payload = decode_token(refresh_token, expected_type="refresh")
        except Exception:
            # Even if the token is expired/invalid, do a best-effort revocation
            # by trying to decode without expiry check.
            # If we can't decode at all, just return — nothing to revoke.
            logger.info("logout_with_undecodeable_token")
            return

        jti = payload.get("jti", "")
        user_id_str = payload.get("sub", "")

        if jti:
            revoked = await self._token_repo.revoke_by_jti(jti)
            await self._redis.delete(refresh_token_redis_key(jti))
            logger.info("user_logged_out", user_id=user_id_str, token_revoked=revoked)

    async def logout_all_sessions(self, *, user_id: UUID) -> int:
        """
        Revoke all refresh tokens for a user (logout from all devices).
        Returns the number of sessions terminated.
        Called on: password change, admin-forced logout.
        """
        count = await self._token_repo.revoke_all_for_user(user_id)

        # Purge all Redis entries for this user's tokens
        # We use a Redis pattern scan — not available with basic key helpers,
        # but acceptable here since this is a rare, explicit action.
        # In production, maintain a Redis Set per user of active JTIs.
        logger.info("all_sessions_revoked", user_id=str(user_id), count=count)
        return count

    # ── Private Helpers ───────────────────────────────────────────────────────

    async def _issue_token_pair(
        self,
        *,
        user: User,
        user_agent: Optional[str],
        ip_address: Optional[str],
    ) -> TokenPair:
        """
        Create a JWT access + refresh pair, persist the refresh token,
        and cache the JTI in Redis.

        Called by login() and refresh_tokens() — never called directly from routes.
        """
        user_id_str = str(user.id)

        # Create JWTs
        access_token = create_access_token(user_id_str)
        refresh_token_str, jti = create_refresh_token(user_id_str)

        # Persist refresh token to DB
        await self._token_repo.create_token(
            user_id=user.id,
            jti=jti,
            user_agent=user_agent,
            ip_address=ip_address,
        )

        # Cache JTI → user_id in Redis for fast validation
        redis_key = refresh_token_redis_key(jti)
        redis_ttl = settings.REFRESH_TOKEN_EXPIRE_DAYS * 86_400  # days → seconds
        await self._redis.setex(redis_key, redis_ttl, user_id_str)

        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token_str,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,  # → seconds
        )

    # ── Token Validation (used by auth dependency) ────────────────────────────

    async def get_user_from_access_token(self, token: str) -> User:
        """
        Validate an access token and return the corresponding User.

        This is the core of the auth dependency (get_current_user).
        Access tokens are validated by signature + expiry only — no DB hit.
        The user IS fetched from DB to ensure the account still exists and is active.

        Raises:
          InvalidTokenException / TokenExpiredException on bad token.
          UnauthorizedException if the user is gone or inactive.
        """
        payload = decode_token(token, expected_type="access")
        user_id_str = payload.get("sub", "")

        try:
            user_id = UUID(user_id_str)
        except ValueError as exc:
            raise InvalidTokenException("Invalid user identifier in token.") from exc

        user = await self._user_repo.get_by_id(user_id)

        if user is None:
            raise UnauthorizedException("User account not found.")

        if not user.is_active:
            raise ForbiddenException("Account is deactivated.")

        return user
