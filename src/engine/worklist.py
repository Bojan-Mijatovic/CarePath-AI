"""worklist_today: who the Centro Servizi calls today, and why (SPEC §5.2, C20; delivery plan step 2.4).

One row per patient who is out of hospital and has an overdue step, a high risk or a pathway rule that
holds (Monitoring, step 2.8), ranked by risk; the top KEPT of the ranking are kept (C32, step 2.13). The reasons are texts filled by code from the pathway's step
and drug names (AC17), in Italian and English: every overdue step with its days, every rule that holds
with its values, and for a high-risk patient the chance of admission with the drivers Risk found. Rows are kept for every day, so the console can go back to the list of
day 31 (demo step 9a). The escalation step comes from pathway_state (the action service owns it);
`script` waits for the Daily Worklist agent (phase 3) and `outcome` for the call (steps 2.12 and 2.20).

The baseline arm has no worklist: it is "without CarePath" (SPEC §9).
"""

import math

import duckdb
import numpy as np
import pandas as pd

from engine import rules
from engine.risk import HIGH_RISK, RiskModel, features
from engine.state import NEVER, StateEngine

SKIPPED_DRIVERS = {"overdue_steps", "days_overdue"}  # the overdue steps are reasons of their own
# The top of the day's ranking is kept (C32): the Centro Servizi calls from the top and AC12 reads the top 20,
# while the texts of all ~2,400 patients cost the agents arm about 40 ms a tick, which AC2 has no room for
# once Intervention acts (step 2.13).
KEPT = 200
COLUMNS = ["day", "rank", "patient_id", "risk_score", "reasons_it", "reasons_en", "pathway_id"]


def it_number(x: float) -> str:
    return f"{x:.1f}".replace(".", ",")


DAY_WORDS = {"it": ("giorno", "giorni"), "en": ("day", "days")}


def days(n: int, lang: str) -> str:
    one, many = DAY_WORDS[lang]
    return f"{n} {one if n == 1 else many}"


def ago(n: int, lang: str) -> str:
    if n == 0:
        return "oggi" if lang == "it" else "today"
    return f"{days(n, lang)} {'fa' if lang == 'it' else 'ago'}"


def driver_text(name: str, value: float, female: bool, state: StateEngine) -> dict[str, str]:
    """One driver with its value, for example {"it": "vive sola", "en": "lives alone"}."""
    a = "a" if female else "o"
    n = 0 if math.isnan(value) else int(value)  # NaN never reaches a positive driver, but stay safe
    # Neutral wording: a driver says that this value raises the risk, not that something is missing (a
    # dispense 0 days ago can be a driver).
    if name.startswith("days_since_last_dispense:"):
        drug = state.pathway.eligibility.drug_names[name.split(":", 1)[1]]
        return {"it": f"ultimo ritiro di {drug.it} {ago(n, 'it')}", "en": f"{drug.en} last collected {ago(n, 'en')}"}
    texts = {
        "age": (f"{n} anni", f"aged {n}"),
        "distance_km": (f"{it_number(value)} km dall'ospedale", f"{value:.1f} km from hospital"),
        "lives_alone": (f"vive sol{a}", "lives alone"),
        "days_since_discharge": (f"dimess{a} {ago(n, 'it')}", f"discharged {ago(n, 'en')}"),
        "on_telemonitoring": ("in telemonitoraggio", "on telemonitoring"),
        "days_since_last_reading": (f"ultima lettura {ago(n, 'it')}", f"last reading {ago(n, 'en')}"),
        "weight_gain_kg_3d": (f"{'+' if value >= 0 else ''}{it_number(value)} kg in 3 giorni", f"{value:+.1f} kg in 3 days"),
    }
    it, en = texts[name]
    return {"it": it, "en": en}


def _risk_reasons(state: StateEngine, risk: RiskModel, day: int, idx: np.ndarray) -> dict[str, pd.Series]:
    """The high-risk reason of each listed patient (None for the others), with the drivers Risk found and
    their values. A loop, but over the high-risk 1% only."""
    texts = {lang: pd.Series(None, index=range(len(idx)), dtype=object) for lang in ("it", "en")}
    high = np.flatnonzero(risk.risk[idx] >= HIGH_RISK)
    x = features(state, day)[idx[high]]
    for r, p in enumerate(idx[high]):
        drivers = [driver_text(risk.names[j], float(x[r, j]), state.female[p], state)
                   for j in risk.top[p] if j >= 0 and risk.names[j] not in SKIPPED_DRIVERS]
        pct = f"{risk.risk[p] * 100:.0f}%"
        for lang, head in (("it", f"Rischio alto: {pct} di ricovero in 30 giorni"),
                           ("en", f"High risk: {pct} chance of admission in 30 days")):
            listed = ", ".join(d[lang] for d in drivers)
            texts[lang][high[r]] = f"{head} ({listed})" if drivers else head
    return texts


def _joined(columns: list[pd.Series]) -> pd.Series:
    """Each row's non-null texts joined by "; ", column by column (a row-wise apply took 160 ms a tick)."""
    out = columns[0]
    for col in columns[1:]:
        both = out.notna() & col.notna()
        out = out.where(out.notna(), col).where(~both, out + "; " + col)
    return out


def build(state: StateEngine, risk: RiskModel, day: int, fired: dict[str, np.ndarray] | None = None) -> pd.DataFrame:
    """The day's list: patient_id, rank, risk_score, reasons_it, reasons_en (state and risk updated to day).
    `fired` is who meets each pathway rule today, from Monitoring (step 2.8)."""
    fired = fired or {}
    e = (state.enrolled_day <= day) & ~state.in_hospital()
    late = (state.due < day) & (state.due < NEVER)  # per step, overdue today (SPEC §5.1)
    ruled = np.any(list(fired.values()), axis=0) if fired else np.zeros(len(e), bool)
    on_list = e & (late.any(axis=0) | (risk.risk >= HIGH_RISK) | ruled)
    idx = np.flatnonzero(on_list)
    order = np.lexsort((idx, -risk.risk[idx]))  # highest risk first; patient_id breaks ties
    idx = idx[order][:KEPT]
    if not len(idx):
        return pd.DataFrame(columns=COLUMNS)
    parts = {lang: [s] for lang, s in _risk_reasons(state, risk, day, idx).items()}
    for rule in state.pathway.rules:  # each rule that holds, with its values
        hit = np.flatnonzero(fired.get(rule.id, np.zeros(len(e), bool))[idx])
        texts = rules.texts(rule, state, risk.risk, day, idx[hit])
        for lang in parts:
            col = pd.Series(None, index=range(len(idx)), dtype=object)
            col[hit] = texts[lang]
            parts[lang].append(col)
    for j, step in enumerate(state.pathway.steps):  # every overdue step with its days, vectorised
        hit = late[j, idx]
        n = pd.Series(day - state.due[j, idx]).astype(str)
        for lang, label, middle, unit in (("it", step.label.it, " in ritardo di ", " giorni"),
                                          ("en", step.label.en, " ", " days overdue")):
            parts[lang].append((label + middle + n + unit).where(hit, None))
    reasons = {lang: _joined(cols) for lang, cols in parts.items()}
    return pd.DataFrame({"day": np.int32(day), "rank": np.arange(1, len(idx) + 1, dtype=np.int32),
                         "patient_id": state.ids[idx], "risk_score": risk.risk[idx],
                         "reasons_it": reasons["it"], "reasons_en": reasons["en"],
                         "pathway_id": state.pathway.pathway_id})


def refresh(con: duckdb.DuckDBPyConnection, state: StateEngine, risk: RiskModel, day: int,
            fired: dict[str, np.ndarray] | None = None) -> int:
    """Writes the day's worklist_today rows. Returns how many patients are on the list."""
    rows = build(state, risk, day, fired)
    con.execute("DELETE FROM worklist_today WHERE day = $d", {"d": day})
    con.register("worklist_rows", rows)
    con.execute("""
        INSERT INTO worklist_today
        SELECT w.day, w.rank, w.patient_id, w.risk_score, json_object('it', w.reasons_it, 'en', w.reasons_en),
               [w.pathway_id], ps.escalation_step, NULL, NULL
        FROM worklist_rows w JOIN pathway_state ps ON ps.patient_id = w.patient_id AND ps.pathway_id = w.pathway_id""")
    con.unregister("worklist_rows")
    return len(rows)


def record_outcomes(con: duckdb.DuckDBPyConnection, day: int) -> None:
    """The day's call outcomes on its list (SPEC §5.2 `outcome`, C20): the list is built at the start of the day
    (§9 step 6) and the calls are made by Intervention afterwards (step 8), so their CALL events are written back
    here. Step 2.20 found the column empty on screen."""
    con.execute("""
        UPDATE worklist_today w SET outcome = c.code
        FROM (SELECT patient_id, arg_max(code, CAST(substr(event_id, 4) AS BIGINT)) AS code FROM events
              WHERE event_type = 'CALL' AND day = $d GROUP BY 1) c
        WHERE w.day = $d AND w.patient_id = c.patient_id""", {"d": day})
