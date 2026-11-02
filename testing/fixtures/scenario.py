"""Fixtures for every contract, from one scenario (delivery plan step 1.23).

Scenario 2, seed 42, 10,000 patients, days 0–62 (the demo runs to about day 62, D21), both arms. In the
agents arm two actions go through the action service (step 2.12) with the default levels: the Centro
Servizi call to Maria on day 31, executed, and an echo reschedule at the bottleneck hospital on day 35,
waiting for approval. Rationales are templates filled by code (D17); the reschedule's numbers, the alarm,
the investigation steps and the tool fixtures come from agents.tools called on the live run (step 1.24).

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

from agents import actions, tools
from engine import pathway as pathway_model
from engine.db import create_run, open_run, tool_cursor
from agents.monitoring import Monitoring
from engine import investigations, reports, worklist
from engine.queries import investigations as investigations_rows
from engine.queries import reports as reports_rows
from engine.queries import capacity, kpi_headline, map_comuni, patient_360, rows, sankey
from engine.queries import worklist as worklist_rows
from engine.risk import HIGH_RISK, RiskModel
from engine.state import StateEngine
from sim.population import generate_patients, load_reference
from sim.run import append, load_reference_tables
from sim.step import Simulator, load_scenario

FIXTURES = Path(__file__).resolve().parent
SCENARIO, SEED, DAYS = 2, 42, 63
PATHWAY_ID = "hf_lombardia_v1"
RUNS = {"s2_baseline": False, "s2_agents": True}
MARIA, CALL_DAY, ALARM_DAY = "p_00001", 31, 35
CALL_ID, RESCHEDULE_ID = "act_s2_agents_1", "act_s2_agents_2"
WAIT_ARGS = {"pathway_id": PATHWAY_ID, "step": "echo", "period_days": 7}
FREE_ARGS = {"service": "echo"}
WORKLIST_SIZE = 20


def source(tool: str, args: dict, day: int) -> dict:
    return {"tool": tool, "args": args, "run_id": "s2_agents", "day": day}  # SPEC §6 envelope (C5)


def it_number(x: float) -> str:
    return f"{x:.1f}".replace(".", ",")


def facility_ids(con) -> dict[str, str]:
    return {name: fid for fid, name in con.execute("SELECT facility_id, name FROM facilities").fetchall()}


def live_tool(con, sim: Simulator, day: int, name: str, args: dict) -> dict:
    """A tool call on the live run, as the agents will make it (SPEC §6, D29). capacity_slots is refreshed
    first: the simulator books slots every day, and the demo's tick keeps the table current (step 2.1)."""
    con.execute("DELETE FROM capacity_slots")
    append(con, "capacity_slots", sim.capacity_slots())
    result = tools.call(tools.Context("s2_agents", tools.Query(tool_cursor(con)), day), name, args)
    assert "data" in result, result
    return result


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
    row = actions.create(con, "s2_agents", day, {"agent": "intervention", "type": "call_task", "patient_id": MARIA,
                                                 "pathway_id": PATHWAY_ID, "payload": {"cs_id": f["cs_id"]},
                                                 "rationale": rationale, "evidence": evidence}, emit(con, sim, day))
    assert (row["action_id"], row["status"]) == (CALL_ID, "executed")


def propose_reschedule(con, sim: Simulator, day: int) -> dict:
    """Echo reschedule at the slowest hospital, level 2: waits in the approval queue (SPEC §7.2). Its
    numbers come from the tools. Returns the two tool results, which the alarm, the investigation and the
    tool fixtures show."""
    wait = live_tool(con, sim, day, "wait_by_hospital", WAIT_ARGS)
    free = live_tool(con, sim, day, "free_slots", FREE_ARGS)
    w, f, ids = wait["data"], free["data"], facility_ids(con)
    slow = max(w, key=w.get)
    to = max((n for n in f if n != slow), key=f.get)
    others = sum(v for n, v in w.items() if n != slow) / (len(w) - 1)
    waiting = con.execute("""
        SELECT count(DISTINCT patient_id) FROM events
        WHERE event_type = 'BOOKING' AND code = 'echo' AND facility_id = $f AND day <= $d AND value > $d""",
                          {"d": day, "f": ids[slow]}).fetchall()[0][0]
    rationale = {"it": f"{slow}: attesa media per l'ecocardiogramma {it_number(w[slow])} giorni, negli altri "
                       f"ospedali {it_number(others)}. {waiting} pazienti in attesa a {slow}; "
                       f"{to} ha {f[to]} posti liberi nei prossimi 21 giorni.",
                 "en": f"{slow}: mean wait for an echo {w[slow]:.1f} days, {others:.1f} at the other hospitals. "
                       f"{waiting} patients waiting at {slow}; {to} has {f[to]} free slots in the next 21 days."}
    row = actions.create(con, "s2_agents", day, {
        "agent": "intervention", "type": "reschedule", "scope": {"facility_id": ids[slow], "patients": waiting},
        "pathway_id": PATHWAY_ID, "payload": {"from_facility": ids[slow], "to_facility": ids[to], "service": "echo"},
        "rationale": rationale, "evidence": [wait["source"], free["source"]]}, emit(con, sim, day))
    assert (row["action_id"], row["status"]) == (RESCHEDULE_ID, "proposed")
    return {"wait": wait, "free": free, "ids": ids}


def emit(con, sim: Simulator, day: int):
    """The action service's feedback (SPEC §9), as engine.tick.Run.feedback does it on the live tick."""
    return lambda rows: append(con, "events", sim.apply_actions(day, pd.DataFrame(
        [{k: r[k] for k in ("action_id", "type", "patient_id")} for r in rows if r["patient_id"] is not None])))


def build_runs(runs_dir: Path) -> dict:
    """Both runs into runs_dir. Returns the stream-message facts that only exist while the run is live."""
    ref = load_reference()
    patients, mmg = generate_patients(SEED, ref)
    hf = pathway_model.load(PATHWAY_ID)
    live, investigation, report = {}, [], []
    for run_id, agents in RUNS.items():
        sim = Simulator(SEED, patients, ref, hf, days=DAYS)
        sim.apply_scenario(load_scenario(SCENARIO), mmg)
        create_run(run_id, runs_dir=runs_dir, overwrite=True)
        with open_run(run_id, runs_dir) as con:
            load_reference_tables(con, ref, patients, mmg)
            for events in sim.warm_up():
                append(con, "events", events)
            state = StateEngine(con, hf)
            risk = RiskModel(hf)
            monitoring = Monitoring(hf, run_id, dict(con.execute("SELECT name, facility_id FROM facilities").fetchall()))
            for d in range(DAYS):
                append(con, "events", sim.step(d))
                state.update(con, d)
                risk.update(con, state, d)
                monitoring.run(con, state, risk, d, SCENARIO)
                state.refresh_kpi(con, d)
                state.refresh_map(con, d, risk.risk, HIGH_RISK)
                if agents:
                    worklist.refresh(con, state, risk, d, monitoring.fired)
                if agents and d == CALL_DAY:  # Intervention runs after the views (SPEC §9, steps 5–6)
                    call_maria(con, sim, d)
                if agents and con.execute("SELECT count(*) FROM alerts WHERE level = 'regional' AND day = $d",
                                          {"d": d}).fetchall()[0][0]:  # step 7, on capacity as the tick has it (C25)
                    con.execute("DELETE FROM capacity_slots")
                    append(con, "capacity_slots", sim.capacity_slots())
                    investigation = investigations.on_alarms(con, run_id, hf, d, SCENARIO, [])
                if agents:  # the month's report on its last day (step 2.14, C36)
                    report = reports.on_day(con, run_id, hf, d, SCENARIO) or report
                if agents and d == ALARM_DAY:
                    live = propose_reschedule(con, sim, d) | {"investigation": investigation}
            con.execute("DELETE FROM capacity_slots")
            append(con, "capacity_slots", sim.capacity_slots())
    return live | {"report": report[0]}


def stream(con, live: dict) -> dict[str, object]:
    """WebSocket messages (SPEC §10) of the agents arm."""
    msg = lambda type_, day, payload: {"type": type_, "scenario": SCENARIO, "day": day, "payload": payload}
    call = rows(con, "SELECT * FROM actions WHERE action_id = $a", {"a": CALL_ID})[0]
    # The first alerts Monitoring raised from the demo's start day on (step 2.8)
    alert = lambda level: rows(con, """
        SELECT day, alert_id, level, facility_id, group_key, investigation_id, text FROM alerts
        WHERE level = $l AND day >= 23 ORDER BY day, alert_id LIMIT 1""", {"l": level})[0]
    as_message = lambda a: msg("alert", a.pop("day"), a)
    return {
        "tick.json": msg("tick", ALARM_DAY, {"speed": 1, "kpi": kpi_headline(con, ALARM_DAY, PATHWAY_ID)}),
        "alert_patient.json": as_message(alert("patient")),
        "alert_regional.json": as_message(alert("regional")),
        "action.json": msg("action", CALL_DAY, call),
        "investigation.json": live["investigation"],  # the Investigator on the alarm's tick, from the cache (C25)
        "report.json": live["report"],  # the last month's report (C36)
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
        out["api/sankey_s2_agents.json"] = sankey(con, None)
        out["api/map_s2_agents.json"] = map_comuni(con, None)
        out["api/capacity_echo_s2_agents.json"] = capacity(con, PATHWAY_ID, "echo", last)  # C28
        out["api/worklist_s2_agents.json"] = worklist_rows(con, last)[:WORKLIST_SIZE]
        out["api/investigations_s2_agents.json"] = investigations_rows(con)
        out["api/reports_s2_agents.json"] = reports_rows(con)  # C36
        out["api/settings_s2_agents.json"] = {"autonomy": actions.settings(con)}  # C30, the defaults
        out |= {f"stream/{name}": m for name, m in stream(con, live).items()}
        out["tools/wait_by_hospital.json"] = live["wait"]
        out["tools/free_slots.json"] = live["free"]
        out["tools/error.json"] = tools.call(tools.Context("s2_agents", tools.Query(con), last), "wait_by_hospital",
                                             {"pathway_id": PATHWAY_ID, "step": "ecg"})
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
