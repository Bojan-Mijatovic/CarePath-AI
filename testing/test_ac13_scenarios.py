"""AC13: In each of the 3 scenarios agents name the right ASST, comune group and MMG group.

Measured by: 3 runs vs `scenario_truth`. Owner: R1. Layer: core. Spec: SPEC.md §11.
The alarm investigations of AC1 (the `alarm_investigations` fixture), scored against demo/truth/ by testing
code. The ASST: the Investigator names the bottleneck hospital on its wait_by_hospital claim, and code maps
the hospital to its ASST (`investigation_run.bottleneck_asst`); no answer names the ASST itself. The comune
group and the MMG group are AC1's patterns 3 and 2.
"""

import pytest

import investigation_run


@pytest.mark.acceptance
@pytest.mark.parametrize("scenario", [1, 2, 3])
@pytest.mark.parametrize("what", ["asst", "comune_group", "mmg_group"])
def test_ac13_scenarios(alarm_investigations, scenario, what):
    invs, names, assts = alarm_investigations[scenario]
    assert invs and None not in invs, "an alarm without investigation: a cache miss in cache_only"
    score = {"asst": lambda inv: investigation_run.bottleneck_asst(inv, scenario, names, assts),
             "comune_group": lambda inv: investigation_run.pattern_3(inv, scenario),
             "mmg_group": lambda inv: investigation_run.pattern_2(inv, scenario)}[what]
    scores = [score(inv) for inv in invs]
    assert any(s["found"] for s in scores), scores
