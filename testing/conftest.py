import pytest

from fixtures import scenario


def pytest_collection_modifyitems(items):
    """Timers first, on a laptop that has not been working for minutes, as in the demo, where the tick starts
    after a pause on day 23 (D21). Step 2.22: right after AC1's three runs, AC2's both-arms p95 went from
    about 300 to 655-686 ms; in a process of its own it stays near 300."""
    items.sort(key=lambda item: item.get_closest_marker("timing") is None)  # stable: keeps the order otherwise


@pytest.fixture(scope="session")
def alarm_investigations(tmp_path_factory):
    """{scenario: ([stored investigations, None for a cache miss], facility names, facility ASSTs, [stored
    answers to the scenario's Chiedi questions])}: each scenario's agents arm ticked to its echo alarm in
    cache_only (D14), and on that day the questions of demo/cache/manifest.json asked, for AC1, AC10 and
    AC13. Every step carries its tool's result of the alarm's day. About 2 minutes."""
    import json

    import investigation_run
    from agents import llm
    from engine import investigations
    from engine.tick import Population

    from pathlib import Path

    manifest = json.loads((Path(__file__).resolve().parents[1] / "demo/cache/manifest.json").read_text(encoding="utf-8"))
    questions = {s["scenario"]: s["questions"] for s in manifest["scenarios"]}
    population, out = Population(), {}
    llm.configure(mode="cache_only", log_path=None)
    try:
        for n in (1, 2, 3):
            run, alarms, _ = investigation_run.run_to_alarm(n, population, tmp_path_factory.mktemp(f"s{n}"))
            try:
                facilities = run.con.execute("SELECT facility_id, name, asst_id FROM facilities").fetchall()
                answers = []
                for q in questions.get(n, []):
                    row, _ = investigations.on_question(run.con, run.run_id, run.state.pathway, run.day, n, q)
                    answers.append(investigation_run.stored(run, {"payload": {"investigation_id": row["investigation_id"]}}))
                out[n] = ([investigation_run.stored(run, a) for a in alarms], {f: name for f, name, _ in facilities},
                          {f: asst for f, _, asst in facilities}, answers)
            finally:
                run.close()
    finally:
        llm.configure()
    return out


@pytest.fixture(scope="session")
def demo_played(tmp_path_factory):
    """The manifest's demo outputs played through the API in cache_only (step 2.11, testing/cache_warmup.py),
    for the cache completeness check (C10) and AC5. About 2 minutes."""
    import cache_warmup
    from agents import llm

    llm.configure(mode="cache_only", log_path=None)
    try:
        return cache_warmup.play(tmp_path_factory.mktemp("demo_runs"), tmp_path_factory.mktemp("demo_ui"))
    finally:
        llm.configure()


@pytest.fixture(scope="session")
def fixture_scenario(tmp_path_factory):
    """The fixture scenario of step 1.23: (directory with s2_baseline and s2_agents run databases,
    {path under testing/fixtures/: JSON text}). Built once per test session, in about 15 s."""
    runs = tmp_path_factory.mktemp("fixture_runs")
    return runs, scenario.build(runs)
