"""
FastAPI application entry point.

This module:
  1. Configures structured logging (must happen before any other import that logs)
  2. Creates the FastAPI application instance
  3. Registers middleware (order matters — see middleware.py for details)
  4. Registers exception handlers
  5. Mounts the versioned API router
  6. Manages the application lifespan (startup / shutdown hooks)

Run locally:
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

Run in production:
    uvicorn app.main:app --workers 4 --host 0.0.0.0 --port 8000
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Logging must be configured before anything that emits log events
from app.core.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)

from app.api.v1.router import v1_router
from app.config.settings import settings
from app.core.exceptions import register_exception_handlers
from app.core.middleware import register_middleware
from app.db.base import close_db, init_db


# ── Application Lifespan ──────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Manage startup and shutdown events using the modern asynccontextmanager
    pattern (replaces deprecated @app.on_event("startup")).

    Startup:
      - Verify database connectivity
      - Ensure pgvector extension is installed
      - Create uploads directory if absent
      - Log application boot

    Shutdown:
      - Drain and close database connection pool
    """
    # ── Startup ───────────────────────────────────────────────────────────────
    logger.info(
        "application_starting",
        app=settings.APP_NAME,
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT,
        debug=settings.DEBUG,
    )

    # Ensure the upload directory exists
    settings.upload_dir_path          # property creates dir as a side effect

    # Connect to the database and install pgvector
    await init_db()

    logger.info("application_ready", host=settings.HOST, port=settings.PORT)

    yield  # Application is running — handle requests

    # ── Shutdown ──────────────────────────────────────────────────────────────
    logger.info("application_shutting_down")
    await close_db()
    logger.info("application_stopped")


# ── Application Factory ───────────────────────────────────────────────────────

def create_application() -> FastAPI:
    """
    Create and fully configure the FastAPI application.

    Separated into a factory function so tests can call create_application()
    to get a fresh instance rather than importing the module-level `app`.
    """
    application = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description=(
            "Multi-Agent Research & Analysis Platform. "
            "Upload documents, chat with AI, generate summaries, quizzes, and flashcards."
        ),
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
        # Disable FastAPI's default 422 response schema — we override it
        generate_unique_id_function=lambda route: route.name,
    )

    # ── CORS ──────────────────────────────────────────────────────────────────
    # Must be added before other middleware to ensure preflight OPTIONS requests
    # are handled before reaching auth middleware.
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,             # required for httpOnly cookie auth
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],    # let frontend read our request ID
    )

    # ── Custom Middleware ─────────────────────────────────────────────────────
    register_middleware(application)

    # ── Exception Handlers ────────────────────────────────────────────────────
    register_exception_handlers(application)

    # ── API Routes ────────────────────────────────────────────────────────────
    application.include_router(v1_router, prefix="/api/v1")

    return application


# Module-level app instance — this is what uvicorn imports
app: FastAPI = create_application()


# ── Root Redirect ─────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def root() -> dict:
    """Minimal root endpoint — useful for uptime monitors."""
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "health": "/api/v1/health",
    }
