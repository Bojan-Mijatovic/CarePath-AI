"""Real-time tick (SPEC §9, delivery plan step 2.1): the six demo runs, advanced one day at a time.

A Run is one simulator with its run database and state engine, kept open in this process. `Run.tick()`
does the next day in the order of SPEC §9. Steps 4 to 7 of that order arrive with their own plan steps:
Monitoring (2.8), the worklist (2.4), Intervention through the action service (2.12, 2.13) and the
Investigator (2.9). Until then a tick is steps 1, 2, 3 (Risk), 5 (kpi_daily, map_comuni, sankey_flows) and
8, and the two arms of a scenario do not differ.

Demo holds the six runs (3 scenarios × 2 arms): `start()` replays them to the start day and leaves them
paused (D21); afterwards only the two runs of the scenario on screen advance (C9). A jump forward
continues; a jump backward rebuilds those two runs from the warm-up, which gives the same days again
(AC14). Every method takes the lock, so the API's reads never meet a run being rebuilt.
"""

import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import duckdb

from engine import pathway as pathway_model
from engine import queries
from engine.db import RUNS_DIR, create_run, open_run
from engine.risk import HIGH_RISK, RiskModel
from engine.state import StateEngine
from sim import feedback
from sim.population import generate_patients, load_reference
from sim.run import append, load_reference_tables
from sim.step import Simulator, load_scenario

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
    def __init__(self, run_id: str, population: Population, runs_dir: Path = RUNS_DIR, days: int = HORIZON_DAYS):
        p = population
        self.run_id, self.scenario = run_id, int(run_id[1])
        self.pathway_id = p.pathway.pathway_id
        self.sim = Simulator(p.seed, p.patients, p.ref, p.pathway, days=days)
        self.sim.apply_scenario(load_scenario(self.scenario), p.mmg)
        create_run(run_id, runs_dir=runs_dir, overwrite=True)
        self.con = open_run(run_id, runs_dir)
        load_reference_tables(self.con, p.ref, p.patients, p.mmg)
        for events in self.sim.warm_up():
            append(self.con, "events", events)
        self.state = StateEngine(self.con, p.pathway)
        self.risk = RiskModel(p.pathway)
        feedback.register(run_id, self.sim)
        self.day = -1  # the last day done
        self.last_ms = 0.0
        self.capacity = None  # slots_total and slots_booked as last written

    def tick(self) -> int:
        """Day `self.day + 1`, SPEC §9 steps 1–8. Returns the day."""
        t = time.perf_counter()
        d = self.day + 1
        append(self.con, "events", self.sim.step(d))  # 1
        self.state.update(self.con, d)                  # 2
        self.risk.update(self.con, self.state, d)       # 3
        self.state.refresh_kpi(self.con, d)             # 5: views (sankey_flows is a DuckDB view)
        self.state.refresh_map(self.con, d, self.risk.risk, HIGH_RISK)
        self._write_capacity()
        self.day = d
        self.last_ms = (time.perf_counter() - t) * 1000
        return d

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

    def advance_to(self, day: int) -> None:
        while self.day < day:
            self.tick()

    def close(self) -> None:
        feedback.unregister(self.run_id)
        self.con.close()


class Demo:
    def __init__(self, runs_dir: Path = RUNS_DIR, scenarios: tuple[int, ...] = (1, 2, 3), start_day: int = START_DAY,
                 days: int = HORIZON_DAYS, seed: int = SEED):
        self.runs_dir, self.scenarios, self.start_day, self.days, self.seed = runs_dir, scenarios, start_day, days, seed
        self.lock = threading.RLock()
        self.population: Population | None = None
        self.runs: dict[str, Run] = {}
        self.scenario = scenarios[0]
        self.speed = 0
        self.ready = False
        # Runs share nothing they write (own database, simulator, engine and model), and DuckDB, numpy and
        # XGBoost release the GIL, so the runs of a scenario advance in parallel threads (SPEC §9 budget).
        self.pool = ThreadPoolExecutor(max_workers=len(scenarios) * len(ARMS))

    def run_ids(self, scenario: int) -> list[str]:
        return [f"s{scenario}_{arm}" for arm in ARMS]

    def _parallel(self, work: Callable[[str], object], run_ids: list[str]) -> None:
        for future in [self.pool.submit(work, run_id) for run_id in run_ids]:
            future.result()  # raises the first failure

    def _build(self, run_id: str, day: int) -> None:
        old = self.runs.pop(run_id, None)
        if old is not None:
            old.close()
        run = Run(run_id, self.population, self.runs_dir, self.days)
        run.advance_to(day)
        self.runs[run_id] = run

    def start(self) -> None:
        """All runs to the start day, paused. Also what POST /api/sim/reset does."""
        with self.lock:
            self.ready, self.speed = False, 0
            if self.population is None:
                self.population = Population(self.seed)
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
            self._parallel(lambda run_id: self.runs[run_id].tick(), self.run_ids(self.scenario))
            return [self.tick_message()]

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

    def tick_message(self) -> dict:
        """SPEC §10 `tick` for the scenario on screen; `kpi` is the agents arm's."""
        with self.lock:
            run = self.runs[f"s{self.scenario}_agents"]
            with run.con.cursor() as cur:
                kpi = queries.kpi_headline(cur, run.day, run.pathway_id)
            return {"type": "tick", "scenario": self.scenario, "day": run.day, "payload": {"speed": self.speed, "kpi": kpi}}

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
