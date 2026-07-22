"""Tests for cblaster parameter validation and command construction."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cagecat_web.analysis import input_processor_cblaster as cb
from cagecat_web.analysis.tools.base import ParameterError

if TYPE_CHECKING:
    from pathlib import Path


def test_clean_params_defaults():
    cleaned = cb.clean_search_params({})
    assert cleaned["mode"] == "remote"
    assert cleaned["database"] == "clusterednr"
    assert cleaned["intermediate_genes"] is False


def test_clean_params_rejects_unknown_database():
    with pytest.raises(ParameterError, match="database"):
        cb.clean_search_params({"database": "not-a-db"})


def test_clean_params_bounds_numeric():
    with pytest.raises(ParameterError, match="min_identity"):
        cb.clean_search_params({"min_identity": "150"})


def test_clean_params_coerces_valid_numbers():
    cleaned = cb.clean_search_params({"hitlist_size": "250", "max_evalue": "0.05"})
    assert cleaned["hitlist_size"] == 250
    assert cleaned["max_evalue"] == 0.05


def test_build_search_args_uses_real_flags(tmp_path: Path):
    params = cb.clean_search_params({"database": "nr", "hitlist_size": "100"})
    args = cb.build_search_args(
        query_file=tmp_path / "q.fasta", output_dir=tmp_path / "out", params=params
    )
    assert args[:2] == ["cblaster", "search"]
    assert args[args.index("--database") + 1] == "nr"
    assert "--query_file" in args
    # "Maximum hits" maps to --hitlist_size, not --max_hits.
    assert "--hitlist_size" in args
    assert "--max_hits" not in args
    assert "--session_file" in args


def test_build_search_args_without_query_file_uses_ids(tmp_path: Path):
    params = cb.clean_search_params({"query_ids": "ABC123 DEF456"})
    args = cb.build_search_args(
        query_file=None, output_dir=tmp_path / "out", params=params
    )
    assert "--query_ids" in args
    assert "ABC123" in args and "DEF456" in args
    assert "--query_file" not in args


def test_build_search_args_toggles_flags(tmp_path: Path):
    params = cb.clean_search_params(
        {"intermediate_genes": "on", "sort_clusters": "true", "max_distance": "4000"}
    )
    args = cb.build_search_args(
        query_file=tmp_path / "q.fasta", output_dir=tmp_path / "out", params=params
    )
    assert "--intermediate_genes" in args
    assert "--sort_clusters" in args
    assert args[args.index("--max_distance") + 1] == "4000"


def test_hmm_requires_profiles():
    with pytest.raises(ParameterError, match="Pfam profile"):
        cb.clean_search_params({"mode": "hmm", "hmm_database": "testdb"})


def test_hmm_rejects_unknown_database():
    with pytest.raises(ParameterError, match="Unknown HMM database"):
        cb.clean_search_params(
            {"mode": "hmm", "query_profiles": "PF00005", "hmm_database": "nope"}
        )


def test_hmm_clean_params_ok():
    cleaned = cb.clean_search_params(
        {
            "mode": "hmm",
            "hmm_database": "testdb",
            "query_profiles": "PF00593.27 PF00664.26, PF00005.30",
        }
    )
    assert cleaned["mode"] == "hmm"
    assert cleaned["hmm_database"] == "testdb"
    # Version suffixes are stripped so profiles match any installed Pfam release.
    assert cleaned["query_profiles"] == ["PF00593", "PF00664", "PF00005"]


def test_hmm_rejects_invalid_profile():
    with pytest.raises(ParameterError, match="Invalid Pfam"):
        cb.clean_search_params(
            {"mode": "hmm", "hmm_database": "testdb", "query_profiles": "notapfam"}
        )


def test_hmm_build_args(tmp_path: Path):
    params = cb.clean_search_params(
        {"mode": "hmm", "hmm_database": "testdb", "query_profiles": "PF00005", "gap": "5000"}
    )
    args = cb.build_search_args(query_file=None, output_dir=tmp_path, params=params)
    assert args[args.index("--mode") + 1] == "hmm"
    assert "--query_profiles" in args
    assert "PF00005" in args
    assert "--database_pfam" in args
    # HMM must not carry BLAST-hit filtering flags.
    assert "--min_identity" not in args
    assert "--max_evalue" not in args
    # Clustering flags still apply.
    assert args[args.index("--gap") + 1] == "5000"


def test_unsupported_mode_rejected():
    with pytest.raises(ParameterError, match="Unsupported search mode"):
        cb.clean_search_params({"mode": "combi_remote"})


def test_local_database_switches_to_local_mode():
    cleaned = cb.clean_search_params({"database": "testdb", "min_identity": "40"})
    assert cleaned["mode"] == "local"
    assert cleaned["local_database"] == "testdb"


def test_local_build_args_use_dmnd(tmp_path: Path):
    params = cb.clean_search_params({"database": "testdb"})
    args = cb.build_search_args(
        query_file=tmp_path / "q.fasta", output_dir=tmp_path / "out", params=params
    )
    assert args[args.index("--mode") + 1] == "local"
    assert any(a.endswith("testdb.dmnd") for a in args)
    assert "--entrez_query" not in args


def test_remote_database_stays_remote():
    cleaned = cb.clean_search_params({"database": "nr"})
    assert cleaned["mode"] == "remote"
    assert cleaned["database"] == "nr"


def test_parse_clusters():
    session = {
        "organisms": [
            {
                "name": "haemophilus",
                "scaffolds": [
                    {
                        "accession": "NC_000907.1",
                        "clusters": [
                            {"number": 24, "score": 9.07573, "start": 1, "end": 99, "indices": [1, 2, 3]},
                            {"number": 4, "score": 3.1, "start": 5, "end": 9, "indices": [4]},
                        ],
                    }
                ],
            }
        ]
    }
    clusters = cb.parse_clusters(session)
    assert [c["number"] for c in clusters] == [4, 24]  # sorted by number
    assert clusters[1]["organism"] == "haemophilus"
    assert clusters[1]["scaffold"] == "NC_000907.1"
    assert clusters[1]["score"] == 9.08
    assert clusters[1]["n_genes"] == 3


def test_parse_cluster_neighborhoods():
    session = {
        "queries": ["QueryA", "QueryB"],
        "organisms": [
            {
                "name": "haemophilus",
                "strain": "Rd",
                "scaffolds": [
                    {
                        "accession": "NC_000907.1",
                        "subjects": [
                            {"name": "geneL", "start": 10, "end": 40, "strand": "+", "hits": []},
                            {"name": "geneA", "start": 50, "end": 110, "strand": "-",
                             "hits": [{"query": "QueryA", "identity": 88.4}]},
                            {"name": "geneB", "start": 120, "end": 200, "strand": "+",
                             "hits": [{"query": "QueryB", "identity": 55.1},
                                      {"query": "QueryA", "identity": 91.0}]},
                        ],
                        "clusters": [
                            {"number": 3, "score": 7.5, "start": 10, "end": 200,
                             "indices": [2, 0, 1]},
                        ],
                    }
                ],
            }
        ],
    }
    result = cb.parse_cluster_neighborhoods(session)
    assert result["queries"] == ["QueryA", "QueryB"]
    assert len(result["loci"]) == 1
    locus = result["loci"][0]
    assert locus["number"] == 3
    assert locus["organism"] == "haemophilus"
    assert locus["strain"] == "Rd"
    genes = locus["genes"]
    # Genes are returned sorted by start coordinate.
    assert [g["name"] for g in genes] == ["geneL", "geneA", "geneB"]
    # Flanking gene has no family; strand normalised to +1/-1.
    assert genes[0]["family"] is None and genes[0]["anchor"] is False and genes[0]["strand"] == 1
    assert genes[1]["family"] == "QueryA" and genes[1]["anchor"] is True and genes[1]["strand"] == -1
    # Best hit (highest identity) defines the family/identity.
    assert genes[2]["family"] == "QueryA" and genes[2]["identity"] == 91.0


def test_parse_cluster_neighborhoods_includes_intermediate_genes():
    # cblaster stores the surrounding genes in a separate "intermediate_genes"
    # list, not in the cluster indices. They must appear as grey (no-family) genes.
    session = {
        "queries": ["Q"],
        "organisms": [{"name": "org", "scaffolds": [{
            "accession": "acc",
            "subjects": [{"name": "hit", "start": 500, "end": 900, "strand": "+",
                          "hits": [{"query": "Q", "identity": 90.0}]}],
            "clusters": [{"number": 1, "score": 5.0, "start": 500, "end": 900,
                          "indices": [0],
                          "intermediate_genes": [
                              {"name": "flankL", "start": 100, "end": 400, "strand": 1, "hits": []},
                              {"name": "flankR", "start": 1000, "end": 1400, "strand": -1, "hits": []},
                          ]}],
        }]}],
    }
    genes = cb.parse_cluster_neighborhoods(session)["loci"][0]["genes"]
    assert [g["name"] for g in genes] == ["flankL", "hit", "flankR"]  # sorted by start
    hit = next(g for g in genes if g["name"] == "hit")
    flanks = [g for g in genes if g["name"] != "hit"]
    assert hit["anchor"] and hit["family"] == "Q"
    assert all(not g["anchor"] and g["family"] is None for g in flanks)


def test_parse_cluster_neighborhoods_ignores_bad_indices():
    session = {
        "organisms": [
            {
                "name": "org",
                "scaffolds": [
                    {
                        "accession": "acc",
                        "subjects": [{"name": "g", "start": 1, "end": 9, "strand": "+", "hits": []}],
                        "clusters": [{"number": 1, "score": 1.0, "indices": [0, 5, "x"]}],
                    }
                ],
            }
        ]
    }
    loci = cb.parse_cluster_neighborhoods(session)["loci"]
    assert len(loci) == 1
    assert [g["name"] for g in loci[0]["genes"]] == ["g"]


def test_build_recompute_args(tmp_path: Path):
    params = cb.clean_search_params({"gap": "40000", "unique": "4"})
    args = cb.build_recompute_args(
        parent_session=tmp_path / "session.json",
        output_dir=tmp_path / "out",
        params=params,
    )
    assert args[:2] == ["cblaster", "search"]
    assert "--recompute" in args
    assert args[args.index("--gap") + 1] == "40000"
