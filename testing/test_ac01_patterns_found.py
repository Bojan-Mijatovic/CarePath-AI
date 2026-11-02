"""AC1: Agents find patterns 1–3 without hints in the prompt.

Measured by: agent log vs `scenario_truth`. Owner: R3. Layer: core. Spec: SPEC.md §11.
Each scenario's agents arm is ticked to its echo alarm in cache_only (D14). The Investigator runs on every
regional alarm's tick (C25): the echo alarm, and the group alarms of C26, which open earlier. A pattern is
found when one of the stored investigations finds it, scored against demo/truth/ (steps 2.22, 2.30). The
investigations come from the `alarm_investigations` fixture (testing/conftest.py), which AC13 shares.
"""

import pytest

import investigation_run


@pytest.mark.acceptance
@pytest.mark.parametrize("scenario", [1, 2, 3])
@pytest.mark.parametrize("pattern", [1, 2, 3])
def test_ac01_patterns_found(alarm_investigations, scenario, pattern):
    invs, names, *_ = alarm_investigations[scenario]
    assert invs and None not in invs, "an alarm without investigation: a cache miss in cache_only"
    score = {1: lambda inv: investigation_run.pattern_1(inv, scenario, names),
             2: lambda inv: investigation_run.pattern_2(inv, scenario),
             3: lambda inv: investigation_run.pattern_3(inv, scenario)}[pattern]
    scores = [score(inv) for inv in invs]
    assert any(s["found"] for s in scores), scores
