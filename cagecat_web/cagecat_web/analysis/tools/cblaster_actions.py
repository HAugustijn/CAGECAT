"""Derived cblaster tools that operate on a completed search's session file.

Each of these corresponds to a cblaster subcommand (``gne``, ``extract``,
``extract_clusters``, ``plot_clusters``) or a recompute run of ``search``. They
take the parent job's ``session.json`` as their single input and write their
results into their own job directory.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from cagecat_web.analysis import input_processor_cblaster as cbi
from cagecat_web.analysis.tools.base import ParameterError, Tool

if TYPE_CHECKING:
    from pathlib import Path

#: Parent tools whose sessions these actions can be run against.
_CBLASTER_PARENTS = ("cblaster", "cblaster_recompute")


class _DerivedCblasterTool(Tool):
    """Base for cblaster tools that consume a parent ``session.json``."""

    is_derived = True
    parent_tools = _CBLASTER_PARENTS
    accepted_formats = ()


class CblasterRecomputeTool(_DerivedCblasterTool):
    """Re-run a search with new filtering/clustering thresholds."""

    name = "cblaster_recompute"
    label = "Search again"
    description = "Recompute the search with different filtering and clustering thresholds."

    def clean_params(self, raw: dict[str, Any]) -> dict[str, Any]:
        # Reuse the search cleaner, but drop input/database-only options that
        # do not apply to a recompute.
        cleaned = cbi.clean_search_params({**raw, "mode": "remote", "database": "nr"})
        for key in ("mode", "database", "query_ids", "entrez_query", "hitlist_size"):
            cleaned.pop(key, None)
        return cleaned

    def build_command(
        self, *, input_paths: list[Path], output_dir: Path, params: dict[str, Any]
    ) -> list[str]:
        return cbi.build_recompute_args(
            parent_session=input_paths[0], output_dir=output_dir, params=params
        )

    def output_summary(self, output_dir: Path) -> dict[str, Any]:
        return CblasterRecomputeTool._cluster_count(output_dir)

    @staticmethod
    def _cluster_count(output_dir: Path) -> dict[str, Any]:
        import json

        session = output_dir / cbi.SESSION_FILE
        if not session.is_file():
            return {}
        try:
            data = json.loads(session.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return {"cluster_count": cbi.count_clusters(data)}


class CblasterGneTool(_DerivedCblasterTool):
    """Gene neighborhood estimation over a range of gap values."""

    name = "cblaster_gne"
    label = "Gene neighborhood"
    description = "Estimate a suitable maximum intergenic gap by resampling."

    def clean_params(self, raw: dict[str, Any]) -> dict[str, Any]:
        cleaned: dict[str, Any] = {
            "max_gap": cbi.coerce_number(
                "max_gap", raw.get("max_gap", 100000), 1, 5_000_000, False
            ),
            "samples": cbi.coerce_number(
                "samples", raw.get("samples", 100), 1, 300, False
            ),
        }
        scale = str(raw.get("scale", "linear")).lower()
        if scale not in {"linear", "log"}:
            raise ParameterError("'scale' must be 'linear' or 'log'.")
        cleaned["scale"] = scale
        return cleaned

    def build_command(
        self, *, input_paths: list[Path], output_dir: Path, params: dict[str, Any]
    ) -> list[str]:
        return [
            "cblaster",
            "gne",
            str(input_paths[0]),
            "--max_gap",
            str(params["max_gap"]),
            "--samples",
            str(params["samples"]),
            "--scale",
            params["scale"],
            "--plot",
            str(output_dir / "gne.html"),
            "--output",
            str(output_dir / "gne_summary.csv"),
        ]


class CblasterExtractSequencesTool(_DerivedCblasterTool):
    """Extract hit sequence names (and optionally FASTA sequences)."""

    name = "cblaster_extract_sequences"
    label = "Extract sequences"
    description = "Extract hit sequences from the session, optionally as FASTA."

    def clean_params(self, raw: dict[str, Any]) -> dict[str, Any]:
        cleaned: dict[str, Any] = {
            "download_sequences": cbi.as_bool(raw.get("download_sequences", False)),
            "name_only": cbi.as_bool(raw.get("name_only", False)),
        }
        for key in ("queries", "organisms"):
            values = cbi._split_multi(raw.get(key))
            if values:
                cleaned[key] = values
        delimiter = str(raw.get("delimiter", "")).strip()
        if delimiter:
            cleaned["delimiter"] = delimiter
        return cleaned

    def build_command(
        self, *, input_paths: list[Path], output_dir: Path, params: dict[str, Any]
    ) -> list[str]:
        download = params.get("download_sequences")
        out_name = "sequences.fasta" if download else "sequences.txt"
        args = ["cblaster", "extract", str(input_paths[0]), "--output", str(output_dir / out_name)]
        if params.get("queries"):
            args += ["--queries", *params["queries"]]
        if params.get("organisms"):
            args += ["--organisms", *params["organisms"]]
        if params.get("delimiter"):
            args += ["--delimiter", params["delimiter"]]
        if params.get("name_only"):
            args.append("--name_only")
        if download:
            args.append("--extract_sequences")
        return args


class CblasterExtractClustersTool(_DerivedCblasterTool):
    """Extract clusters from a session as GenBank files."""

    name = "cblaster_extract_clusters"
    label = "Extract clusters"
    description = "Export selected clusters as GenBank files."

    def clean_params(self, raw: dict[str, Any]) -> dict[str, Any]:
        from cagecat_web.config import get_settings

        cap = get_settings().extract_cluster_cap()
        requested = cbi.coerce_number(
            "maximum_clusters", raw.get("maximum_clusters", cap), 1, 1_000_000, False
        )
        cleaned: dict[str, Any] = {"maximum_clusters": min(int(requested), cap)}
        fmt = str(raw.get("format", "genbank")).lower()
        if fmt not in {"genbank", "fasta"}:
            raise ParameterError("'format' must be 'genbank' or 'fasta'.")
        cleaned["format"] = fmt
        clusters = cbi._split_multi(raw.get("clusters"))
        if clusters:
            cleaned["clusters"] = clusters
        organisms = cbi._split_multi(raw.get("organisms"))
        if organisms:
            cleaned["organisms"] = organisms
        if str(raw.get("score_threshold", "")).strip() != "":
            cleaned["score_threshold"] = cbi.coerce_number(
                "score_threshold", raw["score_threshold"], 0.0, 1.0, True
            )
        return cleaned

    def build_command(
        self, *, input_paths: list[Path], output_dir: Path, params: dict[str, Any]
    ) -> list[str]:
        args = [
            "cblaster",
            "extract_clusters",
            str(input_paths[0]),
            "--output",
            str(output_dir),
            "--format",
            params["format"],
            "--maximum_clusters",
            str(params["maximum_clusters"]),
        ]
        if params.get("clusters"):
            args += ["--clusters", *params["clusters"]]
        if params.get("organisms"):
            args += ["--organisms", *params["organisms"]]
        if "score_threshold" in params:
            args += ["--score_threshold", str(params["score_threshold"])]
        return args
