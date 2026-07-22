"""geneNeighborhood tool adapters.

Two entry points onto the same subprocess runner
(:mod:`cagecat_web.analysis.neighborhood.runner`):

* :class:`CblasterNeighborhoodTool` — the cblaster handoff: a derived tool that
  reads a search's ``session.json`` and fetches the surrounding genes of each
  selected hit cluster from NCBI.
* :class:`NeighborhoodSearchTool` — a primary tool that runs a plain cblaster
  search on the query (FASTA or GenBank) against clusteredNR (or a chosen
  database), then immediately builds the neighborhood of the top hits. This is
  the entry point for a query with no existing BLAST results.

Both write ``neighborhood.json`` for the interactive viewer on the results page.
(Visualising *uploaded* annotated clusters — with no search — is out of scope
here and will live in a dedicated ``clusterViz`` tool.)
"""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING, Any

from cagecat_web.analysis.neighborhood.runner import OUTPUT_FILE
from cagecat_web.analysis.tools.base import ParameterError, Tool

if TYPE_CHECKING:
    from pathlib import Path

_RUNNER = "cagecat_web.analysis.neighborhood.runner"


def _session_mode(session_path: Path) -> str:
    """Return a cblaster session's search ``mode`` ("local"/"remote"/"")."""
    try:
        data = json.loads(session_path.read_text(encoding="utf-8"))
        return str(data.get("params", {}).get("mode", "")).lower()
    except (OSError, json.JSONDecodeError, AttributeError):
        return ""


def _summary(output_dir: Path) -> dict[str, Any]:
    """Summarise a finished neighborhood: locus/gene/family counts."""
    path = output_dir / OUTPUT_FILE
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    loci = data.get("loci", [])
    genes = sum(len(locus.get("genes", [])) for locus in loci)
    families = {
        g.get("family")
        for locus in loci
        for g in locus.get("genes", [])
        if g.get("family")
    }
    return {
        "loci": len(loci),
        "genes": genes,
        "families": len(families),
        "enriched": bool(data.get("enriched")),
    }


class CblasterNeighborhoodTool(Tool):
    """cblaster→geneNeighborhood handoff: fetch and visualise the neighborhood
    of a search's hit clusters."""

    name = "cblaster_neighborhood"
    label = "geneNeighborhood"
    description = "Fetch surrounding genes from NCBI and visualise the neighborhood."
    is_derived = True
    parent_tools = ("cblaster", "cblaster_recompute")
    parent_input = "session"

    def clean_params(self, raw: dict[str, Any]) -> dict[str, Any]:
        from cagecat_web.analysis import input_processor_cblaster as cbi
        from cagecat_web.config import get_settings

        settings = get_settings()
        cleaned: dict[str, Any] = {}
        flank_raw = str(raw.get("flank", "")).strip()
        flank = settings.neighborhood_flank_bp
        if flank_raw:
            try:
                flank = int(float(flank_raw))
            except (TypeError, ValueError) as exc:
                raise ParameterError("'flank' must be a whole number of bp.") from exc
        cleaned["flank"] = max(0, min(flank, settings.max_neighborhood_flank_bp))
        # Restrict to the user's selected clusters when forwarded from the
        # cblaster results page; otherwise all clusters are used.
        clusters = [
            int(c) for c in cbi._split_multi(raw.get("clusters")) if str(c).strip().isdigit()
        ]
        if clusters:
            cleaned["clusters"] = clusters
        return cleaned

    def build_command(
        self, *, input_paths: list[Path], output_dir: Path, params: dict[str, Any]
    ) -> list[str]:
        if not input_paths:
            raise ParameterError("The parent job has no session file to analyse.")
        session = input_paths[0]
        args = [sys.executable, "-m", _RUNNER,
                "--session", str(session),
                "--flank", str(params.get("flank", 0)),
                "--output", str(output_dir / OUTPUT_FILE)]
        if params.get("clusters"):
            args += ["--clusters", *[str(n) for n in params["clusters"]]]
        # A local-database search has no NCBI accessions to enrich from, so ask
        # cblaster to add the surrounding genes from the local database instead.
        # A remote search is enriched from NCBI (richer annotation + clinker input).
        if _session_mode(session) == "local":
            args.append("--add-intermediate")
        else:
            args.append("--enrich")
        return args

    def output_summary(self, output_dir: Path) -> dict[str, Any]:
        return _summary(output_dir)


class NeighborhoodSearchTool(Tool):
    """Search a database on the query, then build each hit's neighborhood.

    A single job with two steps: run a plain cblaster search on the uploaded
    query (FASTA or GenBank) — against clusteredNR by default, or a database the
    user picks — with intermediate genes on, then build the neighborhood of the
    top ``max_neighborhood_fetch`` hit clusters. Remote (NCBI) searches are
    enriched with each cluster's surrounding genes; local-database searches
    already carry them in the session.
    """

    name = "neighborhood_search"
    label = "geneNeighborhood"
    description = "Search a database for the query and build each hit's neighborhood."
    accepted_formats = ("fasta", "genbank")
    min_inputs = 1
    max_inputs = 1

    def clean_params(self, raw: dict[str, Any]) -> dict[str, Any]:
        from cagecat_web.analysis import input_processor_cblaster as cbi
        from cagecat_web.config import get_settings

        settings = get_settings()
        # A plain search (clusteredNR by default, or a chosen database) that also
        # stores the neighborhood, so the result is drawable even without NCBI
        # enrichment. clean_search_params maps the database to local/remote mode.
        forced = dict(raw)
        forced.setdefault("database", "clusterednr")
        forced["intermediate_genes"] = "on"
        cleaned = cbi.clean_search_params(forced)

        flank_raw = str(raw.get("flank", "")).strip()
        flank = settings.neighborhood_flank_bp
        if flank_raw:
            try:
                flank = int(float(flank_raw))
            except (TypeError, ValueError) as exc:
                raise ParameterError("'flank' must be a whole number of bp.") from exc
        cleaned["flank"] = max(0, min(flank, settings.max_neighborhood_flank_bp))
        # Tell cblaster to collect the surrounding genes within ``flank`` bp of
        # each cluster — this is what draws the grey neighborhood, and for local
        # databases it is the only source of it (no NCBI).
        cleaned["max_distance"] = cleaned["flank"]
        return cleaned

    def build_command(
        self, *, input_paths: list[Path], output_dir: Path, params: dict[str, Any]
    ) -> list[list[str]]:
        from cagecat_web.analysis import input_processor_cblaster as cbi
        from cagecat_web.config import get_settings

        if not input_paths:
            raise ParameterError("Upload a query FASTA or GenBank file to search.")
        # Step 1: cblaster search writes session.json.
        search = cbi.build_search_args(
            query_file=input_paths[0], output_dir=output_dir, params=params
        )
        # Step 2: build the top-N neighborhood from the session, with the query
        # shown as the top row. Remote searches are enriched from NCBI; local ones
        # use the session's intermediate genes.
        build = [sys.executable, "-m", _RUNNER,
                 "--session", str(output_dir / cbi.SESSION_FILE),
                 "--flank", str(params.get("flank", 0)),
                 "--top", str(get_settings().max_neighborhood_fetch),
                 "--query-row", "--query", str(input_paths[0]),
                 "--output", str(output_dir / OUTPUT_FILE)]
        if params.get("mode") == "remote":
            build.append("--enrich")
        return [search, build]

    def output_summary(self, output_dir: Path) -> dict[str, Any]:
        return _summary(output_dir)
