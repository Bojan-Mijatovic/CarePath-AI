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

from agents import actions
from agents.monitoring import Monitoring
from engine import pathway as pathway_model
from engine import investigations, queries, whatif, worklist
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


class Population:
    """Reference data, patients and pathway: the same for every run of a seed, so built once."""

    def __init__(self, seed: int = SEED, pathway_id: str = PATHWAY_ID):
        self.seed = seed
        self.ref = load_reference()
        self.patients, self.mmg = generate_patients(seed, self.ref)
        self.pathway = pathway_model.load(pathway_id)


class Run:
    def __init__(self, run_id: str, population: Population, runs_dir: Path = RUNS_DIR, days: int = HORIZON_DAYS,
                 levers: tuple[CapacityChange, ...] = ()):
        """`levers` are capacity changes on top of the scenario (what-if, step 2.5): before their first day
        the run is the same as without them, day by day, since every random draw is per day (AC14)."""
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
        for events in self.sim.warm_up():
            append(self.con, "events", events)
        self.state = StateEngine(self.con, p.pathway)
        self.risk = RiskModel(p.pathway)
        self.monitoring = Monitoring(p.pathway, run_id, dict(self.con.execute("SELECT name, facility_id FROM facilities").fetchall()))
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

    def feedback(self, rows: list[dict]) -> None:
        """The action service's `emit` (SPEC §7.3, §9): executed actions on a patient become events of the
        day through the simulator's feedback hook; an action on a scope has its effects with step 2.13."""
        on_patients = [r for r in rows if r["patient_id"] is not None]
        if on_patients:
            append(self.con, "events", feedback.apply(self.run_id, on_patients))

    def advance_to(self, day: int) -> None:
        while self.day < day:
            self.tick()

    def close(self) -> None:
        feedback.unregister(self.run_id)
        self.con.close()


class Demo:
    def __init__(self, runs_dir: Path = RUNS_DIR, scenarios: tuple[int, ...] = (1, 2, 3), start_day: int = START_DAY,
                 days: int = HORIZON_DAYS, seed: int = SEED, whatif_dir: Path | None = whatif.WHATIF_DIR):
        """`whatif_dir` holds the grids the lever runs come from; None leaves them out."""
        self.runs_dir, self.scenarios, self.start_day, self.days, self.seed = runs_dir, scenarios, start_day, days, seed
        self.whatif_dir = whatif_dir
        self.lock = threading.RLock()
        self.population: Population | None = None
        self.runs: dict[str, Run] = {}
        self.levers: dict[int, dict] = {}  # scenario -> whatif.proposed_lever(...)
        self.scenario = scenarios[0]
        self.speed = 0
        self.ready = False
        # Runs share nothing they write (own database, simulator, engine and model), and DuckDB, numpy and
        # XGBoost release the GIL, so the runs of a scenario advance in parallel threads (SPEC §9 budget).
        self.pool = ThreadPoolExecutor(max_workers=len(scenarios) * (len(ARMS) + 1))

    def run_ids(self, scenario: int) -> list[str]:
        lever = self.levers.get(scenario)
        return [f"s{scenario}_{arm}" for arm in ARMS] + ([lever["run_id"]] if lever else [])

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
        lever = self.levers.get(int(run_id[1]))
        levers = (lever["lever"],) if lever and lever["run_id"] == run_id else ()
        run = Run(run_id, self.population, self.runs_dir, self.days, levers)
        run.advance_to(day)
        self.runs[run_id] = run

    def start(self) -> None:
        """All runs to the start day, paused. Also what POST /api/sim/reset does."""
        with self.lock:
            self.ready, self.speed = False, 0
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
            return [self.tick_message()] + messages[self.default_run()]  # the screen shows the agents arm

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

    def autonomy(self) -> dict[str, dict]:
        """GET /api/settings: per action type the level in force on the scenario on screen, its default, and
        whether it is fixed (SPEC §7.2)."""
        with self.lock:
            return actions.settings(self.runs[self.default_run()].con)

    def set_autonomy(self, action_type: str, level: int) -> None:
        """PUT /api/settings/autonomy: the manager's level holds for the ATS, so it is logged in every agents
        run of the demo on its day. A run built again after a jump back starts from the defaults, as on reset."""
        with self.lock:
            for run in self.runs.values():
                if run.agents:
                    actions.set_level(run.con, run.day, action_type, level)

    def decide(self, action_id: str, decision: str) -> list[dict]:
        """POST /api/actions/{id}/approve, /reject or /undo, on the agents arm of the scenario on screen.
        Returns the `action` message of the changed action (SPEC §10)."""
        with self.lock:
            run = self.runs[self.default_run()]
            if decision == "undo":
                row = actions.undo(run.con, run.day, action_id)
            else:
                row = actions.decide(run.con, run.day, action_id, decision == "approve", run.feedback)
            return [{"type": "action", "scenario": self.scenario, "day": run.day, "payload": row}]

    def tick_message(self) -> dict:
        """SPEC §10 `tick` for the scenario on screen; `kpi` is the agents arm's."""
        with self.lock:
            run = self.runs[f"s{self.scenario}_agents"]
            with run.con.cursor() as cur:
                kpi = queries.kpi_headline(cur, run.day, run.pathway_id)
            payload = {"speed": self.speed, "kpi": kpi}
            if (lever := self.lever_run()) is not None:  # C28: the console shows whether it has caught up
                payload["lever_run"] = {"run_id": lever.run_id, "day": lever.day}
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
