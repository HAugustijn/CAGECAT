"""Tests for upload validation."""

from __future__ import annotations

import pytest

from cagecat_web.analysis.validation import ValidationError, validate_upload


def test_valid_fasta_is_accepted(fasta_bytes):
    result = validate_upload(
        "query.fasta", fasta_bytes, accepted_formats=("fasta", "genbank")
    )
    assert result.fmt == "fasta"
    assert result.filename == "query.fasta"


def test_valid_genbank_is_accepted(genbank_bytes):
    result = validate_upload(
        "cluster.gbk", genbank_bytes, accepted_formats=("genbank",)
    )
    assert result.fmt == "genbank"


def test_unsupported_extension_is_rejected(fasta_bytes):
    with pytest.raises(ValidationError, match="Unsupported file type"):
        validate_upload("query.exe", fasta_bytes, accepted_formats=("fasta",))


def test_format_not_accepted_by_tool_is_rejected(genbank_bytes):
    with pytest.raises(ValidationError):
        validate_upload("cluster.gbk", genbank_bytes, accepted_formats=("fasta",))


def test_binary_content_is_rejected():
    with pytest.raises(ValidationError, match="binary"):
        validate_upload("query.fasta", b">seq\n\x00\x01\x02", accepted_formats=("fasta",))


def test_empty_file_is_rejected():
    with pytest.raises(ValidationError, match="empty"):
        validate_upload("query.fasta", b"", accepted_formats=("fasta",))


def test_wrong_signature_is_rejected():
    with pytest.raises(ValidationError, match="does not look like"):
        validate_upload(
            "query.fasta", b"not a fasta file at all", accepted_formats=("fasta",)
        )


def test_too_many_sequences_is_rejected():
    from cagecat_web.config import Settings

    settings = Settings(max_sequences=2)
    many = b"".join(f">s{i}\nMKT\n".encode() for i in range(3))
    with pytest.raises(ValidationError, match="maximum is 2"):
        validate_upload(
            "query.fasta", many, accepted_formats=("fasta",), settings=settings
        )


def test_oversize_file_is_rejected(fasta_bytes):
    from cagecat_web.config import Settings

    settings = Settings(max_upload_bytes=4)
    with pytest.raises(ValidationError, match="maximum upload size"):
        validate_upload(
            "query.fasta", fasta_bytes, accepted_formats=("fasta",), settings=settings
        )
