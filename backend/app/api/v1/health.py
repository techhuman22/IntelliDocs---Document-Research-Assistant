"""
Health check endpoint.

GET /api/v1/health

Returns the status of every critical dependency:
  - PostgreSQL database
  - Redis cache
  - Gemini API (lightweight check — does NOT consume tokens)

Used by:
  - Docker Compose healthcheck
  - Kubernetes liveness and readiness probes
  - Load balancer health checks
  - CI/CD deployment verification

Response codes:
  200 — all systems operational
  503 — one or more dependencies are unavailable
"""

import time
from typing import Literal

import redis.asyncio as aioredis
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text

from app.config.settings import settings
from app.core.logging import get_logger
from app.db.base import AsyncSessionLocal

logger = get_logger(__name__)
router = APIRouter()


# ── Response Schemas ──────────────────────────────────────────────────────────

class DependencyStatus(BaseModel):
    status: Literal["ok", "error"]
    latency_ms: int
    detail: str = ""


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "error"]
    version: str
    environment: str
    dependencies: dict[str, DependencyStatus]


# ── Dependency Checks ─────────────────────────────────────────────────────────

async def _check_database() -> DependencyStatus:
    """Ping PostgreSQL with a trivial query and measure round-trip time."""
    start = time.perf_counter()
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        latency_ms = int((time.perf_counter() - start) * 1000)
        return DependencyStatus(status="ok", latency_ms=latency_ms)
    except Exception as exc:
        latency_ms = int((time.perf_counter() - start) * 1000)
        logger.error("health_check_db_failed", error=str(exc))
        return DependencyStatus(
            status="error",
            latency_ms=latency_ms,
            detail="Database unreachable.",
        )


async def _check_redis() -> DependencyStatus:
    """Ping Redis and measure round-trip time."""
    start = time.perf_counter()
    try:
        client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=2,
        )
        await client.ping()
        await client.aclose()
        latency_ms = int((time.perf_counter() - start) * 1000)
        return DependencyStatus(status="ok", latency_ms=latency_ms)
    except Exception as exc:
        latency_ms = int((time.perf_counter() - start) * 1000)
        logger.error("health_check_redis_failed", error=str(exc))
        return DependencyStatus(
            status="error",
            latency_ms=latency_ms,
            detail="Redis unreachable.",
        )


async def _check_gemini() -> DependencyStatus:
    """
    Verify the Groq API key is configured.
    """
    start = time.perf_counter()
    if not settings.GROQ_API_KEY or settings.GROQ_API_KEY == "your-groq-api-key-here":
        latency_ms = int((time.perf_counter() - start) * 1000)
        return DependencyStatus(
            status="error",
            latency_ms=latency_ms,
            detail="GROQ_API_KEY is not configured.",
        )
    latency_ms = int((time.perf_counter() - start) * 1000)
    return DependencyStatus(status="ok", latency_ms=latency_ms, detail="Groq API key present.")


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.get(
    "/health",
    response_model=HealthResponse,
    summary="System health check",
    description=(
        "Returns the operational status of all system dependencies. "
        "Returns HTTP 200 when all dependencies are healthy, HTTP 503 otherwise."
    ),
    responses={
        200: {"description": "All systems operational"},
        503: {"description": "One or more dependencies are unavailable"},
    },
)
async def health_check() -> JSONResponse:
    """
    Perform parallel health checks against all system dependencies and
    return a unified status report.
    """
    import asyncio

    db_status, redis_status, gemini_status = await asyncio.gather(
        _check_database(),
        _check_redis(),
        _check_gemini(),
        return_exceptions=False,
    )

    dependencies = {
        "database": db_status,
        "redis": redis_status,
        "gemini_api": gemini_status,
    }

    all_ok = all(dep.status == "ok" for dep in dependencies.values())
    any_error = any(dep.status == "error" for dep in dependencies.values())

    if all_ok:
        overall_status = "ok"
        http_status = status.HTTP_200_OK
    elif any_error:
        overall_status = "error"
        http_status = status.HTTP_503_SERVICE_UNAVAILABLE
    else:
        overall_status = "degraded"
        http_status = status.HTTP_200_OK

    payload = HealthResponse(
        status=overall_status,
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT,
        dependencies=dependencies,
    )

    logger.info(
        "health_check",
        overall=overall_status,
        db=db_status.status,
        redis=redis_status.status,
        gemini=gemini_status.status,
    )

    return JSONResponse(
        status_code=http_status,
        content=payload.model_dump(),
    )
