"""Intervention (delivery plan step 2.13): the escalation ladder, the warning sign, the MMG proposal and the
reschedule after a wait alarm (D53), on scenario 2's agents arm ticked to day 45."""

import json

import pytest

from agents import actions, llm
from engine.tick import Population, Run

DAY = 45


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    llm.configure(mode="cache_only", log_path=None)
    r = Run("s2_agents", Population(), tmp_path_factory.mktemp("intervention"), days=DAY + 5)
    try:
        r.advance_to(DAY)
        yield r
    finally:
        r.close()
        llm.configure()


def q(run, sql: str, params: dict | None = None) -> list[tuple]:
    return run.con.execute(sql, params or {}).fetchall()


def test_reminders_are_one_action_a_day_per_problem_with_an_event_per_patient(run):
    per_day = q(run, "SELECT created_day, count(*), count(DISTINCT payload->>'rule') + count(DISTINCT payload->>'step') "
                     "FROM actions WHERE type = 'reminder' GROUP BY 1")
    assert per_day and all(n == kinds for _, n, kinds in per_day)
    listed = q(run, "SELECT sum(json_array_length(payload->'patients')) FROM actions WHERE type = 'reminder'")[0][0]
    events = q(run, "SELECT count(*) FROM events WHERE event_type = 'REMINDER' AND source = 'agent_action'")[0][0]
    assert listed == events > 1000


def test_a_call_follows_a_reminder_after_call_after_days(run):
    after = run.state.pathway.escalation.call_after_days
    late = q(run, """
        SELECT c.patient_id, c.created_day, c.payload->>'rule' FROM actions c
        WHERE c.type = 'call_task' AND c.rationale->>'en' LIKE '%after the reminder%'""")
    assert len(late) > 50
    reminded = {(p, d, rule) for p, d, rule in q(run, """
        SELECT unnest(from_json(payload->'patients', '["VARCHAR"]')), created_day, payload->>'rule' FROM actions
        WHERE type = 'reminder'""")}
    assert all((p, d - after, rule) in reminded for p, d, rule in late if rule)


def test_a_weight_gain_gets_a_call_the_same_day(run):
    signs = {(p, d) for p, d in q(run, "SELECT patient_id, day FROM deviations WHERE code = 'weight_gain'")}
    calls = {(p, d) for p, d in q(run, "SELECT patient_id, created_day FROM actions WHERE type = 'call_task' "
                                       "AND payload->>'effect' = 'review'")}
    assert calls and calls <= signs
    in_hospital = {(p, d) for p, d in signs - calls}
    assert len(in_hospital) < len(signs) / 2  # the others were in hospital that day


def test_one_mmg_proposal_waits_at_a_time(run):
    rows = q(run, "SELECT status, scope->>'patients' FROM actions WHERE type = 'notify_mmg'")
    assert [s for s, _ in rows] == ["proposed"]  # nobody approved it, so no second one
    assert int(rows[0][1]) > 0


def test_reschedule_only_after_a_wait_alarm(run):
    alarm = q(run, "SELECT min(day) FROM alerts WHERE level = 'regional' AND facility_id IS NOT NULL")[0][0]
    proposals = q(run, "SELECT created_day, status, payload FROM actions WHERE type = 'reschedule'")
    assert alarm is not None and proposals
    assert min(d for d, _, _ in proposals) >= alarm  # D53: agents move bookings only once the alarm is open
    assert [s for _, s, _ in proposals] == ["proposed"]  # level 2 waits for the manager
    payload = json.loads(proposals[0][2])
    assert payload["from_facility"] == "osp_B" and payload["to_facility"] != "osp_B" and payload["patients"]


def test_escalation_step_follows_the_ladder(run):
    steps = dict(q(run, "SELECT escalation_step, count(*) FROM pathway_state GROUP BY 1"))
    assert set(steps) <= {0, 1, 2, 3} and steps.get(1) and steps.get(2)
    assert actions.levels(run.con)["reschedule"] == 2
