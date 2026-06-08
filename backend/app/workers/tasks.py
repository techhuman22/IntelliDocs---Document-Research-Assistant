"""
Celery tasks for background document processing.

Design notes:

  Async vs sync:
    Celery workers run synchronous tasks. We create a fresh asyncio event loop
    per task execution and run the async processing pipeline inside it.
    This avoids the complexity of running Celery with asyncio-native mode
    (which is experimental as of Celery 5.4).

  Session lifecycle:
    Each task creates its own SQLAlchemy AsyncSession and disposes of it at the
    end. We do NOT reuse the FastAPI dependency-injected session — tasks run
    in a separate process with no access to the ASGI app.

  Retry logic:
    - DocumentProcessingException: non-retryable (parsing/embedding failure,
      stored in DB with status='failed')
    - Any other unexpected exception: retried up to 3 times with 60s backoff
      (e.g. network blip, DB connection hiccup during startup)

  Idempotency:
    DocumentProcessingService.process() handles force=False by default, so
    re-queuing an already-ready document is a no-op.
"""

import asyncio
import logging

from celery.exceptions import SoftTimeLimitExceeded

from app.core.exceptions import DocumentNotFoundException, DocumentProcessingException
from app.workers.celery_app import celery

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run a coroutine in a new event loop (Celery workers are synchronous)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _process_document_async(document_id: str, user_id: str) -> int:
    """
    Async wrapper — builds all dependencies from scratch and runs the pipeline.

    We instantiate all services here rather than relying on FastAPI DI because
    Celery workers have no ASGI context.
    """
    # Import inside the function to avoid circular imports at module load time
    from app.config.settings import settings
    from app.db.base import create_async_engine, async_sessionmaker
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.services.storage_service import StorageService
    from app.services.document_parser_service import DocumentParserService
    from app.services.chunking_service import ChunkingService
    from app.services.embedding_service import EmbeddingService
    from app.services.document_processing_service import DocumentProcessingService

    # Build a dedicated engine + session for this task
    from sqlalchemy.ext.asyncio import create_async_engine as _engine_factory
    engine = _engine_factory(
        settings.DATABASE_URL,
        pool_pre_ping=True,
        pool_size=2,         # small pool — each worker task needs at most 1 connection
        max_overflow=0,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)

    async with session_factory() as session:
        svc = DocumentProcessingService(
            session=session,
            storage_service=StorageService(),
            parser_service=DocumentParserService(),
            chunking_service=ChunkingService(),
            embedding_service=EmbeddingService(),
        )
        chunk_count = await svc.process(
            document_id=document_id,
            user_id=user_id,
        )

    await engine.dispose()
    return chunk_count


async def run_document_processing_inline(document_id: str, user_id: str) -> int:
    """
    Inline async version of document processing — used in dev mode without Celery.
    Reuses the same logic as _process_document_async but can be awaited directly
    from within a FastAPI route handler.
    """
    return await _process_document_async(document_id, user_id)


@celery.task(
    name="app.workers.tasks.process_document",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
)
def process_document(self, document_id: str, user_id: str) -> dict:
    """
    Celery task — triggers the RAG indexing pipeline for a single document.

    Args:
        document_id: UUID string of the Document record to process.
        user_id:     UUID string of the owning user.

    Returns:
        dict with status and chunk_count (stored in Redis result backend).

    Side-effects:
        - Updates documents.status to 'processing' then 'ready' / 'failed'.
        - Inserts rows into document_chunks.
    """
    logger.info(
        "process_document_task_started",
        extra={"document_id": document_id, "user_id": user_id},
    )

    try:
        chunk_count = _run_async(
            _process_document_async(document_id, user_id)
        )
        logger.info(
            "process_document_task_complete",
            extra={"document_id": document_id, "chunk_count": chunk_count},
        )
        return {"status": "ready", "chunk_count": chunk_count}

    except (DocumentNotFoundException, DocumentProcessingException) as exc:
        # Non-retryable — document is already marked 'failed' in the DB
        logger.error(
            "process_document_task_failed_no_retry",
            extra={"document_id": document_id, "error": str(exc)},
        )
        return {"status": "failed", "error": str(exc)}

    except SoftTimeLimitExceeded:
        logger.error(
            "process_document_task_timeout",
            extra={"document_id": document_id},
        )
        # The status stays as 'processing'; the hard kill will follow shortly
        # and the monitor can clean it up.  We do NOT retry on timeout.
        return {"status": "failed", "error": "Task timed out"}

    except Exception as exc:
        logger.warning(
            "process_document_task_retrying",
            extra={
                "document_id": document_id,
                "error": str(exc),
                "retry_count": self.request.retries,
            },
        )
        raise self.retry(exc=exc)
