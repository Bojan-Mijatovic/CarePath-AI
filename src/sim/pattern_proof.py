"""Pattern proof: patterns 1–3 and the PNE calibration, found from a run's data alone (step 1.21).

Every query goes through engine.db.connect_for_tools, the connection agent tools will get, so what is
found here is visible to agents. `detect` names the places blind; `compare` checks them against
scenario_truth afterwards, the way the Rivelazione screen does. The pattern-3 segment comes from the
Solution Plan's description (older, living alone, more than 40 km away), not from the scenario files.
Numbers are rounded as SPEC §2 requires.
"""

import duckdb
import pandas as pd

SEGMENT = "p.age >= 75 AND p.lives_alone AND p.distance_km > 40"  # Solution Plan §6, pattern 3


def q(con: duckdb.DuckDBPyConnection, sql: str, **params) -> pd.DataFrame:
    return con.execute(sql, params).df()


def echo_wait(con, day_from: int, day_to: int) -> pd.Series:
    """Mean days from booking to echo slot, by facility, for bookings made in [day_from, day_to]."""
    df = q(con, """SELECT facility_id, round(avg(value - day), 1) AS wait FROM events
                   WHERE event_type = 'BOOKING' AND code = 'echo' AND day BETWEEN $a AND $b
                   GROUP BY 1 ORDER BY 1""", a=day_from, b=day_to)
    return df.set_index("facility_id").wait


def echo_wait_weekly(con, days: int) -> pd.DataFrame:
    return q(con, """SELECT day // 7 AS week, facility_id, round(avg(value - day), 1) AS wait FROM events
                     WHERE event_type = 'BOOKING' AND code = 'echo' AND day BETWEEN 0 AND $d
                     GROUP BY ALL ORDER BY ALL""", d=days - 1).pivot(index="week", columns="facility_id", values="wait")


def free_echo_slots(con, day: int, horizon: int = 21) -> pd.Series:
    """Free echo slots from day + 1 to day + horizon, by facility (the free_slots tool of SPEC §6)."""
    df = q(con, """SELECT facility_id, sum(slots_total - slots_booked) AS free FROM capacity_slots
                   WHERE service = 'echo' AND day BETWEEN $a AND $b GROUP BY 1 ORDER BY 1""", a=day + 1, b=day + horizon)
    return df.set_index("facility_id").free


def cooperatives(con, days: int) -> pd.DataFrame:
    """Per MMG cooperative: patients, drug collections and admissions per patient-year, days 0..days-1."""
    return q(con, """
        WITH pc AS (SELECT p.patient_id, m.coop_id FROM patients p JOIN mmg m USING (mmg_id)),
             ev AS (SELECT patient_id, event_type FROM events WHERE day BETWEEN 0 AND $d - 1
                    AND event_type IN ('DISPENSE', 'ADMISSION'))
        SELECT pc.coop_id, count(DISTINCT pc.patient_id) AS patients,
               round(count(*) FILTER (WHERE ev.event_type = 'DISPENSE') * 365.0 / $d / count(DISTINCT pc.patient_id), 2) AS collections_per_year,
               round(count(*) FILTER (WHERE ev.event_type = 'ADMISSION') * 365.0 / $d / count(DISTINCT pc.patient_id), 3) AS admissions_per_year
        FROM pc LEFT JOIN ev USING (patient_id) GROUP BY 1 ORDER BY 3""", d=days)


def telemonitoring_by_comune(con, day: int, segment: str = SEGMENT) -> pd.DataFrame:
    """Among patients in `segment` who were ever on telemonitoring by `day`: share still sending a
    reading in the last 7 days (the `telemonitoring` measure of SPEC §6), by comune."""
    return q(con, f"""
        WITH ever AS (SELECT DISTINCT patient_id FROM events
                      WHERE event_type IN ('TELEMON_START', 'TELEMON_READING') AND day <= $t),
             recent AS (SELECT DISTINCT patient_id FROM events
                        WHERE event_type = 'TELEMON_READING' AND day BETWEEN $t - 6 AND $t)
        SELECT c.name AS comune, count(*) AS patients, round(avg((r.patient_id IS NOT NULL)::INT), 4) AS share_reading
        FROM patients p JOIN ever e USING (patient_id) JOIN comuni c USING (comune_istat)
        LEFT JOIN recent r USING (patient_id)
        WHERE {segment} GROUP BY 1 ORDER BY 3, 2 DESC""", t=day)


def readmission_30d(con, days: int) -> pd.DataFrame:
    """SPEC §5.2: unplanned ADMISSION within 30 days after an HF DISCHARGE, discharges on days 0..days-31."""
    return q(con, """
        WITH d AS (SELECT patient_id, day, facility_id FROM events WHERE event_type = 'DISCHARGE' AND day BETWEEN 0 AND $d - 31),
             r AS (SELECT d.*, EXISTS (SELECT 1 FROM events a WHERE a.event_type = 'ADMISSION' AND a.patient_id = d.patient_id
                                       AND a.day > d.day AND a.day <= d.day + 30) AS readmitted FROM d)
        SELECT coalesce(facility_id, 'ATS') AS unit, count(*) AS discharges, round(avg(readmitted::INT), 4) AS rate
        FROM r GROUP BY ROLLUP (facility_id) ORDER BY unit""", d=days)


def detect(con, days: int, alarm_day: int = 35) -> dict:
    """Name the places of patterns 1–3 from data alone."""
    wait = echo_wait(con, alarm_day - 5, alarm_day + 5)
    bottleneck = wait.idxmax()
    free = free_echo_slots(con, alarm_day).drop(bottleneck)
    coop = cooperatives(con, days).iloc[0].coop_id
    tm = telemonitoring_by_comune(con, days - 1)
    tm = tm[tm.patients >= 2]  # rural comuni are small; a single patient is noise
    rural = sorted(tm[tm.share_reading < 0.5 * tm.share_reading.median()].comune)
    return {"echo_bottleneck": bottleneck, "echo_free_capacity": free.idxmax(), "low_adherence_group": coop,
            "rural_dropout_comuni": rural}


def compare(found: dict, truth: dict) -> dict:
    """Detected places against scenario_truth: True per pattern when they match."""
    rural_truth = set(truth["rural_dropout_comuni"])
    rural = set(found["rural_dropout_comuni"])
    return {
        "echo_bottleneck": found["echo_bottleneck"] == truth["echo_bottleneck"]["facility_id"],
        "echo_free_capacity": found["echo_free_capacity"] == truth["echo_free_capacity"]["facility_id"],
        "low_adherence_group": found["low_adherence_group"] == truth["low_adherence_group"]["coop_id"],
        # At least half of the hidden comuni found, and most of what was found is right.
        "rural_dropout_comuni": len(rural & rural_truth) * 2 >= len(rural_truth) and len(rural & rural_truth) * 2 > len(rural),
    }
