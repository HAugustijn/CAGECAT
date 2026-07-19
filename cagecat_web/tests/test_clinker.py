"""Tests for the clinker tool adapter."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cagecat_web.analysis.tools import get_tool
from cagecat_web.analysis.tools.base import ParameterError

if TYPE_CHECKING:
    from pathlib import Path


def test_clean_params_defaults_empty():
    assert get_tool("clinker").clean_params({}) == {}


def test_clean_params_identity_bounds():
    with pytest.raises(ParameterError, match="identity"):
        get_tool("clinker").clean_params({"identity": "5"})


def test_clean_params_flags_and_values():
    cleaned = get_tool("clinker").clean_params(
        {
            "identity": "0.5",
            "decimals": "4",
            "delimiter": ",",
            "no_align": "on",
            "as_separate_clusters": "true",
        }
    )
    assert cleaned["identity"] == 0.5
    assert cleaned["decimals"] == 4
    assert cleaned["delimiter"] == ","
    assert cleaned["no_align"] is True
    assert cleaned["as_separate_clusters"] is True


def test_build_command(tmp_path: Path):
    tool = get_tool("clinker")
    params = tool.clean_params({"identity": "0.5", "no_align": "on"})
    cmd = tool.build_command(
        input_paths=[tmp_path / "a.gbk", tmp_path / "b.gbk"],
        output_dir=tmp_path,
        params=params,
    )
    assert cmd[0] == "clinker"
    assert str(tmp_path / "a.gbk") in cmd
    assert str(tmp_path / "b.gbk") in cmd
    assert "--plot" in cmd
    assert "--session" in cmd
    assert cmd[cmd.index("--identity") + 1] == "0.5"
    assert "--no_align" in cmd
