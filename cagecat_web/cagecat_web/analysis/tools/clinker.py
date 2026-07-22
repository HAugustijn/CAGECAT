"""clinker tool adapter.

Wraps ``clinker`` behind the generic :class:`Tool` interface to align and
visualise annotated gene clusters (clinker 0.0.x CLI). :class:`ClinkerTool`
takes uploaded files; :class:`ClinkerClustersTool` is the cblaster→clinker
handoff — it runs on the GenBank clusters produced by an extract-clusters job.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from cagecat_web.analysis.tools.base import GENBANK_TOKEN, ParameterError, Tool

if TYPE_CHECKING:
    from pathlib import Path

# Canonical output file names written into a job's ``output/`` directory.
PLOT_FILE = "plot.html"
ALIGNMENTS_FILE = "alignments.csv"
SESSION_FILE = "session.json"
MATRIX_FILE = "matrix.csv"

#: Boolean flags: form key -> clinker flag.
_FLAGS = {
    "no_align": "--no_align",
    "as_separate_clusters": "--as_separate_clusters",
    "use_file_order": "--use_file_order",
    "hide_link_headers": "--hide_link_headers",
    "hide_aln_headers": "--hide_aln_headers",
}


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "on", "yes"}


def clean_clinker_params(raw: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalise clinker form parameters."""
    cleaned: dict[str, Any] = {}

    identity = raw.get("identity", raw.get("min_identity"))
    if identity is not None and str(identity).strip() != "":
        try:
            value = float(identity)
        except (TypeError, ValueError) as exc:
            raise ParameterError("'identity' must be a number.") from exc
        if not 0.0 <= value <= 1.0:
            raise ParameterError("'identity' must be between 0 and 1.")
        cleaned["identity"] = value

    if str(raw.get("decimals", "")).strip() != "":
        try:
            decimals = int(raw["decimals"])
        except (TypeError, ValueError) as exc:
            raise ParameterError("'decimals' must be a whole number.") from exc
        if not 0 <= decimals <= 10:
            raise ParameterError("'decimals' must be between 0 and 10.")
        cleaned["decimals"] = decimals

    delimiter = str(raw.get("delimiter", "")).strip()
    if delimiter:
        cleaned["delimiter"] = delimiter

    for key in _FLAGS:
        if _as_bool(raw.get(key, False)):
            cleaned[key] = True
    return cleaned


def build_clinker_command(
    input_paths: list[Path], output_dir: Path, params: dict[str, Any]
) -> list[str]:
    """Build the ``clinker`` argv for the given input files and parameters."""
    args: list[str] = ["clinker", *[str(p) for p in input_paths]]
    args += [
        "--plot",
        str(output_dir / PLOT_FILE),
        "--output",
        str(output_dir / ALIGNMENTS_FILE),
        "--session",
        str(output_dir / SESSION_FILE),
        "--matrix_out",
        str(output_dir / MATRIX_FILE),
        "--force",
    ]
    if "identity" in params:
        args += ["--identity", str(params["identity"])]
    if "delimiter" in params:
        args += ["--delimiter", params["delimiter"]]
    if "decimals" in params:
        args += ["--decimals", str(params["decimals"])]
    for key, flag in _FLAGS.items():
        if params.get(key):
            args.append(flag)
    return args


class ClinkerTool(Tool):
    """Align and visualise homologous gene clusters with clinker."""

    name = "clinker"
    label = "clinker"
    accepted_formats = ("genbank", "embl", "gff")
    # One file is allowed (e.g. a multi-record GenBank with "as separate
    # clusters"); comparisons naturally use several.
    min_inputs = 1
    max_inputs = 50

    def clean_params(self, raw: dict[str, Any]) -> dict[str, Any]:
        return clean_clinker_params(raw)

    def build_command(
        self, *, input_paths: list[Path], output_dir: Path, params: dict[str, Any]
    ) -> list[str]:
        return build_clinker_command(input_paths, output_dir, params)


class ClinkerClustersTool(Tool):
    """Align GenBank clusters with clinker. Runs on the GenBank output of an
    extract-clusters job or a geneNeighborhood job (the fetched region GenBanks)."""

    name = "clinker_clusters"
    label = "Align with clinker"
    description = "Align and visualise the clusters with clinker to compute similarity."
    is_derived = True
    parent_tools = ("cblaster_extract_clusters", "cblaster_neighborhood",
                    "neighborhood_search")
    parent_input = "genbank"

    def clean_params(self, raw: dict[str, Any]) -> dict[str, Any]:
        return clean_clinker_params(raw)

    def build_command(
        self, *, input_paths: list[Path], output_dir: Path, params: dict[str, Any]
    ) -> list[str]:
        if not input_paths:
            raise ParameterError("No GenBank clusters were found to visualise.")
        return build_clinker_command(input_paths, output_dir, params)


class CblasterClinkerTool(Tool):
    """One-step cblaster→clinker: extract the selected clusters from a search
    session, then align them with clinker — a single job with a new id."""

    name = "cblaster_clinker"
    label = "Visualise with clinker"
    description = "Extract the selected clusters and align them with clinker."
    is_derived = True
    parent_tools = ("cblaster", "cblaster_recompute")
    parent_input = "session"

    def clean_params(self, raw: dict[str, Any]) -> dict[str, Any]:
        from cagecat_web.analysis import input_processor_cblaster as cbi
        from cagecat_web.config import get_settings

        cap = get_settings().clinker_cluster_cap()
        cleaned = clean_clinker_params(raw)
        clusters = cbi._split_multi(raw.get("clusters"))
        if clusters:
            cleaned["clusters"] = clusters
        requested = str(raw.get("maximum_clusters", "")).strip()
        n = (
            cbi.coerce_number("maximum_clusters", requested, 1, 1_000_000, False)
            if requested
            else cap
        )
        # Cap so the figure stays readable and remote extraction doesn't hit
        # NCBI's rate limit; extracts the highest-scoring clusters.
        cleaned["maximum_clusters"] = min(int(n), cap)
        return cleaned

    def build_command(
        self, *, input_paths: list[Path], output_dir: Path, params: dict[str, Any]
    ) -> list[list[str]]:
        session = input_paths[0]
        extract = [
            "cblaster",
            "extract_clusters",
            str(session),
            "--output",
            str(output_dir),
            "--format",
            "genbank",
            "--maximum_clusters",
            str(params.get("maximum_clusters", 50)),
        ]
        if params.get("clusters"):
            extract += ["--clusters", *params["clusters"]]
        # Second step: clinker on whatever GenBank clusters step one produced.
        clinker = build_clinker_command([GENBANK_TOKEN], output_dir, params)
        return [extract, clinker]
