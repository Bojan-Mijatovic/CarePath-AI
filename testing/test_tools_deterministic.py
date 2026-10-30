"""C7: every tool returns identical bytes on two fresh connections with default threads, on a full-size run
(10,000 patients, 365 days; SPEC §6). Below one row group DuckDB's parallel DOUBLE aggregation looks stable,
so a small fixture would not show the problem (SPEC §2)."""

import pytest

from agents import tools
from sim.run import run

PW = "hf_lombardia_v1"
SEGMENT = {"lives_alone": True, "distance_km_min": 40, "age_min": 75}
CALLS = [
    ("compliance_by_step", {"pathway_id": PW}),
    ("wait_by_hospital", {"pathway_id": PW, "step": "echo"}),
    ("wait_by_hospital", {"pathway_id": PW, "step": "cardio_visit", "period_days": 365}),
    ("patients_overdue", {"pathway_id": PW, "step": "lab_bnp"}),
    ("free_slots", {"service": "echo", "horizon_days": 90}),
    ("adherence_by_group", {"pathway_id": PW, "grouping": "mmg_group"}),
    ("adherence_by_group", {"pathway_id": PW, "grouping": "comune", "measure": "telemonitoring", "period_days": 365}),
    ("adherence_by_area", {"pathway_id": PW, "segment": SEGMENT}),
    ("readmissions_by_comune", {"pathway_id": PW, "period_days": 365}),
] + [("compare_segments", {"pathway_id": PW, "a": SEGMENT, "b": {}, "metric": m})
     for m in ("dispensing", "telemonitoring", "readmission_rate_30d", "on_time_fraction")]


@pytest.fixture(scope="module")
def year(tmp_path_factory):
    d = tmp_path_factory.mktemp("year")
    run("s2_baseline", days=365, runs_dir=d)
    return d


def test_events_exceed_one_row_group(year):
    ctx = tools.Context.for_run("s2_baseline", year)
    try:
        assert ctx.db.rows("SELECT count(*) FROM events")[0][0] > 10 * 122_880
    finally:
        ctx.close()


@pytest.mark.parametrize("name, args", CALLS, ids=[f"{n}-{i}" for i, (n, _) in enumerate(CALLS)])
def test_same_bytes_on_two_connections(year, name, args):
    out = []
    for _ in range(2):
        ctx = tools.Context.for_run("s2_baseline", year)
        try:
            result = tools.call(ctx, name, args)
        finally:
            ctx.close()
        assert "data" in result, result
        out.append(tools.canonical(result))
    assert out[0] == out[1]
