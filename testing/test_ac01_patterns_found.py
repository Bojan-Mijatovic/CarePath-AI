"""AC1: Agents find patterns 1–3 without hints in the prompt.

Measured by: agent log vs `scenario_truth`. Owner: R3. Layer: core. Spec: SPEC.md §11.
Each scenario's agents arm is ticked to its echo alarm in cache_only (D14). The Investigator runs on every
regional alarm's tick (C25): the echo alarm, and the group alarms of C26, which open earlier. A pattern is
found when one of the stored investigations finds it, scored against demo/truth/ (steps 2.22, 2.30).
"""

import pytest

import investigation_run
from agents import llm
from engine.tick import Population


@pytest.fixture(scope="module")
def investigations(tmp_path_factory):
    """{scenario: ([stored investigations, None for a cache miss], facility names)}."""
    population, out = Population(), {}
    llm.configure(mode="cache_only", log_path=None)
    try:
        for n in (1, 2, 3):
            run, alarms, _ = investigation_run.run_to_alarm(n, population, tmp_path_factory.mktemp(f"s{n}"))
            try:
                names = dict(run.con.execute("SELECT facility_id, name FROM facilities").fetchall())
                out[n] = [investigation_run.stored(run, a) for a in alarms], names
            finally:
                run.close()
    finally:
        llm.configure()
    return out


@pytest.mark.acceptance
@pytest.mark.parametrize("scenario", [1, 2, 3])
@pytest.mark.parametrize("pattern", [1, 2, 3])
def test_ac01_patterns_found(investigations, scenario, pattern):
    invs, names = investigations[scenario]
    assert invs and None not in invs, "an alarm without investigation: a cache miss in cache_only"
    score = {1: lambda inv: investigation_run.pattern_1(inv, scenario, names),
             2: lambda inv: investigation_run.pattern_2(inv, scenario),
             3: lambda inv: investigation_run.pattern_3(inv, scenario)}[pattern]
    scores = [score(inv) for inv in invs]
    assert any(s["found"] for s in scores), scores
