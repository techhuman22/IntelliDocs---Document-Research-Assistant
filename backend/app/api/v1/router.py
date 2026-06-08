"""
API v1 root router.

Every feature module registers its sub-router here. This file is the
single source of truth for the /api/v1/* URL namespace.

Adding a new feature:
  1. Create backend/app/api/v1/my_feature.py with an APIRouter.
  2. Import it here and call v1_router.include_router(...).
"""

from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.chat import router as chat_router
from app.api.v1.documents import router as documents_router
from app.api.v1.health import router as health_router
from app.api.v1.rag import router as rag_router
from app.api.v1.tools import router as tools_router
from app.api.v1.users import router as users_router

v1_router = APIRouter()

# ── Mount sub-routers ─────────────────────────────────────────────────────────

v1_router.include_router(
    health_router,
    tags=["Health"],
)

v1_router.include_router(
    auth_router,
    prefix="/auth",
    tags=["Authentication"],
)

v1_router.include_router(
    users_router,
    prefix="/users",
    tags=["Users"],
)

v1_router.include_router(
    documents_router,
    prefix="/documents",
    tags=["Documents"],
)

v1_router.include_router(
    rag_router,
    tags=["RAG"],
)

v1_router.include_router(
    chat_router,
    tags=["Chat"],
)

v1_router.include_router(
    tools_router,
    tags=["Tools"],
)
