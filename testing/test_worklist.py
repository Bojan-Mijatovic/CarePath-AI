"""worklist_today (delivery plan step 2.4, SPEC C20) on the fixture run, scenario 2, day 62."""

import json
from pathlib import Path

import duckdb
import pytest

from engine import pathway as pathway_model
from engine import worklist
from engine.risk import HIGH_RISK, RiskModel

DAY = 62
HF = pathway_model.load("hf_lombardia_v1")


@pytest.fixture(scope="module")
def runs(fixture_scenario):
    return fixture_scenario[0]


@pytest.fixture(scope="module")
def con(runs):
    with duckdb.connect(runs / "s2_agents.duckdb", read_only=True) as c:
        yield c


def test_one_ranked_row_per_patient_with_a_reason(con):
    rows = con.execute("""
        SELECT w.rank, w.risk_score, len(s.overdue_steps) AS late, w.reasons, s.risk_score AS state_risk
        FROM worklist_today w JOIN pathway_state s USING (patient_id) WHERE w.day = $d ORDER BY w.rank""",
                       {"d": DAY}).fetchall()
    assert [r[0] for r in rows] == list(range(1, len(rows) + 1))
    assert [r[1] for r in rows] == sorted((r[1] for r in rows), reverse=True)  # by risk
    assert all(json.loads(r[3])["it"] for r in rows)  # everyone has a reason
    assert all(r[1] == r[4] for r in rows)  # the score Risk wrote today
    expected = con.execute("""
        SELECT count(*) FROM pathway_state WHERE len(overdue_steps) > 0 OR risk_score >= $h OR len(flags) > 0""",
                           {"h": HIGH_RISK}).fetchone()[0]
    assert 1000 < len(rows) <= expected + 50  # minus the patients in hospital, plus the few a weight rule adds
    flagged_missing = con.execute("""
        SELECT count(*) FROM pathway_state s
        WHERE len(s.flags) > 0 AND s.patient_id NOT IN (SELECT patient_id FROM worklist_today WHERE day = $d)
          AND NOT EXISTS (SELECT 1 FROM events e WHERE e.patient_id = s.patient_id AND e.event_type = 'ADMISSION'
                          AND e.day > coalesce((SELECT max(day) FROM events x WHERE x.patient_id = s.patient_id
                                                AND x.event_type = 'DISCHARGE'), -1000000))""", {"d": DAY}).fetchone()[0]
    assert flagged_missing == 0  # a flag (Monitoring, step 2.8) puts a patient out of hospital on the list


def test_top_20_are_high_risk_or_overdue(con):
    # AC12, data side: at least 15 of the top 20; by construction all of them are.
    top = con.execute("""
        SELECT count(*) FROM worklist_today w JOIN pathway_state s USING (patient_id)
        WHERE w.day = $d AND w.rank <= 20 AND (s.risk_score >= $h OR len(s.overdue_steps) > 0)""",
                      {"d": DAY, "h": HIGH_RISK}).fetchone()[0]
    assert top >= 15


def test_reasons_name_every_overdue_step_and_the_risk(con):
    label = {s.id: s.label for s in HF.steps}
    rows = con.execute("""
        SELECT w.reasons, s.overdue_steps, w.risk_score FROM worklist_today w JOIN pathway_state s USING (patient_id)
        WHERE w.day = $d""", {"d": DAY}).fetchall()
    for reasons, late, risk in rows:
        reasons = json.loads(reasons)
        assert set(reasons) == {"it", "en"}
        for step in late:
            assert f"{label[step].it} in ritardo di" in reasons["it"]
            assert f"{label[step].en} " in reasons["en"]
        assert reasons["it"].startswith("Rischio alto") == (risk >= HIGH_RISK)
        assert reasons["en"].startswith("High risk") == (risk >= HIGH_RISK)


def test_a_list_for_every_day_and_none_without_carepath(con, runs):
    assert con.execute("SELECT count(DISTINCT day) FROM worklist_today").fetchone() == (DAY + 1,)
    assert con.execute("SELECT count(*) FROM worklist_today WHERE outcome IS NOT NULL OR script IS NOT NULL").fetchone() == (0,)
    with duckdb.connect(runs / "s2_baseline.duckdb", read_only=True) as baseline:
        assert baseline.execute("SELECT count(*) FROM worklist_today").fetchone() == (0,)


def test_every_driver_has_a_text_in_both_languages():
    class State:  # what driver_text reads
        pathway = HF
    for name in RiskModel(HF).names:
        if name in worklist.SKIPPED_DRIVERS:
            continue
        for value in (0.0, 1.0, 12.0, 2.3):
            text = worklist.driver_text(name, value, True, State())
            assert set(text) == {"it", "en"} and all(text.values()), name
            assert "0 giorni" not in text["it"] and "0 days" not in text["en"], name
    assert worklist.driver_text("lives_alone", 1.0, False, State())["it"] == "vive solo"


def test_texts_come_from_the_pathway_not_the_code():
    source = Path(worklist.__file__).read_text(encoding="utf-8").lower()
    for word in ("furosemide", "c03ca01", "echo", "ecocardio", "cardiolog", "bnp", "hf_"):
        assert word not in source, word
