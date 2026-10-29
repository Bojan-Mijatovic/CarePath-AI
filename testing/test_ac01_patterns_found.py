"""AC1: Agents find patterns 1–3 without hints in the prompt.

Measured by: agent log vs `scenario_truth`. Owner: R3. Layer: core. Spec: SPEC.md §11.
Each scenario's agents arm is ticked to its regional alarm in cache_only (D14), where the Investigator runs
(C25), and the stored investigation is scored against demo/truth/ (step 2.22). Patterns 2 and 3 are strict
xfails: no investigation looks at them yet (delivery plan step 2.22), so the test fails as soon as one does.
"""

import pytest

import investigation_run
from agents import llm
from engine.tick import Population

NO_PATH = pytest.mark.xfail(strict=True, reason="step 2.22: only the echo alarm starts an investigation, and it "
                                                "never looks at dispensing by MMG group or telemonitoring by comune")


@pytest.fixture(scope="module")
def investigations(tmp_path_factory):
    """{scenario: (stored investigation, facility names)}, each from its own alarm tick."""
    population, out = Population(), {}
    llm.configure(mode="cache_only", log_path=None)
    try:
        for n in (1, 2, 3):
            run, alarm, _ = investigation_run.run_to_alarm(n, population, tmp_path_factory.mktemp(f"s{n}"))
            try:
                names = dict(run.con.execute("SELECT facility_id, name FROM facilities").fetchall())
                out[n] = investigation_run.stored(run, alarm), names
            finally:
                run.close()
    finally:
        llm.configure()
    return out


@pytest.mark.acceptance
@pytest.mark.parametrize("scenario", [1, 2, 3])
@pytest.mark.parametrize("pattern", [1, pytest.param(2, marks=NO_PATH), pytest.param(3, marks=NO_PATH)])
def test_ac01_patterns_found(investigations, scenario, pattern):
    inv, names = investigations[scenario]
    assert inv is not None, "no investigation: a cache miss in cache_only"
    score = {1: lambda: investigation_run.pattern_1(inv, scenario, names),
             2: lambda: investigation_run.pattern_2(inv, scenario),
             3: lambda: investigation_run.pattern_3(inv, scenario)}[pattern]()
    assert score["found"], score
