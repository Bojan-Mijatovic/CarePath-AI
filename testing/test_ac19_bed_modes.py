"""AC19: Confirm mode writes no admission without confirmation; assign mode logs every admission and can undo it.

Measured by: test + audit log. Owner: R3. Layer: optional. Spec: SPEC.md §11, C42.
On a copy of the fixture scenario's run without CarePath (scenario 2), day 47. Confirm mode is level 2 of
`bed_assignment` (SPEC §7.2), assign mode its default level 3.
"""

import json
import shutil

import pytest

from agents import actions, bed_finder, tools
from engine import pathway as pathway_model
from engine.db import open_run, tool_cursor

HF = pathway_model.load("hf_lombardia_v1")
RUN, DAY, DIAGNOSIS = "s2_baseline", 47, "428.0"
NO_EVENT = lambda rows: None  # noqa: E731


@pytest.fixture
def con(fixture_scenario, tmp_path):
    runs, _ = fixture_scenario
    shutil.copy(runs / f"{RUN}.duckdb", tmp_path / f"{RUN}.duckdb")
    con = open_run(RUN, tmp_path)
    yield con
    con.close()


def free_now(con, facility: str, ward: str) -> int:
    with tool_cursor(con) as cur:
        found = tools.call(tools.Context(RUN, tools.Query(cur), DAY), "free_beds",
                           {"pathway_id": HF.pathway_id, "diagnosis": DIAGNOSIS, "from_facility": "osp_A"})
    return next(b["free_now"] for b in found["data"]["beds"] if (b["facility_id"], b["ward"]) == (facility, ward))


def audit(con, action_id: str) -> list[tuple[str, str]]:
    return con.execute("SELECT event, actor FROM audit_log WHERE action_id = $a ORDER BY rowid",
                       {"a": action_id}).fetchall()


def admit(con, patient: str, choice: int = 0) -> dict:
    return bed_finder.admit(con, RUN, HF, DAY, patient, DIAGNOSIS, "osp_A", choice)


@pytest.mark.acceptance
def test_ac19_confirm_mode_writes_nothing_until_the_doctor_confirms(con):
    actions.set_level(con, DAY, bed_finder.ACTION, 2)
    out = admit(con, "p_00001")
    row, p = out["action"], out["action"]["payload"]
    assert row["status"] == "proposed" and row["autonomy_level"] == 2
    before = free_now(con, p["facility_id"], p["ward"])
    assert before == out["candidates"][0]["free_now"]  # the proposal holds no bed
    assert con.execute("SELECT count(*) FROM actions WHERE status = 'executed'").fetchall()[0][0] == 0
    assert audit(con, row["action_id"]) == [("created", bed_finder.AGENT)]

    done = actions.decide(con, DAY, row["action_id"], True, NO_EVENT, actor=bed_finder.DOCTOR)
    assert (done["status"], done["decided_by"]) == ("executed", bed_finder.DOCTOR)
    assert free_now(con, p["facility_id"], p["ward"]) == before - 1
    assert audit(con, row["action_id"]) == [("created", bed_finder.AGENT), ("approved", bed_finder.DOCTOR),
                                            ("executed", actions.SERVICE)]

    # A doctor who picks an alternative has decided: it is assigned at once, in the doctor's name
    alt = admit(con, "p_00002", choice=1)
    assert (alt["action"]["status"], alt["action"]["decided_by"]) == ("executed", bed_finder.DOCTOR)
    assert alt["action"]["payload"]["choice"] == 1
    assert (alt["action"]["payload"]["facility_id"], alt["action"]["payload"]["ward"]) == (
        alt["candidates"][1]["facility_id"], alt["candidates"][1]["ward"])
    with pytest.raises(ValueError):
        admit(con, "p_00003", choice=9)


@pytest.mark.acceptance
def test_ac19_assign_mode_logs_every_admission_and_undoes_it(con):
    assert actions.levels(con)[bed_finder.ACTION] == 3  # the default (SPEC §7.2)
    rows = [admit(con, pid)["action"] for pid in ("p_00001", "p_00002", "p_00003")]
    assert all(r["status"] == "executed" and r["decided_by"] == "auto" for r in rows)
    for r in rows:
        assert audit(con, r["action_id"]) == [("created", bed_finder.AGENT), ("executed", "auto")]
        assert r["evidence"][0]["tool"] == "free_beds" and r["rationale"]["it"] and r["rationale"]["en"]
    last = rows[-1]["payload"]
    taken = free_now(con, last["facility_id"], last["ward"])
    undone = actions.undo(con, DAY, rows[-1]["action_id"], bed_finder.DOCTOR)
    assert undone["status"] == "undone"
    assert audit(con, rows[-1]["action_id"])[-1] == ("undone", bed_finder.DOCTOR)
    assert free_now(con, last["facility_id"], last["ward"]) == taken + 1  # the bed is free again
    stored = json.loads(con.execute("SELECT payload FROM actions WHERE action_id = $a",
                                    {"a": rows[0]["action_id"]}).fetchall()[0][0])
    assert stored["bed"] == rows[0]["payload"]["bed"] and stored["day"] == DAY
