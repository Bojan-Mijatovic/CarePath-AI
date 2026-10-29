"""Read-only tools for the agents (SPEC §6; delivery plan step 1.24).

Each tool takes typed arguments, defined once as a Pydantic model that is also the JSON schema the model
sees (descriptions in Italian, names in English), and returns the SPEC §6 envelope: `{"data", "source"}`
or `{"error": {"code", "message"}}`. The `source` block holds the arguments with their defaults, so the
Verifier can repeat exactly the call behind a claim (C5).

Tools read a run through `Query`, which runs one SELECT or WITH statement and nothing else (D29): in the
simulation process the connection is a cursor of the run's writable `engine.db.open_run` connection, and
this guard is what keeps tools read-only. Every DOUBLE is rounded in SQL after aggregation, or computed
from integer counts, so the same call gives the same bytes (C7). A tool sees the run up to `Context.day`.

Steps, codes and drugs come from the pathway file (AC17). Step deadlines follow SPEC §5.1, the same rules
as engine.state. Group tools return the worst groups only, see GROUPS_SHOWN.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import duckdb
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from engine.db import RUNS_DIR, connect_for_tools
from engine.pathway import ID, PATHWAYS_DIR, Pathway, Step, load
from engine.risk import HIGH_RISK

ERROR_CODES = ("unknown_pathway", "unknown_step", "bad_argument", "empty_result")
GROUPS_SHOWN, MIN_GROUP_PATIENTS, MIN_GROUP_DISCHARGES = 10, 10, 5
COMPLIANCE_PERIOD_DAYS = 90  # compliance_by_step and the on_time_fraction metric
READMISSION_DAYS = 30
READING_WINDOW_DAYS = 7      # the `telemonitoring` measure (SPEC §6)
AGE_BANDS = ((0, 64, "<65"), (65, 74, "65-74"), (75, 84, "75-84"), (85, 200, "85+"))
Asst = Literal["asst_mantova", "asst_cremona", "asst_crema"]


class ToolError(Exception):
    def __init__(self, code: str, message: str):
        assert code in ERROR_CODES, code
        super().__init__(message)
        self.code, self.message = code, message


class Query:
    """The only way tools touch the database: one SELECT (or WITH ... SELECT) statement per call."""

    def __init__(self, con: duckdb.DuckDBPyConnection):
        self.con = con

    def rows(self, sql: str, params: dict | None = None) -> list[tuple]:
        statements = self.con.extract_statements(sql)
        if len(statements) != 1 or statements[0].type != duckdb.StatementType.SELECT:
            raise PermissionError(f"tools run one SELECT statement only, got {[str(s.type) for s in statements]}")
        return self.con.execute(sql, params or {}).fetchall()


@dataclass
class Context:
    run_id: str
    db: Query
    day: int  # "today" for every tool

    @classmethod
    def for_run(cls, run_id: str, runs_dir: Path = RUNS_DIR, day: int | None = None) -> "Context":
        """A finished run, read through connect_for_tools (notebooks, tests). `day` defaults to the last
        day the state engine reached. Note: capacity_slots holds the bookings of the whole run, so
        free_slots is exact only on the run's last day or in the live tick."""
        db = Query(connect_for_tools(run_id, runs_dir))
        last = db.rows("SELECT coalesce((SELECT max(day) FROM kpi_daily), (SELECT max(day) FROM events))")[0][0]
        return cls(run_id, db, last if day is None else day)

    def close(self) -> None:
        self.db.con.close()


# --- arguments: the schemas the model sees ------------------------------------------------------------

class Args(BaseModel):
    model_config = ConfigDict(extra="forbid")


PathwayId = Field(pattern=ID, description="ID del percorso, es. hf_lombardia_v1")
StepId = Field(pattern=ID, description="ID dello step del percorso, es. echo, cardio_visit, telemon, lab_bnp")
AsstArg = Field(None, description="Limita a una ASST")


class Segment(Args):
    """C8: every key optional, combined with AND; {} is the whole population of the pathway."""
    asst_id: Asst | None = None
    comune_istat: list[str] | None = Field(None, description="codici ISTAT dei comuni")
    coop_id: str | None = Field(None, description="gruppo (cooperativa) di MMG, es. coop_3")
    age_min: int | None = None
    age_max: int | None = None
    lives_alone: bool | None = None
    distance_km_min: float | None = Field(None, description="distanza minima dall'ospedale di riferimento, km")


class ComplianceArgs(Args):
    pathway_id: str = PathwayId
    asst: Asst | None = AsstArg


class WaitArgs(Args):
    pathway_id: str = PathwayId
    step: str = StepId
    period_days: int = Field(90, ge=1, le=365, description="prenotazioni fatte negli ultimi N giorni")


class OverdueArgs(Args):
    pathway_id: str = PathwayId
    step: str = StepId
    asst: Asst | None = AsstArg
    limit: int = Field(20, ge=1, le=100)


class FreeSlotsArgs(Args):
    service: str = Field(pattern=ID, description="servizio, es. echo, cardio_visit, lab")
    asst: Asst | None = AsstArg
    horizon_days: int = Field(21, ge=1, le=90, description="posti liberi da domani per N giorni")


class AdherenceArgs(Args):
    pathway_id: str = PathwayId
    grouping: Literal["mmg", "mmg_group", "comune", "age_band"] = Field(
        description="mmg = singolo medico; mmg_group = gruppo o cooperativa di MMG; comune = comune di residenza; "
                    "age_band = fascia di eta'")
    measure: Literal["dispensing", "telemonitoring"] = Field(
        "dispensing", description="dispensing = ritiro in farmacia di ogni farmaco del percorso nel periodo; "
                                  "telemonitoring = pazienti in telemonitoraggio con almeno una lettura negli "
                                  "ultimi 7 giorni")
    period_days: int = Field(60, ge=7, le=365)


class ReadmissionArgs(Args):
    pathway_id: str = PathwayId
    period_days: int = Field(180, ge=30, le=365)


class RiskDriversArgs(Args):
    pathway_id: str = PathwayId
    segment: Segment | None = None


class CompareArgs(Args):
    pathway_id: str = PathwayId
    a: Segment
    b: Segment
    metric: Literal["dispensing", "telemonitoring", "readmission_rate_30d", "on_time_fraction", "risk_mean"]


# --- SQL pieces built from the pathway --------------------------------------------------------------

def _lit(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def _codes(patterns: list[str]) -> str:
    """A pathway code list as SQL on e.code; a trailing * matches a prefix (SPEC §4)."""
    return "(" + " OR ".join(f"starts_with(e.code, {_lit(p[:-1])})" if p.endswith("*") else f"e.code = {_lit(p)}"
                             for p in patterns) + ")"


def _own(s: Step) -> str:
    """Events of the step's own type (SPEC §5.1)."""
    parts = [f"e.event_type = {_lit(s.event)}"]
    if s.codes:
        parts.append(_codes(s.codes))
    if s.specialty:
        parts.append(f"e.code = {_lit(s.specialty)}")
    if s.loinc:
        parts.append(_codes(s.loinc))
    return "(" + " AND ".join(parts) + ")"


def _done(s: Step) -> str:
    """Events that complete the step: a telemonitoring step is also done by a reading (SPEC §5.1)."""
    return f"({_own(s)} OR e.event_type = 'TELEMON_READING')" if s.event == "TELEMON_START" else _own(s)


def _starts(p: Pathway) -> list[Step]:
    return [s for s in p.steps if s.after is None and s.every_days is None]


def _timed(p: Pathway) -> list[Step]:
    return [s for s in p.steps if s.after is not None or s.every_days is not None]


ENROLLED = "SELECT patient_id, enrolled_day FROM pathway_state WHERE pathway_id = $pw AND enrolled_day <= $d"


def _current_due(p: Pathway, s: Step) -> str:
    """(patient_id, due) of the open deadline of `s` on day $d, one row per patient with one."""
    if s.after is not None:
        anchor = _own(next(x for x in p.steps if x.id == s.after))
        return f"""
            SELECT a.patient_id, a.day + {s.due_days} AS due
            FROM (SELECT e.patient_id, max(e.day) AS day FROM events e WHERE e.day <= $d AND {anchor} GROUP BY 1) a
            JOIN ({ENROLLED}) en USING (patient_id)
            LEFT JOIN (SELECT e.patient_id, max(e.day) AS day FROM events e WHERE e.day <= $d AND {_done(s)} GROUP BY 1) dn
                   USING (patient_id)
            WHERE dn.day IS NULL OR dn.day < a.day"""
    restart = " OR ".join([_done(s)] + [_own(x) for x in _starts(p)])
    return f"""
        SELECT en.patient_id, greatest(coalesce(st.day, en.enrolled_day), en.enrolled_day) + {s.every_days} AS due
        FROM ({ENROLLED}) en
        LEFT JOIN (SELECT e.patient_id, max(e.day) AS day FROM events e WHERE e.day <= $d AND ({restart}) GROUP BY 1) st
               USING (patient_id)"""


def _pulled_due(p: Pathway, s: Step) -> str | None:
    """(patient_id, due) where a rule pulled `s` earlier (SPEC §4, step 2.8): Monitoring records the day a
    rule starts to hold in `deviations`; the pull holds until the step is done after that day or its clock
    starts again after it (its anchor, or a start step for a periodic step), and the earliest such deadline
    counts, as in engine.state."""
    pulls = [r for r in p.rules if r.then.step == s.id]
    if not pulls:
        return None
    if s.after is not None:
        restart = _own(next(x for x in p.steps if x.id == s.after))
    else:
        restart = " OR ".join(_own(x) for x in _starts(p)) if s.every_days is not None and _starts(p) else "false"
    return " UNION ALL ".join(f"""
        SELECT v.patient_id, min(v.day) + {r.then.due_days} AS due
        FROM deviations v
        LEFT JOIN (SELECT e.patient_id, max(e.day) AS day FROM events e WHERE e.day <= $d AND {_done(s)} GROUP BY 1) dn
               USING (patient_id)
        LEFT JOIN (SELECT e.patient_id, max(e.day) AS day FROM events e WHERE e.day <= $d AND ({restart}) GROUP BY 1) rs
               USING (patient_id)
        WHERE v.pathway_id = $pw AND v.kind = 'rule' AND v.code = {_lit(r.id)} AND v.day <= $d
          AND (dn.day IS NULL OR v.day > dn.day) AND (rs.day IS NULL OR v.day >= rs.day)
        GROUP BY 1""" for r in pulls)


def _open_due(p: Pathway, s: Step) -> str:
    """(patient_id, due): the step's open deadline today, a rule's earlier one included."""
    pulled = _pulled_due(p, s)
    if pulled is None:
        return _current_due(p, s)
    return f"SELECT patient_id, min(due) AS due FROM ({_current_due(p, s)} UNION ALL {pulled}) GROUP BY 1"


def _deadlines(p: Pathway, s: Step) -> str:
    """(patient_id, step, met) for every deadline of `s` that fell due in the last COMPLIANCE_PERIOD_DAYS
    days before $d. A deadline is met by a completion on or before its due day; one that a new anchor or a
    discharge replaced before it fell due is not counted."""
    window = f"due BETWEEN $d - {COMPLIANCE_PERIOD_DAYS} AND $d - 1"
    if s.after is not None:
        anchor = _own(next(x for x in p.steps if x.id == s.after))
        return f"""
            SELECT patient_id, {_lit(s.id)} AS step,
                   coalesce(dn <= due AND (next_a IS NULL OR dn < next_a), false) AS met
            FROM (SELECT x.patient_id, x.a + {s.due_days} AS due, x.next_a, min(e.day) AS dn
                  FROM (SELECT patient_id, day AS a, lead(day) OVER (PARTITION BY patient_id ORDER BY day) AS next_a
                        FROM (SELECT DISTINCT e.patient_id, e.day FROM events e WHERE e.day <= $d AND {anchor})) x
                  JOIN ({ENROLLED}) en USING (patient_id)
                  LEFT JOIN events e ON e.patient_id = x.patient_id AND e.day >= x.a AND e.day <= $d AND {_done(s)}
                  GROUP BY ALL)
            WHERE {window} AND (next_a IS NULL OR next_a > due OR dn < next_a)"""
    restarts = " OR ".join(_own(x) for x in _starts(p)) or "false"
    return f"""
        SELECT patient_id, {_lit(s.id)} AS step, coalesce(next_kind = 1 AND next_day <= due, false) AS met
        FROM (SELECT patient_id, day + {s.every_days} AS due,
                     lead(day) OVER w AS next_day, lead(kind) OVER w AS next_kind
              FROM (SELECT patient_id, day, max(kind) AS kind FROM (
                        SELECT e.patient_id, e.day, 1 AS kind FROM events e WHERE e.day <= $d AND {_done(s)}
                        UNION ALL SELECT e.patient_id, e.day, 0 FROM events e WHERE e.day <= $d AND ({restarts})
                        UNION ALL SELECT patient_id, enrolled_day, 0 FROM ({ENROLLED}))
                    WHERE patient_id IN (SELECT patient_id FROM ({ENROLLED})) GROUP BY ALL)
              WINDOW w AS (PARTITION BY patient_id ORDER BY day))
        WHERE {window} AND NOT (next_day <= due AND next_kind = 0)"""


def _segment(seg: Segment, prefix: str) -> tuple[str, dict]:
    """SQL on patients p and mmg m for a segment, with its parameters."""
    clauses, params = [], {}
    checks = [("asst_id", "p.asst_id = ${}"), ("coop_id", "m.coop_id = ${}"), ("age_min", "p.age >= ${}"),
              ("age_max", "p.age <= ${}"), ("lives_alone", "p.lives_alone = ${}"),
              ("distance_km_min", "p.distance_km >= ${}"), ("comune_istat", "list_contains(${}, p.comune_istat)")]
    for key, sql in checks:
        value = getattr(seg, key)
        if value is not None:
            name = f"{prefix}_{key}"
            clauses.append(sql.format(name))
            params[name] = value
    return " AND ".join(clauses) or "true", params


def _per_patient(p: Pathway, metric: str, period: int) -> str:
    """(patient_id, num, den) for a measure (SPEC §6); a group's value is sum(num) / sum(den)."""
    since = f"$d - {period - 1}"
    if metric == "dispensing":
        if not p.eligibility.any_drug_atc:
            raise ToolError("bad_argument", f"{p.pathway_id} has no drug, so there is no dispensing to measure")
        drugs = " ".join(f"WHEN {_codes([atc])} THEN {_lit(atc)}" for atc in p.eligibility.any_drug_atc)
        return f"""
            SELECT en.patient_id, (coalesce(d.n, 0) = {len(p.eligibility.any_drug_atc)})::INT AS num, 1 AS den
            FROM ({ENROLLED}) en LEFT JOIN (
                SELECT e.patient_id, count(DISTINCT CASE {drugs} END) AS n FROM events e
                WHERE e.event_type = 'DISPENSE' AND e.day BETWEEN {since} AND $d GROUP BY 1) d USING (patient_id)"""
    if metric == "telemonitoring":
        # Everyone ever started, warm-up included: a patient who stopped long ago still counts as stopped.
        # A window on the denominator would drop exactly those patients (measured on scenario 2).
        return f"""
            SELECT e.patient_id,
                   max((e.event_type = 'TELEMON_READING' AND e.day > $d - {READING_WINDOW_DAYS})::INT) AS num, 1 AS den
            FROM events e JOIN ({ENROLLED}) en USING (patient_id)
            WHERE e.event_type IN ('TELEMON_START', 'TELEMON_READING') AND e.day <= $d GROUP BY 1"""
    if metric == "readmission_rate_30d":
        # SPEC §5.2 over the period: unplanned admissions in it within 30 days after an index discharge
        # (which may be earlier), divided by the index discharges in it.
        diagnosis = _codes(p.eligibility.any_diagnosis) if p.eligibility.any_diagnosis else "false"
        index = f"SELECT e.patient_id, e.day FROM events e WHERE e.event_type = 'DISCHARGE' AND e.day <= $d AND {diagnosis}"
        return f"""
            SELECT en.patient_id, coalesce(r.n, 0) AS num, coalesce(x.n, 0) AS den
            FROM ({ENROLLED}) en
            LEFT JOIN (SELECT a.patient_id, count(DISTINCT a.day) AS n
                       FROM events a JOIN ({index}) i ON i.patient_id = a.patient_id AND i.day < a.day
                                                      AND a.day - i.day <= {READMISSION_DAYS}
                       WHERE a.event_type = 'ADMISSION' AND a.value = 1 AND a.day BETWEEN {since} AND $d
                       GROUP BY 1) r USING (patient_id)
            LEFT JOIN (SELECT patient_id, count(*) AS n FROM ({index}) WHERE day >= {since} GROUP BY 1) x
                   USING (patient_id)"""
    if metric == "on_time_fraction":
        deadlines = " UNION ALL ".join(_deadlines(p, s) for s in _timed(p))
        return f"SELECT patient_id, count_if(met) AS num, count(*) AS den FROM ({deadlines}) GROUP BY 1"
    # risk_mean: integers, so the sum is exact (C7); risk_score has 4 decimals (SPEC §2)
    return """SELECT patient_id, round(risk_score * 10000)::BIGINT AS num, 10000 AS den FROM pathway_state
              WHERE pathway_id = $pw AND enrolled_day <= $d"""


def _grouped(db: Query, ctx: Context, p: Pathway, metric: str, period: int, key: str, worst: str,
             minimum: int) -> dict:
    """The GROUPS_SHOWN worst groups with at least `minimum` in the denominator, then `rest_of_ats` over
    every other patient, small groups included (SPEC §6). Hundreds of groups would not fit a prompt, and a
    group of three patients is noise."""
    groups = db.rows(f"""
        SELECT {key} AS g, sum(x.num)::BIGINT, sum(x.den)::BIGINT
        FROM ({_per_patient(p, metric, period)}) x JOIN patients p USING (patient_id)
        JOIN mmg m ON m.mmg_id = p.mmg_id JOIN comuni c ON c.comune_istat = p.comune_istat
        GROUP BY 1 ORDER BY 1""", {"pw": p.pathway_id, "d": ctx.day})
    rated = [(g, n, d) for g, n, d in groups if d >= minimum]
    if not rated:
        raise ToolError("empty_result", f"no group has at least {minimum} patients in the period")
    sign = 1 if worst == "lowest" else -1
    shown = sorted(rated, key=lambda r: (sign * r[1] / r[2], r[0]))[:GROUPS_SHOWN]
    names = {g for g, _, _ in shown}
    rest_n = sum(n for g, n, d in groups if g not in names)
    rest_d = sum(d for g, n, d in groups if g not in names)
    data = {g: round(n / d, 4) for g, n, d in shown}
    data["rest_of_ats"] = round(rest_n / rest_d, 4) if rest_d else None
    return data


# --- the tools --------------------------------------------------------------------------------------

def compliance_by_step(ctx: Context, a: ComplianceArgs) -> dict:
    p = _pathway(a.pathway_id)
    asst = "AND p.asst_id = $asst" if a.asst else ""
    deadlines = " UNION ALL ".join(_deadlines(p, s) for s in _timed(p))
    rows = dict(ctx.db.rows(f"""
        SELECT x.step, round(count_if(x.met) / count(*), 4) FROM ({deadlines}) x
        JOIN patients p USING (patient_id) WHERE true {asst} GROUP BY 1""",
                            {"pw": p.pathway_id, "d": ctx.day} | ({"asst": a.asst} if a.asst else {})))
    if not rows:
        raise ToolError("empty_result", "no deadline fell due in the last 90 days")
    return {s.id: rows.get(s.id) for s in _timed(p)}


def wait_by_hospital(ctx: Context, a: WaitArgs) -> dict:
    p = _pathway(a.pathway_id)
    s = _step(p, a.step)
    if not s.service:
        raise ToolError("bad_argument", f"step {s.id} is not booked, so it has no wait")
    rows = ctx.db.rows(f"""
        SELECT f.name, round(avg(e.value - e.day), 1) FROM events e JOIN facilities f USING (facility_id)
        WHERE e.event_type = 'BOOKING' AND e.code = $service AND e.day BETWEEN $d - {a.period_days - 1} AND $d
          AND e.patient_id IN (SELECT patient_id FROM ({ENROLLED}))
        GROUP BY 1 ORDER BY 1""", {"service": s.service, "pw": p.pathway_id, "d": ctx.day})
    if not rows:
        raise ToolError("empty_result", f"no {s.service} booking in the last {a.period_days} days")
    return dict(rows)


def patients_overdue(ctx: Context, a: OverdueArgs) -> dict:
    p = _pathway(a.pathway_id)
    s = _step(p, a.step)
    if s not in _timed(p):
        raise ToolError("bad_argument", f"step {s.id} has no deadline")
    asst = "AND p.asst_id = $asst" if a.asst else ""
    rows = ctx.db.rows(f"""
        SELECT x.patient_id, $d - x.due AS days_overdue, round(ps.risk_score, 4)
        FROM ({_open_due(p, s)}) x JOIN patients p USING (patient_id)
        JOIN pathway_state ps ON ps.patient_id = x.patient_id AND ps.pathway_id = $pw
        WHERE x.due < $d {asst} ORDER BY days_overdue DESC, x.patient_id""",
                       {"pw": p.pathway_id, "d": ctx.day} | ({"asst": a.asst} if a.asst else {}))
    return {"count": len(rows),
            "patients": [{"patient_id": pid, "days_overdue": days, "risk_score": risk} for pid, days, risk in rows[:a.limit]]}


def free_slots(ctx: Context, a: FreeSlotsArgs) -> dict:
    services = [r[0] for r in ctx.db.rows("SELECT DISTINCT service FROM capacity_slots ORDER BY 1")]
    if a.service not in services:
        raise ToolError("bad_argument", f"unknown service {a.service!r}; known: {services}")
    asst = "AND f.asst_id = $asst" if a.asst else ""
    rows = ctx.db.rows(f"""
        SELECT f.name, sum(c.slots_total - c.slots_booked)::BIGINT FROM capacity_slots c JOIN facilities f USING (facility_id)
        WHERE c.service = $service AND c.day BETWEEN $d + 1 AND $d + {a.horizon_days} {asst}
        GROUP BY 1 ORDER BY 1""", {"service": a.service, "d": ctx.day} | ({"asst": a.asst} if a.asst else {}))
    if not rows:
        raise ToolError("empty_result", f"no {a.service} capacity in the next {a.horizon_days} days")
    return dict(rows)


def adherence_by_group(ctx: Context, a: AdherenceArgs) -> dict:
    p = _pathway(a.pathway_id)
    bands = " ".join(f"WHEN p.age BETWEEN {lo} AND {hi} THEN {_lit(label)}" for lo, hi, label in AGE_BANDS)
    key = {"mmg": "p.mmg_id", "mmg_group": "m.coop_id", "comune": "c.name", "age_band": f"CASE {bands} END"}[a.grouping]
    return _grouped(ctx.db, ctx, p, a.measure, a.period_days, key, "lowest", MIN_GROUP_PATIENTS)


def readmissions_by_comune(ctx: Context, a: ReadmissionArgs) -> dict:
    p = _pathway(a.pathway_id)
    return _grouped(ctx.db, ctx, p, "readmission_rate_30d", a.period_days, "c.name", "highest", MIN_GROUP_DISCHARGES)


def _require_risk(ctx: Context, p: Pathway) -> None:
    if not ctx.db.rows("SELECT count(*) FROM pathway_state WHERE pathway_id = $pw AND risk_score > 0",
                       {"pw": p.pathway_id})[0][0]:
        raise ToolError("empty_result", "this run has no risk scores: Risk did not run on its ticks")


def risk_drivers(ctx: Context, a: RiskDriversArgs) -> dict:
    """Among the segment's high-risk patients (C19), the share whose top 3 drivers include each driver."""
    p = _pathway(a.pathway_id)
    _require_risk(ctx, p)
    where, params = _segment(a.segment or Segment(), "s")
    high = f"""
        SELECT ps.patient_id, ps.risk_drivers FROM pathway_state ps JOIN patients p USING (patient_id)
        JOIN mmg m ON m.mmg_id = p.mmg_id
        WHERE ps.pathway_id = $pw AND ps.enrolled_day <= $d AND ps.risk_score >= {HIGH_RISK} AND {where}"""
    args = {"pw": p.pathway_id, "d": ctx.day} | params
    patients = ctx.db.rows(f"SELECT count(*) FROM ({high})", args)[0][0]
    if not patients:
        raise ToolError("empty_result", f"no patient of the segment has a risk of {HIGH_RISK} or more")
    counts = ctx.db.rows(f"SELECT name, count(*) FROM (SELECT unnest(risk_drivers) AS name FROM ({high})) GROUP BY 1", args)
    drivers = sorted(((name, round(n / patients, 4)) for name, n in counts), key=lambda d: (-d[1], d[0]))
    return {"drivers": [{"name": name, "weight": w} for name, w in drivers], "patients": patients}


def compare_segments(ctx: Context, a: CompareArgs) -> dict:
    p = _pathway(a.pathway_id)
    if a.metric == "risk_mean":
        _require_risk(ctx, p)
    period = {"dispensing": 60, "telemonitoring": 60, "readmission_rate_30d": 180,
              "on_time_fraction": COMPLIANCE_PERIOD_DAYS}.get(a.metric, 0)
    values = {}
    for name, seg in (("a", a.a), ("b", a.b)):
        where, params = _segment(seg, name)
        num, den = ctx.db.rows(f"""
            SELECT coalesce(sum(x.num), 0)::BIGINT, coalesce(sum(x.den), 0)::BIGINT
            FROM ({_per_patient(p, a.metric, period)}) x JOIN patients p USING (patient_id)
            JOIN mmg m ON m.mmg_id = p.mmg_id WHERE {where}""", {"pw": p.pathway_id, "d": ctx.day} | params)[0]
        if not den:
            raise ToolError("empty_result", f"segment {name} has nobody to measure")
        values[name] = round(num / den, 4)
    return {"a": values["a"], "b": values["b"], "difference": round(values["a"] - values["b"], 4)}


def _pathway(pathway_id: str) -> Pathway:
    if not (PATHWAYS_DIR / f"{pathway_id}.json").is_file():
        raise ToolError("unknown_pathway", f"no pathway {pathway_id!r}")
    return load(pathway_id, PATHWAYS_DIR)  # read at call time, so a test can point the tools at other files


def _step(p: Pathway, step: str) -> Step:
    for s in p.steps:
        if s.id == step:
            return s
    raise ToolError("unknown_step", f"step {step!r} is not in {p.pathway_id}; steps: {[s.id for s in p.steps]}")


# name -> (arguments, function, description shown to the model). eligibility_candidates (option B) and
# free_beds (Bed Finder) come with their gated extensions.
TOOLS = {
    "compliance_by_step": (ComplianceArgs, compliance_by_step,
                           "Quota di scadenze di ogni step del percorso rispettate in tempo, negli ultimi 90 giorni."),
    "wait_by_hospital": (WaitArgs, wait_by_hospital,
                         "Attesa media in giorni tra prenotazione e appuntamento per uno step del percorso, per ospedale."),
    "patients_overdue": (OverdueArgs, patients_overdue,
                         "Pazienti con la scadenza di uno step superata: quanti sono e i piu' in ritardo."),
    "free_slots": (FreeSlotsArgs, free_slots, "Posti liberi per un servizio, per ospedale, nei prossimi giorni."),
    "adherence_by_group": (AdherenceArgs, adherence_by_group,
                           "Aderenza per gruppo di pazienti (ritiro dei farmaci o letture del telemonitoraggio): i 10 "
                           "gruppi peggiori e il resto dell'ATS (rest_of_ats)."),
    "readmissions_by_comune": (ReadmissionArgs, readmissions_by_comune,
                               "Tasso di riammissione a 30 giorni per comune: i 10 comuni peggiori e il resto dell'ATS."),
    "risk_drivers": (RiskDriversArgs, risk_drivers, "Principali fattori di rischio per un segmento di pazienti."),
    "compare_segments": (CompareArgs, compare_segments,
                         "Confronta due segmenti di pazienti su una metrica: valori di a e b e differenza a - b."),
}


def _inline(node, defs: dict):
    """Replace every $ref by its definition: small models follow a flat schema more reliably."""
    if isinstance(node, dict):
        if "$ref" in node:
            return _inline(defs[node["$ref"].rsplit("/", 1)[-1]], defs)
        return {k: _inline(v, defs) for k, v in node.items() if k != "$defs"}
    if isinstance(node, list):
        return [_inline(v, defs) for v in node]
    return node


def definitions() -> list[dict]:
    """The tools in the function-calling format of Ollama (SPEC §8)."""
    out = []
    for name, (args, _, description) in TOOLS.items():
        schema = args.model_json_schema()
        out.append({"type": "function", "function": {"name": name, "description": description,
                                                     "parameters": _inline(schema, schema.get("$defs", {}))}})
    return out


def call(ctx: Context, name: str, args: dict) -> dict:
    """Run one tool and return the SPEC §6 envelope; never raises for a bad call from the model."""
    if name not in TOOLS:
        return {"error": {"code": "bad_argument", "message": f"unknown tool {name!r}"}}
    model, fn, _ = TOOLS[name]
    try:
        parsed = model.model_validate(args)
    except ValidationError as e:
        return {"error": {"code": "bad_argument", "message": "; ".join(
            f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors(include_url=False))}}
    try:
        data = fn(ctx, parsed)
    except ToolError as e:
        return {"error": {"code": e.code, "message": e.message}}
    return {"data": data, "source": {"tool": name, "args": parsed.model_dump(mode="json", exclude_none=True),
                                     "run_id": ctx.run_id, "day": ctx.day}}


def canonical(result: dict) -> str:
    """The bytes a result is compared and cached by (SPEC §8: keys sorted, no whitespace, UTF-8)."""
    return json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
