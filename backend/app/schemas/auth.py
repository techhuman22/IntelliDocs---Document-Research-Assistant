"""
Authentication request and response schemas.

All schemas use Pydantic v2 with strict validation.
Passwords are validated for strength at the schema level before
they ever reach the service layer.
"""

import re
from typing import Optional

from pydantic import EmailStr, Field, field_validator, model_validator

from app.schemas.base import BaseRequest, BaseResponse
from app.schemas.user import UserResponse


# ─────────────────────────────────────────────────────────────────────────────
# Password Validation
# ─────────────────────────────────────────────────────────────────────────────

def validate_password_strength(password: str) -> str:
    """
    Enforce password strength rules.

    Requirements:
      - At least 8 characters
      - At least one uppercase letter
      - At least one lowercase letter
      - At least one digit
      - At least one special character

    Raises ValueError (caught by Pydantic as a validation error) on failure.
    """
    errors: list[str] = []

    if len(password) < 8:
        errors.append("at least 8 characters")
    if not re.search(r"[A-Z]", password):
        errors.append("at least one uppercase letter (A-Z)")
    if not re.search(r"[a-z]", password):
        errors.append("at least one lowercase letter (a-z)")
    if not re.search(r"\d", password):
        errors.append("at least one digit (0-9)")
    if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?`~]", password):
        errors.append("at least one special character (!@#$%^&*...)")

    if errors:
        raise ValueError(f"Password must contain: {', '.join(errors)}.")

    return password


# ─────────────────────────────────────────────────────────────────────────────
# Registration
# ─────────────────────────────────────────────────────────────────────────────

class UserRegisterRequest(BaseRequest):
    """
    Request body for POST /api/v1/auth/register.

    The `full_name` field is trimmed and collapsed (multiple spaces → one).
    The `email` is lowercased to prevent duplicate accounts via case variation.
    """

    full_name: str = Field(
        min_length=2,
        max_length=255,
        examples=["Jane Doe"],
        description="User's display name. 2–255 characters.",
    )
    email: EmailStr = Field(
        examples=["jane@example.com"],
        description="Must be a valid email address. Case-insensitive.",
    )
    password: str = Field(
        min_length=8,
        max_length=128,
        examples=["MyStr0ng!Pass"],
        description="Minimum 8 chars with upper, lower, digit, and special character.",
    )

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        """Lowercase and strip email to prevent duplicate accounts."""
        return v.strip().lower()

    @field_validator("full_name", mode="before")
    @classmethod
    def normalize_name(cls, v: str) -> str:
        """Strip and collapse whitespace in names."""
        return " ".join(v.strip().split())

    @field_validator("password")
    @classmethod
    def check_password_strength(cls, v: str) -> str:
        return validate_password_strength(v)


# ─────────────────────────────────────────────────────────────────────────────
# Login
# ─────────────────────────────────────────────────────────────────────────────

class UserLoginRequest(BaseRequest):
    """Request body for POST /api/v1/auth/login."""

    email: EmailStr = Field(examples=["jane@example.com"])
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()


# ─────────────────────────────────────────────────────────────────────────────
# Token Responses
# ─────────────────────────────────────────────────────────────────────────────

class TokenPair(BaseResponse):
    """
    Access + refresh token pair returned after login or token refresh.

    The access_token is a short-lived JWT (15 min).
    The refresh_token is a long-lived JWT (7 days) — clients must store
    it securely (httpOnly cookie recommended; we support both).
    """

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access token lifetime in seconds.")


class AccessTokenResponse(BaseResponse):
    """Returned by the refresh endpoint — new access token only."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int


class LoginResponse(BaseResponse):
    """Full login response — tokens + user profile."""

    tokens: TokenPair
    user: UserResponse


# ─────────────────────────────────────────────────────────────────────────────
# Refresh / Logout
# ─────────────────────────────────────────────────────────────────────────────

class RefreshTokenRequest(BaseRequest):
    """
    Request body for POST /api/v1/auth/refresh.

    Clients that store the refresh token in a cookie send it via the cookie
    (handled transparently by FastAPI). Clients storing in localStorage
    must send it in this body.
    """

    refresh_token: str = Field(min_length=1)


class LogoutRequest(BaseRequest):
    """
    Request body for POST /api/v1/auth/logout.
    The refresh_token is required so the server can revoke it immediately.
    """

    refresh_token: str = Field(min_length=1)


# ─────────────────────────────────────────────────────────────────────────────
# Password Change
# ─────────────────────────────────────────────────────────────────────────────

class ChangePasswordRequest(BaseRequest):
    """Request body for POST /api/v1/users/me/change-password."""

    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)
    confirm_new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def check_new_password_strength(cls, v: str) -> str:
        return validate_password_strength(v)

    @model_validator(mode="after")
    def passwords_match(self) -> "ChangePasswordRequest":
        if self.new_password != self.confirm_new_password:
            raise ValueError("new_password and confirm_new_password do not match.")
        return self


# ─────────────────────────────────────────────────────────────────────────────
# Generic message response
# ─────────────────────────────────────────────────────────────────────────────

class MessageResponse(BaseResponse):
    """Simple acknowledgement response."""

    message: str
