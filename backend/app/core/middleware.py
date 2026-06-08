"""
ASGI middleware stack for AgentFlow AI.

Middleware is applied in the order it is added to the app.
Execution order (request): first added → last added
Execution order (response): last added → first added

Current middleware:
  1. RequestLoggingMiddleware   — logs every request/response with timing
  2. RequestIDMiddleware        — injects X-Request-ID header
  3. SecurityHeadersMiddleware  — adds OWASP-recommended security headers
  4. CORSMiddleware             (added in main.py via FastAPI built-in)

All middleware is pure ASGI — no dependencies on FastAPI routing.
"""

import time
import uuid
from typing import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.core.logging import get_logger, request_id_var

logger = get_logger(__name__)


# ── Request ID Middleware ─────────────────────────────────────────────────────

class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Assigns a unique ID to every incoming request.

    - Reads X-Request-ID header if the upstream proxy provides one.
    - Generates a new UUID v4 otherwise.
    - Sets the ID in the ContextVar so all log events within the request
      automatically include it.
    - Echoes the ID back in the response via X-Request-ID header so
      clients can correlate their requests with server logs.
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

        # Set the ContextVar — this is picked up by the logging processor
        token = request_id_var.set(request_id)

        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)

        response.headers["X-Request-ID"] = request_id
        return response


# ── Request Logging Middleware ─────────────────────────────────────────────────

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Logs every HTTP request and its response with timing information.

    Skips logging for:
      - /api/health  (too noisy in production)
      - /metrics     (Prometheus scrapes every 15s)

    Fields logged:
      method, path, status_code, duration_ms, client_ip, user_agent
    """

    SKIP_PATHS: frozenset[str] = frozenset({"/api/health", "/metrics", "/favicon.ico"})

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.url.path in self.SKIP_PATHS:
            return await call_next(request)

        start = time.perf_counter()

        # Extract client IP — check forwarded headers first (behind proxy/nginx)
        client_ip = (
            request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
            or request.headers.get("X-Real-IP", "")
            or (request.client.host if request.client else "unknown")
        )

        response: Response
        try:
            response = await call_next(request)
            duration_ms = int((time.perf_counter() - start) * 1000)

            log_fn = logger.warning if response.status_code >= 400 else logger.info
            log_fn(
                "http_request",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=duration_ms,
                client_ip=client_ip,
                user_agent=request.headers.get("User-Agent", "-"),
            )
        except Exception as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            logger.exception(
                "http_request_failed",
                method=request.method,
                path=request.url.path,
                duration_ms=duration_ms,
                client_ip=client_ip,
                exc_info=exc,
            )
            raise

        return response


# ── Security Headers Middleware ───────────────────────────────────────────────

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Adds OWASP-recommended security headers to every response.

    These headers are defensive defaults appropriate for an API backend.
    Adjust CSP if serving HTML from this origin.
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)

        # Prevent MIME-type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Prevent clickjacking (not strictly needed for an API, but safe)
        response.headers["X-Frame-Options"] = "DENY"

        # Force HTTPS for 1 year (only enable when serving over TLS)
        # response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        # Minimal referrer info leakage
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Disable browser features not needed by an API
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=()"
        )

        # Content Security Policy for API responses
        response.headers["Content-Security-Policy"] = "default-src 'none'"

        # Remove server identification header
        if "server" in response.headers:
            del response.headers["server"]

        return response


# ── Registration Helper ───────────────────────────────────────────────────────

def register_middleware(app: ASGIApp) -> None:
    """
    Register all middleware on the FastAPI app.

    Note: BaseHTTPMiddleware wraps the ASGI app in reverse order —
    the last add_middleware call is the outermost layer (runs first on request).

    Desired request execution order:
      RequestID → RequestLogging → SecurityHeaders → route handler

    Therefore we add them in reverse:
    """
    from fastapi import FastAPI
    assert isinstance(app, FastAPI)

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(RequestIDMiddleware)
