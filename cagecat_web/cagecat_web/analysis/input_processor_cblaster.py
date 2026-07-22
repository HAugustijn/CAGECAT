"""Parameter handling and command construction for ``cblaster search``.

This module isolates everything cblaster-specific: the set of accepted form
fields, how they are validated and bounded, and how they map onto the cblaster
``search`` command line (cblaster 1.4.x). Keeping it separate from the generic
tool machinery makes the mapping easy to audit and adjust as cblaster evolves.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from cagecat_web.analysis.tools.base import ParameterError

#: A Pfam accession, optionally with a version suffix (e.g. PF00005 or PF00005.30).
_PFAM_RE = re.compile(r"^PF\d{5}(\.\d+)?$", re.IGNORECASE)

if TYPE_CHECKING:
    from pathlib import Path

# Canonical output file names written into a job's ``output/`` directory.
SESSION_FILE = "session.json"
SUMMARY_FILE = "summary.csv"
BINARY_FILE = "binary.csv"
PLOT_FILE = "plot.html"

#: Databases the user may search against, mapped to the NCBI BLAST database name
#: passed to cblaster's ``--database``.
#: ``mibig``/``antismashdb`` require a local DIAMOND database (local mode only).
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

#: Modes CAGECAT currently supports end-to-end. ``remote`` searches NCBI with a
#: sequence/id query; ``local`` searches a local DIAMOND database; ``hmm``
#: searches a local database with Pfam profiles.
SUPPORTED_MODES = {"remote", "local", "hmm"}

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


def count_clusters(session: dict[str, Any]) -> int:
    """Count hit clusters in a cblaster session.

    Clusters are nested under ``organisms -> scaffolds -> clusters``.
    """
    return sum(
        len(scaffold.get("clusters", []))
        for organism in session.get("organisms", [])
        for scaffold in organism.get("scaffolds", [])
    )


def parse_clusters(session: dict[str, Any]) -> list[dict[str, Any]]:
    """Return a flat, UI-friendly list of clusters from a cblaster session.

    Each entry has the cluster ``number`` (as used by extract/plot commands),
    its organism, scaffold, score, genomic span and gene count.
    """
    clusters: list[dict[str, Any]] = []
    for organism in session.get("organisms", []):
        name = organism.get("name") or organism.get("strain") or "Unknown organism"
        for scaffold in organism.get("scaffolds", []):
            accession = scaffold.get("accession", "")
            for cluster in scaffold.get("clusters", []):
                clusters.append(
                    {
                        "number": cluster.get("number"),
                        "organism": name,
                        "scaffold": accession,
                        "score": round(float(cluster.get("score", 0) or 0), 2),
                        "start": cluster.get("start"),
                        "end": cluster.get("end"),
                        "n_genes": len(cluster.get("indices", [])),
                    }
                )
    clusters.sort(key=lambda c: (c["number"] is None, c["number"]))
    return clusters


def _strand_to_int(value: Any) -> int:
    """Normalise a cblaster strand (``+``/``-``/``1``/``-1``) to ``1``/``-1``/``0``."""
    if value in ("+", 1, "1"):
        return 1
    if value in ("-", -1, "-1"):
        return -1
    return 0


def _gene_from_subject(subject: dict[str, Any]) -> dict[str, Any]:
    """Convert one cblaster subject into a neighborhood-diagram gene.

    A subject's ``hits`` link it to one or more query sequences; the best hit
    (highest identity) defines the gene's *family* and identity, which the viewer
    uses to colour homologous genes consistently across loci. Subjects without
    hits are flanking ("intermediate") genes with no family.
    """
    hits = subject.get("hits") or []
    family: str | None = None
    identity: float | None = None
    if hits:
        best = max(hits, key=lambda h: float(h.get("identity", 0) or 0))
        family = best.get("query")
        try:
            identity = round(float(best.get("identity")), 1)
        except (TypeError, ValueError):
            identity = None
    name = subject.get("name") or subject.get("id") or "gene"
    return {
        "name": name,
        "start": subject.get("start"),
        "end": subject.get("end"),
        "strand": _strand_to_int(subject.get("strand")),
        "family": family,
        "identity": identity,
        "anchor": bool(hits),
        # cblaster subject names are the NCBI protein accession, used for the
        # out-link. cblaster stores no product text, so annotation is the family.
        "protein_id": name,
        "product": None,
    }


def parse_cluster_neighborhoods(session: dict[str, Any]) -> dict[str, Any]:
    """Return per-cluster gene neighborhoods for EFI-GNT-style visualisation.

    Unlike :func:`parse_clusters` (which returns cluster-level metadata only),
    this walks each cluster's ``indices`` into its scaffold's ``subjects`` list
    and returns every gene in the cluster window — the query hits (anchors) plus
    any flanking/intermediate genes cblaster stored. The ``queries`` list is the
    set of query families used to colour homologous genes across loci.

    Flanking genes are only present when the search was run with
    ``--intermediate_genes``; otherwise each cluster contains just its hits.
    """
    queries = list(session.get("queries") or [])
    loci: list[dict[str, Any]] = []
    for organism in session.get("organisms", []):
        org_name = organism.get("name") or organism.get("strain") or "Unknown organism"
        strain = organism.get("strain")
        for scaffold in organism.get("scaffolds", []):
            accession = scaffold.get("accession", "")
            subjects = scaffold.get("subjects", [])
            for cluster in scaffold.get("clusters", []):
                indices = cluster.get("indices", []) or []
                genes: list[dict[str, Any]] = []
                for idx in indices:
                    if isinstance(idx, int) and 0 <= idx < len(subjects):
                        gene = _gene_from_subject(subjects[idx])
                        if gene["start"] is not None and gene["end"] is not None:
                            genes.append(gene)
                # cblaster stores the surrounding ("intermediate") genes in a
                # separate list (Subject dicts with no hits), not in ``indices``.
                # They are the grey neighborhood genes shown around the hits.
                for sub in cluster.get("intermediate_genes", []) or []:
                    gene = _gene_from_subject(sub)
                    if gene["start"] is not None and gene["end"] is not None:
                        genes.append(gene)
                genes.sort(key=lambda g: g["start"])
                loci.append(
                    {
                        "number": cluster.get("number"),
                        "organism": org_name,
                        "strain": strain,
                        "scaffold": accession,
                        "score": round(float(cluster.get("score", 0) or 0), 2),
                        "start": cluster.get("start"),
                        "end": cluster.get("end"),
                        "genes": genes,
                    }
                )
    loci.sort(key=lambda c: c["score"], reverse=True)
    return {"queries": queries, "loci": loci}


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
    from cagecat_web.config import get_settings

    cleaned: dict[str, Any] = {}

    mode = str(raw.get("mode", "remote")).lower()
    if mode not in SUPPORTED_MODES:
        raise ParameterError(
            f"Unsupported search mode '{mode}'. Supported modes: "
            f"{', '.join(sorted(SUPPORTED_MODES))}."
        )
    cleaned["mode"] = mode

    if mode == "hmm":
        profiles = _split_multi(raw.get("query_profiles"))
        if not profiles:
            raise ParameterError(
                "An HMM search needs at least one Pfam profile identifier "
            )
        invalid = [p for p in profiles if not _PFAM_RE.match(p)]
        if invalid:
            raise ParameterError(
                f"Invalid Pfam profile identifier(s): {', '.join(invalid)}. "
            )
        # Strip version suffixes (PF00005.30 -> PF00005) so profiles match the
        # installed Pfam release regardless of its per-profile version numbers.
        cleaned["query_profiles"] = [
            re.sub(r"\.\d+$", "", p).upper() for p in profiles
        ]

        available = get_settings().hmm_databases()
        if not available:
            raise ParameterError(
                "No HMM search databases are installed on this server."
            )
        db_key = str(raw.get("hmm_database", raw.get("database", ""))).strip()
        if db_key not in available:
            raise ParameterError(
                f"Unknown HMM database '{db_key}'. Available: "
                f"{', '.join(sorted(available))}."
            )
        cleaned["hmm_database"] = db_key
    else:  # sequence-query search: remote NCBI, or a local DIAMOND database
        database = str(raw.get("database", "clusterednr")).strip()
        local_dbs = get_settings().local_databases()
        if database in local_dbs:
            cleaned["mode"] = "local"
            cleaned["local_database"] = database
        elif database.lower() in DATABASES:
            cleaned["mode"] = "remote"
            cleaned["database"] = database.lower()
            entrez_query = str(raw.get("entrez_query", "")).strip()
            if entrez_query:
                cleaned["entrez_query"] = entrez_query
        else:
            raise ParameterError(f"Unknown database '{database}'.")

        query_ids = _split_multi(raw.get("query_ids"))
        if query_ids:
            cleaned["query_ids"] = query_ids

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


#: BLAST-hit filtering flags (not applicable to HMM searches).
_FILTERING_KEYS = ("max_evalue", "min_identity", "min_coverage")
#: Clustering flags (applicable to every mode).
_CLUSTERING_KEYS = ("gap", "unique", "min_hits", "percentage", "maximum_clusters")


def _numeric_args(params: dict[str, Any], keys: tuple[str, ...]) -> list[str]:
    args: list[str] = []
    for key in keys:
        if key in params:
            args += [_NUMERIC_PARAMS[key][0], str(params[key])]
    return args


def _clustering_extras(params: dict[str, Any]) -> list[str]:
    args: list[str] = []
    if params.get("require"):
        args += ["--require", *params["require"]]
    return args


def _plot_cap_args() -> list[str]:
    """Sort clusters by score and cap how many are drawn, so plots stay
    renderable even when a search returns thousands of clusters.
    """
    from cagecat_web.config import get_settings

    return ["--sort_clusters", "--max_plot_clusters", str(get_settings().max_plot_clusters)]


def build_search_args(
    *,
    query_file: Path | None,
    output_dir: Path,
    params: dict[str, Any],
) -> list[str]:
    """Build the ``cblaster search`` argv for a validated parameter set."""
    mode = params.get("mode", "remote")
    args: list[str] = [
        "cblaster",
        "search",
        "--mode",
        mode,
        "--output",
        str(output_dir / SUMMARY_FILE),
        "--binary",
        str(output_dir / BINARY_FILE),
        "--plot",
        str(output_dir / PLOT_FILE),
        "--session_file",
        str(output_dir / SESSION_FILE),
    ]

    if mode == "hmm":
        from cagecat_web.config import get_settings

        settings = get_settings()
        args += ["--query_profiles", *params["query_profiles"]]
        args += ["--database_pfam", str(settings.pfam_dir)]
        args += ["--database", str(settings.hmm_databases()[params["hmm_database"]])]
    else:  # remote or local sequence search
        if mode == "local":
            from cagecat_web.config import get_settings

            db_path = get_settings().local_databases()[params["local_database"]]
            args += ["--database", str(db_path)]
        else:
            args += ["--database", DATABASES[params.get("database", "clusterednr")]]
        if query_file is not None:
            args += ["--query_file", str(query_file)]
        elif params.get("query_ids"):
            args += ["--query_ids", *params["query_ids"]]
        if "hitlist_size" in params:
            args += ["--hitlist_size", str(params["hitlist_size"])]
        if params.get("entrez_query"):
            args += ["--entrez_query", params["entrez_query"]]
        args += _numeric_args(params, _FILTERING_KEYS)

    args += _numeric_args(params, _CLUSTERING_KEYS)
    args += _clustering_extras(params)
    args += _plot_cap_args()

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
    args += _numeric_args(params, _FILTERING_KEYS)
    args += _numeric_args(params, _CLUSTERING_KEYS)
    args += _clustering_extras(params)
    args += _plot_cap_args()
    if params.get("intermediate_genes"):
        args.append("--intermediate_genes")
        if "max_distance" in params:
            args += ["--max_distance", str(params["max_distance"])]
    return args
