"""AC18: Bed Finder answers under 3 s; ward matches diagnosis; bed really free.

Measured by: 20 test admissions. Owner: R2. Layer: optional. Spec: SPEC.md §11, C42.
On a copy of the fixture scenario's run without CarePath (scenario 2), day 47: Maria's own admission (demo
step 9c), then 19 more patients of the cohort through the emergency department of their own hospital, at the
default level (3, assigned at once).
"""

import shutil
import time

import pytest

from agents import bed_finder, tools
from engine import pathway as pathway_model
from engine.db import open_run, tool_cursor

HF = pathway_model.load("hf_lombardia_v1")
RUN, DAY, DIAGNOSIS = "s2_baseline", 47, "428.0"


@pytest.fixture(scope="module")
def con(fixture_scenario, tmp_path_factory):
    runs, _ = fixture_scenario
    directory = tmp_path_factory.mktemp("ac18")
    shutil.copy(runs / f"{RUN}.duckdb", directory / f"{RUN}.duckdb")
    con = open_run(RUN, directory)
    yield con
    con.close()


def free(con, patient: str | None = None) -> dict[tuple[str, str], dict]:
    args = {"pathway_id": HF.pathway_id, "diagnosis": DIAGNOSIS, "from_facility": "osp_A"}
    with tool_cursor(con) as cur:
        found = tools.call(tools.Context(RUN, tools.Query(cur), DAY), "free_beds", args | ({"patient_id": patient} if patient else {}))
    return {(b["facility_id"], b["ward"]): b for b in found["data"]["beds"]}


@pytest.mark.acceptance
def test_ac18_bed_finder(con):
    # Maria is admitted on day 47 in this run, so until Bed Finder places her she is not yet in a bed
    before = free(con, "p_00001")
    # Taken beds, per facility, are the patients outside the cohort plus the cohort's own inpatients, counted
    # here from the events with a query of their own (wards summed, so the ward split does not matter)
    inpatients = con.execute("""
        SELECT a.patient_id, a.facility_id FROM events a
        WHERE a.event_type = 'ADMISSION' AND a.day <= $d AND NOT EXISTS (
            SELECT 1 FROM events x WHERE x.patient_id = a.patient_id AND x.event_type = 'DISCHARGE'
              AND x.day > a.day AND x.day <= $d)""", {"d": DAY}).fetchall()
    assert ("p_00001", "osp_A") in inpatients
    others = dict(con.execute("""SELECT facility_id, sum(occupied) FROM bed_occupancy WHERE day = $d
                                 AND ward IN ('cardiologia', 'medicina_interna') GROUP BY 1""", {"d": DAY}).fetchall())
    for fac in {f for f, _ in before}:
        wards = [b for (f, _), b in before.items() if f == fac]
        cohort = sum(f == fac and p != "p_00001" for p, f in inpatients)
        if all(b["free_now"] for b in wards):  # no ward full, so nothing was cut at zero
            assert sum(b["beds_total"] - b["free_now"] for b in wards) == others[fac] + cohort, fac

    # 19 more, none in hospital that day: each new admission takes one more bed
    in_hospital = {p for p, _ in inpatients}
    patients = ["p_00001"] + [p for (p,) in con.execute(
        "SELECT patient_id FROM patients ORDER BY patient_id").fetchall() if p not in in_hospital][:19]
    homes = dict(con.execute("SELECT patient_id, ref_facility_id FROM patients").fetchall())
    seconds, rows = [], []
    for pid in patients:
        t = time.perf_counter()
        out = bed_finder.admit(con, RUN, HF, DAY, pid, DIAGNOSIS, homes[pid])
        seconds.append(time.perf_counter() - t)
        assert out["action"] is not None, f"no bed for {pid}"
        rows.append(out["action"])
    assert max(seconds) < 3, seconds
    wards = tools.wards_for(HF, DIAGNOSIS)
    assert wards == ["cardiologia", "medicina_interna"]
    beds = [(r["payload"]["facility_id"], r["payload"]["ward"], r["payload"]["bed"]) for r in rows]
    assert all(r["status"] == "executed" and r["payload"]["ward"] in wards for r in rows)  # level 3 by default
    assert len(set(beds)) == len(beds)  # no bed given twice
    for fac, ward, bed in beds:
        assert 1 <= bed <= before[(fac, ward)]["beds_total"]
    after = free(con, "p_00001")  # she now holds her own bed, so the call leaves out nothing
    for key, b in before.items():  # each assignment took one bed that was free
        taken = sum((f, w) == key for f, w, _ in beds)
        assert after[key]["free_now"] == b["free_now"] - taken >= 0, key
    # Maria came to Ospedale A's emergency department: a bed there, in its first ward with one free (step 9c)
    maria = rows[0]["payload"]
    assert maria["facility_id"] == "osp_A" and maria["candidates"][0]["same_facility"]
    assert maria["ward"] == next(w for w in wards if before[("osp_A", w)]["free_now"])
    assert "diagnosis" not in maria and DIAGNOSIS not in str(maria)  # SPEC §7.3: the action names no diagnosis
