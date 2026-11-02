"""State engine (delivery plan step 1.22): pathway_state status rules of SPEC §5.1 and kpi_daily of §5.2."""

import time

import duckdb
import numpy as np
import pandas as pd
import pytest

from engine import pathway as pathway_model
from engine.db import create_run
from engine.state import StateEngine
from sim.population import generate_patients, load_reference
from sim.run import append, load_reference_tables
from sim.step import Simulator, load_scenario

HF = pathway_model.load("hf_lombardia_v1")
MANTOVA, CREMONA = ("asst_mantova", "020030"), ("asst_cremona", "019036")

# (patient, day, event_type, code, value). Thresholds: due_soon 7 days, dropped after 30 days or 2 steps.
EVENTS = [
    # p1: telemonitoring through readings only; cardiology booked for day 25, then missed.
    ("p_00001", -40, "DISPENSE", "C03CA01", 30), ("p_00001", 0, "DISCHARGE", "428.0", None),
    ("p_00001", 2, "TELEMON_READING", None, 71.0), ("p_00001", 5, "BOOKING", "cardio_visit", 25),
    # p2: nothing after the discharge.
    ("p_00002", 0, "DISCHARGE", "428.1", None),
    # p3: every early step done; the echo is never done.
    ("p_00003", 0, "DISCHARGE", "428.0", None), ("p_00003", 3, "TELEMON_START", None, None),
    ("p_00003", 10, "VISIT", "cardiologia", None), ("p_00003", 60, "LAB", "30934-4", 410),
    # p4: BNP late before day 0; the discharge on day 1 restarts its clock.
    ("p_00004", -100, "DISPENSE", "C03CA01", 30), ("p_00004", -95, "LAB", "30934-4", 380),
    ("p_00004", 1, "DISCHARGE", "428.0", None),
    # p5: not eligible (another drug).
    ("p_00005", -10, "DISPENSE", "C07AB07", 30),
    # Readmissions (ASST Cremona): within 30 days, after 31 days, index discharge in the warm-up, planned.
    ("p_00006", 0, "DISCHARGE", "428.0", None), ("p_00006", 20, "ADMISSION", "428.0", 1),
    ("p_00007", 0, "DISCHARGE", "428.0", None), ("p_00007", 31, "ADMISSION", "428.0", 1),
    ("p_00008", -10, "DISCHARGE", "428.0", None), ("p_00008", 5, "ADMISSION", "428.0", 1),
    ("p_00009", 0, "DISCHARGE", "428.0", None), ("p_00009", 10, "ADMISSION", "428.0", 0),
]
CREMONA_PATIENTS = {"p_00006", "p_00007", "p_00008", "p_00009"}
LAST_DAY = 125


def small_run(tmp_path, events=EVENTS):
    con = duckdb.connect(create_run("s1_agents", runs_dir=tmp_path))
    for n in range(1, 10):
        pid = f"p_{n:05d}"
        asst, comune = CREMONA if pid in CREMONA_PATIENTS else MANTOVA
        con.execute("INSERT INTO patients VALUES (?, 'F', 80, ?, ?, 'mmg_001', false, 'osp_A', 10.0, ['HF'])",
                    [pid, comune, asst])
    for e, (pid, day, etype, code, value) in enumerate(events, 1):
        comune = (CREMONA if pid in CREMONA_PATIENTS else MANTOVA)[1]
        con.execute("INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, 'mmg_001', ?, 'sim', NULL)",
                    [f"ev_{e}", pid, day, etype, code, value, comune])
    return con


def state(con):
    return con.execute("SELECT * EXCLUDE (updated_day) FROM pathway_state ORDER BY patient_id").df()


@pytest.fixture(scope="module")
def daily(tmp_path_factory):
    """The small run advanced one day at a time; pathway_state of every day."""
    con = small_run(tmp_path_factory.mktemp("small"))
    engine = StateEngine(con, HF)
    days = {}
    for d in range(LAST_DAY + 1):
        engine.update(con, d)
        engine.refresh_kpi(con, d)
        days[d] = state(con).set_index("patient_id")
    return con, engine, days


@pytest.mark.parametrize("pid, day, status, overdue", [
    ("p_00001", 0, "due_soon", []),                 # telemonitoring due on day 7
    ("p_00001", 2, "on_track", []),                 # a reading counts as telemonitoring active
    ("p_00001", 23, "on_track", []),                # cardiology due within 7 days but booked
    ("p_00001", 26, "due_soon", []),                # the booked day passed without a visit
    ("p_00001", 31, "overdue", ["cardio_visit"]),
    ("p_00002", 7, "due_soon", []),                 # due today is not late yet
    ("p_00002", 8, "overdue", ["telemon"]),
    ("p_00002", 31, "dropped", ["telemon", "cardio_visit"]),  # 2 steps overdue at once
    ("p_00003", 61, "on_track", []),
    ("p_00003", 83, "due_soon", []),                # echo due on day 90, not booked
    ("p_00003", 120, "overdue", ["echo"]),          # 30 days late is still overdue ...
    ("p_00003", 121, "dropped", ["echo"]),          # ... more than 30 is dropped
    ("p_00004", 0, "overdue", ["lab_bnp"]),         # BNP due on day -5 (done on day -95)
    ("p_00004", 1, "due_soon", []),                 # discharge: BNP due on day 91, telemonitoring on day 8
])
def test_status_rules(daily, pid, day, status, overdue):
    row = daily[2][day].loc[pid]
    assert (row.status, list(row.overdue_steps)) == (status, overdue)


def test_next_and_current_step(daily):
    p1 = daily[2][23].loc["p_00001"]
    assert (p1.current_step, p1.next_step, p1.next_due_day, p1.next_booked_day) == ("discharge", "cardio_visit", 30, 25)
    p1 = daily[2][26].loc["p_00001"]
    assert pd.isna(p1.next_booked_day)  # the booking is in the past
    p3 = daily[2][61].loc["p_00003"]
    assert (p3.current_step, p3.next_step, p3.next_due_day) == ("lab_bnp", "echo", 90)


def test_enrollment_and_columns_owned_by_others(daily):
    rows = daily[2][LAST_DAY]
    assert "p_00005" not in rows.index  # never eligible
    assert rows.loc["p_00001", "enrolled_day"] == -40  # first furosemide
    assert rows.loc["p_00008", "enrolled_day"] == -10  # first HF discharge
    assert set(rows.enrolled_by) == {"mmg"}
    assert (rows.escalation_step == 0).all()
    assert (rows.risk_score == 0.0).all()  # until Risk (step 2.3)
    assert rows["flags"].map(len).eq(0).all()
    assert rows["risk_drivers"].map(len).eq(0).all()


def test_rows_are_written_only_when_they_change(daily):
    con = daily[0]
    updated = dict(con.execute("SELECT patient_id, updated_day FROM pathway_state").fetchall())
    assert updated["p_00003"] == 121  # last change: dropped
    assert updated["p_00009"] < LAST_DAY


def test_day_by_day_equals_one_pass(daily, tmp_path):
    con = small_run(tmp_path)
    StateEngine(con, HF).update(con, LAST_DAY)
    pd.testing.assert_frame_equal(state(con), daily[2][LAST_DAY].reset_index())


def test_kpi_daily(daily):
    con = daily[0]
    kpi = con.execute("SELECT * FROM kpi_daily WHERE day = 40 ORDER BY level, key").df().set_index(["level", "key"])
    assert list(kpi.index) == [("asst", "asst_cremona"), ("asst", "asst_mantova"), ("ats", "ats"),
                               ("comune", "019036"), ("comune", "020030")]
    ats = kpi.loc[("ats", "ats")]
    assert ats.patients == 8
    assert ats.readmissions_30d == 2  # p6 (20 days) and p8 (index in the warm-up)
    assert ats.readmission_rate_30d == round(2 / 7, 4)  # 7 index discharges from day 0
    assert kpi.loc[("asst", "asst_cremona")].readmission_rate_30d == round(2 / 3, 4)
    assert kpi.loc[("asst", "asst_mantova")].readmissions_30d == 0
    assert kpi.on_track_pct.between(0, 1).all()
    # C39: readmissions times the pathway's assumed cost per readmission
    eur = pathway_model.load("hf_lombardia_v1").readmission_cost.eur
    assert (kpi.est_readmission_cost_eur == kpi.readmissions_30d * eur).all()
    assert con.execute("SELECT min(day), max(day), count(DISTINCT day) FROM kpi_daily").fetchone() == (0, LAST_DAY, LAST_DAY + 1)


def test_kpi_counts_actions_where_the_patient_lives(tmp_path):
    con = small_run(tmp_path)
    for n, (pid, status, executed) in enumerate([("p_00006", "executed", 3), ("p_00006", "proposed", None),
                                                 (None, "executed", 4), ("p_00001", "executed", 50)]):
        con.execute("INSERT INTO actions VALUES (?, 'intervention', 'call_task', ?, NULL, 'hf_lombardia_v1', '{}', "
                    "'{\"it\": \"\", \"en\": \"\"}', '[]', 3, ?, 2, ?, 'auto')", [f"act_s1_agents_{n}", pid, status, executed])
    engine = StateEngine(con, HF)
    engine.update(con, 10)
    engine.refresh_kpi(con, 10)
    kpi = con.execute("SELECT level, key, actions_executed, actions_pending FROM kpi_daily").df().set_index(["level", "key"])
    assert tuple(kpi.loc[("ats", "ats")]) == (2, 1)  # the day-50 action is not executed yet on day 10
    assert tuple(kpi.loc[("asst", "asst_cremona")]) == (1, 1)
    assert tuple(kpi.loc[("asst", "asst_mantova")]) == (0, 0)  # the action without a patient counts for the ATS only


def test_events_recorded_after_the_update_are_applied_next_day(tmp_path):
    con = small_run(tmp_path)
    engine = StateEngine(con, HF)
    engine.update(con, 5)
    engine.refresh_kpi(con, 5)
    # The action service records a call on day 5 after the state engine ran (SPEC §9 tick order).
    con.execute("INSERT INTO events VALUES ('ev_999', 'p_00002', 5, 'CALL', 'completed', NULL, NULL, NULL, "
                "'mmg_001', '020030', 'agent_action', 'act_s1_agents_1')")
    engine.update(con, 5)  # the same day again applies only what is new: no readmission is counted twice
    engine.refresh_kpi(con, 5)
    engine.update(con, 6)
    assert con.execute("SELECT last_event_day FROM pathway_state WHERE patient_id = 'p_00002'").fetchone() == (5,)
    assert con.execute("SELECT readmissions_30d FROM kpi_daily WHERE day = 5 AND level = 'ats'").fetchone() == (1,)
    with pytest.raises(ValueError, match="replay"):
        engine.update(con, 4)


def test_nothing_names_the_disease(tmp_path):
    # AC17: other step ids and thresholds come straight from the pathway file.
    renamed = {"telemon": "telemonitoraggio", "cardio_visit": "visita_cardio"}
    steps = [s.model_copy(update={"id": renamed.get(s.id, s.id)}) for s in HF.steps]
    other = HF.model_copy(update={"pathway_id": "hf_variant", "steps": steps, "rules": [],
                                  "status_thresholds": HF.status_thresholds.model_copy(update={"due_soon_days": 3})})
    other = pathway_model.Pathway.model_validate(other.model_dump(by_alias=True))
    con = small_run(tmp_path)
    engine = StateEngine(con, other)
    engine.update(con, 8)
    rows = state(con).set_index("patient_id")
    assert set(rows.pathway_id) == {"hf_variant"}
    assert list(rows.loc["p_00002", "overdue_steps"]) == ["telemonitoraggio"]
    engine.update(con, 26)
    assert state(con).set_index("patient_id").loc["p_00001", "status"] == "on_track"  # due in 4 days > 3


# A real run: 10,000 patients, scenario 2, both arms, Maria's day-31 call in the agents arm.
DAYS = 60


def simulate(tmp_path, call):
    ref = load_reference()
    patients, mmg = generate_patients(42, ref)
    sim = Simulator(42, patients, ref, HF, days=DAYS)
    sim.apply_scenario(load_scenario(2), mmg)
    con = duckdb.connect(create_run("s2_agents" if call else "s2_baseline", runs_dir=tmp_path))
    load_reference_tables(con, ref, patients, mmg)
    for ev in sim.warm_up():
        append(con, "events", ev)
    engine = StateEngine(con, HF)
    maria, ms = [], []
    for d in range(DAYS):
        append(con, "events", sim.step(d))
        t = time.perf_counter()
        engine.update(con, d)
        engine.refresh_kpi(con, d)
        ms.append((time.perf_counter() - t) * 1000)
        maria.append(con.execute("SELECT status, next_step FROM pathway_state WHERE patient_id = 'p_00001'").fetchall()[0])
        if call and d == 31:
            append(con, "events", sim.apply_actions(d, pd.DataFrame(
                [{"action_id": "act_s2_agents_1", "type": "call_task", "patient_id": "p_00001"}])))
    return con, engine, maria, ms


@pytest.fixture(scope="module")
def arms(tmp_path_factory):
    return {call: simulate(tmp_path_factory.mktemp(f"real_{call}"), call) for call in (False, True)}


@pytest.mark.parametrize("call", [False, True], ids=["without_agents", "with_agents"])
def test_maria_stays_on_the_pathway_through_the_demo(arms, call):
    # Telemonitoring is due on day 7 (started day 6); cardiology on day 30 was booked on day 3 for day 24;
    # echo and BNP fall due on day 90. Without agents the readmission (47–55) restarts the clock.
    statuses = [s for s, _ in arms[call][2]]
    assert statuses == ["due_soon"] * 6 + ["on_track"] * (DAYS - 6)
    assert arms[call][2][30][1] == "echo"


def test_one_pass_equals_day_by_day_on_a_real_run(arms):
    con, engine, _, _ = arms[True]
    fresh = StateEngine(con, HF)
    fresh._apply(con.execute("SELECT event_id, patient_id, day, event_type, code, value FROM events "
                             "WHERE day <= $d", {"d": DAYS - 1}).df())
    fresh._sweep(DAYS - 1)
    for name in ("enrolled_day", "last_event", "own", "done", "booked_on", "booked_for", "readmissions",
                 "index_discharges", "status", "last_drug", "telemon_started", "last_reading", "last_admission",
                 "last_discharge", "n_overdue", "days_overdue"):
        np.testing.assert_array_equal(getattr(fresh, name), getattr(engine, name), err_msg=name)
    # The weight ring keeps stale slots day by day; what is read from it must agree.
    np.testing.assert_array_equal(fresh.weight_gain_kg_3d(DAYS - 1), engine.weight_gain_kg_3d(DAYS - 1))


def test_real_run_kpis_are_plausible(arms):
    con = arms[False][0]
    ats = con.execute(f"SELECT * FROM kpi_daily WHERE level = 'ats' AND day = {DAYS - 1}").df().iloc[0]
    assert ats.patients > 9900
    assert 0.5 < ats.on_track_pct < 0.95
    assert 0.08 < ats.readmission_rate_30d < 0.20  # PNE range 10–16% (step 1.16); 60 days are noisy
    by_asst = con.execute(f"SELECT sum(patients) FROM kpi_daily WHERE level = 'asst' AND day = {DAYS - 1}").fetchone()[0]
    assert by_asst == ats.patients


def test_state_update_fits_the_tick_budget(arms):
    # SPEC §9: both arms of the scenario on screen under 500 ms per simulated day, everything included.
    ms = arms[False][3][1:]  # day 0 also reads the 120-day history
    assert np.mean(ms) < 150, np.mean(ms)
