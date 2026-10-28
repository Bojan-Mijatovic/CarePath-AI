"""scenario_truth must be unreachable for agents (delivery plan step 1.18, CLAUDE.md rule 5)."""

import ast
import json
from pathlib import Path

import duckdb
import pytest

from engine.db import connect_for_tools, create_run
from sim.population import load_reference
from sim.step import SCENARIOS_DIR
from sim.truth import SCENARIOS, TRUTH_DIR, text

AGENTS_DIR = Path(__file__).resolve().parents[1] / "src" / "agents"


@pytest.mark.parametrize("n", SCENARIOS)
def test_truth_files_match_the_scenarios(n):
    # Regenerate with: uv run python -m sim.truth
    assert (TRUTH_DIR / f"scenario_{n}.json").read_text(encoding="utf-8") == text(n, load_reference())


def test_truth_has_the_spec_shape():
    t = json.loads((TRUTH_DIR / "scenario_2.json").read_text(encoding="utf-8"))
    assert set(t) == {"scenario", "echo_bottleneck", "echo_free_capacity", "rural_dropout_comuni",
                      "low_adherence_group"}  # SPEC §3.3; option_b comes with option B
    assert t["echo_bottleneck"] == {"facility_id": "osp_B", "asst_id": "asst_cremona"}


@pytest.fixture
def tool_con(tmp_path):
    with duckdb.connect(create_run("s2_agents", runs_dir=tmp_path)) as con:
        con.execute("INSERT INTO mmg VALUES ('mmg_001', 'coop_3', 'cs_3', '019035')")
    con = connect_for_tools("s2_agents", runs_dir=tmp_path)
    yield con
    con.close()


def test_tool_connection_reads_the_run(tool_con):
    assert tool_con.execute("SELECT coop_id FROM mmg").fetchall() == [("coop_3",)]
    tables = {r[0] for r in tool_con.execute("SELECT table_name FROM duckdb_tables()").fetchall()}
    assert "scenario_truth" not in tables


@pytest.mark.parametrize("sql", [
    "SELECT * FROM read_json_auto('{truth}')",
    "SELECT * FROM read_text('{truth}')",
    "SELECT * FROM '{truth}'",
    "SELECT * FROM read_json_auto('{scenario}')",  # the scenario files hold the same answer
    "SET enable_external_access = true",
    "SET lock_configuration = false",
    "RESET enable_external_access",
    "ATTACH '{other}' AS o",
    "COPY mmg TO '{other}'",
    "CREATE TABLE x (a INTEGER)",
    "INSERT INTO mmg VALUES ('mmg_002', 'coop_3', 'cs_3', '019035')",
    "INSTALL httpfs",
])
def test_tool_connection_cannot_reach_the_truth_or_change_anything(tool_con, tmp_path, sql):
    sql = sql.format(truth=(TRUTH_DIR / "scenario_2.json").as_posix(), scenario=(SCENARIOS_DIR / "2.json").as_posix(),
                     other=(tmp_path / "other.duckdb").as_posix())
    with pytest.raises(duckdb.Error):
        tool_con.execute(sql).fetchall()


def test_agent_code_never_mentions_the_truth_or_imports_the_simulator():
    for path in AGENTS_DIR.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "truth" not in source.lower(), path
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                assert not any(a.name.split(".")[0] == "sim" for a in node.names), path
            if isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] != "sim", path
