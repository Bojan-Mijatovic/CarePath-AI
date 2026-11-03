"""Real-time tick (SPEC §9, delivery plan step 2.1): the six demo runs, advanced one day at a time.

A Run is one simulator with its run database and state engine, kept open in this process. `Run.tick()`
does the next day in the order of SPEC §9. Intervention through the action service (2.12, 2.13) arrives
with its own plan steps. Until then a tick is steps 1, 2, 3 (Risk), 4 (Monitoring), 5 (kpi_daily,
map_comuni, sankey_flows), 6 (worklist_today, agents arm only), 7 (the Investigator on a regional alarm,
agents arm only, engine.investigations) and 8 (the agents arm's alerts and investigation steps), and the
two arms differ only in the worklist and the investigations.

Demo holds the six runs (3 scenarios × 2 arms) and, per scenario, the agents arm with the lever the
what-if grid proposes (D45, step 2.28; `s<n>_agents_<service>+<k>`): `start()` replays them to the start
day and leaves them paused (D21); afterwards only the runs of the scenario on screen advance (C9). A jump
forward continues; a jump backward rebuilds those runs from the warm-up, which gives the same days again
(AC14). Every method takes the lock, so the API's reads never meet a run being rebuilt.
"""

import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import duckdb

from agents import actions, bed_finder, intervention
from agents.intervention import Intervention
from agents.monitoring import Monitoring
from engine import pathway as pathway_model
from engine import investigations, queries, reports, whatif, worklist
from engine import reveal as reveal_model
from engine.db import RUNS_DIR, create_run, open_run
from engine.risk import HIGH_RISK, RiskModel
from engine.state import StateEngine
from sim import feedback
from sim.population import generate_patients, load_reference
from sim.run import append, load_reference_tables
from sim.step import CapacityChange, Simulator, load_scenario

SEED = 42
START_DAY = 23  # the demo opens on day 23 (D21)
HORIZON_DAYS = 365
PATHWAY_ID = "hf_lombardia_v1"  # the pathway on screen
ARMS = ("agents", "baseline")
SPEEDS = (0, 1, 4)  # pause, ×1 = 1 day per 2 s, ×4 = 2 days per s (SPEC §9)
DEMO_ORDER = (2, 1, 3)  # D44: the demo walks the scenarios in this order, scenario 2 with the full flow


class Population:
    """Reference data, patients and pathway: the same for every run of a seed, so built once."""

    def __init__(self, seed: int = SEED, pathway_id: str = PATHWAY_ID):
        self.seed = seed
        self.ref = load_reference()
        self.patients, self.mmg = generate_patients(seed, self.ref)
        self.pathway = pathway_model.load(pathway_id)


class Run:
    def __init__(self, run_id: str, population: Population, runs_dir: Path = RUNS_DIR, days: int = HORIZON_DAYS,
                 levers: tuple[CapacityChange, ...] = (), proposal: dict | None = None):
        """`levers` are capacity changes on top of the scenario (what-if, step 2.5): before their first day
        the run is the same as without them, day by day, since every random draw is per day (AC14).
        `proposal` is the lever Intervention proposes on the wait alarm (`whatif.proposed_lever`, step 2.27);
        it changes no event of the run, only its actions."""
        p = population
        self.run_id, self.scenario = run_id, int(run_id[1])
        self.agents = run_id.split("_")[1] == "agents"
        self.pathway_id = p.pathway.pathway_id
        self.sim = Simulator(p.seed, p.patients, p.ref, p.pathway, days=days)
        self.sim.apply_scenario(load_scenario(self.scenario), p.mmg)
        self.sim.apply_capacity(list(levers))
        create_run(run_id, runs_dir=runs_dir, overwrite=True)
        self.con = open_run(run_id, runs_dir)
        load_reference_tables(self.con, p.ref, p.patients, p.mmg)
        append(self.con, "bed_occupancy", self.sim.bed_occupancy())  # once, not per tick (C42)
        for events in self.sim.warm_up():
            append(self.con, "events", events)
        self.state = StateEngine(self.con, p.pathway)
        self.risk = RiskModel(p.pathway)
        self.monitoring = Monitoring(p.pathway, run_id, dict(self.con.execute("SELECT name, facility_id FROM facilities").fetchall()))
        names = dict(self.con.execute("SELECT facility_id, name FROM facilities").fetchall())
        self.intervention = Intervention(p.pathway, run_id, names, len(p.patients), proposal)
        feedback.register(run_id, self.sim)
        self.day = -1  # the last day done
        self.last_ms = 0.0
        self.capacity = None  # slots_total and slots_booked as last written

    def tick(self) -> list[dict]:
        """Day `self.day + 1`, SPEC §9 steps 1–8. Returns the day's alert and investigation messages (the
        agents arm's are pushed)."""
        t = time.perf_counter()
        d = self.day + 1
        append(self.con, "events", self.sim.step(d))  # 1
        self.state.update(self.con, d)                  # 2
        self.risk.update(self.con, self.state, d)       # 3
        messages = self.monitoring.run(self.con, self.state, self.risk, d, self.scenario)  # 4
        self.state.refresh_kpi(self.con, d)             # 5: views (sankey_flows is a DuckDB view)
        self.state.refresh_map(self.con, d, self.risk.risk, HIGH_RISK)
        if self.agents:                                 # 6: the baseline arm is without CarePath
            worklist.refresh(self.con, self.state, self.risk, d, self.monitoring.fired)
        self._write_capacity()
        if self.agents:  # 7: after capacity_slots, so the Investigator's tools see the alarm's day (C25)
            messages += investigations.on_alarms(self.con, self.run_id, self.state.pathway, d, self.scenario, messages)
            # 8: Intervention after the investigation: the alarm is explained on the day as it was, then agents
            # act (D53), and the cached investigation keeps its inputs
            rows = self.intervention.run(self.con, self.state, self.risk.risk, self.monitoring, d, self.feedback)
            if any(r["type"] == "reschedule" and r["status"] == "executed" for r in rows):
                self._write_capacity()
            worklist.record_outcomes(self.con, d)  # the calls just made, on the day's list (C20)
            shown = sorted(rows, key=lambda r: (intervention.PRIORITY.get(r["type"], 9), -self._risk_of(r)))
            messages += [{"type": "action", "scenario": self.scenario, "day": d, "payload": r}
                         for r in shown[:intervention.STREAM_ACTIONS] if r["status"] != "rejected"]
            # the month's report on its last day, after the agents acted (step 2.14, C36)
            messages += reports.on_day(self.con, self.run_id, self.state.pathway, d, self.scenario)
        self.day = d
        self.last_ms = (time.perf_counter() - t) * 1000
        return messages

    def _write_capacity(self) -> None:
        """capacity_slots, which free_slots reads (SPEC §6). Rewriting all 18,585 rows took 70 ms a day and
        up to 400 ms, so only the rows whose slots changed since the last tick are written."""
        slots = self.sim.capacity_slots()
        now = slots[["slots_total", "slots_booked"]].to_numpy()
        if self.capacity is None:
            append(self.con, "capacity_slots", slots)
        else:
            changed = slots[(now != self.capacity).any(axis=1)]
            if len(changed):
                self.con.register("src", changed)
                self.con.execute("INSERT OR REPLACE INTO capacity_slots SELECT * FROM src")
                self.con.unregister("src")
        self.capacity = now

    def _risk_of(self, row: dict) -> float:
        """A patient action's risk score, so the stream shows the riskiest first; 0 for an action on a scope."""
        if row["patient_id"] is None:
            return 0.0
        return float(self.risk.risk[self.state.ids.get_loc(row["patient_id"])])

    def feedback(self, rows: list[dict]) -> None:
        """The action service's `emit` (SPEC §7.3, §9): executed actions become events of the day, and
        their effects start the next day, through the simulator's feedback hook."""
        if rows:
            append(self.con, "events", feedback.apply(self.run_id, rows))

    def advance_to(self, day: int) -> None:
        while self.day < day:
            self.tick()

    def close(self) -> None:
        feedback.unregister(self.run_id)
        self.con.close()


class Demo:
    def __init__(self, runs_dir: Path = RUNS_DIR, scenarios: tuple[int, ...] = (1, 2, 3), start_day: int = START_DAY,
                 days: int = HORIZON_DAYS, seed: int = SEED, whatif_dir: Path | None = whatif.WHATIF_DIR,
                 lever_runs: bool = True):
        """`whatif_dir` holds the grids the proposed levers and lever runs come from; None leaves both out.
        `lever_runs=False` keeps the proposals but builds no lever run (the cache warm-up, step 2.11)."""
        self.runs_dir, self.scenarios, self.start_day, self.days, self.seed = runs_dir, scenarios, start_day, days, seed
        self.whatif_dir, self.with_lever_runs = whatif_dir, lever_runs
        self.lock = threading.RLock()
        self.population: Population | None = None
        self.runs: dict[str, Run] = {}
        self.levers: dict[int, dict] = {}  # scenario -> whatif.proposed_lever(...)
        self.approved: set[int] = set()  # scenarios whose capacity proposal the manager approved (C34)
        self.scenario = next((n for n in DEMO_ORDER if n in scenarios), scenarios[0])  # the first on screen (D44)
        self.speed = 0
        self.ready = False
        # Runs share nothing they write (own database, simulator, engine and model), and DuckDB, numpy and
        # XGBoost release the GIL, so the runs of a scenario advance in parallel threads (SPEC §9 budget).
        self.pool = ThreadPoolExecutor(max_workers=len(scenarios) * (len(ARMS) + 1))

    def run_ids(self, scenario: int) -> list[str]:
        lever = self.levers.get(scenario)
        return [f"s{scenario}_{arm}" for arm in ARMS] + ([lever["run_id"]] if lever and self.with_lever_runs else [])

    def lever_run(self) -> Run | None:
        lever = self.levers.get(self.scenario)
        return self.runs.get(lever["run_id"]) if lever else None

    def catch_up(self) -> bool:
        """One day of the lever run of the scenario on screen if it is behind; True if it did one. The clock
        calls it while paused, so at ×4, where three runs do not fit the 500 ms budget (step 2.28: both-arms
        p95 646–662 ms with it), the lever run falls behind and catches up during the next pause (D21)."""
        with self.lock:
            run = self.lever_run()
            if run is None or run.day >= self.day:
                return False
            run.tick()
            return True

    def _parallel(self, work: Callable[[str], object], run_ids: list[str]) -> dict[str, object]:
        futures = {run_id: self.pool.submit(work, run_id) for run_id in run_ids}
        return {run_id: f.result() for run_id, f in futures.items()}  # raises the first failure

    def _build(self, run_id: str, day: int) -> None:
        old = self.runs.pop(run_id, None)
        if old is not None:
            old.close()
        scenario = int(run_id[1])
        lever = self.levers.get(scenario)
        levers = (lever["lever"],) if lever and lever["run_id"] == run_id else ()
        # The agents arm proposes the lever on its alarm day, and so does the lever run, which stays the agents
        # run action for action until the lever (C28)
        agents = run_id != f"s{scenario}_baseline"
        if run_id == f"s{scenario}_agents":
            self.approved.discard(scenario)  # a rebuilt run starts from the defaults (C9, D51)
        run = Run(run_id, self.population, self.runs_dir, self.days, levers, lever if agents else None)
        run.advance_to(day)
        self.runs[run_id] = run

    def start(self) -> None:
        """All runs to the start day, paused, on the opening scenario (D44). Also what POST /api/sim/reset does: a
        reset after scenario 3 had left scenario 3 on screen, so a rehearsal started from the wrong one."""
        with self.lock:
            self.ready, self.speed = False, 0
            self.scenario = next((n for n in DEMO_ORDER if n in self.scenarios), self.scenarios[0])
            if self.population is None:
                self.population = Population(self.seed)
            if self.whatif_dir is not None:
                self.levers = {n: lever for n in self.scenarios
                               if (lever := whatif.proposed_lever(n, self.population.pathway, self.whatif_dir))}
            self._parallel(lambda run_id: self._build(run_id, self.start_day),
                           [run_id for n in self.scenarios for run_id in self.run_ids(n)])
            self.ready = True

    @property
    def day(self) -> int:
        # Under the lock: a jump back takes the scenario's runs out while it rebuilds them, and the API's status
        # read in between found no run (KeyError and a 500, 3 Nov 2026); now it waits for the rebuild
        with self.lock:
            return self.runs[f"s{self.scenario}_agents"].day

    def choose(self, scenario: int) -> None:
        if scenario not in self.scenarios:
            raise ValueError(f"scenario is one of {self.scenarios}")
        with self.lock:
            self.scenario = scenario

    def set_speed(self, factor: int) -> None:
        if factor not in SPEEDS:
            raise ValueError(f"speed is one of {SPEEDS}")
        self.speed = factor

    def advance(self) -> list[dict]:
        """The next day for the two runs on screen. Returns the WebSocket messages of that day."""
        with self.lock:
            if self.day + 1 >= self.days:
                self.speed = 0
                return []
            ids = [f"s{self.scenario}_{arm}" for arm in ARMS]
            lever = self.lever_run()  # at ×1 it keeps up; at ×4, or once behind, it waits for catch_up
            if lever is not None and self.speed == 1 and lever.day == self.day:
                ids.append(lever.run_id)
            messages = self._parallel(lambda run_id: self.runs[run_id].tick(), ids)
            shown = messages[self.default_run()]  # the screen shows the agents arm
            if self.speed == 1 and any(m["type"] == "alert" and m["payload"]["level"] == "regional"
                                       and m["payload"]["facility_id"] for m in shown):
                # Demo step 4 (D21): at ×1 the clock stops on the day a wait alarm opens, so the demo is on the
                # day its answers were prepared for (C41); a human pause landed a day late in 6 of 10 dry runs
                self.speed = 0
            return [self.tick_message()] + shown

    def jump(self, day: int) -> list[dict]:
        if not 0 <= day < self.days:
            raise ValueError(f"day is between 0 and {self.days - 1}")

        def go(run_id: str) -> None:
            if day < self.runs[run_id].day:
                self._build(run_id, day)  # replay from the warm-up (C9)
            else:
                self.runs[run_id].advance_to(day)

        with self.lock:
            self._parallel(go, self.run_ids(self.scenario))
            return [self.tick_message()]

    def ask(self, question: str) -> tuple[dict, list[dict]]:
        """POST /api/ask: an operator's question to the agents arm of the scenario on screen, on its day."""
        with self.lock:
            run = self.runs[self.default_run()]
            return investigations.on_question(run.con, run.run_id, run.state.pathway, run.day, self.scenario, question)

    def reveal(self, scenario: int) -> dict:
        """GET /api/reveal/{scenario}: the agents arm's own alarms next to scenario_truth (Rivelazione, C37)."""
        if scenario not in self.scenarios:
            raise ValueError(f"scenario is one of {self.scenarios}")
        with self.lock, self.runs[f"s{scenario}_agents"].con.cursor() as cur:
            return reveal_model.reveal(cur, self.population.pathway, scenario)

    def autonomy(self) -> dict[str, dict]:
        """GET /api/settings: per action type the level in force on the scenario on screen, its default, and
        whether it is fixed (SPEC §7.2)."""
        with self.lock:
            return actions.settings(self.runs[self.default_run()].con)

    def set_autonomy(self, action_type: str, level: int) -> None:
        """PUT /api/settings/autonomy: the manager's level holds for the ATS, so it is logged in every agents
        run of the demo on its day. A run built again after a jump back starts from the defaults, as on reset.
        Bed Finder serves the hospitals in both arms (C42), so its level goes to the baseline runs too."""
        with self.lock:
            for run in self.runs.values():
                if run.agents or action_type == bed_finder.ACTION:
                    actions.set_level(run.con, run.day, action_type, level)

    def _run_of(self, action_id: str) -> Run:
        """The run an action belongs to, from its id (`act_<run_id>_<n>`, SPEC §7.3); the agents arm on screen
        for an id of no run of the demo, where it is then not found."""
        return self.runs.get(action_id.removeprefix("act_").rpartition("_")[0]) or self.runs[self.default_run()]

    def decide(self, action_id: str, decision: str) -> list[dict]:
        """POST /api/actions/{id}/approve, /reject or /undo, in the action's own run: the agents arm, or a
        baseline run for a bed (C42). A bed is the doctor's decision, every other action the manager's.
        Returns the `action` message of the changed action (SPEC §10)."""
        with self.lock:
            run = self._run_of(action_id)
            kind = run.con.execute("SELECT type FROM actions WHERE action_id = $id", {"id": action_id}).fetchall()
            actor = bed_finder.DOCTOR if kind and kind[0][0] == bed_finder.ACTION else actions.MANAGER
            if decision == "undo":
                row = actions.undo(run.con, run.day, action_id, actor)
            else:
                row = actions.decide(run.con, run.day, action_id, decision == "approve", run.feedback, actor)
                if row["type"] == "capacity_proposal" and row["status"] == "executed":
                    self.approved.add(run.scenario)  # the console turns to the lever run (D45, C34)
            return [{"type": "action", "scenario": run.scenario, "day": run.day, "payload": row},
                    *([self.tick_message()] if row["type"] == "capacity_proposal" else [])]

    def admit(self, run_id: str, patient_id: str, day: int | None = None, diagnosis: str | None = None,
              facility_id: str | None = None, choice: int = 0) -> tuple[dict, list[dict]]:
        """POST /api/admissions (C42): Bed Finder for a patient a doctor admits in `run_id` on `day` (today by
        default). Without a diagnosis and an emergency department, they are the patient's ADMISSION of that day
        in the run, as Maria's on day 47 without CarePath (demo step 9c). Returns the result and its `action`
        message. KeyError for a run of no scenario, ValueError for a bad request."""
        with self.lock:
            run = self.runs[run_id]
            day = run.day if day is None else day
            if not 0 <= day <= run.day:
                raise ValueError(f"day is between 0 and {run.day}, the run's today")
            if not run.con.execute("SELECT count(*) FROM patients WHERE patient_id = $p", {"p": patient_id}).fetchall()[0][0]:
                raise ValueError(f"no patient {patient_id} in {run_id}")
            if diagnosis is None or facility_id is None:
                found = run.con.execute("""SELECT code, facility_id FROM events WHERE patient_id = $p AND day = $d
                                           AND event_type = 'ADMISSION'""", {"p": patient_id, "d": day}).fetchall()
                if not found:
                    raise ValueError(f"{patient_id} has no admission on day {day}: give the diagnosis and the facility")
                diagnosis, facility_id = diagnosis or found[0][0], facility_id or found[0][1]
            result = bed_finder.admit(run.con, run_id, run.state.pathway, day, patient_id, diagnosis, facility_id, choice)
            admission = {"run_id": run_id, "patient_id": patient_id, "day": day, "facility_id": facility_id}
            message = ([{"type": "action", "scenario": run.scenario, "day": run.day, "payload": result["action"]}]
                       if result["action"] else [])
            return {"admission": admission} | result, message

    def tick_message(self) -> dict:
        """SPEC §10 `tick` for the scenario on screen; `kpi` is the agents arm's."""
        with self.lock:
            run = self.runs[f"s{self.scenario}_agents"]
            with run.con.cursor() as cur:
                kpi = queries.kpi_headline(cur, run.day, run.pathway_id)
            payload = {"speed": self.speed, "kpi": kpi}
            if (lever := self.lever_run()) is not None:  # C28: the console shows whether it has caught up
                payload["lever_run"] = {"run_id": lever.run_id, "day": lever.day,
                                        "approved": self.scenario in self.approved}  # C34
            return {"type": "tick", "scenario": self.scenario, "day": run.day, "payload": payload}

    def default_run(self) -> str:
        return f"s{self.scenario}_agents"  # SPEC §10: the scenario on screen, agents arm

    def read(self, run_id: str, query: Callable[[duckdb.DuckDBPyConnection], object]):
        """`query` on a cursor of the run's connection. KeyError if the run is not one of the demo's."""
        with self.lock, self.runs[run_id].con.cursor() as cur:
            return query(cur)

    def close(self) -> None:
        with self.lock:
            for run in self.runs.values():
                run.close()
            self.runs.clear()
            self.ready = False
        self.pool.shutdown()
