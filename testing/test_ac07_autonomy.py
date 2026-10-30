"""AC7: No action above its autonomy level without approval.

Measured by: test + audit log. Owner: R3. Layer: core. Spec: SPEC.md §11.
Every action type of SPEC §7.2 at every level the manager may set goes through the action service (step
2.12); then the audit log is read back: an action was executed only at level 3, or after an `approved` entry.
"""

import pytest

from agents import actions
from engine.db import create_run, open_run

SOURCE = {"tool": "free_slots", "args": {"service": "echo"}, "day": 35, "run_id": "s2_agents"}


@pytest.mark.acceptance
def test_ac07_autonomy(tmp_path):
    create_run("s2_agents", runs_dir=tmp_path)
    con = open_run("s2_agents", tmp_path)
    emitted = []
    try:
        day = 0
        for type_ in actions.DEFAULT_LEVELS:
            for level in ([actions.DEFAULT_LEVELS[type_]] if type_ in actions.FIXED else range(4)):
                day += 1
                actions.set_level(con, day, type_, level)
                row = actions.create(con, "s2_agents", day, {
                    "agent": "intervention", "type": type_, "patient_id": None, "pathway_id": "hf_lombardia_v1",
                    "scope": {"facility_id": "osp_B", "patients": 3}, "payload": {"from_facility": "osp_B"},
                    "rationale": {"it": "x", "en": "x"}, "evidence": [SOURCE]}, emitted.extend)
                assert row["status"] == ("executed" if level == 3 else "proposed"), (type_, level, row["status"])
                if level < 3 and day % 2:  # half of the waiting ones are approved, the rest stay waiting
                    actions.decide(con, day, row["action_id"], True, emitted.extend)

        log = con.execute("SELECT action_id, event, actor FROM audit_log WHERE action_id IS NOT NULL ORDER BY rowid").fetchall()
        levels = dict(con.execute("SELECT action_id, autonomy_level FROM actions").fetchall())
        executed = [a for a, e, _ in log if e == "executed"]
        approved = {a for a, e, actor in log if e == "approved" and actor == actions.MANAGER}
        assert executed
        assert approved
        without_approval = [a for a in executed if levels[a] < 3 and a not in approved]
        assert not without_approval
        assert sorted(r["action_id"] for r in emitted) == sorted(executed)  # only executed actions reach the simulator
    finally:
        con.close()
