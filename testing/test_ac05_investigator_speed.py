"""AC5: Investigator under 2 s from cache (live 30 s not reachable on CPU laptops, delivery plan D18).

Measured by: timer. Owner: R3. Layer: core. Spec: SPEC.md §11.
Each Chiedi question of the demo manifest goes through POST /api/ask in cache_only: the Investigator's every
turn, the translation, the stored row and the stream messages, timed from request to response (step 2.11).
"""

import pytest


@pytest.mark.acceptance
def test_ac05_investigator_speed(demo_played):
    answers = [a for got in demo_played.values() for a in got["answers"]]
    assert answers, "the manifest has no question to time"
    print("\n" + "\n".join(f"{seconds} s  {q}" for q, _, seconds, _ in answers))
    assert all(status == 200 and seconds < 2 for _, status, seconds, _ in answers), answers
