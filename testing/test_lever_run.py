"""Lever runs in the demo and the capacity metrics (delivery plan step 2.28, SPEC C28, D45)."""

import json

import duckdb
import pytest

from agents import tools
from engine import pathway as pathway_model
from engine import queries, whatif
from engine.tick import Demo

HF = pathway_model.load("hf_lombardia_v1")


def test_the_proposed_lever_is_the_smallest_within_the_threshold():
    # D45: the smallest number of extra slots whose 6-month mean wait is within max_wait_days (30 for echo).
    for n in (1, 2, 3):
        grid = {r["levers"]["extra_slots"]: r["wait_days"] for r in json.loads(whatif.path(n).read_text())["runs"]
                if r["arm"] == "agents"}
        lever = whatif.proposed_lever(n, HF)
        k = lever["extra_slots"]
        assert lever["wait_days"] == grid[k] <= lever["limit"] == 30
        assert all(grid[j] > 30 for j in range(1, k))
        assert lever["run_id"] == f"s{n}_agents_echo+{k}"
    assert whatif.proposed_lever(2, HF, whatif.WHATIF_DIR / "none") is None


def test_capacity_mean_is_the_number_the_agents_see(fixture_scenario):
    # The alarm's day in scenario 2: queries.capacity and wait_by_hospital (period 7) give the same mean.
    runs, _ = fixture_scenario
    with duckdb.connect(runs / "s2_agents.duckdb", read_only=True) as con:
        day = con.execute("SELECT day FROM alerts WHERE level = 'regional' AND facility_id IS NOT NULL").fetchall()[0][0]
        rows = {r["name"]: r for r in queries.capacity(con, HF.pathway_id, "echo", day)}
        wait = tools.call(tools.Context("s2_agents", tools.Query(con), day), "wait_by_hospital",
                          {"pathway_id": HF.pathway_id, "step": "echo", "period_days": 7})["data"]
    assert {name: r["wait_mean"] for name, r in rows.items()} == wait
    b = rows["Ospedale B"]
    assert b["use_pct"] == 1.0
    assert b["wait_median"] <= b["wait_p90"]
    assert b["bookings"] > 0


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    d = Demo(tmp_path_factory.mktemp("lever_runs"), scenarios=(2,), start_day=0, days=40)
    d.start()
    d.set_speed(1)  # ×1: the lever run keeps up
    while d.day < 36:
        d.advance()
    yield d
    d.close()


def test_the_lever_run_is_the_agents_run_until_the_lever(demo):
    lever = whatif.proposed_lever(2, HF)
    run = demo.lever_run()
    assert run.run_id == lever["run_id"] and run.day == demo.day
    first = lever["lever"].from_day
    kpi = lambda run_id: [r for r in demo.read(run_id, lambda c: queries.kpi(c, HF.pathway_id, "ats", None))
                          if r["day"] < first]
    assert kpi(run.run_id) == kpi("s2_agents")
    after = lambda run_id: {r["facility_id"]: r["slots_total"]
                            for r in demo.read(run_id, lambda c: queries.capacity(c, HF.pathway_id, "echo", 36))}
    assert after(run.run_id)["osp_B"] > after("s2_agents")["osp_B"]


def test_the_lever_run_waits_at_x4_and_catches_up(demo):
    demo.set_speed(4)
    day = demo.lever_run().day
    demo.advance()
    assert demo.lever_run().day == day < demo.day
    assert demo.tick_message()["payload"]["lever_run"] == {"run_id": demo.lever_run().run_id, "day": day}
    demo.set_speed(0)
    while demo.catch_up():
        pass
    assert demo.lever_run().day == demo.day
