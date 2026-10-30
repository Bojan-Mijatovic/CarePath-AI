"""AC4: What-if 6 months, with and without agents, under 10 s.

Measured by: timer. Owner: R2. Layer: core. Spec: SPEC.md §11.
A full run takes minutes for 6 months on the team laptops, so the grid of each scenario is computed in advance
from full runs (D48, the fallback of D22) and AC4 times reading it, as the demo does (step 2.5). The other
tests check that the grid is complete, that a lever run is the agents run until the lever starts, and that
the file is not stale against the fixture run of step 1.23.
"""

import json
import time

import duckdb
import pytest

from engine import whatif

SCENARIOS = (1, 2, 3)
GRIDS = {n: json.loads(whatif.path(n).read_text(encoding="utf-8")) for n in SCENARIOS}


def runs(n):
    return {(r["arm"], (r["levers"] or {}).get("extra_slots", 0)): r for r in GRIDS[n]["runs"]}


@pytest.mark.acceptance
@pytest.mark.timing
def test_ac04_whatif_speed():
    started = time.perf_counter()
    for n in SCENARIOS:
        for k in range(whatif.MAX_EXTRA_SLOTS + 1):
            out = whatif.result(n, whatif.Levers(extra_slots=k))
            assert out["avoided_readmissions"] == out["baseline"]["readmissions"] - out["lever"]["readmissions"]
    assert time.perf_counter() - started < 10


@pytest.mark.parametrize("n", SCENARIOS)
def test_the_grid_is_complete(n):
    g = GRIDS[n]
    assert set(runs(n)) == {("baseline", 0)} | {("agents", k) for k in range(whatif.MAX_EXTRA_SLOTS + 1)}
    assert g["last_day"] - g["lever_day"] + 1 == whatif.PERIOD_DAYS
    assert g["lever_day"] == g["alarm_day"] + 1
    for r in g["runs"]:
        assert r["kpi"][-1]["day"] == g["last_day"]


@pytest.mark.parametrize("n", SCENARIOS)
def test_a_lever_run_is_the_agents_run_until_the_lever(n):
    g, by = GRIDS[n], runs(n)
    before = lambda r: [row for row in r["kpi"] if row["day"] < g["lever_day"]]
    for k in range(1, whatif.MAX_EXTRA_SLOTS + 1):
        assert before(by["agents", k]) == before(by["agents", 0])
        assert by["agents", k]["kpi"] != by["agents", 0]["kpi"]  # and the lever changes something after it


@pytest.mark.parametrize("n", SCENARIOS)
def test_more_slots_never_lengthen_the_wait(n):
    by = runs(n)
    waits = [by["agents", k]["wait_days"] for k in range(whatif.MAX_EXTRA_SLOTS + 1)]
    assert waits == sorted(waits, reverse=True)
    assert waits[-1] < waits[0]


def test_the_grid_is_not_stale(fixture_scenario):
    # The fixture run (step 1.23) is built from the code on every test run; the grid's baseline arm of
    # scenario 2 must give its daily KPIs, or the grid was computed by older code: run engine.whatif again.
    runs_dir, _ = fixture_scenario
    with duckdb.connect(runs_dir / "s2_baseline.duckdb", read_only=True) as con:
        fixture = con.execute(f"SELECT {', '.join(whatif.KPI_COLUMNS)} FROM kpi_daily WHERE level = 'ats' "
                              "ORDER BY day").fetchall()
    grid = [tuple(row[c] for c in whatif.KPI_COLUMNS) for row in runs(2)["baseline", 0]["kpi"]]
    assert grid[:len(fixture)] == fixture
