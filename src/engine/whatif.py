"""What-if (SPEC §9, C27; delivery plan step 2.5, D48): the levers' results come from full runs, computed in
advance on a grid and read back.

A full run is the demo's own code (simulator, state engine, Risk, Monitoring, worklist), which takes 230–317
ms a day per arm (step 2.22): 6 months of two arms are minutes, against AC4's 10 s, and a simulator-only run
is fast but has no agents in it. So the fallback of D22 is the design (D48): `uv run python -m
engine.whatif` computes each scenario's grid once, and POST /api/whatif reads it, in milliseconds.

Per scenario the grid is the baseline arm, the agents arm, and the agents arm with 1 to MAX_EXTRA_SLOTS extra
slots a day for the service of the first wait alarm, at its facility, from the day after it, for MONTHS
months. Facility and day come from the alarm Monitoring raised in the agents run, never from demo/truth.
A lever run is the agents run until the lever's first day (tick.Run), so the two differ only after it.
A lever on the telemonitoring deadline changes only when agents act; it comes with Intervention (step 2.13).

Every run then goes on to the year's last day (YEAR_END_DAY), and its PNE indicator there, the 30-day
readmission rate from day 0, is kept for the year-end forecast (engine.pne, step 2.6, C35); the 6-month summary
is still taken on its last day.

Results go to demo/whatif/scenario_<n>.json and must be computed again after a change to the simulator, the
engine or the agents, like the LLM cache; `testing/test_ac04_whatif_speed.py` catches a stale file.
"""

import json
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from agents import tools
from engine.db import tool_cursor
from engine.pathway import Pathway
from sim.step import CapacityChange

WHATIF_DIR = Path(__file__).resolve().parents[2] / "demo" / "whatif"
MONTHS, DAYS_PER_MONTH = 6, 30.5
PERIOD_DAYS = round(MONTHS * DAYS_PER_MONTH)  # 183: from the lever's first day to the last day, both included
MAX_EXTRA_SLOTS = 4
LAST_ALARM_DAY = 60  # every scenario's wait alarm opens by day 33 (SPEC §5.3)
YEAR_END_DAY = 364  # the last day of the demo's year (tick.HORIZON_DAYS - 1): PNE counts a calendar year
KPI_COLUMNS = ["day", "patients", "on_track_pct", "overdue", "dropped", "readmissions_30d", "readmission_rate_30d"]


class Levers(BaseModel):
    """POST /api/whatif `levers` (C27)."""
    model_config = ConfigDict(extra="forbid")
    extra_slots: int = Field(0, ge=0, le=MAX_EXTRA_SLOTS, description="slots a day added at the alarm's facility")


def path(scenario: int, directory: Path = WHATIF_DIR) -> Path:
    return directory / f"scenario_{scenario}.json"


def proposed_lever(scenario: int, pathway: Pathway, directory: Path = WHATIF_DIR) -> dict | None:
    """The smallest lever whose mean wait over the 6 months is within the step's `max_wait_days` (D45): the
    run id, the extra slots and the capacity change, or None without a grid or a lever that is enough. Code
    picks it; the LLM may only phrase it (CLAUDE.md rule 1). Step 2.27 makes it a proposal to approve."""
    if not path(scenario, directory).is_file():
        return None
    grid = json.loads(path(scenario, directory).read_text(encoding="utf-8"))
    limit = next(s.max_wait_days for s in pathway.steps if s.id == grid["step"])
    without = next(r["wait_days"] for r in grid["runs"] if r["arm"] == "agents" and not r["levers"]["extra_slots"])
    for r in sorted((r for r in grid["runs"] if r["arm"] == "agents" and r["levers"]["extra_slots"]),
                    key=lambda r: r["levers"]["extra_slots"]):
        if r["wait_days"] is not None and r["wait_days"] <= limit:
            k = r["levers"]["extra_slots"]
            change = CapacityChange(facility_id=grid["facility_id"], service=grid["service"],
                                    slots_per_day=grid["base_slots"] + k, from_day=grid["lever_day"])
            return {"run_id": r["run_id"], "extra_slots": k, "wait_days": r["wait_days"], "limit": limit,
                    "facility": grid["facility"], "lever": change, "step": grid["step"],
                    "wait_days_without": without, "base_slots": grid["base_slots"], "months": grid["months"]}
    return None


def _first_wait_alarm(run) -> tuple[str, str, int] | None:
    rows = run.con.execute("""
        SELECT facility_id, step, day FROM alerts
        WHERE level = 'regional' AND facility_id IS NOT NULL ORDER BY day, alert_id LIMIT 1""").fetchall()
    return rows[0] if rows else None


def _summary(run, lever_day: int, service: str, facility: str) -> dict:
    """What the What-if screen shows for one run, on its last day, and its daily ATS KPIs."""
    kpi = run.con.execute(f"""
        SELECT {', '.join(KPI_COLUMNS)} FROM kpi_daily
        WHERE level = 'ats' AND pathway_id = $pw ORDER BY day""", {"pw": run.pathway_id}).fetchall()
    rows = [dict(zip(KPI_COLUMNS, r)) for r in kpi]
    by_day = {r["day"]: r for r in rows}
    step = next(s.id for s in run.state.pathway.steps if s.service == service)
    with tool_cursor(run.con) as cur:  # the same number the Investigator and the Verifier would see (C5)
        ctx = tools.Context(run.run_id, tools.Query(cur), run.day)
        wait = tools.call(ctx, "wait_by_hospital", {"pathway_id": run.pathway_id, "step": step,
                                                    "period_days": PERIOD_DAYS}).get("data", {})
    last = by_day[run.day]
    return {"run_id": run.run_id,
            "readmissions": last["readmissions_30d"] - by_day[lever_day - 1]["readmissions_30d"],
            "readmission_rate_30d": last["readmission_rate_30d"], "on_track_pct": last["on_track_pct"],
            "overdue": last["overdue"], "wait_days": wait.get(facility), "wait_by_facility": wait, "kpi": rows}


def _year_end(run) -> dict:
    """The run's PNE indicator on YEAR_END_DAY (SPEC §5.2): readmissions and index discharges from day 0."""
    (readmissions, rate), = run.con.execute("""
        SELECT readmissions_30d, readmission_rate_30d FROM kpi_daily
        WHERE level = 'ats' AND pathway_id = $pw AND day = $d""", {"pw": run.pathway_id, "d": YEAR_END_DAY}).fetchall()
    return {"day": YEAR_END_DAY, "readmissions_30d": readmissions, "readmission_rate_30d": rate}


def compute(scenario: int, population, runs_dir: Path, directory: Path = WHATIF_DIR) -> dict:
    """The grid of one scenario (see the module docstring), written to `path(scenario, directory)`."""
    from engine.tick import HORIZON_DAYS, Run  # engine.tick reads the grid (proposed_lever), so not at the top

    agents = Run(f"s{scenario}_agents", population, runs_dir, HORIZON_DAYS)
    try:
        while (alarm := _first_wait_alarm(agents)) is None:
            if agents.day >= LAST_ALARM_DAY:
                raise RuntimeError(f"scenario {scenario}: no wait alarm by day {LAST_ALARM_DAY}")
            agents.tick()
        facility_id, step_id, alarm_day = alarm
        lever_day, last_day = alarm_day + 1, alarm_day + PERIOD_DAYS
        service = next(s.service for s in population.pathway.steps if s.id == step_id)
        sim = agents.sim
        row = next(r for r in range(len(sim.res_fac)) if sim.fac_id[sim.res_fac[r]] == facility_id
                   and sim.res_service[r] == service)
        base = int(sim.cap[row, lever_day - sim.first_day])
        facility = agents.con.execute("SELECT name FROM facilities WHERE facility_id = $f",
                                      {"f": facility_id}).fetchall()[0][0]

        def one(arm: str, extra: int) -> dict:
            if arm == "agents" and extra == 0:
                run = agents
            else:
                levers = (CapacityChange(facility_id=facility_id, service=service, slots_per_day=base + extra,
                                         from_day=lever_day),) if extra else ()
                run_id = f"s{scenario}_{arm}" + (f"_{service}+{extra}" if extra else "")
                run = Run(run_id, population, runs_dir, HORIZON_DAYS, levers)
            try:
                run.advance_to(last_day)
                out = {"arm": arm, "levers": Levers(extra_slots=extra).model_dump() if arm == "agents" else None,
                       **_summary(run, lever_day, service, facility)}
                run.advance_to(YEAR_END_DAY)
                return out | {"year_end": _year_end(run)}
            finally:
                if run is not agents:
                    run.close()

        grid = [("baseline", 0)] + [("agents", k) for k in range(1, MAX_EXTRA_SLOTS + 1)]
        with ThreadPoolExecutor(max_workers=len(grid)) as pool:  # runs share nothing they write (SPEC §9)
            futures = [pool.submit(one, arm, k) for arm, k in grid]
            mine = one("agents", 0)
            runs = [f.result() for f in futures]
    finally:
        agents.close()
    out = {"scenario": scenario, "seed": population.seed, "facility_id": facility_id, "facility": facility,
           "service": service, "step": step_id, "alarm_day": alarm_day, "lever_day": lever_day, "last_day": last_day,
           "months": MONTHS, "base_slots": base, "runs": [runs[0], mine, *runs[1:]]}
    directory.mkdir(parents=True, exist_ok=True)
    path(scenario, directory).write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8",
                                         newline="\n")
    return out


def result(scenario: int, levers: Levers, months: int = MONTHS, directory: Path = WHATIF_DIR,
           pathway: Pathway | None = None) -> dict:
    """POST /api/whatif (C27): without CarePath, with CarePath, and with CarePath and the lever, from the grid,
    and with `pathway` the PNE forecast to year end (C35). Raises FileNotFoundError when the grid was not
    computed, ValueError for a lever or a period it lacks."""
    from engine import pne  # engine.pne reads YEAR_END_DAY from here

    if months != MONTHS:
        raise ValueError(f"the grid covers {MONTHS} months")
    grid = json.loads(path(scenario, directory).read_text(encoding="utf-8"))
    runs = {(r["arm"], (r["levers"] or {}).get("extra_slots", 0)): r for r in grid["runs"]}
    if ("agents", levers.extra_slots) not in runs:
        raise ValueError(f"extra_slots is one of 0..{MAX_EXTRA_SLOTS}")
    strip = lambda r: {k: v for k, v in r.items() if k not in ("kpi", "year_end")}
    baseline, agents, lever = runs["baseline", 0], runs["agents", 0], runs["agents", levers.extra_slots]
    return {k: grid[k] for k in ("scenario", "facility_id", "facility", "service", "lever_day", "last_day", "months",
                                 "base_slots")} | {
        "levers": levers.model_dump(), "baseline": strip(baseline), "agents": strip(agents), "lever": strip(lever),
        "avoided_readmissions": baseline["readmissions"] - lever["readmissions"], "precomputed": True} | (
        {"pne": pne.forecast(grid, levers.extra_slots, pathway)} if pathway is not None else {}) | (
        # C39: the euros the avoided readmissions are worth, at the pathway's cost per readmission
        {"saving_eur": (baseline["readmissions"] - lever["readmissions"]) * pathway.readmission_cost.eur,
         "cost": pathway.readmission_cost.model_dump()} if pathway is not None and pathway.readmission_cost else {})


def main(argv: list[str]) -> None:
    from engine.tick import Population

    scenarios = [int(a) for a in argv if a.isdigit()] or [1, 2, 3]
    population = Population()
    with tempfile.TemporaryDirectory() as tmp:
        for n in scenarios:
            out = compute(n, population, Path(tmp))
            print(f"scenario {n}: {out['facility']} {out['service']} from day {out['lever_day']} to "
                  f"{out['last_day']}, base {out['base_slots']} a day", flush=True)
            for r in out["runs"]:
                print(f"  {r['run_id']:<24} readmissions {r['readmissions']:>4}  wait at {out['facility']} "
                      f"{r['wait_days']}  on track {r['on_track_pct']}  PNE on day {r['year_end']['day']} "
                      f"{r['year_end']['readmission_rate_30d']}", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
