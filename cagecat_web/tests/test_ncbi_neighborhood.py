"""Tests for NCBI gene-neighborhood enrichment (network access is stubbed)."""

from __future__ import annotations

from io import StringIO

import pytest
from Bio.Seq import Seq
from Bio.SeqFeature import FeatureLocation, SeqFeature
from Bio.SeqIO import write as seqio_write
from Bio.SeqRecord import SeqRecord

from cagecat_web.analysis.neighborhood import ncbi as nb


def _genbank_region() -> str:
    """A small GenBank region with two CDS features at local coordinates."""
    record = SeqRecord(Seq("ATGACG" * 30), id="TESTREG", name="TESTREG",
                       description="unit test region")
    record.annotations["molecule_type"] = "DNA"
    record.features.append(SeqFeature(
        FeatureLocation(10, 40, strand=1), type="CDS",
        qualifiers={"gene": ["abcA"], "product": ["Abc protein"]}))
    record.features.append(SeqFeature(
        FeatureLocation(50, 80, strand=-1), type="CDS",
        qualifiers={"locus_tag": ["X_0002"]}))
    buffer = StringIO()
    seqio_write(record, buffer, "genbank")
    return buffer.getvalue()


def test_parse_region_genbank_maps_absolute_coordinates():
    genes = nb.parse_region_genbank(_genbank_region(), region_start=1000)
    assert [g["name"] for g in genes] == ["abcA", "X_0002"]
    # Local 0-based [10,40) -> absolute 1-based [1010, 1039].
    assert genes[0]["start"] == 1010 and genes[0]["end"] == 1039
    assert genes[0]["strand"] == 1
    assert genes[1]["start"] == 1050 and genes[1]["end"] == 1079
    assert genes[1]["strand"] == -1
    assert all(g["family"] is None and g["anchor"] is False for g in genes)


def test_fetch_region_genes_uses_injected_fetcher():
    calls = []

    def fake(accession, start, end):
        calls.append((accession, start, end))
        return _genbank_region()

    genes = nb.fetch_region_genes("ACC.1", 1000, 1200, email="x@y.z", fetcher=fake)
    assert calls and genes[0]["name"] == "abcA"


def test_merge_anchors_overlays_family_on_fetched_gene():
    anchors = [{"name": "hitA", "start": 1010, "end": 1039, "strand": 1,
                "family": "QueryA", "identity": 92.0, "anchor": True}]
    fetched = nb.parse_region_genbank(_genbank_region(), region_start=1000)
    merged = nb.merge_anchors(anchors, fetched)
    assert len(merged) == 2
    anchor = next(g for g in merged if g["anchor"])
    flank = next(g for g in merged if not g["anchor"])
    # The overlapping fetched gene inherits the hit's family/identity and name.
    assert anchor["family"] == "QueryA" and anchor["identity"] == 92.0
    assert anchor["name"] == "hitA"
    assert flank["name"] == "X_0002" and flank["family"] is None


def test_merge_anchors_keeps_unmatched_anchor():
    anchors = [{"name": "far", "start": 9000, "end": 9100, "strand": 1,
                "family": "Q", "identity": 50.0, "anchor": True}]
    fetched = [{"name": "g", "start": 10, "end": 40, "strand": 1,
                "family": None, "identity": None, "anchor": False}]
    merged = nb.merge_anchors(anchors, fetched)
    assert {g["name"] for g in merged} == {"far", "g"}


def test_enrich_loci_merges_and_flags():
    loci = [{
        "number": 1, "scaffold": "NC_TEST.1", "score": 5.0,
        "start": 1010, "end": 1039,
        "genes": [{"name": "hitA", "start": 1010, "end": 1039, "strand": 1,
                   "family": "QueryA", "identity": 92.0, "anchor": True}],
    }]
    fetched = nb.parse_region_genbank(_genbank_region(), region_start=1000)

    def gene_fetcher(accession, region_start, region_end):
        assert accession == "NC_TEST.1"
        assert region_start == 1010 - 500  # flank applied, clamped at >=1
        return fetched

    out, enriched = nb.enrich_loci(loci, "x@y.z", None, flank=500, max_loci=10,
                                   gene_fetcher=gene_fetcher)
    assert enriched is True
    assert out[0]["enriched"] is True
    names = {g["name"] for g in out[0]["genes"]}
    assert "hitA" in names and "X_0002" in names  # hit + a real flanking gene


def test_enrich_loci_writes_genbank_for_clinker(tmp_path, monkeypatch):
    # The default (real-NCBI) path also saves each region's GenBank for a
    # downstream clinker alignment; here the Entrez call is stubbed.
    monkeypatch.setattr(
        nb, "_entrez_fetch",
        lambda accession, start, end, *, email, api_key=None: _genbank_region())
    loci = [{
        "number": 1, "scaffold": "NC_TEST.1", "score": 5.0, "start": 1010, "end": 1039,
        "genes": [{"name": "hitA", "start": 1010, "end": 1039, "strand": 1,
                   "family": "QueryA", "identity": 92.0, "anchor": True,
                   "protein_id": "hitA", "product": None}],
    }]
    out, enriched = nb.enrich_loci(loci, "x@y.z", None, flank=1000, max_loci=10,
                                   genbank_dir=tmp_path)
    assert enriched is True
    assert out[0]["genbank"]
    assert (tmp_path / out[0]["genbank"]).is_file()


def test_enrich_loci_survives_fetch_failure():
    loci = [{"number": 1, "scaffold": "ACC", "score": 1.0, "start": 100, "end": 200,
             "genes": [{"name": "a", "start": 100, "end": 200, "strand": 1,
                        "family": "Q", "identity": 80.0, "anchor": True}]}]

    def boom(accession, region_start, region_end):
        raise RuntimeError("NCBI unreachable")

    out, enriched = nb.enrich_loci(loci, "x@y.z", None, flank=100, max_loci=10,
                                   gene_fetcher=boom)
    assert enriched is False
    assert out[0]["enriched"] is False
    assert [g["name"] for g in out[0]["genes"]] == ["a"]  # anchors preserved


def test_enrich_loci_skips_locus_without_accession():
    loci = [{"number": 1, "scaffold": "", "score": 1.0, "start": 1, "end": 9, "genes": []}]
    out, enriched = nb.enrich_loci(loci, "x@y.z", None, flank=100, max_loci=10,
                                   gene_fetcher=lambda *a: [])
    assert enriched is False and out[0]["enriched"] is False


@pytest.fixture(autouse=True)
def _clear_region_cache():
    nb._REGION_CACHE.clear()
    yield
    nb._REGION_CACHE.clear()
