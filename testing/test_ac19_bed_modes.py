"""AC19: Confirm mode writes no admission without confirmation; assign mode logs every admission and can undo it.

Measured by: test + audit log. Owner: R3. Layer: optional. Spec: SPEC.md §11.
Stub from delivery plan step 1.7; replaced by the real test in Phase 3 (Bed Finder).
"""

import pytest


@pytest.mark.acceptance
def test_ac19_bed_modes():
    pytest.skip("AC19 stub: implemented in delivery plan Phase 3 (Bed Finder)")
