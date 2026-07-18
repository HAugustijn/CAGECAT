"""Background cleanup of expired job directories.

Job results are transient: directories older than the configured retention
period are removed so stored data does not accumulate indefinitely. The
``example`` directory, if present, is always preserved.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from cagecat_web.config import Settings, get_settings

if TYPE_CHECKING:
    from pathlib import Path

EXCLUDED_DIR = "example"


def delete_old_directories(target_dir: Path, excluded_dir: str, age_limit_days: int) -> int:
    """Remove immediate sub-directories older than ``age_limit_days``.

    Arguments:
        target_dir: Directory whose sub-directories are candidates for removal.
        excluded_dir: Name of a sub-directory to never delete.
        age_limit_days: Directories last modified longer ago than this are removed.

    Returns:
        The number of directories deleted.
    """
    import shutil

    if not target_dir.is_dir():
        return 0

    now = datetime.now(UTC)
    age_limit = timedelta(days=age_limit_days)
    deleted = 0

    for path in target_dir.iterdir():
        if not path.is_dir() or path.name == excluded_dir:
            continue
        modified = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
        if now - modified > age_limit:
            shutil.rmtree(path, ignore_errors=True)
            deleted += 1
    return deleted


def main(settings: Settings | None = None) -> None:
    """Run an infinite loop, sweeping expired job directories periodically."""
    settings = settings or get_settings()
    settings.ensure_directories()

    while True:
        delete_old_directories(
            settings.jobs_dir, EXCLUDED_DIR, settings.job_retention_days
        )
        time.sleep(settings.cleanup_interval_seconds)


if __name__ == "__main__":
    main()
