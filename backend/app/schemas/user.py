"""
User request and response schemas.

UserResponse is imported by auth.py (LoginResponse), so it must not
import from auth.py — that would create a circular import.
"""

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import EmailStr, Field, field_validator

from app.schemas.base import BaseRequest, BaseResponse


class UserResponse(BaseResponse):
    """
    Public-safe user representation — never includes password_hash.
    Used in /users/me responses and embedded in LoginResponse.
    """

    id: UUID
    email: EmailStr
    full_name: Optional[str]
    is_active: bool
    is_verified: bool
    plan_tier: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserUpdateRequest(BaseRequest):
    """
    Request body for PATCH /api/v1/users/me.
    All fields optional — only provided fields are updated.
    """

    full_name: Optional[str] = Field(
        default=None,
        min_length=2,
        max_length=255,
        examples=["Jane Smith"],
    )

    @field_validator("full_name", mode="before")
    @classmethod
    def normalize_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        normalized = " ".join(v.strip().split())
        if len(normalized) < 2:
            raise ValueError("full_name must be at least 2 characters after trimming.")
        return normalized


class UserPublicResponse(BaseResponse):
    """Minimal user representation for public-facing contexts."""

    id: UUID
    full_name: Optional[str]
    plan_tier: str
