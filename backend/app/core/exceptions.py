"""
Custom exception classes and global FastAPI exception handlers.

Design:
  - All application exceptions inherit from AgentFlowException.
  - Each exception maps to a specific HTTP status code.
  - Exception handlers registered in main.py convert exceptions to
    standardized JSON error responses.
  - Unhandled exceptions are caught by a catch-all handler that returns
    500 without leaking internal details to clients.

Error response envelope (all endpoints):
    {
      "error": {
        "code":    "DOCUMENT_NOT_FOUND",
        "message": "Document with id abc-123 not found.",
        "details": {}   ← optional extra context
      }
    }
"""

from typing import Any, Optional
from uuid import UUID

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Base Exception
# ─────────────────────────────────────────────────────────────────────────────

class AgentFlowException(Exception):
    """
    Base class for all application-specific exceptions.

    Attributes:
        status_code: HTTP status code to return.
        code:        Machine-readable error code (SCREAMING_SNAKE_CASE).
        message:     Human-readable message safe to expose to clients.
        details:     Optional extra context (e.g. field name, resource id).
    """

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    code: str = "INTERNAL_ERROR"

    def __init__(
        self,
        message: str = "An unexpected error occurred.",
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        self.message = message
        self.details = details or {}
        super().__init__(message)

    def to_dict(self) -> dict:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            }
        }


# ─────────────────────────────────────────────────────────────────────────────
# Authentication & Authorization
# ─────────────────────────────────────────────────────────────────────────────

class UnauthorizedException(AgentFlowException):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "UNAUTHORIZED"

    def __init__(self, message: str = "Authentication required.") -> None:
        super().__init__(message)


class ForbiddenException(AgentFlowException):
    status_code = status.HTTP_403_FORBIDDEN
    code = "FORBIDDEN"

    def __init__(self, message: str = "You do not have permission to perform this action.") -> None:
        super().__init__(message)


class InvalidTokenException(AgentFlowException):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "INVALID_TOKEN"

    def __init__(self, message: str = "Token is invalid or has expired.") -> None:
        super().__init__(message)


class TokenExpiredException(AgentFlowException):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "TOKEN_EXPIRED"

    def __init__(self, message: str = "Token has expired. Please log in again.") -> None:
        super().__init__(message)


# ─────────────────────────────────────────────────────────────────────────────
# Resource Not Found
# ─────────────────────────────────────────────────────────────────────────────

class NotFoundException(AgentFlowException):
    status_code = status.HTTP_404_NOT_FOUND
    code = "NOT_FOUND"

    def __init__(self, resource: str, resource_id: Any = None) -> None:
        id_part = f" with id '{resource_id}'" if resource_id else ""
        super().__init__(
            message=f"{resource}{id_part} not found.",
            details={"resource": resource, "id": str(resource_id) if resource_id else None},
        )


class DocumentNotFoundException(NotFoundException):
    code = "DOCUMENT_NOT_FOUND"

    def __init__(self, document_id: Any = None) -> None:
        super().__init__("Document", document_id)


class SessionNotFoundException(NotFoundException):
    code = "SESSION_NOT_FOUND"

    def __init__(self, session_id: Any = None) -> None:
        super().__init__("Chat session", session_id)


class UserNotFoundException(NotFoundException):
    code = "USER_NOT_FOUND"

    def __init__(self, user_id: Any = None) -> None:
        super().__init__("User", user_id)


# ─────────────────────────────────────────────────────────────────────────────
# Validation & Business Logic
# ─────────────────────────────────────────────────────────────────────────────

class ValidationException(AgentFlowException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "VALIDATION_ERROR"

    def __init__(self, message: str, details: Optional[dict] = None) -> None:
        super().__init__(message, details)


class ConflictException(AgentFlowException):
    status_code = status.HTTP_409_CONFLICT
    code = "CONFLICT"

    def __init__(self, message: str, details: Optional[dict] = None) -> None:
        super().__init__(message, details)


class EmailAlreadyExistsException(ConflictException):
    code = "EMAIL_ALREADY_EXISTS"

    def __init__(self, email: str) -> None:
        super().__init__(
            message=f"An account with email '{email}' already exists.",
            details={"field": "email"},
        )


# ─────────────────────────────────────────────────────────────────────────────
# File & Document Processing
# ─────────────────────────────────────────────────────────────────────────────

class FileTooLargeException(AgentFlowException):
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    code = "FILE_TOO_LARGE"

    def __init__(self, max_size_mb: int) -> None:
        super().__init__(
            message=f"File exceeds the maximum allowed size of {max_size_mb} MB.",
            details={"max_size_mb": max_size_mb},
        )


class UnsupportedFileTypeException(AgentFlowException):
    status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    code = "UNSUPPORTED_FILE_TYPE"

    def __init__(self, file_type: str, allowed: list[str]) -> None:
        super().__init__(
            message=f"File type '{file_type}' is not supported.",
            details={"file_type": file_type, "allowed_types": allowed},
        )


class DocumentProcessingException(AgentFlowException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    code = "DOCUMENT_PROCESSING_FAILED"

    def __init__(self, message: str = "Document processing failed.") -> None:
        super().__init__(message)


# ─────────────────────────────────────────────────────────────────────────────
# Rate Limiting
# ─────────────────────────────────────────────────────────────────────────────

class RateLimitException(AgentFlowException):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "RATE_LIMIT_EXCEEDED"

    def __init__(self, retry_after: int = 60) -> None:
        super().__init__(
            message="Too many requests. Please slow down.",
            details={"retry_after_seconds": retry_after},
        )


# ─────────────────────────────────────────────────────────────────────────────
# External Services
# ─────────────────────────────────────────────────────────────────────────────

class ExternalServiceException(AgentFlowException):
    status_code = status.HTTP_502_BAD_GATEWAY
    code = "EXTERNAL_SERVICE_ERROR"

    def __init__(self, service: str, message: str = "") -> None:
        super().__init__(
            message=f"External service '{service}' is unavailable. {message}".strip(),
            details={"service": service},
        )


class GeminiAPIException(ExternalServiceException):
    code = "GEMINI_API_ERROR"

    def __init__(self, message: str = "") -> None:
        super().__init__("Gemini API", message)


# ─────────────────────────────────────────────────────────────────────────────
# Exception Handlers (registered in main.py)
# ─────────────────────────────────────────────────────────────────────────────

async def agentflow_exception_handler(
    request: Request, exc: AgentFlowException
) -> JSONResponse:
    """Handle all custom AgentFlowException subclasses."""
    logger.warning(
        "application_exception",
        code=exc.code,
        message=exc.message,
        status_code=exc.status_code,
        path=request.url.path,
        method=request.method,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_dict(),
    )


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Handle FastAPI/Starlette native HTTPExceptions (404, 405, etc.)."""
    logger.warning(
        "http_exception",
        status_code=exc.status_code,
        detail=exc.detail,
        path=request.url.path,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": "HTTP_ERROR",
                "message": str(exc.detail),
                "details": {},
            }
        },
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """
    Handle Pydantic v2 validation errors on request bodies and query params.
    Reformats the verbose Pydantic error list into our standard envelope.
    """
    errors = []
    for error in exc.errors():
        errors.append(
            {
                "field": " → ".join(str(loc) for loc in error["loc"]),
                "message": error["msg"],
                "type": error["type"],
            }
        )
    logger.info(
        "request_validation_error",
        path=request.url.path,
        error_count=len(errors),
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": {
                "code": "REQUEST_VALIDATION_ERROR",
                "message": "Request data failed validation.",
                "details": {"errors": errors},
            }
        },
    )


async def unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """
    Catch-all for any exception that slips through the other handlers.

    Logs the full traceback server-side but returns a generic message
    to the client so internal details are never leaked.
    """
    logger.exception(
        "unhandled_exception",
        exc_info=exc,
        path=request.url.path,
        method=request.method,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred. Our team has been notified.",
                "details": {},
            }
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    """
    Register all exception handlers on the FastAPI app.
    Called once in main.py during app creation.
    """
    app.add_exception_handler(AgentFlowException, agentflow_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)    # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)
