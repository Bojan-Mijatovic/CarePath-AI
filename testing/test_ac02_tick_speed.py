"""AC2: One simulated day for all patients under 1 s.

Measured by: timer. Owner: R2. Layer: core. Spec: SPEC.md §11.
Also the live budget of SPEC §9 (D22): both arms of the scenario on screen together under 500 ms per day.
"""

import time

import numpy as np
import pytest

from engine.tick import Demo

DAYS_MEASURED = 20


@pytest.mark.acceptance
def test_ac02_tick_speed(tmp_path):
    demo = Demo(tmp_path, scenarios=(2,))  # 10,000 patients, opening on day 23 as in the demo
    demo.start()
    try:
        demo.choose(2)
        both, one = [], []
        for _ in range(DAYS_MEASURED):
            t = time.perf_counter()
            demo.advance()
            both.append((time.perf_counter() - t) * 1000)
            one += [r.last_ms for r in demo.runs.values()]
    finally:
        demo.close()
    print(f"one run: max {max(one):.0f} ms; both arms: mean {np.mean(both):.0f}, p95 {np.percentile(both, 95):.0f} ms")
    assert max(one) < 1000  # AC2, every day
    assert np.percentile(both, 95) < 500  # SPEC §9 live tick at ×4
