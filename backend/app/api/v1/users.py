"""
User profile route handlers.

All routes here require authentication (Depends(get_current_active_user)).
Users can only read and modify their own profile — no admin cross-user access.

Endpoints:
  GET    /api/v1/users/me                   — fetch own profile
  PATCH  /api/v1/users/me                   — update own profile
  POST   /api/v1/users/me/change-password   — change password (all sessions revoked)
  DELETE /api/v1/users/me                   — delete own account (requires password)
"""

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from app.api.dependencies import get_current_active_user, get_user_service
from app.db.models import User
from app.schemas.auth import ChangePasswordRequest, MessageResponse
from app.schemas.user import UserResponse, UserUpdateRequest
from app.services.user_service import UserService

router = APIRouter()


# ── GET /me ───────────────────────────────────────────────────────────────────

@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get the authenticated user's profile",
    responses={
        200: {"description": "User profile returned successfully."},
        401: {"description": "Not authenticated."},
    },
)
async def get_me(
    current_user: User = Depends(get_current_active_user),
) -> UserResponse:
    """
    Return the profile of the currently authenticated user.

    The user object is already loaded by the auth dependency —
    this route handler requires no additional database queries.
    """
    return UserResponse.model_validate(current_user)


# ── PATCH /me ─────────────────────────────────────────────────────────────────

@router.patch(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Update the authenticated user's profile",
    responses={
        200: {"description": "Profile updated successfully."},
        401: {"description": "Not authenticated."},
        422: {"description": "Validation failed."},
    },
)
async def update_me(
    body: UserUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    user_service: UserService = Depends(get_user_service),
) -> UserResponse:
    """
    Update mutable fields of the authenticated user's profile.

    Only include fields you want to change — omitted fields are left unchanged.
    Currently updatable fields: `full_name`.

    Password changes must go through the dedicated `/me/change-password` endpoint.
    """
    updated_user = await user_service.update_profile(
        user=current_user,
        full_name=body.full_name,
    )
    return UserResponse.model_validate(updated_user)


# ── POST /me/change-password ──────────────────────────────────────────────────

@router.post(
    "/me/change-password",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Change the authenticated user's password",
    responses={
        200: {"description": "Password changed. All sessions have been revoked."},
        401: {"description": "Not authenticated."},
        403: {"description": "Current password is incorrect."},
        422: {"description": "New password does not meet strength requirements."},
    },
)
async def change_password(
    body: ChangePasswordRequest,
    current_user: User = Depends(get_current_active_user),
    user_service: UserService = Depends(get_user_service),
) -> MessageResponse:
    """
    Change the authenticated user's password.

    **Security note**: Changing the password immediately revokes ALL active
    refresh tokens across all devices. The user must log in again on every
    device. The current access token remains valid for its remaining TTL.

    Requirements for new password:
    - At least 8 characters
    - At least one uppercase, lowercase, digit, and special character
    """
    await user_service.change_password(
        user=current_user,
        current_password=body.current_password,
        new_password=body.new_password,
    )
    return MessageResponse(
        message="Password changed successfully. All active sessions have been revoked."
    )


class _DeleteAccountRequest(BaseModel):
    password: str


# ── DELETE /me ────────────────────────────────────────────────────────────────

@router.delete(
    "/me",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Permanently delete the authenticated user's account",
    responses={
        200: {"description": "Account deleted. All data has been permanently removed."},
        401: {"description": "Not authenticated."},
        403: {"description": "Password confirmation incorrect."},
    },
)
async def delete_me(
    body: _DeleteAccountRequest,
    current_user: User = Depends(get_current_active_user),
    user_service: UserService = Depends(get_user_service),
) -> MessageResponse:
    """
    Permanently delete the authenticated user's account.

    **This action is irreversible.** All documents, chat sessions, and
    messages are permanently deleted (cascade).

    Password confirmation is required to prevent accidental or CSRF-triggered
    account deletion.
    """
    await user_service.delete_account(
        user=current_user,
        password=body.password,
    )
    return MessageResponse(message="Account permanently deleted.")


# ── Local schema for delete confirmation ─────────────────────────────────────
# Defined here (not in schemas/) because it's only used by this single route.

from app.schemas.base import BaseRequest
from pydantic import Field


class _DeleteAccountRequest(BaseRequest):
    """Password confirmation required to delete account."""

    password: str = Field(
        min_length=1,
        max_length=128,
        description="Current password — required to confirm account deletion.",
    )
