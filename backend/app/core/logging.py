"""
Structured logging configuration using structlog.

In development (LOG_FORMAT=console): colored, human-readable output.
In production  (LOG_FORMAT=json):    newline-delimited JSON, parseable by
                                     Datadog, Loki, CloudWatch, etc.

Every log event is enriched with:
  - timestamp (ISO 8601, UTC)
  - log level
  - logger name (module path)
  - request_id (injected by middleware via contextvars)
  - user_id    (injected by auth dependency via contextvars)

Usage:
    from app.core.logging import get_logger
    logger = get_logger(__name__)
    logger.info("document_uploaded", document_id=str(doc.id), size_bytes=1024)
"""

import logging
import logging.config
import sys
from contextvars import ContextVar
from typing import Any

import structlog
from structlog.types import EventDict, WrappedLogger

from app.config.settings import settings

# ── Context Variables ─────────────────────────────────────────────────────────
# These are set per-request by middleware and auth dependencies, then
# automatically included in every log event via the context processor below.

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
user_id_var: ContextVar[str] = ContextVar("user_id", default="-")


# ── Custom Processors ─────────────────────────────────────────────────────────

def _inject_request_context(
    logger: WrappedLogger, method: str, event_dict: EventDict
) -> EventDict:
    """Add request_id and user_id from context vars to every log event."""
    event_dict["request_id"] = request_id_var.get()
    event_dict["user_id"] = user_id_var.get()
    return event_dict


def _drop_color_message_key(
    logger: WrappedLogger, method: str, event_dict: EventDict
) -> EventDict:
    """Remove uvicorn's 'color_message' key — redundant in JSON logs."""
    event_dict.pop("color_message", None)
    return event_dict


# ── Standard Library Logging Config ──────────────────────────────────────────

def _configure_stdlib_logging() -> None:
    """
    Route Python's standard logging (used by SQLAlchemy, uvicorn, etc.)
    through structlog so all log output is unified.
    """
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.DEBUG)

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "structlog": {
                    "()": structlog.stdlib.ProcessorFormatter,
                    "processors": [
                        structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                        structlog.dev.ConsoleRenderer()
                        if settings.LOG_FORMAT == "console"
                        else structlog.processors.JSONRenderer(),
                    ],
                    "foreign_pre_chain": [
                        structlog.stdlib.add_log_level,
                        structlog.stdlib.add_logger_name,
                        structlog.processors.TimeStamper(fmt="iso", utc=True),
                    ],
                }
            },
            "handlers": {
                "default": {
                    "class": "logging.StreamHandler",
                    "stream": sys.stdout,
                    "formatter": "structlog",
                },
            },
            "root": {
                "handlers": ["default"],
                "level": level,
            },
            "loggers": {
                # Suppress noisy SQLAlchemy pool logs unless debugging
                "sqlalchemy.engine": {
                    "level": "DEBUG" if settings.DB_ECHO else "WARNING",
                    "propagate": True,
                },
                "sqlalchemy.pool": {
                    "level": "WARNING",
                    "propagate": True,
                },
                # Reduce uvicorn access log verbosity in production
                "uvicorn.access": {
                    "level": "WARNING" if settings.is_production else "INFO",
                    "propagate": True,
                },
            },
        }
    )


# ── Structlog Configuration ───────────────────────────────────────────────────

def configure_logging() -> None:
    """
    Must be called once at application startup (in main.py lifespan).

    Configures structlog's processor chain based on LOG_FORMAT setting.
    """
    _configure_stdlib_logging()

    shared_processors: list[Any] = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.contextvars.merge_contextvars,
        _inject_request_context,
        _drop_color_message_key,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.LOG_FORMAT == "console":
        # Human-readable colored output for development
        renderer = structlog.dev.ConsoleRenderer(colors=True)
    else:
        # Machine-parseable JSON for production log aggregators
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.LOG_LEVEL.upper(), logging.DEBUG)
        ),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    """
    Return a bound structlog logger for the given module.

    Usage:
        logger = get_logger(__name__)
        logger.info("event_name", key="value")
    """
    return structlog.get_logger(name)
