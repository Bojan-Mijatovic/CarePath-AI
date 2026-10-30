"""AC8: Fewer readmissions with agents than without, same seed.

Measured by: simulation report. Owner: R1. Layer: core. Spec: SPEC.md §11.
Both arms of scenario 2, seed 42, ticked to day 90 (step 2.13): the arms share every random draw (common random
numbers, step 1.15), so they differ only by what Intervention did. Measured over 120 days in all 3 scenarios:
30-day readmissions −25 to −27%, admissions −11%.
"""

import pytest

from agents import llm
from engine.tick import Population, Run

DAYS = 90


@pytest.mark.acceptance
def test_ac08_effect(tmp_path):
    population, out = Population(), {}
    llm.configure(mode="cache_only", log_path=None)  # the alarm's investigation is not what this measures
    try:
        for arm in ("baseline", "agents"):
            run = Run(f"s2_{arm}", population, tmp_path, days=DAYS + 1)
            try:
                run.advance_to(DAYS)
                admissions = run.con.execute("SELECT count(*) FROM events WHERE event_type = 'ADMISSION' AND day >= 0"
                                             ).fetchall()[0][0]
                out[arm] = (int(run.state.readmissions.sum()), admissions)
            finally:
                run.close()
    finally:
        llm.configure()
    (r0, a0), (r1, a1) = out["baseline"], out["agents"]
    print(f"\nreadmissions {r0} -> {r1}, admissions {a0} -> {a1}")
    assert r1 < 0.9 * r0  # fewer 30-day readmissions with agents, by more than noise
    assert a1 < a0
