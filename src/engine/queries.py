"""Reads of a run database that the API, the tick and the fixtures share (SPEC §10, C15).

The connection is a cursor of the run's open_run connection in the simulation process, or any read-only
connection to a finished run.
"""

import json

import duckdb

JSON_COLUMNS = {"scope", "payload", "rationale", "evidence", "details", "reasons", "script", "text", "question", "steps",
                "claims", "conclusion", "figures"}


def decode(row: dict) -> dict:
    """A row as written, with its JSON columns parsed, as `rows` returns it."""
    return {n: json.loads(v) if n in JSON_COLUMNS and v is not None else v for n, v in row.items()}


def rows(con: duckdb.DuckDBPyConnection, sql: str, params: dict | None = None) -> list[dict]:
    cur = con.execute(sql, params or {})
    names = [d[0] for d in cur.description]
    return [decode(dict(zip(names, r))) for r in cur.fetchall()]


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


CAPACITY_WINDOW_DAYS = 7  # as the wait alarm (agents.monitoring.WAIT_WINDOW_DAYS)


def capacity(con: duckdb.DuckDBPyConnection, pathway_id: str, service: str, day: int | None) -> list[dict]:
    """GET /api/capacity (C28): per facility of a service, over the 7 days up to `day` (the run's last day by
    default), the share of slots used and the wait from booking to booked day of the pathway's patients.
    The mean is wait_by_hospital's with period_days 7, the number the alarm and the agents see; median and
    p90 are of integer days, so exact (SPEC §2)."""
    return rows(con, f"""
        WITH d AS (SELECT coalesce($d, (SELECT max(day) FROM kpi_daily)) AS day),
        slots AS (
            SELECT c.facility_id, sum(c.slots_total)::BIGINT AS slots_total, sum(c.slots_booked)::BIGINT AS slots_booked
            FROM capacity_slots c, d WHERE c.service = $s AND c.day BETWEEN d.day - {CAPACITY_WINDOW_DAYS - 1} AND d.day
            GROUP BY 1),
        waits AS (
            SELECT e.facility_id, count(*)::BIGINT AS bookings, round(avg(e.value - e.day), 1) AS wait_mean,
                   quantile_disc(e.value - e.day, 0.5)::INTEGER AS wait_median,
                   quantile_disc(e.value - e.day, 0.9)::INTEGER AS wait_p90
            FROM events e, d
            WHERE e.event_type = 'BOOKING' AND e.code = $s AND e.day BETWEEN d.day - {CAPACITY_WINDOW_DAYS - 1} AND d.day
              AND e.patient_id IN (SELECT patient_id FROM pathway_state WHERE pathway_id = $pw AND enrolled_day <= d.day)
            GROUP BY 1)
        SELECT (SELECT day FROM d) AS day, f.facility_id, f.name, s.slots_total, s.slots_booked,
               round(s.slots_booked / nullif(s.slots_total, 0), 4) AS use_pct,
               coalesce(w.bookings, 0) AS bookings, w.wait_mean, w.wait_median, w.wait_p90
        FROM slots s JOIN facilities f USING (facility_id) LEFT JOIN waits w USING (facility_id)
        ORDER BY f.facility_id""", {"pw": pathway_id, "s": service, "d": day})


def sankey(con: duckdb.DuckDBPyConnection, pathway_id: str | None) -> list[dict]:
    """GET /api/sankey: sankey_flows (SPEC §5.2, C15)."""
    return rows(con, "SELECT * FROM sankey_flows WHERE $pw IS NULL OR pathway_id = $pw ORDER BY ALL",
                {"pw": pathway_id})


def map_comuni(con: duckdb.DuckDBPyConnection, pathway_id: str | None) -> list[dict]:
    """GET /api/map: map_comuni (SPEC §5.2, C18), one row per comune with enrolled patients."""
    return rows(con, "SELECT * FROM map_comuni WHERE $pw IS NULL OR pathway_id = $pw ORDER BY comune_istat, pathway_id",
                {"pw": pathway_id})


def worklist(con: duckdb.DuckDBPyConnection, day: int | None) -> list[dict]:
    """GET /api/worklist: the list of `day`, or of the run's last day (SPEC §5.2, C20), with who the patient is
    for the Centro Servizi (C37): age, living alone, comune."""
    return rows(con, """
        SELECT w.* EXCLUDE (day), p.age, p.lives_alone, c.name AS comune_name
        FROM worklist_today w JOIN patients p USING (patient_id) JOIN comuni c ON c.comune_istat = p.comune_istat
        WHERE w.day = coalesce($d, (SELECT max(day) FROM worklist_today)) ORDER BY w.rank""", {"d": day})


def actions(con: duckdb.DuckDBPyConnection, status: str | None, day: int | None = None) -> list[dict]:
    """GET /api/actions: the action queue and feed; with `day`, the actions created or executed that day (C38,
    Attività agenti after a jump)."""
    return rows(con, """
        SELECT * FROM actions
        WHERE ($s IS NULL OR status = $s) AND ($d IS NULL OR created_day = $d OR executed_day = $d)
        ORDER BY created_day, action_id""", {"s": status, "d": day})


def investigations(con: duckdb.DuckDBPyConnection) -> list[dict]:
    """GET /api/investigations: every stored investigation, the latest first (SPEC §6, C24, C25)."""
    return rows(con, "SELECT * FROM investigations ORDER BY day DESC, investigation_id DESC")


def reports(con: duckdb.DuckDBPyConnection) -> list[dict]:
    """GET /api/reports: every monthly report, the latest first (C36)."""
    return rows(con, "SELECT * FROM reports ORDER BY day DESC")


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
