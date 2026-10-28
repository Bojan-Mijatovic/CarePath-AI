"""Run the simulator for one run into its DuckDB file and report the time per simulated day.

Delivery plan steps 1.15, 1.17 and 1.22. The scenario comes from the run id (s2_baseline → scenarios/2.json).
From day 0 the state engine fills pathway_state and kpi_daily after each day. This is the batch run for
measuring; the demo advances its runs with engine.tick (step 2.1).

    uv run carepath-sim s2_baseline [--days 365] [--seed 42] [--overwrite]
"""

import argparse
import time

import duckdb
import numpy as np
import pandas as pd

from engine import pathway as pathway_model
from engine.db import RUNS_DIR, create_run, open_run
from engine.risk import HIGH_RISK, RiskModel
from engine.state import StateEngine
from sim.population import generate_patients, load_reference
from sim.step import Simulator, load_scenario

PATHWAY_ID = "hf_lombardia_v1"


def load_reference_tables(con: duckdb.DuckDBPyConnection, ref: dict, patients: pd.DataFrame, mmg: pd.DataFrame) -> None:
    for table, df in [("comuni", ref["comuni"]), ("mmg", mmg), ("facilities", ref["facilities"]),
                      ("patients", patients)]:
        con.register("src", df)
        con.execute(f"INSERT INTO {table} BY NAME SELECT * FROM src")
        con.unregister("src")


def append(con: duckdb.DuckDBPyConnection, table: str, df: pd.DataFrame) -> None:
    if len(df):
        con.register("src", df)
        con.execute(f"INSERT INTO {table} SELECT * FROM src")
        con.unregister("src")


def run(run_id: str, days: int = 365, seed: int = 42, overwrite: bool = False, runs_dir=RUNS_DIR) -> dict[str, float]:
    ref = load_reference()
    patients, mmg = generate_patients(seed, ref)
    create_run(run_id, runs_dir=runs_dir, overwrite=overwrite)  # validates the run id first
    sim = Simulator(seed, patients, ref, pathway_model.load(PATHWAY_ID), days=days)
    sim.apply_scenario(load_scenario(int(run_id[1])), mmg)
    sim_ms, write_ms, state_ms = [], [], []
    with open_run(run_id, runs_dir) as con:
        load_reference_tables(con, ref, patients, mmg)
        state = StateEngine(con, sim.pathway)
        risk = RiskModel(sim.pathway)
        for d in range(sim.first_day, days):
            t0 = time.perf_counter()
            events = sim.step(d)
            t1 = time.perf_counter()
            append(con, "events", events)
            t2 = time.perf_counter()
            if d >= 0:  # the first update reads the warm-up as history
                state.update(con, d)
                risk.update(con, state, d)
                state.refresh_kpi(con, d)
                state.refresh_map(con, d, risk.risk, HIGH_RISK)
                sim_ms.append((t1 - t0) * 1000)
                write_ms.append((t2 - t1) * 1000)
                state_ms.append((time.perf_counter() - t2) * 1000)
        append(con, "capacity_slots", sim.capacity_slots())
        n_events = con.execute("SELECT count(*) FROM events WHERE day >= 0").fetchone()[0]
    return {"sim_ms_mean": float(np.mean(sim_ms)), "sim_ms_p95": float(np.percentile(sim_ms, 95)),
            "write_ms_mean": float(np.mean(write_ms)), "write_ms_p95": float(np.percentile(write_ms, 95)),
            "state_ms_mean": float(np.mean(state_ms[1:] or state_ms)), "state_ms_p95": float(np.percentile(state_ms, 95)),
            "state_ms_first": state_ms[0], "events_per_day": n_events / days}


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate one run (delivery plan, step 1.15).")
    parser.add_argument("run_id", help="for example s2_baseline")
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    t = time.perf_counter()
    stats = run(args.run_id, args.days, args.seed, args.overwrite)
    print(f"{args.run_id}: {args.days} days in {time.perf_counter() - t:.1f} s, {stats['events_per_day']:.0f} events/day")
    print(f"  simulate: {stats['sim_ms_mean']:.1f} ms/day (p95 {stats['sim_ms_p95']:.1f})")
    print(f"  write:    {stats['write_ms_mean']:.1f} ms/day (p95 {stats['write_ms_p95']:.1f})")
    print(f"  state:    {stats['state_ms_mean']:.1f} ms/day (p95 {stats['state_ms_p95']:.1f}; "
          f"day 0 with history {stats['state_ms_first']:.0f} ms)")


if __name__ == "__main__":
    main()
