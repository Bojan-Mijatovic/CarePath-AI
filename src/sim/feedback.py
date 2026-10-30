"""Action feedback hook: actions executed on day D become simulation events (delivery plan step 1.20).

The action service (step 2.12) calls `apply(run_id, actions)` once a day with the rows of SPEC §7.1 it
executed that day. The returned events record the actions themselves on day D (CALL, REMINDER, and the
BOOKING of a reschedule) and go into `events` like the simulator's own; their effects appear from day D + 1
through `Simulator.step`, with the chances of `effects` in the simulator config (step 2.13).

The process that runs the simulation registers each run's Simulator under its run id.
"""

import pandas as pd

from engine.db import ACTION_TYPES
from sim.step import EVENT_COLUMNS, Simulator

REQUIRED = ["action_id", "type", "patient_id", "executed_day"]
_runs: dict[str, Simulator] = {}


def register(run_id: str, sim: Simulator) -> None:
    _runs[run_id] = sim


def unregister(run_id: str) -> None:
    _runs.pop(run_id, None)


def apply(run_id: str, actions: pd.DataFrame | list[dict]) -> pd.DataFrame:
    """Events (SPEC §3.1 columns) recording the actions executed today in `run_id`."""
    if run_id not in _runs:
        raise KeyError(f"run {run_id} is not registered")
    actions = pd.DataFrame(actions)
    missing = [c for c in REQUIRED if c not in actions.columns]
    if missing:
        raise ValueError(f"actions need the columns {missing} (SPEC §7.1)")
    unknown = set(actions.type) - set(ACTION_TYPES)
    if unknown:
        raise ValueError(f"unknown action types {sorted(unknown)}")
    days = set(actions.executed_day)
    if len(days) > 1:
        raise ValueError(f"apply one day at a time, got executed_day {sorted(days)}")
    if not days:
        return pd.DataFrame(columns=EVENT_COLUMNS)
    return _runs[run_id].apply_actions(int(days.pop()), actions)
