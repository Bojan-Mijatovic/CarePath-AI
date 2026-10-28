"""AC10: Verifier catches all injected wrong numbers in 5 answers, no false alarms.

Measured by: injected errors. Owner: R3. Layer: optional. Spec: SPEC.md §11.
Stub from delivery plan step 1.7; replaced by the real test in Phase 3 (Verifier).
"""

import pytest


@pytest.mark.acceptance
def test_ac10_verifier():
    pytest.skip("AC10 stub: implemented in delivery plan Phase 3 (Verifier)")
