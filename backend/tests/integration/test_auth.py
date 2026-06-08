"""
Integration tests for the full authentication flow.

These tests exercise the HTTP layer end-to-end using the ASGI test client.
They hit real database queries (using the rolled-back test transaction from conftest).
Redis calls are mocked so tests do not require a running Redis instance.
"""

from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient


# ── Fixtures ──────────────────────────────────────────────────────────────────

VALID_REGISTER_PAYLOAD = {
    "full_name": "Jane Doe",
    "email": "jane@example.com",
    "password": "MyStr0ng!Pass",
}

VALID_LOGIN_PAYLOAD = {
    "email": "jane@example.com",
    "password": "MyStr0ng!Pass",
}


def _mock_redis():
    """Return a mock Redis client that silently accepts all calls."""
    mock = AsyncMock()
    mock.setex = AsyncMock(return_value=True)
    mock.delete = AsyncMock(return_value=1)
    mock.get = AsyncMock(return_value=None)
    mock.aclose = AsyncMock()
    return mock


# ── Registration ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_register_success(client: AsyncClient):
    with patch("app.api.dependencies.get_redis") as mock_get_redis:
        mock_get_redis.return_value = _mock_redis()

        response = await client.post("/api/v1/auth/register", json=VALID_REGISTER_PAYLOAD)

    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "jane@example.com"
    assert data["full_name"] == "Jane Doe"
    assert "password_hash" not in data
    assert "id" in data
    assert data["plan_tier"] == "free"
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient):
    with patch("app.api.dependencies.get_redis") as mock_get_redis:
        mock_get_redis.return_value = _mock_redis()

        await client.post("/api/v1/auth/register", json=VALID_REGISTER_PAYLOAD)
        response = await client.post("/api/v1/auth/register", json=VALID_REGISTER_PAYLOAD)

    assert response.status_code == 409
    data = response.json()
    assert data["error"]["code"] == "EMAIL_ALREADY_EXISTS"


@pytest.mark.asyncio
async def test_register_weak_password(client: AsyncClient):
    payload = {**VALID_REGISTER_PAYLOAD, "password": "weakpassword"}
    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "REQUEST_VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_register_invalid_email(client: AsyncClient):
    payload = {**VALID_REGISTER_PAYLOAD, "email": "not-an-email"}
    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_email_is_lowercased(client: AsyncClient):
    payload = {**VALID_REGISTER_PAYLOAD, "email": "JANE@EXAMPLE.COM"}
    with patch("app.api.dependencies.get_redis") as mock_get_redis:
        mock_get_redis.return_value = _mock_redis()
        response = await client.post("/api/v1/auth/register", json=payload)

    assert response.status_code == 201
    assert response.json()["email"] == "jane@example.com"


# ── Login ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_login_success(client: AsyncClient):
    with patch("app.api.dependencies.get_redis") as mock_get_redis:
        mock_get_redis.return_value = _mock_redis()

        await client.post("/api/v1/auth/register", json=VALID_REGISTER_PAYLOAD)
        response = await client.post("/api/v1/auth/login", json=VALID_LOGIN_PAYLOAD)

    assert response.status_code == 200
    data = response.json()
    assert "tokens" in data
    assert "user" in data
    assert "access_token" in data["tokens"]
    assert "refresh_token" in data["tokens"]
    assert data["tokens"]["token_type"] == "bearer"
    assert data["user"]["email"] == "jane@example.com"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    with patch("app.api.dependencies.get_redis") as mock_get_redis:
        mock_get_redis.return_value = _mock_redis()

        await client.post("/api/v1/auth/register", json=VALID_REGISTER_PAYLOAD)
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "jane@example.com", "password": "WrongPass1!"},
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_login_unknown_email_returns_401(client: AsyncClient):
    """Should NOT return 404 — that would leak that the email doesn't exist."""
    with patch("app.api.dependencies.get_redis") as mock_get_redis:
        mock_get_redis.return_value = _mock_redis()

        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.com", "password": "AnyPass1!"},
        )

    assert response.status_code == 401


# ── Protected Routes ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_me_requires_auth(client: AsyncClient):
    response = await client.get("/api/v1/users/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_me_with_valid_token(client: AsyncClient):
    with patch("app.api.dependencies.get_redis") as mock_get_redis:
        mock_get_redis.return_value = _mock_redis()

        await client.post("/api/v1/auth/register", json=VALID_REGISTER_PAYLOAD)
        login_resp = await client.post("/api/v1/auth/login", json=VALID_LOGIN_PAYLOAD)
        access_token = login_resp.json()["tokens"]["access_token"]

        me_resp = await client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == "jane@example.com"


@pytest.mark.asyncio
async def test_get_me_with_invalid_token(client: AsyncClient):
    response = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": "Bearer totally.invalid.token"},
    )
    assert response.status_code == 401


# ── Verify Token Endpoint ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_verify_token(client: AsyncClient):
    with patch("app.api.dependencies.get_redis") as mock_get_redis:
        mock_get_redis.return_value = _mock_redis()

        await client.post("/api/v1/auth/register", json=VALID_REGISTER_PAYLOAD)
        login_resp = await client.post("/api/v1/auth/login", json=VALID_LOGIN_PAYLOAD)
        access_token = login_resp.json()["tokens"]["access_token"]

        verify_resp = await client.get(
            "/api/v1/auth/verify",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    assert verify_resp.status_code == 200
    assert verify_resp.json()["email"] == "jane@example.com"
