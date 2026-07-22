"""Tests for derived cblaster actions (gne, extract, recompute, ...)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from cagecat_web.analysis import general_manager as gm
from cagecat_web.analysis.jobs import JobStatus, JobStore
from cagecat_web.analysis.tools import actions_for, get_tool

if TYPE_CHECKING:
    from pathlib import Path


def _completed_search(store: JobStore, monkeypatch_session: bool = True):
    """Create a fake completed cblaster search job with a session file."""
    job = store.create("cblaster")
    job = store.update(job, status=JobStatus.COMPLETED, input_files=["query.fasta"])
    if monkeypatch_session:
        (store.output_dir(job.id) / "session.json").write_text(
            json.dumps({"clusters": [{"number": 1}, {"number": 2}]})
        )
    return job


def test_actions_for_search_includes_expected_tools():
    names = {tool.name for tool in actions_for("cblaster")}
    assert {
        "cblaster_gne",
        "cblaster_extract_sequences",
        "cblaster_extract_clusters",
        "cblaster_recompute",
    } <= names


def test_clinker_handoff_available_on_extract_clusters():
    names = {tool.name for tool in actions_for("cblaster_extract_clusters")}
    assert "clinker_clusters" in names


def test_cblaster_clinker_available_on_search():
    assert "cblaster_clinker" in {tool.name for tool in actions_for("cblaster")}


def test_cblaster_clinker_caps_maximum_clusters():
    # A big selection is capped to max_clinker_clusters (default 25).
    cleaned = get_tool("cblaster_clinker").clean_params(
        {"clusters": " ".join(str(i) for i in range(1, 501)), "maximum_clusters": "500"}
    )
    assert cleaned["maximum_clusters"] == 25


def test_extract_clusters_caps_maximum_clusters():
    # Capped to max_extract_clusters (default 50) to avoid NCBI rate limits.
    cleaned = get_tool("cblaster_extract_clusters").clean_params(
        {"maximum_clusters": "500"}
    )
    assert cleaned["maximum_clusters"] == 50


def test_cluster_caps_boost_with_api_key():
    from cagecat_web.config import Settings

    with_key = Settings(cblaster_api_key="abc123")
    assert with_key.extract_cluster_cap() == with_key.max_extract_clusters_with_key
    assert with_key.clinker_cluster_cap() == with_key.max_clinker_clusters_with_key

    without = Settings(cblaster_api_key="")
    assert without.extract_cluster_cap() == without.max_extract_clusters
    assert without.clinker_cluster_cap() == without.max_clinker_clusters


def test_cblaster_clinker_builds_two_commands(tmp_path: Path):
    from cagecat_web.analysis.tools.base import GENBANK_TOKEN

    tool = get_tool("cblaster_clinker")
    params = tool.clean_params({"clusters": "1 2", "identity": "0.5"})
    cmds = tool.build_command(
        input_paths=[tmp_path / "session.json"], output_dir=tmp_path, params=params
    )
    assert len(cmds) == 2
    assert cmds[0][:2] == ["cblaster", "extract_clusters"]
    assert "--clusters" in cmds[0]
    assert cmds[1][0] == "clinker"
    assert GENBANK_TOKEN in cmds[1]


def test_task_command_helpers(tmp_path: Path):
    from cagecat_web.analysis.tasks import _as_command_list, _expand_command
    from cagecat_web.analysis.tools.base import GENBANK_TOKEN

    assert _as_command_list(["a", "b"]) == [["a", "b"]]
    assert _as_command_list([["a"], ["b"]]) == [["a"], ["b"]]

    (tmp_path / "c1.gbk").write_text("x")
    (tmp_path / "c2.gbk").write_text("y")
    out = _expand_command(["clinker", GENBANK_TOKEN, "-p"], tmp_path)
    assert out[0] == "clinker" and out[-1] == "-p"
    assert sum(a.endswith(".gbk") for a in out) == 2


def test_cblaster_clinker_runs_two_steps(monkeypatch):
    import sys

    from cagecat_web.analysis.tools.base import GENBANK_TOKEN

    store = JobStore()
    parent = _completed_search(store)

    tool = get_tool("cblaster_clinker")
    write_gbk = "import pathlib; pathlib.Path('cluster1.gbk').write_text('x')"
    record = (
        "import sys, pathlib; "
        "pathlib.Path('done.txt').write_text(' '.join(sys.argv[1:]))"
    )
    monkeypatch.setattr(
        tool,
        "build_command",
        lambda *, input_paths, output_dir, params: [
            [sys.executable, "-c", write_gbk],
            [sys.executable, "-c", record, GENBANK_TOKEN],
        ],
    )

    job = gm.submit_derived_job(
        parent_id=parent.id, action="cblaster_clinker", params={"clusters": "1"}
    )
    assert job.status is JobStatus.COMPLETED
    done = (store.output_dir(job.id) / "done.txt").read_text()
    assert "cluster1.gbk" in done  # step 2 saw the file step 1 produced


def test_clinker_handoff_requires_a_cluster(store):
    parent = store.create("cblaster_extract_clusters")
    store.update(parent, status=JobStatus.COMPLETED)  # no GenBank produced
    with pytest.raises(gm.ValidationError, match="no GenBank clusters"):
        gm.submit_derived_job(
            parent_id=parent.id, action="clinker_clusters", params={}, store=store
        )


def test_clinker_handoff_runs(monkeypatch):
    import sys

    store = JobStore()
    parent = store.create("cblaster_extract_clusters")
    store.update(parent, status=JobStatus.COMPLETED)
    for name in ("cluster1.gbk", "cluster2.gbk"):
        (store.output_dir(parent.id) / name).write_text("LOCUS x\n//\n")

    tool = get_tool("clinker_clusters")
    script = "import pathlib; pathlib.Path('clinker_done.txt').write_text('ok')"
    monkeypatch.setattr(
        tool,
        "build_command",
        lambda *, input_paths, output_dir, params: [sys.executable, "-c", script],
    )

    job = gm.submit_derived_job(
        parent_id=parent.id, action="clinker_clusters", params={"identity": "0.3"}
    )
    assert job.parent_id == parent.id
    assert job.status is JobStatus.COMPLETED
    assert (store.output_dir(job.id) / "clinker_done.txt").is_file()


def test_gne_command_shape(tmp_path: Path):
    tool = get_tool("cblaster_gne")
    params = tool.clean_params({"max_gap": "200000", "samples": "50", "scale": "log"})
    cmd = tool.build_command(
        input_paths=[tmp_path / "session.json"], output_dir=tmp_path, params=params
    )
    assert cmd[:2] == ["cblaster", "gne"]
    assert cmd[2].endswith("session.json")
    assert cmd[cmd.index("--scale") + 1] == "log"


def test_extract_sequences_fasta_flag(tmp_path: Path):
    tool = get_tool("cblaster_extract_sequences")
    params = tool.clean_params({"download_sequences": "on"})
    cmd = tool.build_command(
        input_paths=[tmp_path / "session.json"], output_dir=tmp_path, params=params
    )
    assert cmd[:2] == ["cblaster", "extract"]
    assert "--extract_sequences" in cmd
    assert any(a.endswith("sequences.fasta") for a in cmd)


def test_submit_derived_job_requires_completed_parent(store: JobStore):
    parent = store.create("cblaster")  # still pending, no session
    with pytest.raises(gm.ValidationError):
        gm.submit_derived_job(
            parent_id=parent.id, action="cblaster_gne", params={}, store=store
        )


def test_submit_derived_job_runs_eagerly(stub_action):
    # Use the default store so the eager task (which builds its own JobStore
    # from settings) operates on the same job directory.
    store = JobStore()
    parent = _completed_search(store)
    job = gm.submit_derived_job(
        parent_id=parent.id,
        action="cblaster_gne",
        params={"max_gap": "100000", "samples": "10", "scale": "linear"},
    )
    assert job.parent_id == parent.id
    assert job.status is JobStatus.COMPLETED
    assert (store.output_dir(job.id) / "gne_done.txt").is_file()


def test_action_endpoint_end_to_end(client, stub_cblaster, stub_action, fasta_bytes):
    # Submit a search that "completes" via the stub, then run an action on it.
    resp = client.post(
        "/api/jobs/cblaster",
        files={"files": ("query.fasta", fasta_bytes, "text/plain")},
    )
    assert resp.status_code == 202
    parent_id = resp.json()["id"]

    action = client.post(
        f"/api/jobs/{parent_id}/actions/cblaster_gne",
        data={"max_gap": "100000", "samples": "10", "scale": "linear"},
    )
    assert action.status_code == 202, action.text
    body = action.json()
    assert body["parent_id"] == parent_id
    assert body["status"] == "completed"


def test_action_on_unknown_parent_returns_404(client):
    resp = client.post(
        "/api/jobs/11111111-1111-1111-1111-111111111111/actions/cblaster_gne",
        data={},
    )
    assert resp.status_code == 404
