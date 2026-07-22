"""Subprocess entry point for the geneNeighborhood analysis.

Run as ``python -m cagecat_web.analysis.neighborhood.runner`` by the job worker.
It reads a cblaster search ``session.json``, takes each cluster's hits and
(optionally) fetches the surrounding genes from NCBI, and writes
``neighborhood.json`` into the job's output directory in the shape the
geneNeighborhood viewer consumes:

    {"source", "queries", "enriched", "flank", "loci": [
        {"label", "sub", "score", "scaffold", "number", "start", "end",
         "genes": [{"name", "start", "end", "strand", "family", "identity",
                    "anchor", "product", "protein_id"}]}
    ]}

The heavy lifting lives in importable functions so it is unit-testable offline
(NCBI access is injectable); ``main`` only wires argparse to those functions.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

OUTPUT_FILE = "neighborhood.json"


def _cblaster_label(locus: dict[str, Any]) -> tuple[str, str]:
    """Return the (label, sub-label) shown for a cblaster locus."""
    organism = locus.get("organism") or "Unknown"
    strain = locus.get("strain")
    label = organism
    if strain and strain not in organism:
        label = f"{organism} {strain}"
    parts = [
        locus.get("scaffold"),
        f"cluster {locus['number']}" if locus.get("number") is not None else None,
        f"score {locus['score']}" if locus.get("score") is not None else None,
    ]
    return label, "  ·  ".join(p for p in parts if p)


def _query_genes_from_genbank(path: Path) -> list[dict[str, Any]]:
    """Parse the CDS features of a GenBank query into query-row genes."""
    from Bio import SeqIO

    genes: list[dict[str, Any]] = []
    for record in SeqIO.parse(str(path), "genbank"):
        for f in record.features:
            if f.type != "CDS":
                continue
            q = f.qualifiers
            name = (q.get("gene") or q.get("locus_tag") or q.get("protein_id")
                    or q.get("product") or ["gene"])[0]
            genes.append({
                "name": name,
                "start": int(f.location.start) + 1,
                "end": int(f.location.end),
                "strand": 1 if f.location.strand == 1 else -1 if f.location.strand == -1 else 0,
                "product": q.get("product", [None])[0],
                "protein_id": q.get("protein_id", [None])[0],
            })
    genes.sort(key=lambda g: g["start"])
    return genes


def _synthetic_query_genes(queries: list[str]) -> list[dict[str, Any]]:
    """Lay the query genes out evenly (for a FASTA query with no coordinates)."""
    genes, pos = [], 1
    for name in queries:
        genes.append({"name": name, "start": pos, "end": pos + 899, "strand": 1,
                      "product": None, "protein_id": None})
        pos += 1100
    return genes


def build_query_locus(queries: list[str], query_path: Any | None = None) -> dict[str, Any] | None:
    """Build the synthetic "Query" locus shown as the top row of a search.

    Genes are taken from the GenBank query (real coordinates) when available,
    else laid out evenly from the query names. Each gene's family is set to the
    matching cblaster query name so it lines up with its hits in the rows below.
    """
    from cagecat_web.analysis.validation import FORMAT_EXTENSIONS

    genes: list[dict[str, Any]] = []
    if query_path is not None:
        path = Path(query_path)
        if path.suffix.lower() in set(FORMAT_EXTENSIONS["genbank"]) and path.is_file():
            try:
                genes = _query_genes_from_genbank(path)
            except Exception:
                genes = []
    if not genes:
        genes = _synthetic_query_genes(queries)
    if not genes:
        return None

    qset = set(queries)
    for i, g in enumerate(genes):
        g["identity"] = None
        g["anchor"] = True
        if g["name"] in qset:
            g["family"] = g["name"]
        elif i < len(queries):
            g["family"] = queries[i]
        else:
            g["family"] = g["name"]
    return {
        "label": "Query", "sub": f"{len(genes)} query genes",
        "score": None, "scaffold": None, "number": None,
        "start": min(g["start"] for g in genes),
        "end": max(g["end"] for g in genes),
        "genes": genes, "is_query": True,
    }


def add_intermediate_genes(session: dict[str, Any], gene_distance: int,
                           max_clusters: int) -> dict[str, Any]:
    """Populate each cluster's ``intermediate_genes`` (the neighborhood) via cblaster.

    For a local session cblaster reads the DB path from ``session["params"]``; for
    a remote session it fetches from NCBI. It only *adds* genes, so clusters keep
    their numbers. Degrades to the unchanged session if cblaster is unavailable or
    the lookup fails (e.g. the database has moved).
    """
    try:
        from cblaster.classes import Session
        from cblaster.intermediate_genes import find_intermediate_genes
    except ImportError:
        return session
    try:
        obj = Session.from_dict(session)
        find_intermediate_genes(obj, gene_distance=gene_distance or 5000,
                                max_clusters=max_clusters)
        return obj.to_dict()
    except Exception as exc:  # best effort — keep the neighborhood usable
        print(f"Could not compute intermediate genes: {exc}", file=sys.stderr)
        return session


def build_cblaster_neighborhood(
    session: dict[str, Any], *, flank: int, enrich: bool, email: str | None,
    api_key: str | None, max_fetch: int, max_display: int,
    clusters: list[int] | None = None, top: int | None = None,
    add_query_row: bool = False, query_path: Any | None = None,
    add_intermediate: bool = False,
    genbank_dir: Any | None = None, gene_fetcher: Any | None = None,
) -> dict[str, Any]:
    """Build the neighborhood model from a cblaster session dict.

    ``clusters`` (cluster numbers, e.g. the user's selection on the cblaster
    results page) restricts which clusters are included; ``None`` means all.
    ``top`` caps the number of (highest-scoring) loci kept before building.
    ``add_query_row`` prepends a "Query" locus built from the search's queries.
    ``add_intermediate`` first asks cblaster to add the surrounding genes (used
    when forwarding a local-database search, whose accessions are not on NCBI).
    """
    from cagecat_web.analysis.input_processor_cblaster import (
        parse_cluster_neighborhoods,
    )

    if add_intermediate:
        session = add_intermediate_genes(session, flank, max_display)
    parsed = parse_cluster_neighborhoods(session)
    loci = parsed["loci"]  # already sorted by score, descending
    if clusters:
        wanted = set(clusters)
        loci = [locus for locus in loci if locus.get("number") in wanted]
    if top:
        loci = loci[:top]
    enriched = False

    if enrich and email:
        from cagecat_web.analysis.neighborhood import ncbi as nb

        loci, enriched = nb.enrich_loci(
            loci, email, api_key, flank, max_fetch,
            gene_fetcher=gene_fetcher, genbank_dir=genbank_dir,
        )
    else:
        loci = loci[:max_display]

    for locus in loci:
        locus["label"], locus["sub"] = _cblaster_label(locus)

    if add_query_row:
        query_locus = build_query_locus(parsed["queries"], query_path)
        if query_locus:
            loci = [query_locus, *loci]

    return {
        "source": "cblaster",
        "queries": parsed["queries"],
        "enriched": enriched,
        "flank": flank if enrich else 0,
        "loci": loci,
    }


# ── CLI ────────────────────────────────────────────────────────────────────
def main(argv: list[str] | None = None) -> int:
    from cagecat_web.config import get_settings

    parser = argparse.ArgumentParser(description="Build a gene-neighborhood model.")
    parser.add_argument("--session", type=Path, required=True,
                        help="cblaster session.json to build the neighborhood from")
    parser.add_argument("--clusters", type=int, nargs="*", default=None,
                        help="cluster numbers to include (default: all)")
    parser.add_argument("--top", type=int, default=None,
                        help="keep only the top N clusters by score")
    parser.add_argument("--flank", type=int, default=0, help="NCBI fetch flank in bp")
    parser.add_argument("--enrich", action="store_true", help="fetch flanking genes from NCBI")
    parser.add_argument("--add-intermediate", action="store_true",
                        help="ask cblaster to add the surrounding genes (local databases)")
    parser.add_argument("--query-row", action="store_true",
                        help="prepend a Query locus built from the search queries")
    parser.add_argument("--query", type=Path, default=None,
                        help="the query file (for the Query row's real coordinates)")
    parser.add_argument("--output", default=OUTPUT_FILE)
    args = parser.parse_args(argv)

    settings = get_settings()
    if not args.session.is_file():
        print("cblaster session file not found", file=sys.stderr)
        return 1
    session = json.loads(args.session.read_text(encoding="utf-8"))
    result = build_cblaster_neighborhood(
        session, flank=args.flank, enrich=args.enrich,
        email=(settings.cblaster_email or "").strip() or None,
        api_key=settings.cblaster_api_key,
        max_fetch=settings.max_neighborhood_fetch,
        max_display=settings.max_display_clusters,
        clusters=args.clusters or None,
        top=args.top,
        add_query_row=args.query_row,
        query_path=args.query,
        add_intermediate=args.add_intermediate,
        genbank_dir=Path(args.output).resolve().parent,  # region GenBanks for clinker
    )

    if not result["loci"]:
        print("No gene clusters with coordinates were found to visualise.",
              file=sys.stderr)
        return 1

    Path(args.output).write_text(json.dumps(result), encoding="utf-8")
    print(f"Wrote {len(result['loci'])} loci to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
