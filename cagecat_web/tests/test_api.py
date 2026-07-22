"""End-to-end tests for the job API using synchronous (eager) task execution."""

from __future__ import annotations


def test_list_tools(client):
    response = client.get("/api/tools")
    assert response.status_code == 200
    assert set(response.json()["tools"]) >= {"cblaster", "clinker"}


def test_archive_endpoint_returns_zip(client):
    import io
    import zipfile

    from cagecat_web.analysis.jobs import JobStatus, JobStore

    store = JobStore()
    job = store.create("cblaster_extract_clusters")
    store.update(job, status=JobStatus.COMPLETED)
    (store.output_dir(job.id) / "cluster1.gbk").write_text("LOCUS a\n//\n")
    (store.output_dir(job.id) / "cluster2.gbk").write_text("LOCUS b\n//\n")

    resp = client.get(f"/api/jobs/{job.id}/archive")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    names = zipfile.ZipFile(io.BytesIO(resp.content)).namelist()
    assert set(names) == {"cluster1.gbk", "cluster2.gbk"}


def test_archive_endpoint_no_files_404(client):
    from cagecat_web.analysis.jobs import JobStatus, JobStore

    store = JobStore()
    job = store.create("cblaster_extract_clusters")
    store.update(job, status=JobStatus.COMPLETED)  # no output files
    assert client.get(f"/api/jobs/{job.id}/archive").status_code == 404


def test_submit_cblaster_job_completes(client, stub_cblaster, fasta_bytes):
    response = client.post(
        "/api/jobs/cblaster",
        files={"files": ("query.fasta", fasta_bytes, "text/plain")},
        data={"title": "example", "database": "mibig", "max_hits": "50"},
    )
    assert response.status_code == 202, response.text
    body = response.json()
    job_id = body["id"]
    # Eager execution means the task already ran before the response returned.
    assert body["status"] == "completed"

    status = client.get(f"/api/jobs/{job_id}")
    assert status.status_code == 200
    assert status.json()["status"] == "completed"

    results = client.get(f"/api/jobs/{job_id}/results")
    assert results.status_code == 200
    names = {f["name"] for f in results.json()["files"]}
    assert "summary.txt" in names

    download = client.get(f"/api/jobs/{job_id}/results/summary.txt")
    assert download.status_code == 200
    assert download.text == "done"


def test_unknown_tool_returns_404(client, fasta_bytes):
    response = client.post(
        "/api/jobs/does-not-exist",
        files={"files": ("query.fasta", fasta_bytes, "text/plain")},
    )
    assert response.status_code == 404


def test_invalid_upload_returns_422(client):
    response = client.post(
        "/api/jobs/cblaster",
        files={"files": ("query.exe", b"garbage", "application/octet-stream")},
    )
    assert response.status_code == 422


def test_clinker_rejects_wrong_format(client, fasta_bytes):
    # clinker accepts GenBank/EMBL/GFF, not FASTA.
    response = client.post(
        "/api/jobs/clinker",
        files={"files": ("query.fasta", fasta_bytes, "text/plain")},
    )
    assert response.status_code == 422


def test_clinker_requires_a_file(client):
    response = client.post("/api/jobs/clinker", data={"identity": "0.3"})
    assert response.status_code == 422
    assert "at least" in response.json()["detail"]


def test_unknown_job_returns_404(client):
    response = client.get("/api/jobs/11111111-1111-1111-1111-111111111111")
    assert response.status_code == 404


# --- Visualisation pages ---------------------------------------------------


def test_visualisation_pages_render(client):
    for path, marker in (("/neighborhood", "geneNeighborhood"), ("/plasmidviz", "plasmidViz")):
        resp = client.get(path)
        assert resp.status_code == 200, path
        assert marker in resp.text


def _cblaster_session_job():
    """A completed cblaster job whose session has one anchor gene in a cluster."""
    import json

    from cagecat_web.analysis.jobs import JobStatus, JobStore

    store = JobStore()
    job = store.create("cblaster")
    store.update(job, status=JobStatus.COMPLETED)
    session = {
        "queries": ["QueryA"],
        "organisms": [{
            "name": "org",
            "scaffolds": [{
                "accession": "NC_TEST.1",
                "subjects": [{
                    "name": "hitA", "start": 1010, "end": 1039, "strand": "+",
                    "hits": [{"query": "QueryA", "identity": 92.0}],
                }],
                "clusters": [{"number": 1, "score": 5.0, "start": 1010, "end": 1039,
                              "indices": [0]}],
            }],
        }],
    }
    (store.output_dir(job.id) / "session.json").write_text(json.dumps(session))
    return job.id


def test_neighborhood_results_page_renders_viewer(client):
    # A completed neighborhood job opens the interactive viewer at /results/{id}.
    from cagecat_web.analysis.jobs import JobStatus, JobStore

    store = JobStore()
    job = store.create("cblaster_neighborhood")
    store.update(job, status=JobStatus.COMPLETED)
    resp = client.get(f"/results/{job.id}")
    assert resp.status_code == 200
    assert "gnCanvasWrap" in resp.text  # the viewer, not the generic results page


def test_invalid_parameter_returns_422(client, stub_cblaster, fasta_bytes):
    response = client.post(
        "/api/jobs/cblaster",
        files={"files": ("query.fasta", fasta_bytes, "text/plain")},
        data={"database": "not-a-real-database"},
    )
    assert response.status_code == 422


def test_queue_unavailable_returns_503(client, stub_cblaster, fasta_bytes, monkeypatch):
    from kombu.exceptions import OperationalError

    from cagecat_web.analysis import tasks

    def broker_down(_job_id):
        raise OperationalError("broker unreachable")

    monkeypatch.setattr(tasks.run_job, "delay", broker_down)

    response = client.post(
        "/api/jobs/cblaster",
        files={"files": ("query.fasta", fasta_bytes, "text/plain")},
    )
    assert response.status_code == 503
