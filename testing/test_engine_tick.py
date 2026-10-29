"""The demo's runs on the real tick (step 2.1, SPEC §9)."""

import pytest

from engine.tick import Demo

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
    assert sorted(demo.runs) == ["s1_agents", "s1_baseline", "s2_agents", "s2_baseline"]
    assert {r.day for r in demo.runs.values()} == {START}
    assert demo.speed == 0


def test_only_the_scenario_on_screen_advances(demo):
    demo.choose(2)
    msgs = demo.advance()
    assert (msgs[0]["type"], msgs[0]["scenario"], msgs[0]["day"]) == ("tick", 2, START + 1)
    assert {(m["type"], m["day"]) for m in msgs[1:]} <= {("alert", START + 1)}  # Monitoring's, agents arm
    assert {k: r.day for k, r in demo.runs.items()} == {"s1_agents": START, "s1_baseline": START,
                                                        "s2_agents": START + 1, "s2_baseline": START + 1}
    demo.choose(1)
    assert demo.tick_message()["day"] == START
    demo.choose(2)


def test_arms_match_until_agents_act(demo):
    # Steps 3–7 of the tick come with Risk, Monitoring and Intervention; until then the arms are equal.
    demo.jump(START + 3)
    assert ats(demo, "s2_agents") == ats(demo, "s2_baseline")


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


def test_capacity_table_follows_the_simulator(demo):
    run = demo.runs["s2_agents"]
    table = demo.read("s2_agents", lambda con: con.execute(
        "SELECT facility_id, service, day, slots_total, slots_booked FROM capacity_slots "
        "ORDER BY facility_id, service, day").fetchall())
    sim = run.sim.capacity_slots().sort_values(["facility_id", "service", "day"])
    assert table == list(sim.itertuples(index=False, name=None))


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
