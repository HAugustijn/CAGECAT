"""Shared pytest fixtures.

Environment variables are configured before any application module is imported
so that the cached :class:`Settings` and the Celery app start in a test-safe
mode: an isolated jobs directory and synchronous ("eager") task execution.
"""

from __future__ import annotations

import os
import tempfile
from io import StringIO

_TMP_JOBS = tempfile.mkdtemp(prefix="cagecat-tests-")
_TMP_DB = tempfile.mkdtemp(prefix="cagecat-db-")
os.environ.setdefault("JOBS_DIR", _TMP_JOBS)
os.environ.setdefault("DATABASES_DIR", _TMP_DB)
os.environ.setdefault("PFAM_DIR", os.path.join(_TMP_DB, "pfam"))
os.environ.setdefault("CELERY_TASK_ALWAYS_EAGER", "true")
os.environ.setdefault("CELERY_BROKER_URL", "memory://")
os.environ.setdefault("CELERY_RESULT_BACKEND", "cache+memory://")

# A fake installed HMM database ("testdb.fasta" + "testdb.sqlite3").
with open(os.path.join(_TMP_DB, "testdb.fasta"), "w") as _f:
    _f.write(">x\nMKT\n")
open(os.path.join(_TMP_DB, "testdb.sqlite3"), "w").close()

import pytest
from Bio.Seq import Seq
from Bio.SeqIO import write as seqio_write
from Bio.SeqRecord import SeqRecord


@pytest.fixture
def fasta_bytes() -> bytes:
    """A small, valid protein FASTA file."""
    return b">query1\nMKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQ\n"


@pytest.fixture
def genbank_bytes() -> bytes:
    """A valid single-record GenBank file, generated with Biopython."""
    record = SeqRecord(Seq("ATGACGTACG" * 6), id="TEST0001", name="TEST", description="unit test record")
    record.annotations["molecule_type"] = "DNA"
    buffer = StringIO()
    seqio_write(record, buffer, "genbank")
    return buffer.getvalue().encode("utf-8")


@pytest.fixture
def store(tmp_path):
    """A :class:`JobStore` rooted at an isolated temporary directory."""
    from cagecat_web.analysis.jobs import JobStore

    return JobStore(root=tmp_path / "jobs")


@pytest.fixture
def stub_cblaster(monkeypatch):
    """Replace the cblaster command with a harmless one that writes a result."""
    import sys

    from cagecat_web.analysis.tools import get_tool

    tool = get_tool("cblaster")

    script = (
        "import pathlib\n"
        "pathlib.Path('summary.txt').write_text('done')\n"
        "pathlib.Path('session.json').write_text('{\"clusters\": []}')\n"
    )

    def fake_build_command(*, input_paths, output_dir, params):
        return [sys.executable, "-c", script]

    monkeypatch.setattr(tool, "build_command", fake_build_command)
    return tool


@pytest.fixture
def stub_action(monkeypatch):
    """Replace derived cblaster action commands with harmless marker writers."""
    import sys

    from cagecat_web.analysis.tools import actions_for

    def make_build(marker: str):
        script = f"import pathlib; pathlib.Path('{marker}').write_text('ok')"

        def build(*, input_paths, output_dir, params):
            return [sys.executable, "-c", script]

        return build

    for tool in actions_for("cblaster"):
        marker = tool.name.replace("cblaster_", "") + "_done.txt"
        monkeypatch.setattr(tool, "build_command", make_build(marker))
    return None


@pytest.fixture
def client():
    """A FastAPI ``TestClient`` for the application."""
    from fastapi.testclient import TestClient

    from cagecat_web.main import app

    with TestClient(app) as test_client:
        yield test_client
