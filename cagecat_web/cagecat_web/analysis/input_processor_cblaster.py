"""Parameter handling and command construction for ``cblaster search``.

This module isolates everything cblaster-specific: the set of accepted form
fields, how they are validated and bounded, and how they map onto the cblaster
``search`` command line (cblaster 1.4.x). Keeping it separate from the generic
tool machinery makes the mapping easy to audit and adjust as cblaster evolves.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from cagecat_web.analysis.tools.base import ParameterError

if TYPE_CHECKING:
    from pathlib import Path

# Canonical output file names written into a job's ``output/`` directory.
SESSION_FILE = "session.json"
SUMMARY_FILE = "summary.csv"
BINARY_FILE = "binary.csv"
PLOT_FILE = "plot.html"

#: Databases the user may search against, mapped to the NCBI BLAST database name
#: passed to cblaster's ``--database``. ``clusterednr`` (ClusteredNR,
#: ``nr_cluster_seq``) is NCBI's current default for protein BLAST: it is much
#: smaller than full ``nr`` and therefore substantially faster.
#: Note: ``mibig``/``antismashdb`` require a local DIAMOND database and only work
#: in local mode; the NCBI names work directly in remote mode.
DATABASES = {
    "clusterednr": "nr_cluster_seq",
    "nr": "nr",
    "refseq": "refseq_protein",
    "swissprot": "swissprot",
    "mibig": "mibig",
    "asdb": "antismashdb",
}

#: cblaster search modes.
MODES = {"local", "remote", "hmm", "combi_local", "combi_remote"}

#: Binary-table key/attribute choices accepted by cblaster.
BINARY_KEYS = {"len", "max", "sum"}
BINARY_ATTRS = {"identity", "coverage", "bitscore", "evalue"}

#: Numeric parameters: form key -> (cblaster flag, minimum, maximum, is_float).
_NUMERIC_PARAMS: dict[str, tuple[str, float, float, bool]] = {
    "hitlist_size": ("--hitlist_size", 1, 500_000, False),
    "max_evalue": ("--max_evalue", 0.0, 100.0, True),
    "min_identity": ("--min_identity", 0.0, 100.0, True),
    "min_coverage": ("--min_coverage", 0.0, 100.0, True),
    "gap": ("--gap", 0, 1_000_000, False),
    "unique": ("--unique", 0, 10_000, False),
    "min_hits": ("--min_hits", 0, 10_000, False),
    "percentage": ("--percentage", 0, 100, False),
    "max_distance": ("--max_distance", 0, 1_000_000, False),
    "maximum_clusters": ("--maximum_clusters", 1, 1_000_000, False),
}


def coerce_number(
    key: str, value: Any, low: float, high: float, is_float: bool
) -> float | int:
    """Coerce ``value`` to a bounded number or raise :class:`ParameterError`."""
    try:
        number: float | int = float(value) if is_float else int(value)
    except (TypeError, ValueError) as exc:
        raise ParameterError(f"'{key}' must be a number.") from exc
    if not low <= number <= high:
        raise ParameterError(f"'{key}' must be between {low} and {high}.")
    return number


def as_bool(value: Any) -> bool:
    """Interpret a form value as a boolean."""
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "on", "yes"}


def _split_multi(value: Any) -> list[str]:
    """Split a delimited textarea/string field into a list of tokens."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        items = list(value)
    else:
        items = str(value).replace(";", "\n").replace(",", "\n").split()
    return [item.strip() for item in items if item.strip()]


def clean_search_params(raw: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalise cblaster ``search`` form parameters.

    Unknown keys are ignored; missing numeric keys fall back to cblaster's own
    defaults by being omitted from the command line.
    """
    cleaned: dict[str, Any] = {}

    mode = str(raw.get("mode", "remote")).lower()
    if mode not in MODES:
        raise ParameterError(f"Unknown mode '{mode}'.")
    cleaned["mode"] = mode

    database = str(raw.get("database", "clusterednr")).lower()
    if database not in DATABASES:
        raise ParameterError(f"Unknown database '{database}'.")
    cleaned["database"] = database

    query_ids = _split_multi(raw.get("query_ids"))
    if query_ids:
        cleaned["query_ids"] = query_ids

    entrez_query = str(raw.get("entrez_query", "")).strip()
    if entrez_query:
        cleaned["entrez_query"] = entrez_query

    for key, (_flag, low, high, is_float) in _NUMERIC_PARAMS.items():
        if str(raw.get(key, "")).strip() != "":
            cleaned[key] = coerce_number(key, raw[key], low, high, is_float)

    require = _split_multi(raw.get("require"))
    if require:
        cleaned["require"] = require

    # Binary-table options.
    binary_key = str(raw.get("binary_key", "")).lower()
    if binary_key:
        if binary_key not in BINARY_KEYS:
            raise ParameterError(f"Unknown binary key '{binary_key}'.")
        cleaned["binary_key"] = binary_key
    binary_attr = str(raw.get("binary_attr", "")).lower()
    if binary_attr:
        if binary_attr not in BINARY_ATTRS:
            raise ParameterError(f"Unknown binary attribute '{binary_attr}'.")
        cleaned["binary_attr"] = binary_attr

    cleaned["intermediate_genes"] = as_bool(raw.get("intermediate_genes", False))
    cleaned["sort_clusters"] = as_bool(raw.get("sort_clusters", False))
    return cleaned


def _clustering_and_filtering_args(params: dict[str, Any]) -> list[str]:
    """Flags shared by ``search`` and ``recompute`` (thresholds + clustering)."""
    args: list[str] = []
    for key in (
        "max_evalue",
        "min_identity",
        "min_coverage",
        "gap",
        "unique",
        "min_hits",
        "percentage",
        "maximum_clusters",
    ):
        if key in params:
            args += [_NUMERIC_PARAMS[key][0], str(params[key])]
    if params.get("require"):
        args += ["--require", *params["require"]]
    if params.get("sort_clusters"):
        args.append("--sort_clusters")
    return args


def build_search_args(
    *,
    query_file: Path | None,
    output_dir: Path,
    params: dict[str, Any],
) -> list[str]:
    """Build the ``cblaster search`` argv for a validated parameter set."""
    args: list[str] = [
        "cblaster",
        "search",
        "--mode",
        params.get("mode", "remote"),
        "--database",
        DATABASES[params.get("database", "clusterednr")],
        "--output",
        str(output_dir / SUMMARY_FILE),
        "--binary",
        str(output_dir / BINARY_FILE),
        "--plot",
        str(output_dir / PLOT_FILE),
        "--session_file",
        str(output_dir / SESSION_FILE),
    ]

    if query_file is not None:
        args += ["--query_file", str(query_file)]
    elif params.get("query_ids"):
        args += ["--query_ids", *params["query_ids"]]

    if "hitlist_size" in params:
        args += ["--hitlist_size", str(params["hitlist_size"])]
    if params.get("entrez_query"):
        args += ["--entrez_query", params["entrez_query"]]

    args += _clustering_and_filtering_args(params)

    if "binary_key" in params:
        args += ["--binary_key", params["binary_key"]]
    if "binary_attr" in params:
        args += ["--binary_attr", params["binary_attr"]]

    if params.get("intermediate_genes"):
        args.append("--intermediate_genes")
        if "max_distance" in params:
            args += ["--max_distance", str(params["max_distance"])]

    return args


def build_recompute_args(
    *,
    parent_session: Path,
    output_dir: Path,
    params: dict[str, Any],
) -> list[str]:
    """Build a ``cblaster search`` recompute argv (rerun with new thresholds)."""
    args: list[str] = [
        "cblaster",
        "search",
        "--session_file",
        str(parent_session),
        "--recompute",
        str(output_dir / SESSION_FILE),
        "--output",
        str(output_dir / SUMMARY_FILE),
        "--binary",
        str(output_dir / BINARY_FILE),
        "--plot",
        str(output_dir / PLOT_FILE),
    ]
    args += _clustering_and_filtering_args(params)
    if params.get("intermediate_genes"):
        args.append("--intermediate_genes")
        if "max_distance" in params:
            args += ["--max_distance", str(params["max_distance"])]
    return args
