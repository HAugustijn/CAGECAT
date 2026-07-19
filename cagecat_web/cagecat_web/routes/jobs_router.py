"""HTTP API for submitting analysis jobs and retrieving their results."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from cagecat_web.analysis import general_manager as gm
from cagecat_web.analysis.jobs import Job, JobNotFoundError, JobStore
from cagecat_web.analysis.tools import UnknownToolError, available_tools, get_tool
from cagecat_web.analysis.validation import ValidationError

jobs_router = APIRouter(prefix="/api", tags=["jobs"])

_RESERVED_FIELDS = {"title", "email", "files"}


class JobSummary(BaseModel):
    """Public view of a job's state."""

    id: str
    tool: str
    label: str
    status: str
    title: str | None = None
    parent_id: str | None = None
    error: str | None = None
    actions: list[dict[str, str]] = []
    created_at: str
    updated_at: str

    @classmethod
    def from_job(cls, job: Job) -> JobSummary:
        try:
            label = get_tool(job.tool).label
        except UnknownToolError:
            label = job.tool
        return cls(
            id=job.id,
            tool=job.tool,
            label=label,
            status=job.status.value,
            title=job.title,
            parent_id=job.parent_id,
            error=job.error,
            actions=gm.available_actions(job),
            created_at=job.created_at.isoformat(),
            updated_at=job.updated_at.isoformat(),
        )


@jobs_router.get("/tools")
async def list_tools() -> dict[str, list[str]]:
    """Return the names of all registered primary analysis tools."""
    return {"tools": available_tools()}


@jobs_router.post("/jobs/{tool}", status_code=status.HTTP_202_ACCEPTED)
async def create_job(
    tool: str,
    request: Request,
    files: list[UploadFile] = File(default_factory=list),
    title: str | None = Form(default=None),
    email: str | None = Form(default=None),
) -> JobSummary:
    """Submit a new job for ``tool`` with uploaded files and parameters."""
    form = await request.form()
    params: dict[str, Any] = {
        key: value
        for key, value in form.multi_items()
        if key not in _RESERVED_FIELDS and not hasattr(value, "filename")
    }

    uploads = [
        gm.RawUpload(filename=f.filename or "", data=await f.read()) for f in files
    ]

    try:
        job = gm.submit_job(
            tool_name=tool,
            uploads=uploads,
            params=params,
            title=title,
            email=email,
        )
    except UnknownToolError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown tool '{tool}'."
        ) from exc
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except gm.QueueUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The job queue is currently unavailable. Please try again later.",
        ) from exc

    return JobSummary.from_job(job)


@jobs_router.post(
    "/jobs/{parent_id}/actions/{action}", status_code=status.HTTP_202_ACCEPTED
)
async def create_action(parent_id: str, action: str, request: Request) -> JobSummary:
    """Run a derived analysis (gne, extract, recompute, ...) on a job's output."""
    form = await request.form()
    title = form.get("title")
    params: dict[str, Any] = {
        key: value
        for key, value in form.multi_items()
        if key not in _RESERVED_FIELDS and not hasattr(value, "filename")
    }

    try:
        job = gm.submit_derived_job(
            parent_id=parent_id,
            action=action,
            params=params,
            title=title if isinstance(title, str) else None,
        )
    except JobNotFoundError as exc:
        raise _not_found(parent_id) from exc
    except UnknownToolError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown action '{action}'."
        ) from exc
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except gm.QueueUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The job queue is currently unavailable. Please try again later.",
        ) from exc

    return JobSummary.from_job(job)


@jobs_router.get("/jobs/{job_id}")
async def get_job(job_id: str) -> JobSummary:
    """Return the current state of a job."""
    try:
        job = gm.get_job(job_id)
    except JobNotFoundError as exc:
        raise _not_found(job_id) from exc
    return JobSummary.from_job(job)


@jobs_router.get("/jobs/{job_id}/results")
async def get_job_results(job_id: str) -> dict[str, Any]:
    """Return the list of result files, summary and plot for a job."""
    try:
        return gm.get_job_results(job_id)
    except JobNotFoundError as exc:
        raise _not_found(job_id) from exc


@jobs_router.get("/jobs/{job_id}/clusters")
async def get_job_clusters(job_id: str) -> dict[str, Any]:
    """Return the selectable clusters from a cblaster search's session."""
    try:
        return {"clusters": gm.get_job_clusters(job_id)}
    except JobNotFoundError as exc:
        raise _not_found(job_id) from exc


@jobs_router.get("/jobs/{job_id}/view/{filename:path}")
async def view_result(job_id: str, filename: str) -> FileResponse:
    """Serve a result file inline (e.g. an HTML plot embedded in an iframe)."""
    path = _result_path(job_id, filename)
    return FileResponse(path, content_disposition_type="inline")


@jobs_router.get("/jobs/{job_id}/results/{filename:path}")
async def download_result(job_id: str, filename: str) -> FileResponse:
    """Download a single result file produced by a job."""
    path = _result_path(job_id, filename)
    return FileResponse(path, filename=path.name)


@jobs_router.get("/jobs/{job_id}/logs/{name}")
async def get_log(job_id: str, name: str) -> FileResponse:
    """Serve a job's captured stdout/stderr log inline."""
    if name not in {"stdout.log", "stderr.log"}:
        raise _not_found(f"{job_id}/logs/{name}")
    store = JobStore()
    try:
        store.get(job_id)
    except JobNotFoundError as exc:
        raise _not_found(job_id) from exc
    path = store.logs_dir(job_id) / name
    if not path.is_file():
        raise _not_found(f"{job_id}/logs/{name}")
    return FileResponse(
        path, media_type="text/plain", content_disposition_type="inline"
    )


def _result_path(job_id: str, filename: str):
    store = JobStore()
    try:
        store.get(job_id)
        return store.resolve_result_file(job_id, filename)
    except (JobNotFoundError, FileNotFoundError) as exc:
        raise _not_found(f"{job_id}/{filename}") from exc


def _not_found(what: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail=f"Not found: {what}"
    )
