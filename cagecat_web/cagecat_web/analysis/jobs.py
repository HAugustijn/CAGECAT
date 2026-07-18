"""Job model and filesystem-backed job store.

Each job owns an isolated working directory named after a random UUID::

    <jobs_dir>/<uuid>/
        metadata.json
        input/
        output/
        logs/

State is stored on disk (metadata) while the queue tracks task execution, so the
web process and the worker process can operate on the same shared volume without
a database.
"""

from __future__ import annotations

import os
import re
import shutil
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from cagecat_web.config import Settings, get_settings

_JOB_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)

_METADATA_FILE = "metadata.json"


class JobStatus(StrEnum):
    """Lifecycle states of a job."""

    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    INVALID = "invalid"

    @property
    def is_terminal(self) -> bool:
        """Whether no further state transitions are expected."""
        return self in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.INVALID}


class JobNotFoundError(KeyError):
    """Raised when a job id does not resolve to a stored job."""


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Job(BaseModel):
    """Metadata describing a single analysis job."""

    id: str
    tool: str
    status: JobStatus = JobStatus.PENDING
    title: str | None = None
    email: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    input_files: list[str] = Field(default_factory=list)
    task_id: str | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class JobStore:
    """Create, load and update jobs on the local filesystem.

    Arguments:
        root: Directory under which job directories live. Defaults to the
            configured :attr:`Settings.jobs_dir`.
    """

    def __init__(self, root: Path | None = None, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self.root = Path(root) if root is not None else self._settings.jobs_dir

    # -- path helpers -------------------------------------------------------
    @staticmethod
    def is_valid_id(job_id: str) -> bool:
        """Return whether ``job_id`` is a syntactically valid job identifier."""
        return bool(_JOB_ID_RE.match(job_id))

    def _job_dir(self, job_id: str) -> Path:
        if not self.is_valid_id(job_id):
            raise JobNotFoundError(job_id)
        return self.root / job_id

    def input_dir(self, job_id: str) -> Path:
        """Directory holding a job's validated input files."""
        return self._job_dir(job_id) / "input"

    def output_dir(self, job_id: str) -> Path:
        """Directory used as the tool's working directory for its results."""
        return self._job_dir(job_id) / "output"

    def logs_dir(self, job_id: str) -> Path:
        """Directory holding captured stdout/stderr logs."""
        return self._job_dir(job_id) / "logs"

    # -- lifecycle ----------------------------------------------------------
    def create(
        self,
        tool: str,
        *,
        title: str | None = None,
        email: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> Job:
        """Create a new job directory and return its :class:`Job`."""
        self.root.mkdir(parents=True, exist_ok=True)
        job_id = str(uuid.uuid4())
        job = Job(id=job_id, tool=tool, title=title, email=email, params=params or {})
        job_dir = self.root / job_id
        for sub in ("input", "output", "logs"):
            (job_dir / sub).mkdir(parents=True, exist_ok=True)
        self._write(job)
        return job

    def get(self, job_id: str) -> Job:
        """Load a job by id, raising :class:`JobNotFoundError` if unknown."""
        metadata = self._job_dir(job_id) / _METADATA_FILE
        try:
            raw = metadata.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise JobNotFoundError(job_id) from exc
        return Job.model_validate_json(raw)

    def update(self, job: Job, **changes: Any) -> Job:
        """Apply ``changes`` to ``job``, persist, and return the updated job."""
        updated = job.model_copy(update={**changes, "updated_at": _utcnow()})
        self._write(updated)
        return updated

    def save_input(self, job_id: str, filename: str, data: bytes) -> str:
        """Write validated upload ``data`` into the job's input directory.

        Returns the stored (sanitised) file name.
        """
        safe_name = Path(filename).name
        target = self.input_dir(job_id) / safe_name
        target.write_bytes(data)
        return safe_name

    def result_files(self, job_id: str) -> list[Path]:
        """Return the list of files produced in the job's output directory."""
        output = self.output_dir(job_id)
        if not output.is_dir():
            return []
        return sorted(p for p in output.rglob("*") if p.is_file())

    def resolve_result_file(self, job_id: str, filename: str) -> Path:
        """Safely resolve ``filename`` within a job's output directory.

        Raises :class:`FileNotFoundError` if the file does not exist or the
        resolved path escapes the output directory (path-traversal guard).
        """
        output = self.output_dir(job_id).resolve()
        candidate = (output / filename).resolve()
        if not candidate.is_file() or output not in candidate.parents:
            raise FileNotFoundError(filename)
        return candidate

    def delete(self, job_id: str) -> None:
        """Remove a job directory and all its contents."""
        shutil.rmtree(self._job_dir(job_id), ignore_errors=True)

    # -- internals ----------------------------------------------------------
    def _write(self, job: Job) -> None:
        """Atomically persist ``job`` metadata to disk."""
        job_dir = self.root / job.id
        job_dir.mkdir(parents=True, exist_ok=True)
        tmp = job_dir / (_METADATA_FILE + ".tmp")
        tmp.write_text(job.model_dump_json(indent=2), encoding="utf-8")
        os.replace(tmp, job_dir / _METADATA_FILE)
