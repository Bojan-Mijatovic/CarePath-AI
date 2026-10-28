"""Fixtures for every contract, from one scenario (delivery plan step 1.23).

Scenario 2, seed 42, 10,000 patients, days 0–62 (the demo runs to about day 62, D21), both arms. In the
agents arm two actions are written the way the action service will write them (step 2.12): the Centro
Servizi call to Maria on day 31, executed, and an echo reschedule at the bottleneck hospital on day 35,
waiting for approval. Rationales are templates filled by code (D17).

`build_runs` writes runs/s2_baseline.duckdb and runs/s2_agents.duckdb into a directory, for tests of
tools and the engine; they are rebuilt, not committed. `export` turns them into the JSON files next to
this script: API responses and stream messages (SPEC §6, §10). testing/test_fixtures.py rebuilds both and
fails if a committed file differs. What each file holds, and which values are stand-ins: README.md.

    uv run python testing/fixtures/scenario.py   # rewrite the JSON files
"""

import json
import shutil
import tempfile
from pathlib import Path

import duckdb
import pandas as pd

from engine import pathway as pathway_model
from engine.db import create_run
from engine.state import StateEngine
from sim import pattern_proof
from sim.population import generate_patients, load_reference
from sim.run import append, load_reference_tables
from sim.step import Simulator, load_scenario

FIXTURES = Path(__file__).resolve().parent
SCENARIO, SEED, DAYS = 2, 42, 63
PATHWAY_ID = "hf_lombardia_v1"
RUNS = {"s2_baseline": False, "s2_agents": True}
MARIA, CALL_DAY, ALARM_DAY = "p_00001", 31, 35
CALL_ID, RESCHEDULE_ID = "act_s2_agents_1", "act_s2_agents_2"
INVESTIGATION_ID = "inv_s2_agents_1"
JSON_COLUMNS = {"scope", "payload", "rationale", "evidence", "details"}
WAIT_ARGS = {"pathway_id": PATHWAY_ID, "step": "echo", "period_days": 7}
FREE_ARGS = {"service": "echo", "horizon_days": 21}
WORKLIST_SIZE = 20


def rows(con: duckdb.DuckDBPyConnection, sql: str, params: dict | None = None) -> list[dict]:
    cur = con.execute(sql, params or {})
    names = [d[0] for d in cur.description]
    return [{n: json.loads(v) if n in JSON_COLUMNS and v is not None else v for n, v in zip(names, r)}
            for r in cur.fetchall()]


def source(tool: str, args: dict, day: int) -> dict:
    return {"tool": tool, "args": args, "run_id": "s2_agents", "day": day}  # SPEC §6 envelope (C5)


def it_number(x: float) -> str:
    return f"{x:.1f}".replace(".", ",")


def facility_names(con) -> dict[str, str]:
    return dict(con.execute("SELECT facility_id, name FROM facilities").fetchall())


def free_echo_slots(sim: Simulator, day: int, horizon: int = 21) -> pd.Series:
    """Free echo slots from day + 1 to day + horizon, by facility_id (the free_slots tool of SPEC §6)."""
    cap = sim.capacity_slots()
    cap = cap[(cap.service == "echo") & cap.day.between(day + 1, day + horizon)]
    return (cap.slots_total - cap.slots_booked).groupby(cap.facility_id).sum().sort_index()


def maria_facts(con, day: int) -> dict:
    """What the call and the alert say about Maria on `day`, computed from the run."""
    return rows(con, """
        SELECT $d - max(e.day + e.value)::INT AS days_without_drug, p.age, p.distance_km, c.name AS comune, m.cs_id
        FROM events e JOIN patients p USING (patient_id) JOIN comuni c ON c.comune_istat = p.comune_istat
        JOIN mmg m ON m.mmg_id = p.mmg_id
        WHERE e.patient_id = $p AND e.event_type = 'DISPENSE' AND e.day <= $d GROUP BY ALL""", {"d": day, "p": MARIA})[0]


def call_maria(con, sim: Simulator, day: int) -> None:
    """Centro Servizi call, level 3 (SPEC §7.2): action row, audit log and the CALL event (feedback hook)."""
    f = maria_facts(con, day)
    without, km = f["days_without_drug"], f["distance_km"]
    rationale = {"it": f"Scorta di furosemide finita da {without} giorni; vive sola a {it_number(km)} km dall'ospedale. "
                       "Chiamata del Centro Servizi per capire che cosa la ferma.",
                 "en": f"Furosemide supply ran out {without} days ago; lives alone {km:.1f} km from the hospital. "
                       "Centro Servizi call to find out what stops her."}
    evidence = [source("adherence_by_group", {"pathway_id": PATHWAY_ID, "grouping": "comune", "measure": "dispensing",
                                              "period_days": 60}, day)]
    write_action(con, CALL_ID, "call_task", MARIA, None, {"cs_id": f["cs_id"]}, rationale, evidence, 3, "executed", day)
    append(con, "events", sim.apply_actions(day, pd.DataFrame(
        [{"action_id": CALL_ID, "type": "call_task", "patient_id": MARIA}])))


def propose_reschedule(con, sim: Simulator, day: int) -> dict:
    """Echo reschedule at the slowest hospital, level 2: waits in the approval queue (SPEC §7.2). Returns
    the waits and free slots of that day, which the alarm and the investigation fixtures show."""
    wait = pattern_proof.echo_wait(con, day - 6, day)  # bookings of the last week, by facility_id
    slow = wait.idxmax()
    free = free_echo_slots(sim, day)
    names = facility_names(con)
    to = free.drop(slow).idxmax()
    waiting = con.execute("""
        SELECT count(DISTINCT patient_id) FROM events
        WHERE event_type = 'BOOKING' AND code = 'echo' AND facility_id = $f AND day <= $d AND value > $d""",
                          {"d": day, "f": slow}).fetchall()[0][0]
    others = wait.drop(slow).mean()
    rationale = {"it": f"{names[slow]}: attesa media per l'ecocardiogramma {it_number(wait[slow])} giorni, negli altri "
                       f"ospedali {it_number(others)}. {waiting} pazienti in attesa a {names[slow]}; "
                       f"{names[to]} ha {free[to]} posti liberi nei prossimi 21 giorni.",
                 "en": f"{names[slow]}: mean wait for an echo {wait[slow]:.1f} days, {others:.1f} at the other hospitals. "
                       f"{waiting} patients waiting at {names[slow]}; {names[to]} has {free[to]} free slots "
                       "in the next 21 days."}
    evidence = [source("wait_by_hospital", {"pathway_id": PATHWAY_ID, "step": "echo", "period_days": 7}, day),
                source("free_slots", {"service": "echo", "horizon_days": 21}, day)]
    write_action(con, RESCHEDULE_ID, "reschedule", None, {"facility_id": slow, "patients": waiting},
                 {"from_facility": slow, "to_facility": to, "service": "echo"}, rationale, evidence, 2, "proposed", day)
    return {"waits": wait, "free": free, "names": names}


def write_action(con, action_id, type_, patient, scope, payload, rationale, evidence, level, status, day) -> None:
    executed = status == "executed"
    con.execute("INSERT INTO actions VALUES (?, 'intervention', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [action_id, type_, patient, None if scope is None else json.dumps(scope), PATHWAY_ID,
                 json.dumps(payload), json.dumps(rationale, ensure_ascii=False), json.dumps(evidence), level, status,
                 day, day if executed else None, "auto" if executed else None])
    con.execute("INSERT INTO audit_log VALUES (?, ?, 'created', 'intervention', '{}')", [day, action_id])
    if executed:
        con.execute("INSERT INTO audit_log VALUES (?, ?, 'executed', 'auto', '{}')", [day, action_id])


def build_runs(runs_dir: Path) -> dict:
    """Both runs into runs_dir. Returns the stream-message facts that only exist while the run is live."""
    ref = load_reference()
    patients, mmg = generate_patients(SEED, ref)
    hf = pathway_model.load(PATHWAY_ID)
    live = {}
    for run_id, agents in RUNS.items():
        sim = Simulator(SEED, patients, ref, hf, days=DAYS)
        sim.apply_scenario(load_scenario(SCENARIO), mmg)
        with duckdb.connect(create_run(run_id, runs_dir=runs_dir, overwrite=True)) as con:
            load_reference_tables(con, ref, patients, mmg)
            for events in sim.warm_up():
                append(con, "events", events)
            state = StateEngine(con, hf)
            for d in range(DAYS):
                append(con, "events", sim.step(d))
                state.update(con, d)
                state.refresh_kpi(con, d)
                if agents and d == CALL_DAY:  # Intervention runs after the views (SPEC §9, steps 5–6)
                    call_maria(con, sim, d)
                if agents and d == ALARM_DAY:
                    live = propose_reschedule(con, sim, d)
            append(con, "capacity_slots", sim.capacity_slots())
    return live


def patient_360(con, patient_id: str) -> dict:
    """GET /api/patients/{id} (SPEC §10, C15)."""
    patient = rows(con, "SELECT p.*, c.name AS comune_name FROM patients p JOIN comuni c USING (comune_istat) "
                        "WHERE patient_id = $p", {"p": patient_id})[0]
    pathways = rows(con, "SELECT * FROM pathway_state WHERE patient_id = $p ORDER BY pathway_id", {"p": patient_id})
    timeline = rows(con, """
        SELECT * EXCLUDE (k, n) FROM (
            SELECT e.day, 'event' AS kind, e.event_id, e.event_type, e.code, e.value, e.facility_id,
                   f.name AS facility_name, e.source, e.action_id,
                   NULL AS type, NULL AS agent, NULL AS status, NULL::JSON AS rationale,
                   1 AS k, CAST(substr(e.event_id, 4) AS BIGINT) AS n
            FROM events e LEFT JOIN facilities f USING (facility_id) WHERE e.patient_id = $p
            UNION ALL
            SELECT created_day, 'action', NULL, NULL, NULL, NULL, NULL, NULL, NULL, action_id,
                   type, agent, status, rationale, 0, 0
            FROM actions WHERE patient_id = $p)
        ORDER BY day, k, n, action_id""", {"p": patient_id})
    for item in timeline:  # one shape per kind
        for key in (["type", "agent", "status", "rationale"] if item["kind"] == "event" else
                    ["event_id", "event_type", "code", "value", "facility_id", "facility_name", "source"]):
            del item[key]
    return {"patient": patient, "pathways": pathways, "timeline": timeline}


def kpi_headline(con, day: int) -> dict:
    """The `kpi` of a tick (SPEC §10, C15): the ATS row of kpi_daily for the pathway on screen."""
    return rows(con, "SELECT * EXCLUDE (day, level, key) FROM kpi_daily WHERE day = $d AND level = 'ats' "
                     "AND pathway_id = $pw", {"d": day, "pw": PATHWAY_ID})[0]


def sankey(con) -> list[dict]:
    """sankey_flows (SPEC §5.2, C15) from pathway_state; step 2.2 makes it a view."""
    return rows(con, """SELECT pathway_id, current_step AS from_step, next_step AS to_step, status, count(*) AS patients
                        FROM pathway_state GROUP BY ALL ORDER BY ALL""")


def map_stand_in(con, day: int) -> list[dict]:
    """map_comuni shape with stand-in values (README.md): its meaning is defined in step 2.2."""
    return rows(con, """
        SELECT key AS comune_istat, pathway_id, on_track_pct AS adherence_pct, 0.0::DOUBLE AS risk_mean,
               0 AS high_risk_patients, readmission_rate_30d, false AS alarm
        FROM kpi_daily WHERE level = 'comune' AND day = $d ORDER BY key""", {"d": day})


def worklist_stand_in(con, day: int) -> list[dict]:
    """worklist_today shape with stand-in values (README.md): ranked by status and lateness until Risk
    (step 2.3) and the worklist (step 2.4) exist."""
    late = rows(con, f"""
        SELECT patient_id, risk_score, overdue_steps, escalation_step, $d - next_due_day AS days_late
        FROM pathway_state WHERE status IN ('overdue', 'dropped')
        ORDER BY status = 'dropped' DESC, days_late DESC, patient_id LIMIT {WORKLIST_SIZE}""", {"d": day})
    label = {"telemon": ("telemonitoraggio", "telemonitoring"), "cardio_visit": ("visita cardiologica", "cardiology visit"),
             "echo": ("ecocardiogramma", "echocardiogram"), "lab_bnp": ("esame BNP", "BNP test")}
    return [{"rank": i, "patient_id": r["patient_id"], "risk_score": r["risk_score"],
             "reasons": {"it": "; ".join(f"{label[s][0]} in ritardo" for s in r["overdue_steps"]),
                         "en": "; ".join(f"{label[s][1]} overdue" for s in r["overdue_steps"])},
             "pathways": [PATHWAY_ID], "escalation_step": r["escalation_step"], "script": None, "outcome": None}
            for i, r in enumerate(late, 1)]


def stream(con, live: dict) -> dict[str, object]:
    """WebSocket messages (SPEC §10) of the agents arm."""
    msg = lambda type_, day, payload: {"type": type_, "scenario": SCENARIO, "day": day, "payload": payload}
    waits, free, names = live["waits"], live["free"], live["names"]
    slow = waits.idxmax()
    best = free.drop(slow).idxmax()
    others = waits.drop(slow).mean()
    call = rows(con, "SELECT * FROM actions WHERE action_id = $a", {"a": CALL_ID})[0]
    f = maria_facts(con, CALL_DAY)
    return {
        "tick.json": msg("tick", ALARM_DAY, {"speed": 1, "kpi": kpi_headline(con, ALARM_DAY)}),
        "alert_patient.json": msg("alert", CALL_DAY, {
            "level": "patient", "facility_id": None, "investigation_id": None,
            "text": {"it": f"{MARIA} ({f['age']} anni, {f['comune']}): scorta di furosemide finita da "
                           f"{f['days_without_drug']} giorni",
                     "en": f"{MARIA} ({f['age']}, {f['comune']}): furosemide supply ran out {f['days_without_drug']} "
                           "days ago"}}),
        "alert_regional.json": msg("alert", ALARM_DAY, {
            "level": "regional", "facility_id": slow, "investigation_id": INVESTIGATION_ID,
            "text": {"it": f"{names[slow]}: attesa per l'ecocardiogramma {it_number(waits[slow])} giorni, negli altri "
                           f"ospedali {it_number(others)}",
                     "en": f"{names[slow]}: echo wait {waits[slow]:.1f} days, {others:.1f} at the other hospitals"}}),
        "action.json": msg("action", CALL_DAY, call),
        "investigation.json": [
            msg("investigation", ALARM_DAY, {
                "investigation_id": INVESTIGATION_ID, "step": 1, "tool": "wait_by_hospital", "args": WAIT_ARGS,
                "result_summary": {"it": f"Attesa media più alta a {names[slow]}: {it_number(waits[slow])} giorni",
                                   "en": f"Longest mean wait at {names[slow]}: {waits[slow]:.1f} days"},
                "verified": None, "final": False}),
            msg("investigation", ALARM_DAY, {
                "investigation_id": INVESTIGATION_ID, "step": 2, "tool": "free_slots", "args": FREE_ARGS,
                "result_summary": {"it": f"{names[best]} ha {free[best]} posti liberi nei prossimi 21 giorni",
                                   "en": f"{names[best]} has {free[best]} free slots in the next 21 days"},
                "verified": None, "final": True}),
        ],
    }


def export(runs_dir: Path, live: dict) -> dict[str, object]:
    """Every JSON fixture, keyed by its path under testing/fixtures/."""
    out = {}
    for run_id in RUNS:
        with duckdb.connect(runs_dir / f"{run_id}.duckdb", read_only=True) as con:
            out[f"api/kpi_ats_{run_id}.json"] = rows(
                con, "SELECT * FROM kpi_daily WHERE level = 'ats' ORDER BY day, pathway_id")
            out[f"api/patient_{MARIA}_{run_id}.json"] = patient_360(con, MARIA)
    last = DAYS - 1
    with duckdb.connect(runs_dir / "s2_agents.duckdb", read_only=True) as con:
        out["api/kpi_s2_agents_day62.json"] = rows(
            con, "SELECT * FROM kpi_daily WHERE day = $d ORDER BY level, key", {"d": last})
        out["api/actions_s2_agents.json"] = rows(con, "SELECT * FROM actions ORDER BY created_day, action_id")
        out["api/sankey_s2_agents.json"] = sankey(con)
        out["api/map_s2_agents.json"] = map_stand_in(con, last)
        out["api/worklist_s2_agents.json"] = worklist_stand_in(con, last)
        out |= {f"stream/{name}": m for name, m in stream(con, live).items()}
        names = live["names"]
        out["tools/wait_by_hospital.json"] = {
            "data": {names[f]: float(w) for f, w in live["waits"].items()},
            "source": source("wait_by_hospital", WAIT_ARGS, ALARM_DAY)}
        out["tools/free_slots.json"] = {
            "data": {names[f]: int(n) for f, n in live["free"].items()},
            "source": source("free_slots", FREE_ARGS, ALARM_DAY)}
        out["tools/error.json"] = {"error": {"code": "unknown_step", "message": "step 'ecg' is not in hf_lombardia_v1"}}
    return out


def text(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


def build(runs_dir: Path) -> dict[str, str]:
    """Build both runs into runs_dir and return every fixture file's text."""
    return {path: text(obj) for path, obj in export(runs_dir, build_runs(runs_dir)).items()}


def main() -> None:
    tmp = Path(tempfile.mkdtemp())
    try:
        files = build(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    for sub in ("api", "stream", "tools"):
        shutil.rmtree(FIXTURES / sub, ignore_errors=True)
    for path, content in files.items():
        (FIXTURES / path).parent.mkdir(parents=True, exist_ok=True)
        (FIXTURES / path).write_text(content, encoding="utf-8", newline="\n")
        print(FIXTURES / path)


if __name__ == "__main__":
    main()
