"""Investigations on the tick (SPEC §9 step 7, C25; delivery plan step 2.17).

When Monitoring opens a regional alarm on the agents arm, the Investigator looks for its cause on the same
tick, after capacity_slots is written: its tools must see the run as it is on the alarm's day, or their
results, and so the cache keys (SPEC §8), would differ. From the cache that takes well under a second
(D14); a live run (warm-up) holds the tick for minutes. The row goes to `investigations`, the alarm gets its
investigation_id, in the table and in its stream message, and the steps go on the stream.

A model that gives no answer (a cache miss in cache_only, a timeout) leaves the alarm without an
investigation; it is logged and the tick goes on, so the demo never stops on it (AC9). The cache
completeness check (SPEC §8, C10) is what keeps that from happening in the demo.
"""

import json
import logging

import duckdb

from agents import investigator, llm, tools
from engine.db import tool_cursor
from engine.pathway import Pathway

log = logging.getLogger("carepath.investigations")


def on_question(con: duckdb.DuckDBPyConnection, run_id: str, pathway: Pathway, day: int, scenario: int,
                question: str) -> tuple[dict, list[dict]]:
    """An operator's question (POST /api/ask, Chiedi) on the run as it is on `day`: the stored row and the
    investigation's stream messages. Raises llm.LLMUnavailable when the model gives no answer (a cache
    miss in cache_only): the caller says so, there is no template (Solution Plan §8)."""
    facilities = con.execute("SELECT name, type, asst_id FROM facilities ORDER BY facility_id").fetchall()
    done = con.execute("SELECT count(*) FROM investigations").fetchall()[0][0]
    with tool_cursor(con) as cur:
        ctx = tools.Context(run_id, tools.Query(cur), day)
        inv = investigator.ask(ctx, pathway, day, {"it": question, "en": question}, f"inv_{run_id}_{done + 1}",
                               facilities)
    row = inv.row()
    con.execute(f"INSERT INTO investigations BY NAME SELECT {', '.join(f'${k} AS {k}' for k in row)}", row)
    return row, inv.messages(scenario)


def on_alarms(con: duckdb.DuckDBPyConnection, run_id: str, pathway: Pathway, day: int, scenario: int,
              messages: list[dict]) -> list[dict]:
    """Investigates the regional alarms opened on `day`; sets investigation_id on their messages in
    `messages` and returns the investigation messages."""
    alarms = con.execute("""
        SELECT alert_id, step, group_alarm, text FROM alerts
        WHERE level = 'regional' AND day = $d AND pathway_id = $pw AND investigation_id IS NULL ORDER BY alert_id""",
                         {"d": day, "pw": pathway.pathway_id}).fetchall()
    if not alarms:
        return []
    facilities = con.execute("SELECT name, type, asst_id FROM facilities ORDER BY facility_id").fetchall()
    done = con.execute("SELECT count(*) FROM investigations").fetchall()[0][0]  # fetchone() leaves the result open
    out = []
    for alert_id, step, group_alarm, text in alarms:
        investigation_id = f"inv_{run_id}_{done + 1}"  # counted when stored: a miss must not reuse an id later
        try:
            with tool_cursor(con) as cur:
                ctx = tools.Context(run_id, tools.Query(cur), day)
                inv = investigator.investigate(ctx, pathway, day, json.loads(text), investigation_id, facilities,
                                               step_id=step, group_alarm=group_alarm)
        except llm.LLMUnavailable as e:
            log.warning("no investigation of %s on day %d: %s", alert_id, day, e)
            continue
        row = inv.row(alert_id)
        con.execute(f"INSERT INTO investigations BY NAME SELECT {', '.join(f'${k} AS {k}' for k in row)}", row)
        done += 1
        con.execute("UPDATE alerts SET investigation_id = $i WHERE alert_id = $a", {"i": investigation_id, "a": alert_id})
        for m in messages:
            p = m["payload"]
            if m["type"] == "alert" and p.get("alert_id") == alert_id:
                p["investigation_id"] = investigation_id
        out += inv.messages(scenario)
    return out
