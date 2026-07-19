"""High-level orchestration of the job lifecycle.
This is the single entry point the web layer uses to submit and inspect jobs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from cagecat_web.analysis.input_processor_cblaster import SESSION_FILE
from cagecat_web.analysis.jobs import Job, JobStatus, JobStore
from cagecat_web.analysis.session_processor import collect_results
from cagecat_web.analysis.tools import Tool, actions_for, get_tool
from cagecat_web.analysis.validation import ValidationError, validate_upload
from cagecat_web.config import Settings, get_settings


class QueueUnavailableError(RuntimeError):
    """Raised when a job cannot be enqueued because the broker is unreachable."""


@dataclass(frozen=True)
class RawUpload:
    """An uploaded file as received from the request, before validation."""

    filename: str
    data: bytes


def submit_job(
    *,
    tool_name: str,
    uploads: list[RawUpload],
    params: dict[str, Any],
    title: str | None = None,
    email: str | None = None,
    store: JobStore | None = None,
    settings: Settings | None = None,
) -> Job:
    """Validate inputs, persist a new job and enqueue it for execution.

    Arguments:
        tool_name: Registered tool to run.
        uploads: Raw uploaded files.
        params: Raw form parameters (validated per tool).
        title: Optional user-supplied label.
        email: Optional notification address.

    Returns:
        The queued :class:`Job`.

    Raises:
        UnknownToolError: If ``tool_name`` is not registered.
        ValidationError: If the uploads or parameters are invalid.
    """
    settings = settings or get_settings()
    store = store or JobStore(settings=settings)

    tool = get_tool(tool_name)
    _check_input_count(tool, uploads)

    validated = [
        validate_upload(
            upload.filename,
            upload.data,
            accepted_formats=tool.accepted_formats,
            settings=settings,
        )
        for upload in uploads
    ]
    cleaned_params = tool.clean_params(params)

    job = store.create(
        tool.name,
        title=_clean_title(title),
        email=_clean_email(email),
        params=cleaned_params,
    )

    stored_names = [
        store.save_input(job.id, item.filename, item.data) for item in validated
    ]
    job = store.update(job, input_files=stored_names, status=JobStatus.QUEUED)

    try:
        _enqueue(job)
    except QueueUnavailableError:
        store.update(
            job,
            status=JobStatus.FAILED,
            error="The job queue is currently unavailable. Please try again later.",
        )
        raise
    return store.get(job.id)


def submit_derived_job(
    *,
    parent_id: str,
    action: str,
    params: dict[str, Any],
    title: str | None = None,
    store: JobStore | None = None,
    settings: Settings | None = None,
) -> Job:
    """Create and enqueue a derived job (gne, extract, recompute, ...).

    Arguments:
        parent_id: Id of the completed search job to operate on.
        action: Name of a registered derived tool.
        params: Raw form parameters (validated per tool).
        title: Optional user-supplied label.

    Raises:
        JobNotFoundError: If the parent job does not exist.
        UnknownToolError: If ``action`` is not a registered tool.
        ValidationError: If the action is not applicable or the parent has no
            usable session, or the parameters are invalid.
    """
    settings = settings or get_settings()
    store = store or JobStore(settings=settings)

    parent = store.get(parent_id)
    tool = get_tool(action)
    if not tool.is_derived or parent.tool not in tool.parent_tools:
        raise ValidationError(
            f"'{tool.label}' cannot be run on a {parent.tool} job."
        )
    if parent.status is not JobStatus.COMPLETED:
        raise ValidationError("The parent job has not completed successfully.")

    parent_output = store.output_dir(parent_id)
    if tool.parent_input == "genbank":
        from cagecat_web.analysis.validation import FORMAT_EXTENSIONS

        genbank_exts = set(FORMAT_EXTENSIONS["genbank"])
        genbank_files = [
            p for p in parent_output.glob("*") if p.suffix.lower() in genbank_exts
        ]
        if not genbank_files:
            raise ValidationError(
                "This job produced no GenBank clusters to visualise."
            )
    elif not (parent_output / SESSION_FILE).is_file():
        raise ValidationError("The parent job has no session file to analyse.")

    cleaned_params = tool.clean_params(params)
    job = store.create(
        tool.name,
        title=_clean_title(title),
        params=cleaned_params,
        parent_id=parent_id,
    )
    job = store.update(job, status=JobStatus.QUEUED)

    try:
        _enqueue(job)
    except QueueUnavailableError:
        store.update(
            job,
            status=JobStatus.FAILED,
            error="The job queue is currently unavailable. Please try again later.",
        )
        raise
    return store.get(job.id)


def available_actions(job: Job) -> list[dict[str, str]]:
    """Return derived actions available for a completed job, for the UI."""
    if job.status is not JobStatus.COMPLETED:
        return []
    return [
        {"name": tool.name, "label": tool.label, "description": tool.description}
        for tool in actions_for(job.tool)
    ]


def get_job(job_id: str, store: JobStore | None = None) -> Job:
    """Return a stored job (raises ``JobNotFoundError`` if unknown)."""
    store = store or JobStore()
    return store.get(job_id)


def get_job_results(job_id: str, store: JobStore | None = None) -> dict[str, Any]:
    """Return the result-file listing and summary for a job."""
    store = store or JobStore()
    job = store.get(job_id)
    return collect_results(job, store)


def get_job_clusters(job_id: str, store: JobStore | None = None) -> list[dict[str, Any]]:
    """Return the selectable clusters from a cblaster search job's session."""
    import json

    from cagecat_web.analysis.input_processor_cblaster import parse_clusters

    store = store or JobStore()
    store.get(job_id)
    session_path = store.output_dir(job_id) / SESSION_FILE
    if not session_path.is_file():
        return []
    try:
        data = json.loads(session_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return parse_clusters(data)


def _enqueue(job: Job) -> None:
    """Send the job to the Celery queue for asynchronous execution.

    Raises:
        QueueUnavailableError: If the broker cannot be reached.
    """
    from kombu.exceptions import OperationalError

    from cagecat_web.analysis.tasks import run_job

    try:
        run_job.delay(job.id)
    except (OperationalError, ConnectionError, OSError) as exc:
        raise QueueUnavailableError(str(exc)) from exc


def _check_input_count(tool: Tool, uploads: list[RawUpload]) -> None:
    count = len(uploads)
    if count < tool.min_inputs:
        raise ValidationError(
            f"{tool.label} requires at least {tool.min_inputs} input file(s); "
            f"{count} provided."
        )
    if count > tool.max_inputs:
        raise ValidationError(
            f"{tool.label} accepts at most {tool.max_inputs} input file(s); "
            f"{count} provided."
        )


def _clean_title(title: str | None) -> str | None:
    if not title:
        return None
    return title.strip()[:60] or None


def _clean_email(email: str | None) -> str | None:
    if not email:
        return None
    email = email.strip()
    if not email:
        return None
    if "@" not in email or " " in email or len(email) > 254:
        raise ValidationError("The e-mail address is not valid.")
    return email
