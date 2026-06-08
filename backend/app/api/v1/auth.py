"""
Authentication route handlers.

Routes in this file are intentionally thin — they:
  1. Deserialize and validate the request body (Pydantic)
  2. Delegate to AuthService (business logic)
  3. Serialize the result (Pydantic response schema)
  4. Return the HTTP response

No business logic lives here. No SQL. No token creation logic.

Endpoints:
  POST /api/v1/auth/register   — create a new account
  POST /api/v1/auth/login      — authenticate and receive token pair
  POST /api/v1/auth/refresh    — rotate the refresh token
  POST /api/v1/auth/logout     — revoke the refresh token
"""

from typing import Optional

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse

from app.api.dependencies import get_auth_service, get_current_active_user
from app.db.models import User
from app.schemas.auth import (
    LoginResponse,
    LogoutRequest,
    MessageResponse,
    RefreshTokenRequest,
    TokenPair,
    UserLoginRequest,
    UserRegisterRequest,
)
from app.schemas.user import UserResponse
from app.services.auth_service import AuthService

router = APIRouter()


# ── Register ──────────────────────────────────────────────────────────────────

@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
    responses={
        201: {"description": "Account created successfully."},
        409: {"description": "Email address is already registered."},
        422: {"description": "Request validation failed (weak password, invalid email, etc.)."},
    },
)
async def register(
    body: UserRegisterRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> UserResponse:
    """
    Create a new user account.

    - Email must be unique (case-insensitive).
    - Password must satisfy strength requirements (see schema for rules).
    - Returns the created user profile — no tokens are issued on registration.
      The client must call /login after registration.
    """
    user = await auth_service.register(
        email=body.email,
        password=body.password,
        full_name=body.full_name,
    )
    return UserResponse.model_validate(user)


# ── Login ─────────────────────────────────────────────────────────────────────

@router.post(
    "/login",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate and receive JWT token pair",
    responses={
        200: {"description": "Login successful — returns access and refresh tokens."},
        401: {"description": "Invalid email or password."},
        403: {"description": "Account is deactivated."},
    },
)
async def login(
    body: UserLoginRequest,
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
) -> LoginResponse:
    """
    Authenticate with email and password.

    Returns:
      - **access_token**: Short-lived JWT (15 min). Include in every API request
        as `Authorization: Bearer <access_token>`.
      - **refresh_token**: Long-lived JWT (7 days). Use to obtain a new access
        token when it expires. Store securely (httpOnly cookie recommended).
      - **user**: Authenticated user's profile.

    Both "email not found" and "wrong password" return HTTP 401 to prevent
    user enumeration attacks.
    """
    user_agent = request.headers.get("User-Agent")
    client_ip = (
        request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or request.headers.get("X-Real-IP", "")
        or (request.client.host if request.client else None)
    )

    user, token_pair = await auth_service.login(
        email=body.email,
        password=body.password,
        user_agent=user_agent,
        ip_address=client_ip,
    )

    return LoginResponse(
        tokens=token_pair,
        user=UserResponse.model_validate(user),
    )


# ── Refresh Token ─────────────────────────────────────────────────────────────

@router.post(
    "/refresh",
    response_model=TokenPair,
    status_code=status.HTTP_200_OK,
    summary="Rotate the refresh token and issue a new token pair",
    responses={
        200: {"description": "New token pair issued. Old refresh token is now invalid."},
        401: {"description": "Refresh token is invalid, expired, or already used."},
    },
)
async def refresh(
    body: RefreshTokenRequest,
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
) -> TokenPair:
    """
    Exchange a valid refresh token for a new access + refresh token pair.

    **Token rotation**: The submitted refresh token is immediately revoked.
    If you attempt to use the same refresh token twice, the second call
    will fail — this detects token theft/replay attacks.

    The new refresh token returned must replace the old one in client storage.
    """
    user_agent = request.headers.get("User-Agent")
    client_ip = (
        request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or (request.client.host if request.client else None)
    )

    _user, token_pair = await auth_service.refresh_tokens(
        refresh_token=body.refresh_token,
        user_agent=user_agent,
        ip_address=client_ip,
    )

    return token_pair


# ── Logout ────────────────────────────────────────────────────────────────────

@router.post(
    "/logout",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Revoke the refresh token and end the session",
    responses={
        200: {"description": "Session terminated. Refresh token is now invalid."},
    },
)
async def logout(
    body: LogoutRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> MessageResponse:
    """
    Terminate a session by revoking the provided refresh token.

    The access token will remain technically valid until its natural expiry
    (15 minutes). Clients must discard it from memory on logout.

    This endpoint does not require authentication — the refresh token itself
    is the credential being revoked. This allows logout even when the access
    token has already expired.
    """
    await auth_service.logout(refresh_token=body.refresh_token)
    return MessageResponse(message="Successfully logged out.")


# ── Token Verification (dev utility) ─────────────────────────────────────────

@router.get(
    "/verify",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify the current access token and return the user profile",
    responses={
        200: {"description": "Token is valid."},
        401: {"description": "Token is invalid or expired."},
    },
)
async def verify_token(
    current_user: User = Depends(get_current_active_user),
) -> UserResponse:
    """
    Validate the Authorization header token and return the authenticated user.

    Useful for:
      - Frontend bootstrap: validate a stored token on app load
      - Debugging: confirm a token is valid and who it belongs to
    """
    return UserResponse.model_validate(current_user)
