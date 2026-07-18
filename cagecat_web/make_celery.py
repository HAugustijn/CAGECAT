"""Celery entry point.

The canonical Celery application lives in
:mod:`cagecat_web.celery_app`. This module re-exports it so existing worker
commands referencing ``make_celery:celery_app`` keep working. Prefer::

    celery -A cagecat_web.celery_app.celery_app worker
"""

from cagecat_web.celery_app import celery_app

__all__ = ["celery_app"]
