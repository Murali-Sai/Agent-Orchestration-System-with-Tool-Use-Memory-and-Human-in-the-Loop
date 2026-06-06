"""Celery application instance.

Broker  : Redis (same instance used for working memory)
Backend : Redis (stores task results for polling)

Usage:
  Start worker:  celery -A workers.celery_app worker --loglevel=info
  Start Flower:  celery -A workers.celery_app flower --port=5555
"""
from __future__ import annotations
from celery import Celery
from config.settings import get_settings

settings = get_settings()

celery_app = Celery(
    "agent_orchestration",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # Each agent task can take several minutes
    task_soft_time_limit=600,   # 10 min soft limit → SoftTimeLimitExceeded
    task_time_limit=720,        # 12 min hard kill
    # Retry on broker connectivity issues
    broker_connection_retry_on_startup=True,
    # Keep results for 24 h (so UI can poll)
    result_expires=86400,
    # One worker process per task (agent tasks are CPU + I/O heavy)
    worker_prefetch_multiplier=1,
    task_acks_late=True,        # only ack after task finishes (safe re-queue on crash)
)
