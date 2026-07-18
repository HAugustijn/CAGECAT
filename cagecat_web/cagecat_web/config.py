"""Application configuration.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

#: Directory containing the ``cagecat_web`` Python package (``.../cagecat_web``).
PACKAGE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    """Runtime configuration for the CAGECAT web application and workers.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "CAGECAT"
    app_version: str = "2.0"

    # --- Job storage -------------------------------------------------------
    #: Root directory under which per-job working directories are created.
    jobs_dir: Path = PACKAGE_DIR / "upload"
    #: Delete stored job directories older than this many days.
    job_retention_days: int = 30
    #: Interval, in seconds, between cleanup sweeps.
    cleanup_interval_seconds: int = 24 * 60 * 60
    #: Hard wall-clock limit for a single tool invocation, in seconds.
    job_timeout_seconds: int = 60 * 60

    # --- Uploads -----------------------------------------------------------
    #: Maximum accepted size for a single uploaded file, in bytes (100 MiB).
    max_upload_bytes: int = 100 * 1024 * 1024
    #: Maximum number of individual sequences accepted in a query file.
    max_sequences: int = 10

    # --- Queue / broker ----------------------------------------------------
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None
    celery_task_always_eager: bool = False

    @property
    def broker_url(self) -> str:
        """Effective Celery broker URL."""
        return self.celery_broker_url or self.redis_url

    @property
    def result_backend(self) -> str:
        """Effective Celery result backend URL."""
        return self.celery_result_backend or self.redis_url

    def ensure_directories(self) -> None:
        """Create the directories this configuration depends on."""
        self.jobs_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide :class:`Settings` singleton."""
    return Settings()
