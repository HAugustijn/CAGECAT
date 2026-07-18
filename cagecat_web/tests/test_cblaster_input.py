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
