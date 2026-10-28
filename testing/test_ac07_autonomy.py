"""AC7: No action above its autonomy level without approval.

Measured by: test + audit log. Owner: R3. Layer: core. Spec: SPEC.md §11.
Stub from delivery plan step 1.7; replaced by the real test in step 2.12 (action service).
"""

import pytest


@pytest.mark.acceptance
def test_ac07_autonomy():
    pytest.skip("AC7 stub: implemented in delivery plan step 2.12 (action service)")
