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
    assert cleaned["database"] == "nr"
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
