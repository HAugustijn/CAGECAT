"""Validation of user-uploaded annotation and sequence files.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

from Bio import SeqIO

from cagecat_web.config import Settings, get_settings


class ValidationError(ValueError):
    """Raised when an uploaded file fails validation.
    """


@dataclass(frozen=True)
class UploadedFile:
    """An in-memory upload together with its detected format."""

    filename: str
    data: bytes
    fmt: str


#: Canonical formats mapped to their accepted file extensions.
FORMAT_EXTENSIONS: dict[str, tuple[str, ...]] = {
    "fasta": (".fasta", ".fa", ".faa", ".fna", ".fas", ".seq"),
    "genbank": (".gbk", ".gb", ".gbff", ".genbank"),
    "embl": (".embl", ".emb"),
    "gff": (".gff", ".gff3"),
}

#: Formats that Biopython can parse as multi-record sequence files.
_BIOPYTHON_FORMATS = {"fasta": "fasta", "genbank": "genbank", "embl": "embl"}

#: Reverse lookup: extension -> canonical format.
_EXTENSION_FORMAT: dict[str, str] = {
    ext: fmt for fmt, exts in FORMAT_EXTENSIONS.items() for ext in exts
}


def _detect_format(filename: str, accepted: tuple[str, ...]) -> str:
    """Return the canonical format for ``filename`` restricted to ``accepted``."""
    suffix = Path(filename).suffix.lower()
    if not suffix:
        raise ValidationError(
            f"'{filename}' has no file extension; expected one of "
            f"{_readable_extensions(accepted)}."
        )
    fmt = _EXTENSION_FORMAT.get(suffix)
    if fmt is None or fmt not in accepted:
        raise ValidationError(
            f"Unsupported file type '{suffix}'. Expected one of "
            f"{_readable_extensions(accepted)}."
        )
    return fmt


def _readable_extensions(accepted: tuple[str, ...]) -> str:
    exts = sorted({ext for fmt in accepted for ext in FORMAT_EXTENSIONS[fmt]})
    return ", ".join(exts)


def _decode(data: bytes) -> str:
    """Decode text data, rejecting binary content (NUL bytes)."""
    if b"\x00" in data:
        raise ValidationError("File appears to be binary, not a text annotation file.")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return data.decode("latin-1")
        except UnicodeDecodeError as exc:
            raise ValidationError("File is not valid text.") from exc


def _check_structure(fmt: str, text: str, filename: str, max_sequences: int) -> None:
    """Perform a lightweight, format-specific structural sanity check."""
    stripped = text.lstrip()
    if not stripped:
        raise ValidationError(f"'{filename}' is empty.")

    signatures = {
        "fasta": lambda t: t.startswith(">"),
        "genbank": lambda t: t.startswith("LOCUS"),
        "embl": lambda t: t.startswith("ID "),
        "gff": lambda t: t.startswith("##") or "\t" in t.split("\n", 1)[0],
    }
    if not signatures[fmt](stripped):
        raise ValidationError(
            f"'{filename}' does not look like a valid {fmt.upper()} file."
        )

    bio_format = _BIOPYTHON_FORMATS.get(fmt)
    if bio_format is None:
        return

    try:
        records = list(SeqIO.parse(io.StringIO(text), bio_format))
    except Exception as exc:
        raise ValidationError(f"Could not parse '{filename}' as {fmt.upper()}.") from exc

    if not records:
        raise ValidationError(
            f"'{filename}' does not contain any {fmt.upper()} records."
        )
    if len(records) > max_sequences:
        raise ValidationError(
            f"'{filename}' contains {len(records)} sequences; the maximum is "
            f"{max_sequences}."
        )


def validate_upload(
    filename: str,
    data: bytes,
    *,
    accepted_formats: tuple[str, ...],
    settings: Settings | None = None,
) -> UploadedFile:
    """Validate one uploaded file and return it annotated with its format.

    Arguments:
        filename: Original client-supplied file name.
        data: Raw file bytes.
        accepted_formats: Canonical formats the receiving tool accepts.
        settings: Optional settings override (size and sequence limits).

    Raises:
        ValidationError: If the file is missing, too large, of the wrong type,
            binary, or structurally invalid. The message is client-safe.
    """
    settings = settings or get_settings()

    if not filename:
        raise ValidationError("A file name is required.")
    if not data:
        raise ValidationError(f"'{filename}' is empty.")
    if len(data) > settings.max_upload_bytes:
        limit_mb = settings.max_upload_bytes / (1024 * 1024)
        raise ValidationError(
            f"'{filename}' exceeds the maximum upload size of {limit_mb:.0f} MB."
        )

    fmt = _detect_format(filename, accepted_formats)
    text = _decode(data)
    _check_structure(fmt, text, filename, settings.max_sequences)
    return UploadedFile(filename=Path(filename).name, data=data, fmt=fmt)
