"""Monitoring (delivery plan step 2.8, SPEC C21) and the rule language (engine.rules), on the fixture run
(scenario 2, days 0–62) and on a short run for Maria."""

from pathlib import Path

import duckdb
import numpy as np
import pytest

from agents import monitoring
from engine import pathway as pathway_model
from engine import rules
from engine.pathway import Rule
from engine.risk import HIGH_RISK
from engine.tick import Population, Run

HF = pathway_model.load("hf_lombardia_v1")
DAY = 62


@pytest.fixture(scope="module")
def con(fixture_scenario):
    runs, _ = fixture_scenario
    with duckdb.connect(runs / "s2_agents.duckdb", read_only=True) as c:
        yield c


@pytest.fixture(scope="module")
def maria_run(tmp_path_factory):
    run = Run("s2_baseline", Population(), tmp_path_factory.mktemp("monitoring_runs"), days=60)
    run.advance_to(44)
    yield run
    run.close()


def test_echo_alarm_at_the_bottleneck_hospital_around_day_35(con):
    # Done-when of step 2.8: the echo alarm for Ospedale B fires around day 35 in scenario 2.
    regional = con.execute("SELECT day, facility_id, step, text->>'it', closed_day FROM alerts WHERE level = 'regional'"
                           ).fetchall()
    assert len(regional) == 1
    day, facility, step, text, closed = regional[0]
    assert (facility, step) == ("osp_B", "echo")
    assert 30 <= day <= 36
    assert "soglia PDTA 30 giorni" in text
    assert closed is None  # the wait is still above 30 on day 62


def test_flags_follow_the_rule(con):
    # no_furosemide: no dispense of C03CA01 in the last 30 days (independent SQL, day 62)
    expected = {p for (p,) in con.execute("""
        SELECT s.patient_id FROM pathway_state s
        LEFT JOIN (SELECT patient_id, max(day) AS last FROM events WHERE event_type = 'DISPENSE' AND code = 'C03CA01'
                   AND day <= $d GROUP BY 1) e USING (patient_id)
        WHERE coalesce(e.last, -1000000) <= $d - 30""", {"d": DAY}).fetchall()}
    flagged = {p for (p,) in con.execute("SELECT patient_id FROM pathway_state WHERE list_contains(flags, 'adherence_risk')"
                                          ).fetchall()}
    assert flagged == expected
    assert 500 < len(flagged) < 1200


def test_a_deviation_is_recorded_once_when_it_starts(con):
    rows = con.execute("SELECT day, patient_id, kind, code FROM deviations ORDER BY patient_id, kind, code, day").fetchall()
    for a, b in zip(rows, rows[1:]):
        if a[1:] == b[1:]:
            assert b[0] > a[0] + 1, (a, b)  # never on two days in a row: it held, then stopped, then started again
    assert {k for _, _, k, _ in rows} == {"rule", "overdue"}


def test_patient_alerts_are_new_deviations_of_high_risk_patients(con):
    alerts = con.execute("""
        SELECT a.day, a.patient_id, count(d.patient_id) FROM alerts a
        LEFT JOIN deviations d ON d.day = a.day AND d.patient_id = a.patient_id
        WHERE a.level = 'patient' GROUP BY ALL""").fetchall()
    assert all(n > 0 for *_, n in alerts)  # every alert has a deviation that day
    per_day = np.bincount([d for d, _, _ in alerts if d > 0], minlength=DAY + 1)[1:]
    assert 2 <= per_day.mean() <= 20  # D39: about 8 a day
    deviations = con.execute("SELECT count(*) FROM deviations WHERE day > 0").fetchone()[0] / DAY
    assert deviations > 10 * per_day.mean()


def test_weight_gain_pulls_the_cardiology_visit(maria_run):
    # Maria reads +2.1 kg in 3 days on day 43 (demo/story/): the visit falls due within 7 days.
    m = maria_run.monitoring
    assert m.fired["weight_gain"][0]
    assert maria_run.state.due[maria_run.state.pos["cardio_visit"], 0] == 43 + 7
    assert maria_run.risk.risk[0] >= HIGH_RISK  # and she is high risk that week


def test_a_new_discharge_ends_the_pull(fixture_scenario):
    # Without agents Maria's pull of day 43 (visit by day 50) is followed by her readmission on day 47 and a
    # discharge on day 55, which starts the visit's clock again: due on day 85, not overdue since day 50.
    runs, _ = fixture_scenario
    with duckdb.connect(runs / "s2_baseline.duckdb", read_only=True) as c:
        row = c.execute("SELECT next_step, next_due_day, status, overdue_steps FROM pathway_state "
                        "WHERE patient_id = 'p_00001'").fetchone()
    assert row == ("cardio_visit", 55 + 30, "on_track", [])


def test_rule_language_on_the_state(maria_run):
    st, risk, day = maria_run.state, maria_run.risk.risk, 44
    enrolled = st.enrolled_day <= day
    check = lambda cond: rules.evaluate(Rule.model_validate({"id": "x", "if": cond, "then": {"flag": "x"}}), st, risk, day)
    assert check("age >= 90").sum() == (enrolled & (st.age >= 90)).sum()
    assert check("age >= 90 and distance_km > 40").sum() == (enrolled & (st.age >= 90) & (st.distance_km > 40)).sum()
    assert check("risk_score >= 0.1").sum() == (enrolled & (risk >= 0.1)).sum()
    assert check("overdue('telemon', 0)").sum() == (enrolled & (st.due[st.pos["telemon"]] < day)).sum()
    assert not check("days_since_last_reading > 0")[~st.telemon_started].any()  # never read: the clause is false
    texts = rules.texts(Rule.model_validate({"id": "x", "if": "weight_gain_kg_3d >= 2", "then": {"step": "cardio_visit",
                                                                                                 "due_days": 7}}),
                        st, risk, 43, np.array([0]))
    assert texts == {"it": ["Peso +2,1 kg in 3 giorni: Visita cardiologica entro 7 giorni"],
                     "en": ["Weight +2.1 kg in 3 days: Cardiology visit within 7 days"]}


def test_regional_alarm_opens_once_and_closes(monkeypatch):
    waits = iter([{"Ospedale B": 31.0}, {"Ospedale B": 35.0}, {"Ospedale B": 29.0}])
    monkeypatch.setattr(monitoring.tools, "call", lambda ctx, name, args: {"data": next(waits)})

    class Con:  # records the SQL Monitoring writes
        def __init__(self):
            self.sql = []

        def execute(self, sql, params=None):
            self.sql.append((sql.split()[0], params))

        def cursor(self):
            return self

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    m, con = monitoring.Monitoring(HF, "s2_agents", {"Ospedale B": "osp_B"}), Con()
    assert len(m._regional_alarms(con, 33, 2)) == 1
    assert m._regional_alarms(con, 34, 2) == []  # still open: no second alarm
    assert m._regional_alarms(con, 35, 2) == []
    assert [s for s, _ in con.sql] == ["INSERT", "UPDATE"]  # opened, then closed on day 35
    assert m.open == {}


def test_monitoring_names_no_disease():
    for module in (monitoring, rules):
        source = Path(module.__file__).read_text(encoding="utf-8").lower()
        for word in ("furosemide", "c03ca01", "ecocardio", "cardiolog", "bnp", "hf_", "osp_"):
            assert word not in source, (module.__name__, word)
