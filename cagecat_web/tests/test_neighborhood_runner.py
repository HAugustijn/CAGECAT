"""Tests for the geneNeighborhood tool adapters and subprocess runner."""

from __future__ import annotations

import json
from pathlib import Path

from cagecat_web.analysis.neighborhood import runner
from cagecat_web.analysis.tools import get_tool


def _session(numbers=(2,)):
    clusters = [
        {"number": n, "score": float(10 - n), "start": 1010, "end": 1039, "indices": [0]}
        for n in numbers
    ]
    return {
        "queries": ["QueryA"],
        "organisms": [{
            "name": "Escherichia coli", "strain": "K12",
            "scaffolds": [{
                "accession": "NC_000913.3",
                "subjects": [{"name": "hitA", "start": 1010, "end": 1039,
                              "strand": "+", "hits": [{"query": "QueryA", "identity": 90.0}]}],
                "clusters": clusters,
            }],
        }],
    }


def test_build_cblaster_neighborhood_without_enrich():
    result = runner.build_cblaster_neighborhood(
        _session(), flank=5000, enrich=False, email=None, api_key=None,
        max_fetch=20, max_display=500)
    assert result["source"] == "cblaster"
    assert result["enriched"] is False and result["flank"] == 0
    locus = result["loci"][0]
    assert locus["label"] == "Escherichia coli K12"
    assert "cluster 2" in locus["sub"] and "score 8.0" in locus["sub"]
    assert [g["name"] for g in locus["genes"]] == ["hitA"]


def test_build_cblaster_neighborhood_with_injected_fetcher():
    def gene_fetcher(accession, region_start, region_end):
        assert accession == "NC_000913.3"
        return [
            {"name": "flankUp", "start": 700, "end": 950, "strand": 1,
             "family": None, "identity": None, "anchor": False},
            {"name": "hitA_ncbi", "start": 1010, "end": 1039, "strand": 1,
             "family": None, "identity": None, "anchor": False},
        ]

    result = runner.build_cblaster_neighborhood(
        _session(), flank=1000, enrich=True, email="me@example.com", api_key=None,
        max_fetch=20, max_display=500, gene_fetcher=gene_fetcher)
    assert result["enriched"] is True and result["flank"] == 1000
    genes = result["loci"][0]["genes"]
    assert any(g["name"] == "flankUp" and g["family"] is None for g in genes)
    assert any(g["anchor"] and g["family"] == "QueryA" for g in genes)


def test_build_cblaster_neighborhood_caps_to_top():
    result = runner.build_cblaster_neighborhood(
        _session(numbers=(1, 2, 3, 4, 5)), flank=0, enrich=False, email=None,
        api_key=None, max_fetch=20, max_display=500, top=2)
    # Kept the two highest-scoring clusters (score = 10 - number).
    assert [locus["number"] for locus in result["loci"]] == [1, 2]


def test_cblaster_build_filters_selected_clusters():
    result = runner.build_cblaster_neighborhood(
        _session(numbers=(1, 2, 3)), flank=0, enrich=False, email=None, api_key=None,
        max_fetch=20, max_display=500, clusters=[2])
    assert [locus["number"] for locus in result["loci"]] == [2]


def test_build_query_locus_from_query_names():
    locus = runner.build_query_locus(["queryA", "queryB"])
    assert locus["is_query"] is True and locus["label"] == "Query"
    assert [g["name"] for g in locus["genes"]] == ["queryA", "queryB"]
    # Each query gene is an anchor whose family matches its cblaster query name.
    assert all(g["anchor"] and g["family"] == g["name"] for g in locus["genes"])


def test_build_cblaster_neighborhood_prepends_query_row():
    result = runner.build_cblaster_neighborhood(
        _session(), flank=0, enrich=False, email=None, api_key=None,
        max_fetch=20, max_display=500, add_query_row=True)
    assert result["loci"][0]["is_query"] is True     # query row on top
    assert result["loci"][1].get("is_query") is not True  # then the hit clusters
    # The query gene shares the family "QueryA" with the hit below it.
    assert result["loci"][0]["genes"][0]["family"] == "QueryA"


def test_cblaster_tool_build_command_and_params(tmp_path):
    tool = get_tool("cblaster_neighborhood")
    # Only the selected clusters are forwarded.
    params = tool.clean_params({"flank": "8000", "clusters": "3 7 12"})
    assert params["flank"] == 8000
    assert params["clusters"] == [3, 7, 12]
    cmd = tool.build_command(
        input_paths=[Path("/out/session.json")], output_dir=tmp_path, params=params)
    assert cmd[cmd.index("-m") + 1] == "cagecat_web.analysis.neighborhood.runner"
    assert cmd[cmd.index("--flank") + 1] == "8000"
    ci = cmd.index("--clusters")
    assert cmd[ci + 1:ci + 4] == ["3", "7", "12"]


def test_cblaster_tool_local_parent_adds_intermediate(tmp_path):
    session = tmp_path / "session.json"
    session.write_text(json.dumps({"params": {"mode": "local"}}))
    cmd = get_tool("cblaster_neighborhood").build_command(
        input_paths=[session], output_dir=tmp_path, params={"flank": 5000})
    # Local database: get the neighborhood from cblaster/local DB, not NCBI.
    assert "--add-intermediate" in cmd and "--enrich" not in cmd


def test_cblaster_tool_remote_parent_enriches(tmp_path):
    session = tmp_path / "session.json"
    session.write_text(json.dumps({"params": {"mode": "remote"}}))
    cmd = get_tool("cblaster_neighborhood").build_command(
        input_paths=[session], output_dir=tmp_path, params={"flank": 5000})
    assert "--enrich" in cmd and "--add-intermediate" not in cmd


def test_add_intermediate_genes_degrades_without_cblaster():
    # cblaster is not installed in the test venv, so the session is returned as-is
    # (the real worker has cblaster and populates intermediate_genes).
    sess = {"queries": [], "organisms": []}
    assert runner.add_intermediate_genes(sess, 5000, 20) == sess


def test_cblaster_tool_caps_flank():
    tool = get_tool("cblaster_neighborhood")
    params = tool.clean_params({"flank": "999999999"})
    assert params["flank"] == 50_000  # max_neighborhood_flank_bp


def test_search_tool_remote_two_step_command(tmp_path):
    tool = get_tool("neighborhood_search")
    params = tool.clean_params({"flank": "6000"})  # default database = clusteredNR
    assert params["mode"] == "remote"
    assert params["database"] == "clusterednr"
    assert params["intermediate_genes"] is True
    assert params["flank"] == 6000
    assert params["max_distance"] == 6000  # cblaster collects genes within the flank
    cmds = tool.build_command(
        input_paths=[Path("/in/query.fasta")], output_dir=tmp_path, params=params)
    # Step 1: cblaster search; step 2: the neighborhood runner.
    assert cmds[0][0] == "cblaster" and cmds[0][1] == "search"
    assert "--database" in cmds[0] and "--query_file" in cmds[0]
    assert "--intermediate_genes" in cmds[0]
    runner_cmd = cmds[1]
    assert runner_cmd[runner_cmd.index("-m") + 1] == "cagecat_web.analysis.neighborhood.runner"
    assert runner_cmd[runner_cmd.index("--flank") + 1] == "6000"
    assert "--top" in runner_cmd
    assert "--query-row" in runner_cmd  # the query is drawn as the top row
    assert runner_cmd[runner_cmd.index("--query") + 1] == "/in/query.fasta"
    assert "--enrich" in runner_cmd  # remote search → enrich from NCBI


def test_search_tool_accepts_genbank():
    assert set(get_tool("neighborhood_search").accepted_formats) == {"fasta", "genbank"}


def test_search_tool_local_db_skips_enrich(tmp_path):
    # A local database (the test fixture "testdb") searches in local mode and does
    # not enrich from NCBI — the session already carries the intermediate genes.
    tool = get_tool("neighborhood_search")
    params = tool.clean_params({"database": "testdb"})
    assert params["mode"] == "local"
    cmds = tool.build_command(
        input_paths=[Path("/in/query.fasta")], output_dir=tmp_path, params=params)
    assert "--enrich" not in cmds[1]


def test_output_summary_reads_neighborhood_json(tmp_path):
    (tmp_path / "neighborhood.json").write_text(json.dumps({
        "enriched": True,
        "loci": [{"genes": [{"family": "Q"}, {"family": None}]},
                 {"genes": [{"family": "Q"}]}],
    }))
    summary = get_tool("neighborhood_search").output_summary(tmp_path)
    assert summary == {"loci": 2, "genes": 3, "families": 1, "enriched": True}
