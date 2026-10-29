"""Reads of a run database that the API, the tick and the fixtures share (SPEC §10, C15).

The connection is a cursor of the run's open_run connection in the simulation process, or any read-only
connection to a finished run.
"""

import json

import duckdb

JSON_COLUMNS = {"scope", "payload", "rationale", "evidence", "details", "reasons", "script", "text"}


def rows(con: duckdb.DuckDBPyConnection, sql: str, params: dict | None = None) -> list[dict]:
    cur = con.execute(sql, params or {})
    names = [d[0] for d in cur.description]
    return [{n: json.loads(v) if n in JSON_COLUMNS and v is not None else v for n, v in zip(names, r)}
            for r in cur.fetchall()]


def kpi(con: duckdb.DuckDBPyConnection, pathway_id: str | None, level: str | None, key: str | None) -> list[dict]:
    """GET /api/kpi: kpi_daily rows, every filter optional."""
    return rows(con, """
        SELECT * FROM kpi_daily
        WHERE ($pw IS NULL OR pathway_id = $pw) AND ($lv IS NULL OR level = $lv) AND ($k IS NULL OR key = $k)
        ORDER BY day, pathway_id, level, key""", {"pw": pathway_id, "lv": level, "k": key})


def kpi_headline(con: duckdb.DuckDBPyConnection, day: int, pathway_id: str) -> dict | None:
    """The `kpi` of a tick (SPEC §10, C15): the ATS row of kpi_daily for the pathway on screen."""
    found = rows(con, "SELECT * EXCLUDE (day, level, key) FROM kpi_daily WHERE day = $d AND level = 'ats' "
                      "AND pathway_id = $pw", {"d": day, "pw": pathway_id})
    return found[0] if found else None


def sankey(con: duckdb.DuckDBPyConnection, pathway_id: str | None) -> list[dict]:
    """GET /api/sankey: sankey_flows (SPEC §5.2, C15)."""
    return rows(con, "SELECT * FROM sankey_flows WHERE $pw IS NULL OR pathway_id = $pw ORDER BY ALL",
                {"pw": pathway_id})


def map_comuni(con: duckdb.DuckDBPyConnection, pathway_id: str | None) -> list[dict]:
    """GET /api/map: map_comuni (SPEC §5.2, C18), one row per comune with enrolled patients."""
    return rows(con, "SELECT * FROM map_comuni WHERE $pw IS NULL OR pathway_id = $pw ORDER BY comune_istat, pathway_id",
                {"pw": pathway_id})


def worklist(con: duckdb.DuckDBPyConnection, day: int | None) -> list[dict]:
    """GET /api/worklist: the list of `day`, or of the run's last day (SPEC §5.2, C20)."""
    return rows(con, """
        SELECT * EXCLUDE (day) FROM worklist_today
        WHERE day = coalesce($d, (SELECT max(day) FROM worklist_today)) ORDER BY rank""", {"d": day})


def actions(con: duckdb.DuckDBPyConnection, status: str | None) -> list[dict]:
    """GET /api/actions: the action queue and feed."""
    return rows(con, "SELECT * FROM actions WHERE $s IS NULL OR status = $s ORDER BY created_day, action_id",
                {"s": status})


def patient_360(con: duckdb.DuckDBPyConnection, patient_id: str) -> dict | None:
    """GET /api/patients/{id} (SPEC §10, C15)."""
    found = rows(con, "SELECT p.*, c.name AS comune_name FROM patients p JOIN comuni c USING (comune_istat) "
                      "WHERE patient_id = $p", {"p": patient_id})
    if not found:
        return None
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
    return {"patient": found[0], "pathways": pathways, "timeline": timeline}
