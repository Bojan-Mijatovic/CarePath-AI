"""AC5: Investigator under 2 s from cache (live 30 s not reachable on CPU laptops, delivery plan D18).

Measured by: timer. Owner: R3. Layer: core. Spec: SPEC.md §11.
Stub from delivery plan step 1.7; replaced by the real test in step 2.11 (cache warm-up).
"""

import pytest


@pytest.mark.acceptance
def test_ac05_investigator_speed():
    pytest.skip("AC5 stub: implemented in delivery plan step 2.11 (cache warm-up)")
