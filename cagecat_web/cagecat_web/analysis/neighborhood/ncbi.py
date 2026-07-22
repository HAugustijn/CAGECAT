"""Fetch the genomic neighborhood of cblaster hits from NCBI.

A cblaster search only stores the *hit* genes for each cluster unless it was run
with ``--intermediate_genes``. To draw a real EFI-GNT-style neighborhood we need
the surrounding genes too. This module uses each cluster's scaffold accession and
genomic coordinates to fetch the flanking region from NCBI Entrez, parse its gene
annotations, and merge them with the cblaster hits (which keep their query family
and identity so the viewer can colour homologous genes across loci).

Network access is isolated behind an injectable *fetcher* so the merge/parse logic
is fully unit-testable offline.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from io import StringIO
from typing import Any

#: Feature types treated as genes, in priority order for de-duplication.
_GENE_TYPES = ("CDS", "tRNA", "rRNA", "ncRNA", "tmRNA")

# Process-wide cache of fetched region GenBank text, keyed by (accession, start,
# end). NCBI regions are immutable, so repeated fetches (e.g. genes + saving the
# GenBank for a clinker handoff) reuse the same download.
_REGION_CACHE: dict[tuple[str, int, int], str] = {}

#: A callable that returns the GenBank text for a region of an accession.
TextFetcher = Callable[[str, int, int], str]
#: A callable that returns parsed gene dicts for a region of an accession.
GeneFetcher = Callable[[str, int, int], list[dict[str, Any]]]


def _strand_int(value: Any) -> int:
    """Map a Biopython strand """
    if value == 1:
        return 1
    if value == -1:
        return -1
    return 0


def parse_region_genbank(text: str, region_start: int) -> list[dict[str, Any]]:
    """Parse NCBI GenBank ``text`` for a sub-region into absolute-coordinate genes.

    ``region_start`` is the 1-based genomic coordinate the region was fetched from
    (Entrez re-bases a ``seq_start``/``seq_stop`` fetch so the returned sequence
    starts at 1); feature coordinates are shifted back onto the genome.
    """
    from Bio import SeqIO

    record = SeqIO.read(StringIO(text), "genbank")
    feats = [f for f in record.features if f.type == "CDS"]
    if not feats:
        feats = [f for f in record.features if f.type == "gene"]
    feats += [f for f in record.features if f.type in _GENE_TYPES[1:]]

    genes: list[dict[str, Any]] = []
    for f in feats:
        q = f.qualifiers
        name = (q.get("gene") or q.get("locus_tag") or q.get("product") or [f.type])[0]
        product = q.get("product", [None])[0]
        protein_id = q.get("protein_id", [None])[0]
        start = region_start + int(f.location.start)
        end = region_start + int(f.location.end) - 1
        genes.append(
            {
                "name": name,
                "start": start,
                "end": end,
                "strand": _strand_int(f.location.strand),
                "family": None,
                "identity": None,
                "anchor": False,
                "product": product,
                "protein_id": protein_id,
            }
        )
    genes.sort(key=lambda g: g["start"])
    return genes


def _entrez_fetch(accession: str, start: int, end: int, *, email: str,
                  api_key: str | None = None) -> str:
    """Fetch a region of ``accession`` from NCBI nuccore as GenBank text."""
    from Bio import Entrez

    Entrez.email = email
    if api_key:
        Entrez.api_key = api_key
    handle = Entrez.efetch(
        db="nuccore", id=accession, rettype="gbwithparts", retmode="text",
        seq_start=start, seq_stop=end,
    )
    try:
        return handle.read()
    finally:
        handle.close()


def fetch_region_genbank(accession: str, region_start: int, region_end: int, *,
                         email: str, api_key: str | None = None,
                         fetcher: TextFetcher | None = None) -> str:
    """Return the GenBank text for ``[region_start, region_end]`` of ``accession``.

    Cached per region so fetching genes and saving the GenBank (for the clinker
    handoff) share a single download.
    """
    key = (accession, region_start, region_end)
    if key in _REGION_CACHE:
        return _REGION_CACHE[key]
    fetch = fetcher or (
        lambda a, s, e: _entrez_fetch(a, s, e, email=email, api_key=api_key)
    )
    text = fetch(accession, region_start, region_end)
    _REGION_CACHE[key] = text
    return text


def fetch_region_genes(accession: str, region_start: int, region_end: int, *,
                       email: str, api_key: str | None = None,
                       fetcher: TextFetcher | None = None) -> list[dict[str, Any]]:
    """Fetch and parse the genes in ``[region_start, region_end]`` of ``accession``."""
    text = fetch_region_genbank(accession, region_start, region_end,
                                email=email, api_key=api_key, fetcher=fetcher)
    return parse_region_genbank(text, region_start)


def _overlap(a0: int, a1: int, b0: int, b1: int) -> int:
    """Length of the overlap between inclusive ranges ``[a0,a1]`` and ``[b0,b1]``."""
    return max(0, min(a1, b1) - max(a0, b0) + 1)


def merge_anchors(anchors: list[dict[str, Any]],
                  fetched: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Overlay cblaster ``anchors`` (query hits) onto NCBI-``fetched`` genes.

    A fetched gene that overlaps an anchor by >=50 % of the shorter span inherits
    the anchor's family/identity and is marked as the query anchor; other fetched
    genes become flanking genes. Anchors with no matching fetched gene are kept so
    nothing is lost when annotations disagree.
    """
    used: set[int] = set()
    out: list[dict[str, Any]] = []
    for fg in fetched:
        match_i = -1
        for i, a in enumerate(anchors):
            if i in used or a.get("start") is None or a.get("end") is None:
                continue
            ov = _overlap(fg["start"], fg["end"], a["start"], a["end"])
            shorter = min(fg["end"] - fg["start"] + 1, a["end"] - a["start"] + 1)
            if ov > 0 and ov >= 0.5 * shorter:
                match_i = i
                break
        if match_i >= 0:
            a = anchors[match_i]
            used.add(match_i)
            merged = dict(fg)
            merged["family"] = a.get("family")
            merged["identity"] = a.get("identity")
            merged["anchor"] = True
            merged["name"] = a.get("name") or fg["name"]
            # Keep the cblaster protein accession for the out-link; take the
            # product annotation from the NCBI record.
            merged["protein_id"] = a.get("protein_id") or fg.get("protein_id")
            merged["product"] = fg.get("product")
            out.append(merged)
        else:
            out.append(fg)
    for i, a in enumerate(anchors):
        if i not in used:
            out.append(a)
    out.sort(key=lambda g: (g.get("start") is None, g.get("start") or 0))
    return out


def enrich_loci(loci: list[dict[str, Any]], email: str, api_key: str | None,
                flank: int, max_loci: int, gene_fetcher: GeneFetcher | None = None,
                genbank_dir: Any | None = None) -> tuple[list[dict[str, Any]], bool]:
    """Return the top ``max_loci`` loci enriched with NCBI-fetched flanking genes.

    Each locus' ``genes`` list is replaced by the fetched neighborhood merged with
    the original cblaster hits; a per-locus ``enriched`` flag records success. The
    returned bool is ``True`` if at least one locus was enriched. Loci without a
    usable accession/coordinates, or whose fetch fails, keep their original genes.

    When ``genbank_dir`` is given (real-NCBI path only), each enriched region's
    GenBank is written there and its filename recorded on the locus as
    ``genbank`` — the input for a downstream clinker alignment.
    """
    from pathlib import Path

    shown = [dict(locus) for locus in loci[:max_loci]]
    any_enriched = False
    save_genbank = genbank_dir is not None and gene_fetcher is None

    def default_fetcher(accession: str, start: int, end: int) -> list[dict[str, Any]]:
        # Respect NCBI's rate limit (10 req/s with a key, 3 without).
        time.sleep(0.11 if api_key else 0.34)
        return fetch_region_genes(accession, start, end, email=email, api_key=api_key)

    fetch = gene_fetcher or default_fetcher

    for i, locus in enumerate(shown, start=1):
        accession = (locus.get("scaffold") or "").strip()
        start, end = locus.get("start"), locus.get("end")
        if not accession or start is None or end is None:
            locus["enriched"] = False
            continue
        region_start = max(1, int(start) - flank)
        region_end = int(end) + flank
        try:
            fetched = fetch(accession, region_start, region_end)
        except Exception:
            locus["enriched"] = False
            continue
        locus["genes"] = merge_anchors(locus.get("genes", []), fetched)
        locus["enriched"] = True
        any_enriched = True
        if save_genbank:
            try:
                text = fetch_region_genbank(accession, region_start, region_end,
                                            email=email, api_key=api_key)  # cache hit
                safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in accession)
                path = Path(genbank_dir) / f"locus{i:02d}_{safe}.gbk"
                path.write_text(text, encoding="utf-8")
                locus["genbank"] = path.name
            except OSError:
                pass

    return shown, any_enriched
