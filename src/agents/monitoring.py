"""Monitoring agent: pathway rules, patient deviations and regional alarms (SPEC §9 step 4; delivery plan 2.8).

Rules only, no LLM. Every tick it evaluates the pathway's rules over the state engine (engine.rules) and:

- sets `flags` in pathway_state while a flag rule holds (written where they changed);
- pulls a step earlier when a step rule starts to hold (for example a visit within 7 days after a weight
  gain); the next sweep of the state engine shows the new deadline;
- records each new deviation in `deviations`: a rule that starts to hold, or a step that becomes overdue
  (Intervention, step 2.13, acts on them);
- raises a patient alert on the stream for the new deviations of a high-risk patient (D39: about 8 a day
  instead of 160);
- raises a regional alarm when a facility's mean wait for a step, over the bookings of the last 7 days, is
  longer than the step's `max_wait_days`, and closes it when the wait falls back. The wait comes from the
  `wait_by_hospital` tool, so the number in the alarm is the one the Investigator and the Verifier see.

Texts are filled by code from the pathway's names (AC17).
"""

import json

import duckdb
import numpy as np
import pandas as pd

from agents import tools
from engine import rules
from engine.db import tool_cursor
from engine.pathway import Pathway
from engine.risk import HIGH_RISK, RiskModel
from engine.state import NEVER, StateEngine

WAIT_WINDOW_DAYS = 7  # bookings of the last week (PDTA §3)
ALERT_COLUMNS = ["alert_id", "day", "level", "pathway_id", "patient_id", "facility_id", "step", "text"]


def it_number(x: float) -> str:
    return f"{x:.1f}".replace(".", ",")


class Monitoring:
    def __init__(self, pathway: Pathway, run_id: str, facility_ids: dict[str, str]):
        self.pathway, self.run_id, self.facility_ids = pathway, run_id, facility_ids
        self.flags = sorted({r.then.flag for r in pathway.rules if r.then.flag})
        self.fired: dict[str, np.ndarray] = {}      # who meets each rule today
        self.flags_written: np.ndarray | None = None  # flag bit mask per patient, as last written
        self.late_before: np.ndarray | None = None
        self.open: dict[tuple[str, str], str] = {}    # (facility_id, step) -> alert_id of the open alarm
        self.alerts = 0

    def run(self, con: duckdb.DuckDBPyConnection, state: StateEngine, risk: RiskModel, day: int,
            scenario: int) -> list[dict]:
        """One tick, after Risk. Returns the alert messages of the day (SPEC §10)."""
        before = self.fired
        self.fired = {r.id: rules.evaluate(r, state, risk.risk, day) for r in self.pathway.rules}
        new_rules = {rid: hit & ~before.get(rid, np.zeros_like(hit)) for rid, hit in self.fired.items()}
        for r in self.pathway.rules:  # a step rule pulls when it starts to hold, as `deviations` records it
            if r.then.step:
                state.pull(r.then.step, new_rules[r.id], day, r.then.due_days)
        self._write_flags(con, state, day)
        enrolled = state.enrolled_day <= day
        late = (state.due < day) & (state.due < NEVER) & enrolled
        new_late = late & ~(self.late_before if self.late_before is not None else np.zeros_like(late))
        self.late_before = late
        self._write_deviations(con, state, day, new_rules, new_late)
        return (self._patient_alerts(con, state, risk, day, scenario, new_rules, new_late)
                + self._regional_alarms(con, day, scenario))

    def _write_flags(self, con, state: StateEngine, day: int) -> None:
        """Flags as a bit mask per patient, turned into the list in SQL like the engine's overdue_steps, and
        written where they changed. A `no_dispense` rule starts and stops with every late refill, about 360
        patients a day in scenario 2, and DuckDB rewrites a whole row to change a list column: about 35 ms."""
        if not self.flags:
            return
        now = np.zeros(len(state.ids), np.int64)
        for i, f in enumerate(self.flags):
            now |= np.any([self.fired[r.id] for r in self.pathway.rules if r.then.flag == f], axis=0).astype(np.int64) << i
        before = self.flags_written if self.flags_written is not None else np.zeros_like(now)
        changed = np.flatnonzero((now != before) & (state.enrolled_day <= day))
        self.flags_written = now
        if len(changed):
            names = "[" + ", ".join(f"'{f}'" for f in self.flags) + "]"  # ids match ^[a-z][a-z0-9_]*$ (SPEC §4)
            con.register("flag_rows", pd.DataFrame({"patient_id": state.ids[changed], "mask": now[changed]}))
            con.execute(f"UPDATE pathway_state s SET flags = list_filter({names}, lambda x, i: (r.mask >> (i - 1)) & 1 = 1) "
                        "FROM flag_rows r WHERE s.patient_id = r.patient_id AND s.pathway_id = $pw",
                        {"pw": self.pathway.pathway_id})
            con.unregister("flag_rows")

    def _write_deviations(self, con, state: StateEngine, day: int, new_rules: dict, new_late: np.ndarray) -> None:
        kinds = [("rule", rid, hit) for rid, hit in new_rules.items()]
        kinds += [("overdue", s.id, new_late[j]) for j, s in enumerate(self.pathway.steps)]
        who = [np.flatnonzero(hit) for _, _, hit in kinds]
        if not sum(len(w) for w in who):
            return
        rows = pd.DataFrame({"patient_id": state.ids[np.concatenate(who)],
                             "kind": np.repeat([k for k, _, _ in kinds], [len(w) for w in who]),
                             "code": np.repeat([c for _, c, _ in kinds], [len(w) for w in who])})
        con.register("deviation_rows", rows.assign(day=np.int32(day), pathway_id=self.pathway.pathway_id))
        con.execute("INSERT INTO deviations BY NAME SELECT * FROM deviation_rows")
        con.unregister("deviation_rows")

    def _alert(self, day: int, scenario: int, level: str, text: dict, patient_id=None, facility_id=None,
               step=None) -> tuple[list, dict]:
        """A new alert: its `alerts` row, without investigation_id and closed_day, and its stream message."""
        self.alerts += 1
        row = [f"al_{self.run_id}_{self.alerts}", day, level, self.pathway.pathway_id, patient_id, facility_id, step,
               json.dumps(text, ensure_ascii=False)]
        return row, {"type": "alert", "scenario": scenario, "day": day,
                     "payload": {"level": level, "facility_id": facility_id, "investigation_id": None, "text": text}}

    def _patient_alerts(self, con, state: StateEngine, risk: RiskModel, day: int, scenario: int, new_rules: dict,
                        new_late: np.ndarray) -> list[dict]:
        new_any = np.any(list(new_rules.values()) + [new_late.any(axis=0)], axis=0)
        who = np.flatnonzero(new_any & (risk.risk >= HIGH_RISK))
        reasons = {p: {"it": [], "en": []} for p in who}
        for r in self.pathway.rules:
            idx = who[new_rules[r.id][who]]
            if len(idx):
                t = rules.texts(r, state, risk.risk, day, idx)
                for i, p in enumerate(idx):
                    reasons[p]["it"].append(t["it"][i])
                    reasons[p]["en"].append(t["en"][i])
        for j, s in enumerate(self.pathway.steps):
            for p in who[new_late[j, who]]:
                reasons[p]["it"].append(f"{s.label.it}: scadenza superata")
                reasons[p]["en"].append(f"{s.label.en}: deadline passed")
        rows, out = [], []
        for p in who:
            pid, age, comune = state.ids[p], int(state.age[p]), state.comune_name[p]
            text = {"it": f"{pid} ({age} anni, {comune}): " + "; ".join(reasons[p]["it"]),
                    "en": f"{pid} ({age}, {comune}): " + "; ".join(reasons[p]["en"])}
            row, msg = self._alert(day, scenario, "patient", text, patient_id=pid)
            rows.append(row)
            out.append(msg)
        if rows:  # one insert for the day: a single-row INSERT costs about 3 ms
            con.register("alert_rows", pd.DataFrame(rows, columns=ALERT_COLUMNS))
            con.execute("INSERT INTO alerts BY NAME SELECT * FROM alert_rows")
            con.unregister("alert_rows")
        return out

    def _regional_alarms(self, con, day: int, scenario: int) -> list[dict]:
        out = []
        with tool_cursor(con) as cur:
            ctx = tools.Context(self.run_id, tools.Query(cur), day)
            for s in self.pathway.steps:
                if s.max_wait_days is None:
                    continue
                result = tools.call(ctx, "wait_by_hospital", {"pathway_id": self.pathway.pathway_id, "step": s.id,
                                                              "period_days": WAIT_WINDOW_DAYS})
                for name, wait in sorted(result.get("data", {}).items()):
                    key = (self.facility_ids[name], s.id)
                    if wait > s.max_wait_days and key not in self.open:
                        text = {"it": f"{name} · {s.label.it}: attesa media {it_number(wait)} giorni sulle prenotazioni "
                                      f"degli ultimi {WAIT_WINDOW_DAYS} giorni (soglia PDTA {s.max_wait_days} giorni)",
                                "en": f"{name} · {s.label.en}: mean wait {wait:.1f} days over the bookings of the last "
                                      f"{WAIT_WINDOW_DAYS} days (PDTA threshold {s.max_wait_days} days)"}
                        row, msg = self._alert(day, scenario, "regional", text, facility_id=key[0], step=s.id)
                        con.execute("INSERT INTO alerts VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)", row)
                        self.open[key] = row[0]
                        out.append(msg)
                    elif wait <= s.max_wait_days and key in self.open:
                        con.execute("UPDATE alerts SET closed_day = ? WHERE alert_id = ?", [day, self.open.pop(key)])
        return out
