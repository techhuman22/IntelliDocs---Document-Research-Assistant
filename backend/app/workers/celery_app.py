"""
Celery application instance for AgentFlow AI.

Worker startup command (from project root):
  celery -A app.workers.celery_app.celery worker --loglevel=info --concurrency=4

Task discovery:
  Celery auto-discovers tasks defined in app.workers.tasks via
  the include list below. Do not import tasks here — circular import risk.

Serialisation:
  Using JSON serialiser (not pickle) for task arguments so tasks are
  inspectable and secure by default.

Result backend:
  Set to Redis so tasks can report their status and result.
  The process_document task stores its result (chunk_count) so the
  API can poll completion without querying the database.

Soft time limit:
  120s soft + 180s hard. A 50MB PDF typically takes 30-90s.
  The soft limit raises SoftTimeLimitExceeded, which the task catches
  to mark the document as failed before the hard kill signal.
"""

from celery import Celery

from app.config.settings import settings

celery = Celery(
    "agentflow",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.REDIS_URL,
    include=["app.workers.tasks"],
)

celery.conf.update(
    # Serialisation
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # Timezone
    timezone="UTC",
    enable_utc=True,
    # Results
    result_expires=3600,           # keep task results in Redis for 1 hour
    task_ignore_result=False,
    # Time limits
    task_soft_time_limit=120,      # SIGTERM after 120s → task can clean up
    task_time_limit=180,           # SIGKILL after 180s
    # Retry
    task_acks_late=True,           # ack only after task completes (safer for re-queue)
    task_reject_on_worker_lost=True,
    # Routing — all tasks to default queue for now; Phase 5 may add priority queues
    task_default_queue="default",
    task_queues={
        "default": {"exchange": "default", "routing_key": "default"},
    },
)
