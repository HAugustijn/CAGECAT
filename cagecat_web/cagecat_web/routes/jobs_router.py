"""HTTP API for submitting analysis jobs and retrieving their results."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from cagecat_web.analysis import general_manager as gm
from cagecat_web.analysis.jobs import Job, JobNotFoundError, JobStore
from cagecat_web.analysis.tools import UnknownToolError, available_tools
from cagecat_web.analysis.validation import ValidationError

jobs_router = APIRouter(prefix="/api", tags=["jobs"])

_RESERVED_FIELDS = {"title", "email", "files"}


class JobSummary(BaseModel):
    """Public view of a job's state."""

    id: str
    tool: str
    status: str
    title: str | None = None
    error: str | None = None
    created_at: str
    updated_at: str

    @classmethod
    def from_job(cls, job: Job) -> JobSummary:
        return cls(
            id=job.id,
            tool=job.tool,
            status=job.status.value,
            title=job.title,
            error=job.error,
            created_at=job.created_at.isoformat(),
            updated_at=job.updated_at.isoformat(),
        )


@jobs_router.get("/tools")
async def list_tools() -> dict[str, list[str]]:
    """Return the names of all registered analysis tools."""
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
    """Return the list of result files and summary for a job."""
    try:
        return gm.get_job_results(job_id)
    except JobNotFoundError as exc:
        raise _not_found(job_id) from exc


@jobs_router.get("/jobs/{job_id}/results/{filename:path}")
async def download_result(job_id: str, filename: str) -> FileResponse:
    """Download a single result file produced by a job."""
    store = JobStore()
    try:
        store.get(job_id)
        path = store.resolve_result_file(job_id, filename)
    except (JobNotFoundError, FileNotFoundError) as exc:
        raise _not_found(f"{job_id}/{filename}") from exc
    return FileResponse(path, filename=path.name)


def _not_found(what: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail=f"Not found: {what}"
    )
