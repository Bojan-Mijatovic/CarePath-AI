"""Views of SPEC §5.2 from step 2.2: map_comuni (C18) and sankey_flows, on the fixture run (day 62)."""

import duckdb
import pytest

from engine.risk import HIGH_RISK
from engine.state import MAP_ALARM_BELOW, MAP_MIN_PATIENTS

DAY = 62

# An independent computation of adherence_pct (C18), written as SQL over events, for the HF pathway.
ADHERENCE = """
    WITH ev AS (
        SELECT patient_id,
               max(day) FILTER (WHERE event_type = 'DISPENSE' AND code = 'C03CA01') AS last_drug,
               max(day) FILTER (WHERE event_type = 'TELEMON_READING') AS last_reading,
               bool_or(event_type IN ('TELEMON_START', 'TELEMON_READING')) AS started
        FROM events WHERE day <= $d GROUP BY patient_id)
    SELECT p.comune_istat, count(*) AS patients,
           round(avg((s.status = 'on_track' AND coalesce(ev.last_drug > $d - 60, false)
                      AND (NOT coalesce(ev.started, false) OR coalesce(ev.last_reading > $d - 7, false)))::INT), 4) AS adherence
    FROM pathway_state s JOIN patients p USING (patient_id) LEFT JOIN ev USING (patient_id)
    GROUP BY p.comune_istat"""


@pytest.fixture(scope="module")
def con(fixture_scenario):
    runs, _ = fixture_scenario
    with duckdb.connect(runs / "s2_agents.duckdb", read_only=True) as c:
        yield c


def test_map_adherence_and_alarm(con):
    expected = {c: (n, a) for c, n, a in con.execute(ADHERENCE, {"d": DAY}).fetchall()}
    rows = con.execute("SELECT comune_istat, adherence_pct, alarm FROM map_comuni").fetchall()
    assert {c for c, *_ in rows} == set(expected)
    for comune, adherence, alarm in rows:
        n, value = expected[comune]
        if n < MAP_MIN_PATIENTS:
            assert (adherence, alarm) == (None, False), comune
        else:
            assert adherence == value, comune
            assert alarm == (value < MAP_ALARM_BELOW), comune
    assert any(alarm for *_, alarm in rows)  # day 62 of scenario 2 has comuni below 50%


def test_map_readmissions_match_kpi_daily(con):
    mismatched = con.execute("""
        SELECT m.comune_istat FROM map_comuni m JOIN kpi_daily k ON k.key = m.comune_istat
        WHERE k.level = 'comune' AND k.day = $d AND m.readmission_rate_30d IS DISTINCT FROM k.readmission_rate_30d""",
                             {"d": DAY}).fetchall()
    assert mismatched == []


def test_map_risk_matches_pathway_state(con):
    # Risk ran on every tick of the fixture run (C19); the map aggregates the scores it wrote.
    mismatched = con.execute("""
        SELECT m.comune_istat FROM map_comuni m JOIN (
            SELECT p.comune_istat, round(avg(s.risk_score), 4) AS mean, count_if(s.risk_score >= $h) AS high
            FROM pathway_state s JOIN patients p USING (patient_id) GROUP BY 1) x USING (comune_istat)
        WHERE abs(m.risk_mean - x.mean) > 0.00011 OR m.high_risk_patients != x.high""", {"h": HIGH_RISK}).fetchall()
    assert mismatched == []
    assert con.execute("SELECT sum(high_risk_patients) FROM map_comuni").fetchone()[0] > 0


def test_sankey_counts_every_patient_once(con):
    total = con.execute("SELECT sum(patients) FROM sankey_flows").fetchone()[0]
    assert total == con.execute("SELECT count(*) FROM pathway_state").fetchone()[0]
    # A step leads to itself when it is periodic (lab_bnp every 90 days, most patients) or a rule pulled it
    # again (cardio_visit after a weight gain), so the console draws the Sankey in two columns, last step
    # done and next step, where a loop is not a cycle (step 2.16).
    loops = {s for (s,) in con.execute("SELECT DISTINCT from_step FROM sankey_flows WHERE from_step = to_step").fetchall()}
    assert "lab_bnp" in loops
    assert loops <= {"lab_bnp", "cardio_visit"}
