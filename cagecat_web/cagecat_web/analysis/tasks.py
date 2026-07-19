"""Celery tasks that execute analysis tools in isolated job directories."""

from __future__ import annotations

import logging
import shutil
import subprocess
from typing import Any

from cagecat_web.analysis.jobs import JobStatus, JobStore
from cagecat_web.analysis.tools import get_tool
from cagecat_web.celery_app import celery_app
from cagecat_web.config import get_settings

logger = logging.getLogger(__name__)

#: Maximum automatic retries for transient (network) failures.
MAX_RETRIES = 2

#: Substrings in tool stderr that indicate a transient, retryable failure.
_TRANSIENT_MARKERS = (
    "Response ended prematurely",
    "ChunkedEncodingError",
    "ProtocolError",
    "IncompleteRead",
    "Connection aborted",
    "Connection reset",
    "ConnectionError",
    "ConnectionResetError",
    "RemoteDisconnected",
    "Read timed out",
    "ReadTimeout",
    "Max retries exceeded",
    "Temporary failure in name resolution",
    "503 Server Error",
    "502 Server Error",
    "500 Server Error",
)


def _is_transient(stderr: str | None) -> bool:
    """Whether ``stderr`` looks like a transient network error worth retrying."""
    if not stderr:
        return False
    return any(marker in stderr for marker in _TRANSIENT_MARKERS)


@celery_app.task(bind=True, name="cagecat.run_job", max_retries=MAX_RETRIES)
def run_job(self, job_id: str) -> dict[str, Any]:
    """Run the tool associated with ``job_id`` and record the outcome.

    The tool is executed as a subprocess whose working directory is the job's
    ``output/`` directory. stdout and stderr are captured to the job's
    ``logs/`` directory. The job's status is updated to ``running`` on start
    and to ``completed`` or ``failed`` on exit. Transient network failures
    (e.g. a dropped NCBI connection) are retried automatically.
    """
    settings = get_settings()
    store = JobStore(settings=settings)
    job = store.get(job_id)

    task_id = self.request.id
    job = store.update(job, status=JobStatus.RUNNING, task_id=task_id, error=None)

    tool = get_tool(job.tool)
    if job.parent_id:
        parent_output = store.output_dir(job.parent_id)
        if tool.parent_input == "genbank":
            # e.g. clinker aligning the GenBank clusters an extract job produced.
            from cagecat_web.analysis.validation import FORMAT_EXTENSIONS

            genbank_exts = set(FORMAT_EXTENSIONS["genbank"])
            input_paths = sorted(
                p for p in parent_output.glob("*") if p.suffix.lower() in genbank_exts
            )
        else:
            # Most derived jobs operate on the parent search's session file.
            from cagecat_web.analysis.input_processor_cblaster import SESSION_FILE

            input_paths = [parent_output / SESSION_FILE]
    else:
        input_paths = [store.input_dir(job_id) / name for name in job.input_files]
    output_dir = store.output_dir(job_id)
    logs_dir = store.logs_dir(job_id)

    # Start each attempt from a clean output directory so a retry never trips
    # over partial results (e.g. a half-written session file) from a prior run.
    for stale in output_dir.iterdir():
        if stale.is_file() or stale.is_symlink():
            stale.unlink()
        else:
            shutil.rmtree(stale, ignore_errors=True)

    try:
        command = tool.build_command(
            input_paths=input_paths, output_dir=output_dir, params=job.params
        )
    except Exception:
        logger.exception("Job %s: failed to build command", job_id)
        store.update(
            job,
            status=JobStatus.FAILED,
            error="The analysis could not be started due to an internal error.",
        )
        return {"job_id": job_id, "status": JobStatus.FAILED.value}

    logger.info("Job %s: running %s", job_id, " ".join(command))

    try:
        completed = subprocess.run(
            command,
            cwd=output_dir,
            capture_output=True,
            text=True,
            timeout=settings.job_timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        store.update(
            job,
            status=JobStatus.FAILED,
            error=f"The analysis exceeded the time limit of "
            f"{settings.job_timeout_seconds} seconds and was stopped.",
        )
        return {"job_id": job_id, "status": JobStatus.FAILED.value}
    except FileNotFoundError:
        store.update(
            job,
            status=JobStatus.FAILED,
            error=f"The '{tool.name}' executable is not installed on the server.",
        )
        return {"job_id": job_id, "status": JobStatus.FAILED.value}

    (logs_dir / "stdout.log").write_text(completed.stdout or "", encoding="utf-8")
    (logs_dir / "stderr.log").write_text(completed.stderr or "", encoding="utf-8")

    if completed.returncode != 0:
        if _is_transient(completed.stderr) and self.request.retries < MAX_RETRIES:
            attempt = self.request.retries + 1
            logger.warning(
                "Job %s: transient error, retry %d/%d", job_id, attempt, MAX_RETRIES
            )
            store.update(
                job,
                status=JobStatus.QUEUED,
                error=f"A temporary network error occurred; retrying "
                f"({attempt}/{MAX_RETRIES})…",
            )
            # Exponential backoff: 60s, 120s, 240s.
            raise self.retry(countdown=60 * (2**self.request.retries))
        store.update(
            job,
            status=JobStatus.FAILED,
            error=_short_error(completed.stderr, tool.name),
        )
        return {"job_id": job_id, "status": JobStatus.FAILED.value}

    store.update(job, status=JobStatus.COMPLETED)
    return {
        "job_id": job_id,
        "status": JobStatus.COMPLETED.value,
        "summary": tool.output_summary(output_dir),
    }


def _short_error(stderr: str | None, tool_name: str) -> str:
    """Return a error message from tool stderr."""
    if not stderr:
        return f"The {tool_name} analysis failed without an error message."
    last_line = stderr.strip().splitlines()[-1]
    return f"The {tool_name} analysis failed: {last_line}"
