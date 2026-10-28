"""Patterns 1–3 are visible to agent tools in every scenario (delivery plan step 1.21, scope gate data side)."""

import json

import duckdb
import pytest

from engine.db import connect_for_tools
from sim import pattern_proof as pp
from sim.calibration import readmissions
from sim.run import run
from sim.truth import TRUTH_DIR

DAYS = 120  # the notebook uses a full year; 120 days are enough for every pattern and keep the test short


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    d = tmp_path_factory.mktemp("runs")
    for n in (1, 2, 3):
        run(f"s{n}_baseline", days=DAYS, runs_dir=d)
    return d


@pytest.mark.parametrize("n", [1, 2, 3])
def test_patterns_found_blind_match_the_truth(runs, n):
    con = connect_for_tools(f"s{n}_baseline", runs_dir=runs)
    try:
        found = pp.detect(con, DAYS)
    finally:
        con.close()
    truth = json.loads((TRUTH_DIR / f"scenario_{n}.json").read_text(encoding="utf-8"))
    assert pp.compare(found, truth) == {k: True for k in ("echo_bottleneck", "echo_free_capacity",
                                                          "low_adherence_group", "rural_dropout_comuni")}, found


def test_sql_and_pandas_readmission_agree(runs):
    # The SPEC §5.2 definition is implemented twice: in SQL for tools and in pandas for calibration.
    path = runs / "s2_baseline.duckdb"
    with duckdb.connect(path, read_only=True) as con:
        events = con.execute("SELECT * FROM events").df()
    tool = connect_for_tools("s2_baseline", runs_dir=runs)
    try:
        sql = pp.readmission_30d(tool, DAYS).set_index("unit").rate
    finally:
        tool.close()
    assert sql["ATS"] == round(readmissions(events, DAYS)["rate"], 4)
