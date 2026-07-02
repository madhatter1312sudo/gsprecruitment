"""
Talent OS — Celery worker configuration.
"""
from celery import Celery
from core.config import settings

celery_app = Celery(
    "talent_os",
    broker=settings.redis_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Europe/Amsterdam",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

# Auto-discover tasks
celery_app.autodiscover_tasks(["tasks"])