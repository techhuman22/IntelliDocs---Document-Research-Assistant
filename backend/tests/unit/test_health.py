"""
Unit tests for the health check endpoint.

Tests verify:
  - Correct response structure
  - HTTP 200 when all deps are healthy
  - HTTP 503 when a dependency is unavailable
  - Response schema matches HealthResponse
"""

import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_health_check_returns_200(client: AsyncClient):
    """Health endpoint returns 200 when all dependencies are reachable."""
    with (
        patch("app.api.v1.health._check_database", new_callable=AsyncMock) as mock_db,
        patch("app.api.v1.health._check_redis", new_callable=AsyncMock) as mock_redis,
        patch("app.api.v1.health._check_gemini", new_callable=AsyncMock) as mock_gemini,
    ):
        mock_db.return_value = {"status": "ok", "latency_ms": 5, "detail": ""}
        mock_redis.return_value = {"status": "ok", "latency_ms": 1, "detail": ""}
        mock_gemini.return_value = {"status": "ok", "latency_ms": 0, "detail": "API key present."}

        response = await client.get("/api/v1/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "dependencies" in data
    assert "version" in data
    assert "environment" in data


@pytest.mark.asyncio
async def test_health_check_returns_503_on_db_failure(client: AsyncClient):
    """Health endpoint returns 503 when the database is unreachable."""
    with (
        patch("app.api.v1.health._check_database", new_callable=AsyncMock) as mock_db,
        patch("app.api.v1.health._check_redis", new_callable=AsyncMock) as mock_redis,
        patch("app.api.v1.health._check_gemini", new_callable=AsyncMock) as mock_gemini,
    ):
        mock_db.return_value = {"status": "error", "latency_ms": 30, "detail": "Database unreachable."}
        mock_redis.return_value = {"status": "ok", "latency_ms": 1, "detail": ""}
        mock_gemini.return_value = {"status": "ok", "latency_ms": 0, "detail": "API key present."}

        response = await client.get("/api/v1/health")

    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "error"


@pytest.mark.asyncio
async def test_health_response_has_required_fields(client: AsyncClient):
    """Health response always contains status, version, environment, dependencies."""
    with (
        patch("app.api.v1.health._check_database", new_callable=AsyncMock) as mock_db,
        patch("app.api.v1.health._check_redis", new_callable=AsyncMock) as mock_redis,
        patch("app.api.v1.health._check_gemini", new_callable=AsyncMock) as mock_gemini,
    ):
        for mock in (mock_db, mock_redis, mock_gemini):
            mock.return_value = {"status": "ok", "latency_ms": 1, "detail": ""}

        response = await client.get("/api/v1/health")

    data = response.json()
    required_keys = {"status", "version", "environment", "dependencies"}
    assert required_keys.issubset(data.keys())

    required_deps = {"database", "redis", "gemini_api"}
    assert required_deps.issubset(data["dependencies"].keys())
