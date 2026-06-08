"""
Security utilities — JWT token lifecycle and password hashing.

Architecture:
  Access Token  — short-lived (15 min), stored in memory on the client.
  Refresh Token — long-lived (7 days), stored in an httpOnly cookie.
                  Its JTI (JWT ID) is stored in Redis. Logout invalidates
                  the JTI, making the token inert before it expires.

Token payload structure:
  {
    "sub":  "user-uuid",          # subject — always the user's UUID
    "type": "access" | "refresh", # prevents token type confusion attacks
    "jti":  "uuid4",              # unique per token — used for refresh token tracking
    "iat":  unix_timestamp,
    "exp":  unix_timestamp,
  }

Phase 2 will import and use these functions inside:
  POST /api/v1/auth/login
  POST /api/v1/auth/refresh
  POST /api/v1/auth/logout
  GET  /api/v1/auth/me
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config.settings import settings
from app.core.exceptions import InvalidTokenException, TokenExpiredException
from app.core.logging import get_logger

logger = get_logger(__name__)

# ── Password Hashing ──────────────────────────────────────────────────────────

# bcrypt is the industry standard — it is slow by design, defeating brute force.
# deprecated="auto" means passlib will upgrade weaker hashes transparently on next login.
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    """Hash a plain-text password using bcrypt. Store the result, never the plain text."""
    return _pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain-text password against a stored bcrypt hash.

    Uses constant-time comparison internally — immune to timing attacks.
    Returns False for any mismatch, including invalid hash format.
    """
    try:
        return _pwd_context.verify(plain_password, hashed_password)
    except Exception:
        return False


# ── Token Creation ────────────────────────────────────────────────────────────

def create_access_token(user_id: str) -> str:
    """
    Create a short-lived JWT access token.

    Args:
        user_id: The user's UUID as a string.

    Returns:
        Signed JWT string.
    """
    now = datetime.now(tz=timezone.utc)
    payload = {
        "sub": user_id,
        "type": "access",
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> tuple[str, str]:
    """
    Create a long-lived JWT refresh token.

    Returns:
        Tuple of (encoded_token, jti) — the JTI must be stored in Redis
        as the canonical record of this token's validity.
    """
    now = datetime.now(tz=timezone.utc)
    jti = str(uuid.uuid4())
    payload = {
        "sub": user_id,
        "type": "refresh",
        "jti": jti,
        "iat": now,
        "exp": now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    }
    token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return token, jti


# ── Token Validation ──────────────────────────────────────────────────────────

TokenType = Literal["access", "refresh"]


def decode_token(token: str, expected_type: TokenType) -> dict:
    """
    Decode and validate a JWT token.

    Validates:
      - Signature (using JWT_SECRET_KEY)
      - Expiry (exp claim)
      - Token type (prevents using a refresh token as an access token)

    Raises:
      TokenExpiredException  — token signature is valid but expired.
      InvalidTokenException  — any other validation failure.

    Args:
        token:         The encoded JWT string.
        expected_type: "access" or "refresh" — enforced to prevent token confusion.

    Returns:
        The decoded payload dict on success.
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except JWTError as exc:
        error_str = str(exc).lower()
        if "expired" in error_str:
            raise TokenExpiredException()
        raise InvalidTokenException(f"Token validation failed: {exc}") from exc

    # Type confusion guard — a refresh token must never be accepted as an access token
    if payload.get("type") != expected_type:
        logger.warning(
            "token_type_mismatch",
            expected=expected_type,
            received=payload.get("type"),
        )
        raise InvalidTokenException("Token type mismatch.")

    # sub claim must be present
    if not payload.get("sub"):
        raise InvalidTokenException("Token is missing subject claim.")

    return payload


def extract_user_id(token: str) -> str:
    """
    Extract the user ID from an access token. Raises on invalid/expired token.

    This is a convenience wrapper used by the auth dependency.
    """
    payload = decode_token(token, expected_type="access")
    return payload["sub"]


# ── Redis Key Helpers (used by auth service in Phase 2) ──────────────────────

def refresh_token_redis_key(jti: str) -> str:
    """Redis key for a refresh token. Pattern: refresh_token:{jti}"""
    return f"refresh_token:{jti}"


def user_token_blacklist_key(user_id: str) -> str:
    """Redis key pattern for revoking all tokens for a user on password change."""
    return f"token_blacklist:{user_id}"


# ── JTI Hashing (re-exported here for test convenience) ──────────────────────

def hash_jti(jti: str) -> str:
    """
    SHA-256 hash of a JWT JTI claim. Re-exported from token_repository
    so tests can import it from a single location (app.core.security).
    """
    import hashlib
    return hashlib.sha256(jti.encode()).hexdigest()
