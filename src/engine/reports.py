"""Monthly reports on the tick (delivery plan step 2.14, SPEC §9, C36).

On the last day of each simulated month the agents arm's Reporter writes the month's report, after
Intervention, on the run as it is that day; the row goes to `reports` and a `report` message on the stream.
The model's prose is asked only for the reports the demo shows, listed in demo/cache/manifest.json (D17);
every other report is the template filled by code.
"""

import json
from functools import cache
from pathlib import Path

import duckdb

from agents import reporter, tools
from engine.db import tool_cursor
from engine.pathway import Pathway

MANIFEST = Path(__file__).resolve().parents[2] / "demo" / "cache" / "manifest.json"


@cache
def shown() -> frozenset[tuple[int, int]]:
    """(scenario, day) of the reports the demo shows in the model's words."""
    if not MANIFEST.is_file():
        return frozenset()
    scenarios = json.loads(MANIFEST.read_text(encoding="utf-8"))["scenarios"]
    return frozenset((s["scenario"], day) for s in scenarios for day in s.get("report_days", []))


def on_day(con: duckdb.DuckDBPyConnection, run_id: str, pathway: Pathway, day: int, scenario: int) -> list[dict]:
    """The month's report if `day` ends one; returns its stream message."""
    if not reporter.due(day):
        return []
    done = con.execute("SELECT count(*) FROM reports").fetchall()[0][0]
    with tool_cursor(con) as cur:
        r = reporter.report(tools.Context(run_id, tools.Query(cur), day), pathway, day, f"rep_{run_id}_{done + 1}",
                            prose=(scenario, day) in shown() and run_id == f"s{scenario}_agents")
    row = r.row()
    con.execute(f"INSERT INTO reports BY NAME SELECT {', '.join(f'${k} AS {k}' for k in row)}", row)
    return [r.message(scenario)]
