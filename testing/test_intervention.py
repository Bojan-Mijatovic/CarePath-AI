"""Intervention (delivery plan steps 2.13 and 2.27): the escalation ladder, the warning sign, the MMG proposal,
the reschedule after a wait alarm (D53) and the capacity proposal (D45, C34), on scenario 2's agents arm
ticked to day 45 with the proposed lever of its what-if grid."""

import json

import pytest

from agents import actions, llm, verifier
from engine import whatif
from engine.tick import Demo, Population, Run

DAY = 45
POPULATION = Population()


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    llm.configure(mode="cache_only", log_path=None)
    r = Run("s2_agents", POPULATION, tmp_path_factory.mktemp("intervention"), days=DAY + 5,
            proposal=whatif.proposed_lever(2, POPULATION.pathway))
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


def test_the_day_s_calls_have_their_outcome_on_the_list(run):
    """C20: the list is built before Intervention calls (SPEC §9 steps 6 and 8); the outcome is written back."""
    listed = dict(q(run, "SELECT patient_id, outcome FROM worklist_today WHERE day = $d", {"d": DAY}))
    called = dict(q(run, "SELECT patient_id, code FROM events WHERE event_type = 'CALL' AND day = $d", {"d": DAY}))
    both = set(listed) & set(called)
    assert both and all(listed[p] == called[p] for p in both)
    assert all(listed[p] is None for p in set(listed) - set(called))


def test_escalation_step_follows_the_ladder(run):
    steps = dict(q(run, "SELECT escalation_step, count(*) FROM pathway_state GROUP BY 1"))
    assert set(steps) <= {0, 1, 2, 3} and steps.get(1) and steps.get(2)
    assert actions.levels(run.con)["reschedule"] == 2


@pytest.mark.parametrize("scenario", [1, 2, 3])
def test_the_proposed_lever_brings_the_wait_under_max_wait_days(scenario):
    """Step 2.27's "done when": code picks the smallest of +1 to +4 slots whose 6-month mean wait is within the
    step's max_wait_days, from the what-if grid."""
    lever = whatif.proposed_lever(scenario, POPULATION.pathway)
    assert lever is not None and 1 <= lever["extra_slots"] <= 4
    assert lever["wait_days"] <= lever["limit"] < lever["wait_days_without"]


def test_one_capacity_proposal_on_the_alarm_day_waits_for_the_manager(run):
    alarm = q(run, "SELECT min(day) FROM alerts WHERE level = 'regional' AND facility_id = 'osp_B'")[0][0]
    rows = q(run, "SELECT created_day, status, autonomy_level, payload FROM actions WHERE type = 'capacity_proposal'")
    assert [(d, s, level) for d, s, level, _ in rows] == [(alarm, "proposed", 1)]  # once, and level 1 is fixed
    lever = whatif.proposed_lever(2, POPULATION.pathway)
    payload = json.loads(rows[0][3])
    assert (payload["facility_id"], payload["extra_slots"], payload["lever_run"]) == ("osp_B", lever["extra_slots"], lever["run_id"])
    with pytest.raises(ValueError):
        actions.set_level(run.con, DAY, "capacity_proposal", 3)


def test_the_proposal_sentence_has_only_the_codes_numbers(run):
    """Step 2.27: the sentence's numbers equal the code's, in the template or the model's words (from the cache
    in the demo, D17): the payload's, the base slots, the PDTA limit, and the alarm's own wait."""
    (rationale, payload), = q(run, "SELECT rationale, payload FROM actions WHERE type = 'capacity_proposal'")
    rationale, payload = json.loads(rationale), json.loads(payload)
    alarm = json.loads(q(run, "SELECT text FROM alerts WHERE level = 'regional' AND facility_id = 'osp_B' ORDER BY day")[0][0])
    limit = next(s.max_wait_days for s in POPULATION.pathway.steps if s.id == "echo")
    allowed = verifier.leaves(payload) + [payload["slots_per_day"] - payload["extra_slots"], limit]
    allowed += [x for t in verifier.NUMBER.finditer(alarm["it"]) for x, _ in verifier.readings(t.group())]
    assert verifier.unsupported(rationale["it"], allowed) == [] and verifier.unsupported(rationale["en"], allowed) == []
    assert "Ospedale B" in rationale["it"] and "Ospedale B" in rationale["en"]


def test_an_approved_proposal_changes_nothing_in_the_run(run):
    """Buying the devices is the manager's decision outside the system (D45): approval executes the action,
    and no agent changes capacity (rule 3); the console turns to the lever run instead (C34)."""
    (action_id,) = q(run, "SELECT action_id FROM actions WHERE type = 'capacity_proposal'")[0]
    events = q(run, "SELECT count(*) FROM events")[0][0]
    row = actions.decide(run.con, run.day, action_id, True, run.feedback)
    assert row["status"] == "executed"
    assert q(run, "SELECT count(*) FROM events")[0][0] == events
    assert [e for (e,) in q(run, "SELECT event FROM audit_log WHERE action_id = $a ORDER BY rowid", {"a": action_id})] == [
        "created", "approved", "executed"]


def test_the_demo_says_when_the_proposal_is_approved(tmp_path):
    """The tick message's lever_run says the manager approved the proposal (C34), until a jump back rebuilds
    the runs from the defaults."""
    llm.configure(mode="cache_only", log_path=None)
    demo = Demo(tmp_path, scenarios=(2,), start_day=33, days=40)
    try:
        demo.start()
        assert demo.tick_message()["payload"]["lever_run"]["approved"] is False
        (action_id,) = demo.read("s2_agents", lambda c: c.execute(
            "SELECT action_id FROM actions WHERE type = 'capacity_proposal'").fetchall()[0])
        messages = demo.decide(action_id, "approve")
        assert messages[0]["payload"]["status"] == "executed"
        assert messages[1]["payload"]["lever_run"] == {"run_id": "s2_agents_echo+1", "day": 33, "approved": True}
        demo.jump(30)
        assert demo.tick_message()["payload"]["lever_run"]["approved"] is False
    finally:
        demo.close()
        llm.configure()
