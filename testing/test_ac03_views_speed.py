"""AC3: KPI, Sankey and map under 200 ms.

Measured by: timer. Owner: R2. Layer: core. Spec: SPEC.md §11.
Measured on the fixture runs (10,000 patients, day 62) with the queries the API answers with (step 2.2).
"""

import time

import pytest

from engine import queries
from engine.db import connect_for_tools

PATHWAY_ID = "hf_lombardia_v1"
REPEATS = 5
CALLS = {
    "kpi ats, every day": lambda con: queries.kpi(con, PATHWAY_ID, "ats", None),
    "kpi by comune, every day": lambda con: queries.kpi(con, PATHWAY_ID, "comune", None),
    "sankey": lambda con: queries.sankey(con, PATHWAY_ID),
    "map": lambda con: queries.map_comuni(con, PATHWAY_ID),
    "capacity": lambda con: queries.capacity(con, PATHWAY_ID, "echo", None),  # C28, step 2.28
}


@pytest.mark.acceptance
@pytest.mark.timing
def test_ac03_views_speed(fixture_scenario):
    runs, _ = fixture_scenario
    con = connect_for_tools("s2_agents", runs_dir=runs)
    try:
        worst = {}
        for name, call in CALLS.items():
            assert call(con), name  # not timing an empty answer
            times = []
            for _ in range(REPEATS):
                t = time.perf_counter()
                call(con)
                times.append((time.perf_counter() - t) * 1000)
            worst[name] = max(times)
    finally:
        con.close()
    print(", ".join(f"{name} {ms:.0f} ms" for name, ms in worst.items()))
    assert all(ms < 200 for ms in worst.values()), worst
