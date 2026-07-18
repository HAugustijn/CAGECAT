"""Tests for the filesystem-backed job store."""

from __future__ import annotations

import pytest

from cagecat_web.analysis.jobs import JobNotFoundError, JobStatus, JobStore


def test_create_and_get_roundtrip(store: JobStore):
    job = store.create("cblaster", title="my run", params={"mode": "remote"})
    assert JobStore.is_valid_id(job.id)
    assert job.status is JobStatus.PENDING

    loaded = store.get(job.id)
    assert loaded.id == job.id
    assert loaded.title == "my run"
    assert loaded.params == {"mode": "remote"}


def test_directories_are_created(store: JobStore):
    job = store.create("cblaster")
    assert store.input_dir(job.id).is_dir()
    assert store.output_dir(job.id).is_dir()
    assert store.logs_dir(job.id).is_dir()


def test_update_persists_changes(store: JobStore):
    job = store.create("cblaster")
    updated = store.update(job, status=JobStatus.COMPLETED, task_id="abc")
    assert updated.status is JobStatus.COMPLETED
    assert store.get(job.id).task_id == "abc"


def test_unknown_job_raises(store: JobStore):
    with pytest.raises(JobNotFoundError):
        store.get("00000000-0000-0000-0000-000000000000")


def test_invalid_id_is_rejected(store: JobStore):
    # Path-traversal style identifiers must never resolve to a directory.
    with pytest.raises(JobNotFoundError):
        store.get("../../etc/passwd")


def test_resolve_result_file_guards_against_traversal(store: JobStore):
    job = store.create("cblaster")
    (store.output_dir(job.id) / "summary.txt").write_text("ok")

    assert store.resolve_result_file(job.id, "summary.txt").read_text() == "ok"
    with pytest.raises(FileNotFoundError):
        store.resolve_result_file(job.id, "../../metadata.json")


def test_result_files_lists_outputs(store: JobStore):
    job = store.create("cblaster")
    (store.output_dir(job.id) / "a.txt").write_text("a")
    (store.output_dir(job.id) / "b.txt").write_text("b")
    names = {p.name for p in store.result_files(job.id)}
    assert names == {"a.txt", "b.txt"}
