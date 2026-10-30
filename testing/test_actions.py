"""Action service (SPEC §7.3, delivery plan step 2.12): checks, queue, decisions, undo and the audit log."""

import json

import pytest

from agents import actions
from engine.db import create_run, open_run

MOVE = {"from_facility": "osp_B", "to_facility": "osp_C", "service": "echo"}
SOURCE = {"tool": "wait_by_hospital", "args": {"step": "echo"}, "day": 35, "run_id": "s2_agents"}


@pytest.fixture
def con(tmp_path):
    create_run("s2_agents", runs_dir=tmp_path)
    c = open_run("s2_agents", tmp_path)
    yield c
    c.close()


class Emit:
    """The engine's feedback hook, recorded."""

    def __init__(self):
        self.rows = []

    def __call__(self, rows):
        self.rows += rows


def action(type_="reminder", **extra) -> dict:
    return {"agent": "intervention", "type": type_, "patient_id": "p_00001", "pathway_id": "hf_lombardia_v1",
            "payload": {}, "rationale": {"it": "x", "en": "x"}, "evidence": [SOURCE]} | extra


def audit(con) -> list[tuple]:
    return [(a, e, actor, json.loads(d)) for a, e, actor, d in con.execute(
        "SELECT action_id, event, actor, details FROM audit_log ORDER BY rowid").fetchall()]


def test_level_3_executes_at_once_and_feeds_the_simulator(con):
    emit = Emit()
    row = actions.create(con, "s2_agents", 31, action("call_task"), emit)
    assert (row["action_id"], row["status"], row["executed_day"], row["decided_by"]) == ("act_s2_agents_1", "executed", 31, "auto")
    assert [r["action_id"] for r in emit.rows] == ["act_s2_agents_1"]
    assert audit(con) == [("act_s2_agents_1", "created", "intervention", {}), ("act_s2_agents_1", "executed", "auto", {})]


def test_below_level_3_waits_and_approval_executes(con):
    emit = Emit()
    row = actions.create(con, "s2_agents", 35, action("reschedule", payload=MOVE), emit)
    assert (row["status"], row["autonomy_level"], emit.rows) == ("proposed", 2, [])
    done = actions.decide(con, 36, row["action_id"], True, emit)
    assert (done["status"], done["executed_day"], done["decided_by"]) == ("executed", 36, "manager")
    assert [r["action_id"] for r in emit.rows] == [row["action_id"]]
    assert [e for _, e, _, _ in audit(con)] == ["created", "approved", "executed"]
    assert audit(con)[0][3] == {"queued": "autonomy level 2"}
    with pytest.raises(ValueError):
        actions.decide(con, 36, row["action_id"], False, emit)  # decided already


def test_reject_and_undo(con):
    emit = Emit()
    waiting = actions.create(con, "s2_agents", 35, action("notify_mmg"), emit)
    assert actions.decide(con, 35, waiting["action_id"], False, emit)["status"] == "rejected"
    with pytest.raises(ValueError):
        actions.undo(con, 35, waiting["action_id"])  # only an executed action can be undone
    done = actions.create(con, "s2_agents", 35, action("reminder"), emit)
    assert actions.undo(con, 36, done["action_id"])["status"] == "undone"
    assert [e for a, e, _, _ in audit(con) if a == done["action_id"]] == ["created", "executed", "undone"]
    with pytest.raises(KeyError):
        actions.undo(con, 36, "act_none")


@pytest.mark.parametrize("bad, reason", [
    ({"payload": {"drug": "furosemide", "dose": 40}}, "clinical fields"),
    ({"scope": {"diagnosis": "I50"}}, "clinical fields"),
    ({"type": "reschedule", "payload": {"to_facility": "osp_C"}}, "existing booking"),
    ({"evidence": []}, "no tool source"),
    ({"type": "bed_proposal"}, "no autonomy level"),
])
def test_guardrails_and_missing_evidence_reject(con, bad, reason):
    emit = Emit()
    row = actions.create(con, "s2_agents", 35, action() | bad, emit)
    assert (row["status"], row["decided_by"], emit.rows) == ("rejected", "action_service", [])
    rejected = [d for _, e, _, d in audit(con) if e == "rejected"]
    assert len(rejected) == 1 and reason in rejected[0]["reason"]


def test_daily_limit_per_facility_sends_the_rest_to_the_queue(con):
    emit = Emit()
    scope = {"facility_id": "osp_B", "patients": 1}
    rows = [actions.create(con, "s2_agents", 40, action("call_task", scope=scope), emit)
            for _ in range(actions.DAILY_LIMIT + 1)]
    assert [r["status"] for r in rows].count("executed") == actions.DAILY_LIMIT
    assert rows[-1]["status"] == "proposed"
    elsewhere = actions.create(con, "s2_agents", 40, action("call_task", scope={"facility_id": "osp_C"}), emit)
    tomorrow = actions.create(con, "s2_agents", 41, action("call_task", scope=scope), emit)
    assert (elsewhere["status"], tomorrow["status"]) == ("executed", "executed")


def test_a_raised_level_holds_for_new_actions(con):
    emit = Emit()
    actions.set_level(con, 40, "reschedule", 3)
    row = actions.create(con, "s2_agents", 40, action("reschedule", payload=MOVE), emit)
    assert (row["status"], row["autonomy_level"]) == ("executed", 3)
