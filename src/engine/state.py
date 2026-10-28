"""State engine: pathway_state and kpi_daily from a run's events (SPEC §5; §9 tick steps 2 and 5).

Delivery plan step 1.22. A StateEngine follows one pathway in one run. Per patient it keeps the last day
each step was done and the latest booking per service in numpy arrays, so a day costs the same few
vectorised operations on day 1 and on day 365. `update(con, day)` reads the events it has not seen yet (the
first call reads the whole history, warm-up included), sweeps every deadline and upserts the pathway_state
rows that changed. `refresh_kpi(con, day)` writes that day's kpi_daily rows and `refresh_map(con, day)`
the map_comuni rows (step 2.2).

Steps are evaluated as SPEC §5.1 says; nothing here names a disease (AC17). A patient is enrolled, by the
MMG, with the first event that meets the pathway's eligibility. Risk (step 2.3), Monitoring (2.8) and the
action service (2.12) own risk_score and risk_drivers, flags and escalation_step: the engine inserts them
empty and never overwrites them. Rules that pull a step earlier are applied by Monitoring, not here.
"""

import duckdb
import numpy as np
import pandas as pd

from engine.db import PATHWAY_STATUSES
from engine.pathway import Pathway, Step

NO_DAY = -(10**6)  # has not happened
NEVER = 10**9      # not enrolled yet; nothing due
READMISSION_DAYS = 30
READMISSION_COST_EUR: int | None = None  # SPEC §5.2; value and source are open question Q2, so cost is NULL
DIAGNOSIS_EVENTS = ("DISCHARGE", "ADMISSION")
ON_TRACK, DUE_SOON, OVERDUE, DROPPED = range(4)  # positions in PATHWAY_STATUSES
ENGINE_COLUMNS = ("current_step", "next_step", "next_due_day", "next_booked_day", "status", "overdue_steps",
                  "last_event_day", "updated_day")
# map_comuni (SPEC §5.2, C18): the same windows as the tools' dispensing and telemonitoring measures (§6)
DRUG_WINDOW_DAYS = 60
READING_WINDOW_DAYS = 7
MAP_MIN_PATIENTS = 10  # fewer, and a comune has no adherence and no alarm
MAP_ALARM_BELOW = 0.5  # the prototype's low band (< 50%)


def matches(codes: pd.Series, patterns: list[str]) -> np.ndarray:
    """Codes against a pathway list; a trailing * matches a prefix (SPEC §4)."""
    hit = np.zeros(len(codes), bool)
    for p in patterns:
        hit = hit | (codes.str.startswith(p[:-1]) if p.endswith("*") else codes == p).fillna(False).to_numpy(bool)
    return hit


def _nullable(values: np.ndarray, present: np.ndarray) -> pd.arrays.IntegerArray:
    return pd.arrays.IntegerArray(np.where(present, values, 0).astype(np.int32), ~present)


class StateEngine:
    def __init__(self, con: duckdb.DuckDBPyConnection, pathway: Pathway):
        self.pathway = pathway
        patients = con.execute("SELECT patient_id, asst_id, comune_istat FROM patients ORDER BY patient_id").df()
        self.ids = pd.Index(patients.patient_id)
        self.asst = patients.asst_id.to_numpy(object)
        self.comune = patients.comune_istat.to_numpy(object)
        n, k = len(patients), len(pathway.steps)
        self.step_ids = np.array([s.id for s in pathway.steps], object)
        self.pos = {s.id: j for j, s in enumerate(pathway.steps)}
        self.starts = [j for j, s in enumerate(pathway.steps) if s.after is None and s.every_days is None]

        self.enrolled_day = np.full(n, NEVER)
        self.last_event = np.full(n, NO_DAY)
        self.own = np.full((k, n), NO_DAY)         # last event of the step's own type
        self.done = np.full((k, n), NO_DAY)        # same, plus readings for a telemonitoring step
        self.booked_on = np.full((k, n), NO_DAY)   # latest BOOKING of the step's service ...
        self.booked_for = np.full((k, n), NO_DAY)  # ... and the day it is booked for
        self.last_drug = np.full((len(pathway.eligibility.any_drug_atc), n), NO_DAY)  # last DISPENSE per drug
        self.telemon_started = np.zeros(n, bool)  # ever a TELEMON_START or reading, warm-up included
        self.last_reading = np.full(n, NO_DAY)
        self.last_index_discharge = np.full(n, NO_DAY)
        self.index_discharges = np.zeros(n, np.int64)  # from day 0, for kpi_daily
        self.readmissions = np.zeros(n, np.int64)

        self.day: int | None = None
        self.seen = np.empty(0, object)  # ids of the events of `day` already applied
        self.status = np.zeros(n, np.int64)
        self.written: np.ndarray | None = None  # engine columns as last written, to find changed rows
        self.units = {"ats": (np.zeros(n, np.int64), np.array(["ats"], object)),  # level -> (code per patient, keys)
                      "asst": pd.factorize(self.asst, sort=True), "comune": pd.factorize(self.comune, sort=True)}

    def update(self, con: duckdb.DuckDBPyConnection, day: int) -> int:
        """Apply the events up to `day` not seen yet, sweep deadlines and upsert changed rows. Returns how many
        rows were written. Events recorded on `day` after this call (actions, SPEC §9) are applied next time."""
        if self.day is not None and day < self.day:
            raise ValueError(f"day {day} is before day {self.day}; replay from the start with a new engine")
        cols = "event_id, patient_id, day, event_type, code, value"
        if self.day is None:
            ev = con.execute(f"SELECT {cols} FROM events WHERE day <= $d", {"d": day}).df()
        else:
            ev = con.execute(f"SELECT {cols} FROM events WHERE day BETWEEN $a AND $d", {"a": self.day, "d": day}).df()
            ev = ev[~ev.event_id.isin(self.seen)]
        today = ev.event_id[ev.day == day].to_numpy(object)
        self.seen = np.concatenate([self.seen, today]) if day == self.day else today
        self.day = day
        self._apply(ev)
        return self._write(con, day, *self._sweep(day))

    def _is_step(self, s: Step, etype: pd.Series, code: pd.Series) -> np.ndarray:
        hit = (etype == s.event).to_numpy(bool)
        if s.codes:
            hit = hit & matches(code, s.codes)
        if s.specialty:
            hit = hit & (code == s.specialty).fillna(False).to_numpy(bool)
        if s.loinc:
            hit = hit & matches(code, s.loinc)
        return hit

    def _apply(self, ev: pd.DataFrame) -> None:
        if not len(ev):
            return
        i = self.ids.get_indexer(ev.patient_id)
        if (i < 0).any():
            raise ValueError(f"events for patients not in `patients`: {sorted(set(ev.patient_id[i < 0]))[:5]}")
        day, etype, code = ev.day.to_numpy(np.int64), ev.event_type, ev.code
        np.maximum.at(self.last_event, i, day)
        elig = self.pathway.eligibility
        diagnosis = etype.isin(DIAGNOSIS_EVENTS).to_numpy(bool) & matches(code, elig.any_diagnosis)
        eligible = diagnosis | ((etype == "DISPENSE").to_numpy(bool) & matches(code, elig.any_drug_atc))
        np.minimum.at(self.enrolled_day, i[eligible], day[eligible])
        reading = (etype == "TELEMON_READING").to_numpy(bool)
        booking = (etype == "BOOKING").to_numpy(bool)
        dispense = (etype == "DISPENSE").to_numpy(bool)
        for r, atc in enumerate(elig.any_drug_atc):
            hit = dispense & matches(code, [atc])
            np.maximum.at(self.last_drug[r], i[hit], day[hit])
        self.telemon_started[i[reading | (etype == "TELEMON_START").to_numpy(bool)]] = True
        np.maximum.at(self.last_reading, i[reading], day[reading])
        for j, s in enumerate(self.pathway.steps):
            own = self._is_step(s, etype, code)
            np.maximum.at(self.own[j], i[own], day[own])
            done = own | reading if s.event == "TELEMON_START" else own
            np.maximum.at(self.done[j], i[done], day[done])
            if s.service:
                self._book(j, i, day, ev.value.to_numpy(float), booking & (code == s.service).fillna(False).to_numpy(bool))
        index_discharge = (etype == "DISCHARGE").to_numpy(bool) & diagnosis
        unplanned = (etype == "ADMISSION").to_numpy(bool) & (ev.value == 1).to_numpy(bool)
        self._readmissions(i, day, index_discharge, unplanned)

    def _book(self, j: int, i: np.ndarray, day: np.ndarray, value: np.ndarray, hit: np.ndarray) -> None:
        if not hit.any():
            return
        b = (pd.DataFrame({"i": i[hit], "on": day[hit], "for": value[hit].astype(np.int64)})
             .sort_values(["on", "for"]).drop_duplicates("i", keep="last"))
        bi, on = b.i.to_numpy(), b.on.to_numpy()
        newer = on >= self.booked_on[j, bi]
        self.booked_on[j, bi[newer]] = on[newer]
        self.booked_for[j, bi[newer]] = b["for"].to_numpy()[newer]

    def _readmissions(self, i: np.ndarray, day: np.ndarray, discharge: np.ndarray, admission: np.ndarray) -> None:
        """SPEC §5.2: an unplanned ADMISSION within 30 days after a DISCHARGE with the pathway's diagnosis."""
        if admission.any():
            a = pd.DataFrame({"i": i[admission], "day": day[admission]}).sort_values("day")
            d = pd.DataFrame({"i": i[discharge], "dday": day[discharge]}).sort_values("dday")
            a = pd.merge_asof(a, d, left_on="day", right_on="dday", by="i", allow_exact_matches=False)
            ai = a.i.to_numpy()
            prev = np.where(a.dday.isna(), self.last_index_discharge[ai], a.dday.fillna(0)).astype(np.int64)
            hit = (a.day.to_numpy() >= 0) & (a.day.to_numpy() - prev <= READMISSION_DAYS)
            np.add.at(self.readmissions, ai[hit], 1)
        np.add.at(self.index_discharges, i[discharge & (day >= 0)], 1)
        np.maximum.at(self.last_index_discharge, i[discharge], day[discharge])

    def _sweep(self, day: int) -> tuple:
        """Status of every patient on `day` (SPEC §5.1)."""
        steps, th = self.pathway.steps, self.pathway.status_thresholds
        k, n = self.own.shape
        start = self.own[self.starts].max(axis=0) if self.starts else np.full(n, NO_DAY)
        due = np.full((k, n), NEVER)
        for j, s in enumerate(steps):
            if s.after is not None:
                anchor = self.own[self.pos[s.after]]
                pending = (anchor > NO_DAY) & (self.done[j] < anchor)
                due[j] = np.where(pending, anchor + s.due_days, NEVER)
            elif s.every_days is not None:
                due[j] = np.minimum(np.maximum.reduce([self.done[j], start, self.enrolled_day]) + s.every_days, NEVER)
        pending = due < NEVER
        left = due - day
        overdue = pending & (left < 0)
        booked = (self.booked_for >= day) & (self.booked_on > self.done)
        due_soon = pending & (left >= 0) & (left <= th.due_soon_days) & ~booked
        n_overdue = overdue.sum(axis=0)
        worst = np.where(overdue, -left, 0).max(axis=0)
        dropped = (n_overdue >= th.dropped_if_overdue_steps) | (worst > th.dropped_after_days)
        self.status = np.select([dropped, n_overdue > 0, due_soon.any(axis=0)], [DROPPED, OVERDUE, DUE_SOON], ON_TRACK)

        cols = np.arange(n)
        nxt = due.argmin(axis=0)
        next_due = due[nxt, cols]
        has_next = next_due < NEVER
        next_booked = np.where(has_next & booked[nxt, cols], self.booked_for[nxt, cols], NO_DAY)
        cur = k - 1 - self.own[::-1].argmax(axis=0)  # latest step done; a tie goes to the later step
        has_cur = self.own.max(axis=0) > NO_DAY
        overdue_mask = (overdue * (1 << np.arange(k))[:, None]).sum(axis=0)
        return cur, has_cur, nxt, has_next, next_due, next_booked, overdue_mask

    def _write(self, con, day, cur, has_cur, nxt, has_next, next_due, next_booked, overdue_mask) -> int:
        """Insert newly enrolled patients and update the rows that changed. DuckDB rewrites a whole row to
        change a list column (about 13 ms per 1,000 rows, against 2 ms for scalars), and readings change
        last_event_day for thousands of patients a day, so overdue_steps is written only where it changed."""
        enrolled = self.enrolled_day <= day
        state = np.stack([self.enrolled_day, np.where(has_cur, cur, -1), np.where(has_next, nxt, -1),
                          np.where(has_next, next_due, NO_DAY), next_booked, self.status, self.last_event, overdue_mask])
        before = self.written if self.written is not None else np.full_like(state, NEVER)
        self.written = state
        new = enrolled & (before[0] == NEVER)
        changed = enrolled & ~new & (state[:-1] != before[:-1]).any(axis=0)
        relisted = enrolled & ~new & (state[-1] != before[-1])
        c = np.flatnonzero(new | changed | relisted)
        if not len(c):
            return 0
        rows = pd.DataFrame({
            "patient_id": self.ids[c],
            "pathway_id": self.pathway.pathway_id,
            "enrolled_day": self.enrolled_day[c].astype(np.int32),
            "current_step": np.where(has_cur[c], self.step_ids[cur[c]], None),
            "next_step": np.where(has_next[c], self.step_ids[nxt[c]], None),
            "next_due_day": _nullable(next_due[c], has_next[c]),
            "next_booked_day": _nullable(next_booked[c], next_booked[c] > NO_DAY),
            "status": np.array(PATHWAY_STATUSES, object)[self.status[c]],
            "last_event_day": _nullable(self.last_event[c], self.last_event[c] > NO_DAY),
            "updated_day": np.int32(day),
            "overdue_mask": overdue_mask[c],
        })
        steps = "[" + ", ".join(f"'{s}'" for s in self.step_ids) + "]"  # ids match ^[a-z][a-z0-9_]*$ (SPEC §4)
        overdue_steps = f"list_filter({steps}, lambda x, i: (overdue_mask >> (i - 1)) & 1 = 1)"
        key = "s.patient_id = r.patient_id AND s.pathway_id = r.pathway_id"
        for part, sql in [
            (new, f"""INSERT INTO pathway_state BY NAME
                      SELECT * EXCLUDE (overdue_mask), {overdue_steps} AS overdue_steps, 'mmg' AS enrolled_by,
                             0 AS escalation_step, 0.0 AS risk_score, []::VARCHAR[] AS risk_drivers, []::VARCHAR[] AS flags
                      FROM state_rows"""),
            (changed, f"""UPDATE pathway_state s SET {", ".join(f"{col} = r.{col}" for col in ENGINE_COLUMNS if col != "overdue_steps")}
                          FROM state_rows r WHERE {key}"""),
            (relisted, f"""UPDATE pathway_state s SET overdue_steps = {overdue_steps.replace("overdue_mask", "r.overdue_mask")},
                           updated_day = r.updated_day FROM state_rows r WHERE {key}"""),
        ]:
            if part.any():
                con.register("state_rows", rows[part[c]])
                con.execute(sql)
                con.unregister("state_rows")
        return len(c)

    def refresh_kpi(self, con: duckdb.DuckDBPyConnection, day: int) -> None:
        """kpi_daily rows of `day` for the ATS, each ASST and each comune (SPEC §5.2), after update(day).
        Patients count where they live; actions count where their patient lives, and at ATS level only
        when they have no patient."""
        if day != self.day:
            raise ValueError(f"refresh_kpi({day}) needs update({day}) first")
        if day < 0:
            raise ValueError("KPIs start at day 0 (SPEC §2)")
        e = self.enrolled_day <= day
        per_patient = {"patients": e, "on_track": e & (self.status == ON_TRACK), "overdue": e & (self.status == OVERDUE),
                       "dropped": e & (self.status == DROPPED), "readmissions_30d": np.where(e, self.readmissions, 0),
                       "discharges": np.where(e, self.index_discharges, 0)}
        actions = con.execute("""
            SELECT p.asst_id AS asst, p.comune_istat AS comune,
                   count(*) FILTER (WHERE a.status = 'executed' AND a.executed_day <= $d) AS actions_executed,
                   count(*) FILTER (WHERE a.status = 'proposed' AND a.created_day <= $d) AS actions_pending
            FROM actions a LEFT JOIN patients p USING (patient_id)
            WHERE a.pathway_id = $pathway GROUP BY ALL""", {"d": day, "pathway": self.pathway.pathway_id}).df()
        frames = []
        for level, (code, keys) in self.units.items():
            g = pd.DataFrame({name: np.bincount(code, weights=v, minlength=len(keys)).astype(np.int64)
                              for name, v in per_patient.items()})
            g["key"], g["level"] = keys, level
            a = actions.assign(ats="ats").dropna(subset=[level]).groupby(level)[["actions_executed", "actions_pending"]].sum()
            g = g.join(a, on="key").fillna({"actions_executed": 0, "actions_pending": 0})
            frames.append(g[g.patients > 0])
        kpi = pd.concat(frames, ignore_index=True)
        rate = (kpi.readmissions_30d / kpi.discharges.where(kpi.discharges > 0)).round(4)
        kpi = kpi.assign(day=np.int32(day), pathway_id=self.pathway.pathway_id,
                         on_track_pct=(kpi.on_track / kpi.patients).round(4),
                         readmission_rate_30d=rate.astype("Float64"),
                         est_readmission_cost_eur=(pd.array([pd.NA] * len(kpi), dtype="Int64") if READMISSION_COST_EUR is None
                                                   else kpi.readmissions_30d * READMISSION_COST_EUR))
        kpi = kpi.drop(columns=["on_track", "discharges"]).astype({"actions_executed": np.int64, "actions_pending": np.int64})
        self._replace(con, "kpi_daily", kpi, day)

    def refresh_map(self, con: duckdb.DuckDBPyConnection, day: int) -> None:
        """map_comuni rows on `day` (SPEC §5.2, C18), after update(day). `adherence_pct` is the share of
        enrolled patients who are on track, collected every drug of the pathway in the last 60 days and, if
        they ever started telemonitoring, sent a reading in the last 7 days. A comune with fewer than 10
        patients has no adherence and no alarm. risk_mean and high_risk_patients come with Risk (step 2.3)."""
        if day != self.day:
            raise ValueError(f"refresh_map({day}) needs update({day}) first")
        e = self.enrolled_day <= day
        drugs = (self.last_drug > day - DRUG_WINDOW_DAYS).all(axis=0)
        reading = ~self.telemon_started | (self.last_reading > day - READING_WINDOW_DAYS)
        code, keys = self.units["comune"]
        count = lambda v: np.bincount(code, weights=v, minlength=len(keys))
        patients = count(e)
        adherence = (count(e & (self.status == ON_TRACK) & drugs & reading) / np.maximum(patients, 1)).round(4)
        discharges = count(np.where(e, self.index_discharges, 0))
        rate = (count(np.where(e, self.readmissions, 0)) / np.maximum(discharges, 1)).round(4)
        enough = patients >= MAP_MIN_PATIENTS
        none = np.ones(len(keys), bool)
        rows = pd.DataFrame({
            "comune_istat": keys, "pathway_id": self.pathway.pathway_id,
            "adherence_pct": pd.arrays.FloatingArray(adherence, ~enough),
            "risk_mean": pd.arrays.FloatingArray(np.zeros(len(keys)), none),
            "high_risk_patients": pd.arrays.IntegerArray(np.zeros(len(keys), np.int32), none),
            "readmission_rate_30d": pd.arrays.FloatingArray(rate, discharges == 0),
            "alarm": enough & (adherence < MAP_ALARM_BELOW),
        })[patients > 0]
        self._replace(con, "map_comuni", rows)

    def _replace(self, con: duckdb.DuckDBPyConnection, table: str, rows: pd.DataFrame, day: int | None = None) -> None:
        """This pathway's rows of `table` (of `day`, for a table by day) replaced by `rows`."""
        # Delete, then insert: INSERT OR REPLACE checks the key against every earlier day and costs 4 times more.
        con.execute(f"DELETE FROM {table} WHERE pathway_id = $pathway" + ("" if day is None else " AND day = $d"),
                    {"pathway": self.pathway.pathway_id} | ({} if day is None else {"d": day}))
        con.register("new_rows", rows)
        con.execute(f"INSERT INTO {table} BY NAME SELECT * FROM new_rows")
        con.unregister("new_rows")
