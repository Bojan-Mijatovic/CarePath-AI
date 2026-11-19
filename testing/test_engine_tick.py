"""The demo's runs on the real tick (step 2.1, SPEC §9)."""

import pytest

from engine.tick import DEMO_ORDER, Demo

START, DAYS = 5, 30


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    d = Demo(tmp_path_factory.mktemp("tick_runs"), scenarios=(1, 2), start_day=START, days=DAYS)
    d.start()
    yield d
    d.close()


def ats(demo, run_id):
    return demo.read(run_id, lambda con: con.execute(
        "SELECT * FROM kpi_daily WHERE level = 'ats' ORDER BY day").fetchall())


def test_start_replays_every_run_to_the_start_day(demo):
    # Both arms of each scenario, and the lever run of its what-if grid (step 2.28, C28).
    assert sorted(demo.runs) == ["s1_agents", "s1_agents_echo+2", "s1_baseline",
                                 "s2_agents", "s2_agents_echo+1", "s2_baseline"]
    assert {r.day for r in demo.runs.values()} == {START}
    assert demo.speed == 0


def test_only_the_scenario_on_screen_advances(demo):
    demo.choose(2)
    msgs = demo.advance()  # not at ×1, so the lever run waits for catch_up (C28)
    assert (msgs[0]["type"], msgs[0]["scenario"], msgs[0]["day"]) == ("tick", 2, START + 1)
    assert {(m["type"], m["day"]) for m in msgs[1:]} <= {("alert", START + 1), ("action", START + 1)}  # agents arm
    assert {k: r.day for k, r in demo.runs.items()} == {"s1_agents": START, "s1_baseline": START,
                                                        "s1_agents_echo+2": START, "s2_agents": START + 1,
                                                        "s2_baseline": START + 1, "s2_agents_echo+1": START}
    demo.choose(1)
    assert demo.tick_message()["day"] == START
    demo.choose(2)


def test_arms_match_until_agents_act(demo):
    # Intervention acts last in the tick (step 2.13), after the day's KPIs, and its effects start the next day:
    # day 0 is the same in both arms, and from day 1 the agents arm is its own.
    demo.jump(START + 3)
    agents, baseline = ats(demo, "s2_agents"), ats(demo, "s2_baseline")
    assert agents[0] == baseline[0]
    assert agents[1][10] > 0  # actions_executed, counted the day after
    assert agents[1:] != baseline[1:]


def test_jump_back_gives_the_same_days(demo):
    demo.jump(START + 6)
    before = ats(demo, "s2_agents")
    demo.jump(START + 2)
    assert demo.day == START + 2
    assert ats(demo, "s2_agents") == before[:START + 3]
    demo.jump(START + 6)
    assert ats(demo, "s2_agents") == before
    with pytest.raises(ValueError):
        demo.jump(DAYS)


def test_the_day_read_during_a_jump_back_waits_for_it(demo):
    # The API reads demo.day for its status while another request jumps back; the rebuild takes the runs out,
    # and an unlocked read raised KeyError (3 Nov 2026)
    import threading

    demo.jump(START + 4)
    errors = []
    jumping = threading.Thread(target=lambda: demo.jump(START + 1))
    jumping.start()
    while jumping.is_alive():
        try:
            assert demo.day in (START + 1, START + 4)
        except KeyError as e:
            errors.append(e)
    jumping.join()
    assert not errors
    assert demo.day == START + 1


def test_capacity_table_follows_the_simulator(demo):
    run = demo.runs["s2_agents"]
    table = demo.read("s2_agents", lambda con: con.execute(
        "SELECT facility_id, service, day, slots_total, slots_booked FROM capacity_slots "
        "ORDER BY facility_id, service, day").fetchall())
    sim = run.sim.capacity_slots().sort_values(["facility_id", "service", "day"])
    assert table == list(sim.itertuples(index=False, name=None))


def test_at_x1_the_clock_stops_on_the_wait_alarm(tmp_path):
    # C41: scenario 3's echo alarm opens on day 29; at ×1 the clock stops that day, at ×4 it would go on
    d = Demo(tmp_path, scenarios=(3,), start_day=27, days=40, whatif_dir=None)
    d.start()
    try:
        d.set_speed(1)
        days = []
        while d.speed:
            days.append(d.advance()[0]["day"])
        assert days == [28, 29] and d.tick_message()["payload"]["speed"] == 0
    finally:
        d.close()


def test_a_reset_opens_on_the_first_scenario_again(tmp_path):
    # The demo opens on the first situation of DEMO_ORDER (D67, proposed; it was scenario 2 under D44), whatever
    # the order of `scenarios`; a reset after another one must too (found by testing/demo_dryrun.py)
    d = Demo(tmp_path, scenarios=(4, 0), start_day=2, days=DAYS, whatif_dir=None)
    d.start()
    try:
        assert d.scenario == 0
        d.choose(4)
        d.start()
        assert d.scenario == 0
    finally:
        d.close()


def test_runs_stop_at_the_horizon(tmp_path):
    d = Demo(tmp_path, scenarios=(3,), start_day=DAYS - 2, days=DAYS)
    d.start()
    try:
        d.set_speed(1)
        assert d.advance()[0]["day"] == DAYS - 1
        assert d.advance() == []
        assert d.speed == 0
    finally:
        d.close()


def test_the_demo_walks_the_three_situations(tmp_path):
    # D67 (proposed): normal (0), unplanned closure (4), investment (3); only scenarios with a truth reveal.
    d = Demo(tmp_path, whatif_dir=None)
    try:
        assert d.scenarios == DEMO_ORDER == (0, 4, 3)
        assert d.scenario == 0
        for n in (0, 4):
            with pytest.raises(ValueError, match="nothing to reveal"):
                d.reveal(n)
    finally:
        d.close()


def test_the_situations_side_by_side_are_of_one_day(tmp_path):
    # C43 (D67, proposed): each situation keeps its own day; the comparison takes the latest day all runs reached,
    # in the demo's order, and lists the agents arm's wait alarms and the manager's decisions up to it.
    d = Demo(tmp_path, scenarios=(4, 0), start_day=2, days=DAYS, whatif_dir=None)
    d.start()
    try:
        d.choose(4)
        d.jump(6)
        out = d.situations()
        assert out["day"] == 2
        assert [s["scenario"] for s in out["situations"]] == [0, 4]
        assert [s["day_on_screen"] for s in out["situations"]] == [2, 6]
        for s in out["situations"]:
            assert s["with"]["run_id"] == f"s{s['scenario']}_agents" and s["without"]["run_id"] == f"s{s['scenario']}_baseline"
            assert 0 < s["without"]["on_track_pct"] <= 1 and s["with"]["patients"] == s["without"]["patients"]
            assert s["alarms"] == [] and s["decisions"] == [] and s["waits"] == []  # no wait alarm by day 2, nobody decided
    finally:
        d.close()
