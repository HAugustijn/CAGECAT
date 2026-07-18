"""Reading and summarising the results of a finished job."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from cagecat_web.analysis.tools import get_tool

if TYPE_CHECKING:
    from cagecat_web.analysis.jobs import Job, JobStore


def collect_results(job: Job, store: JobStore) -> dict[str, Any]:
    """Return a JSON-serialisable description of a job's output files.

    Includes the relative path and size of every produced file plus a
    tool-specific summary.
    """
    output_dir = store.output_dir(job.id)
    files = [
        {
            "name": str(path.relative_to(output_dir)),
            "size_bytes": path.stat().st_size,
        }
        for path in store.result_files(job.id)
    ]

    summary: dict[str, Any] = {}
    try:
        summary = get_tool(job.tool).output_summary(output_dir)
    except Exception:
        summary = {}

    return {"files": files, "summary": summary}
