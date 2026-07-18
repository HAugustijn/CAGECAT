"""Celery application used to run analysis jobs off the request thread.

Start a worker with::

    celery -A cagecat_web.celery_app.celery_app worker --loglevel=info

The broker and result backend both default to the configured Redis instance.
"""

from __future__ import annotations

from celery import Celery

from cagecat_web.config import get_settings

settings = get_settings()

celery_app = Celery(
    "cagecat",
    broker=settings.broker_url,
    backend=settings.result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_time_limit=settings.job_timeout_seconds + 60,
    task_soft_time_limit=settings.job_timeout_seconds,
    task_always_eager=settings.celery_task_always_eager,
    task_eager_propagates=settings.celery_task_always_eager,
)

# Import task modules so their @celery_app.task functions are registered.
celery_app.autodiscover_tasks(["cagecat_web.analysis"], related_name="tasks")
from cagecat_web.analysis import tasks as _tasks
