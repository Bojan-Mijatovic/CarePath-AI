"""The rule language of SPEC §4 over the state engine's arrays (delivery plan step 2.8).

`evaluate` gives, for one rule, who meets its condition today: every enrolled patient at once, with numpy.
`texts` says why, in Italian and English, from the clause and its values for each patient and from the
pathway's step and drug names (AC17), so a rule needs no label of its own: "Peso +2,1 kg in 3 giorni:
<step label> entro 7 giorni". A feature that does not exist for a patient (no reading ever) makes
its clause false. Monitoring (agents.monitoring) acts on the result; the worklist shows the texts.
"""

import re

import numpy as np

from engine.pathway import Pathway, Rule
from engine.state import NEVER, NO_DAY, StateEngine

OPS = {">=": np.greater_equal, ">": np.greater, "<=": np.less_equal, "<": np.less, "==": np.equal}
NUM = r"(?P<n>-?\d+(?:\.\d+)?)"
COMPARE = re.compile(rf"^(?P<f>weight_gain_kg_3d|days_since_last_reading|age|distance_km|risk_score) (?P<op>>=|>|<=|<|==) {NUM}$")
DISPENSE_COMPARE = re.compile(rf"^days_since_last_dispense\('(?P<atc>[A-Z0-9]+)'\) (?P<op>>=|>|<=|<|==) {NUM}$")
NO_DISPENSE = re.compile(r"^no_dispense\('(?P<atc>[A-Z0-9]+)', (?P<days>\d+)\)$")
OVERDUE = re.compile(r"^overdue\('(?P<step>[a-z][a-z0-9_]*)', (?P<days>\d+)\)$")
WORDS = {"it": {"and": " e ", "days": ("giorno", "giorni"), "ago": "fa", "today": "oggi", "within": "entro"},
         "en": {"and": " and ", "days": ("day", "days"), "ago": "ago", "today": "today", "within": "within"}}


def clauses(rule: Rule) -> list[str]:
    return rule.condition.split(" and ")


def _since(last: np.ndarray, day: int) -> np.ndarray:
    return np.where(last > NO_DAY, day - last, np.nan)


def _drug_row(state: StateEngine, atc: str) -> int:
    return state.pathway.eligibility.any_drug_atc.index(atc)


def values(clause: str, state: StateEngine, risk: np.ndarray, day: int) -> np.ndarray:
    """The number a clause tests, per patient (NaN where it does not exist); for a function, how far the
    patient is: days without the drug, or days overdue."""
    if m := COMPARE.match(clause):
        return {"weight_gain_kg_3d": lambda: state.weight_gain_kg_3d(day),
                "days_since_last_reading": lambda: _since(state.last_reading, day),
                "age": lambda: state.age, "distance_km": lambda: state.distance_km,
                "risk_score": lambda: risk}[m["f"]]()
    if m := DISPENSE_COMPARE.match(clause) or NO_DISPENSE.match(clause):
        return _since(state.last_drug[_drug_row(state, m["atc"])], day)
    if m := OVERDUE.match(clause):
        due = state.due[state.pos[m["step"]]]
        return np.where((due < NEVER) & (due < day), day - due, np.nan)
    raise ValueError(f"not in the rule language: {clause!r}")


def holds(clause: str, state: StateEngine, risk: np.ndarray, day: int) -> np.ndarray:
    v = values(clause, state, risk, day)
    if m := COMPARE.match(clause) or DISPENSE_COMPARE.match(clause):
        return OPS[m["op"]](v, float(m["n"])) & ~np.isnan(v)
    if m := NO_DISPENSE.match(clause):  # no dispense in the last `days` days, never collected included
        last = state.last_drug[_drug_row(state, m["atc"])]
        return last <= day - int(m["days"])
    m = OVERDUE.match(clause)
    return ~np.isnan(v) & (v >= int(m["days"]))


def evaluate(rule: Rule, state: StateEngine, risk: np.ndarray, day: int) -> np.ndarray:
    """Enrolled patients who meet every clause of the rule today."""
    hit = state.enrolled_day <= day
    for clause in clauses(rule):
        hit = hit & holds(clause, state, risk, day)
    return hit


def _days(n: int, lang: str) -> str:
    one, many = WORDS[lang]["days"]
    return f"{n} {one if n == 1 else many}"


def _ago(n: int, lang: str) -> str:
    w = WORDS[lang]
    return w["today"] if n == 0 else f"{_days(n, lang)} {w['ago']}"


def _number(x: float, lang: str) -> str:
    return f"{x:+.1f}".replace(".", ",") if lang == "it" else f"{x:+.1f}"


def clause_text(clause: str, value: float, pathway: Pathway, lang: str) -> str:
    n = 0 if np.isnan(value) else int(value)
    if m := NO_DISPENSE.match(clause):
        drug = getattr(pathway.eligibility.drug_names[m["atc"]], lang)
        return (f"{drug} non ritirato negli ultimi {_days(int(m['days']), lang)}" if lang == "it"
                else f"{drug} not collected in the last {_days(int(m['days']), lang)}")
    if m := DISPENSE_COMPARE.match(clause):
        drug = getattr(pathway.eligibility.drug_names[m["atc"]], lang)
        return f"ultimo ritiro di {drug} {_ago(n, lang)}" if lang == "it" else f"{drug} last collected {_ago(n, lang)}"
    if m := OVERDUE.match(clause):
        label = getattr(next(s for s in pathway.steps if s.id == m["step"]).label, lang)
        return f"{label} in ritardo di {_days(n, lang)}" if lang == "it" else f"{label} {_days(n, lang)} overdue"
    m = COMPARE.match(clause)
    return {"weight_gain_kg_3d": {"it": f"peso {_number(value, 'it')} kg in 3 giorni", "en": f"weight {_number(value, 'en')} kg in 3 days"},
            "days_since_last_reading": {"it": f"ultima lettura {_ago(n, 'it')}", "en": f"last reading {_ago(n, 'en')}"},
            "age": {"it": f"{n} anni", "en": f"aged {n}"},
            "distance_km": {"it": f"{value:.1f} km dall'ospedale".replace(".", ","), "en": f"{value:.1f} km from hospital"},
            "risk_score": {"it": f"rischio {value * 100:.0f}%", "en": f"risk {value * 100:.0f}%"}}[m["f"]][lang]


def texts(rule: Rule, state: StateEngine, risk: np.ndarray, day: int, idx: np.ndarray) -> dict[str, list[str]]:
    """Why the rule holds for each patient in idx, in both languages, with the action it calls for."""
    vals = [values(c, state, risk, day)[idx] for c in clauses(rule)]
    out = {}
    for lang in ("it", "en"):
        action = ""
        if rule.then.step:
            label = getattr(next(s for s in state.pathway.steps if s.id == rule.then.step).label, lang)
            action = f": {label} {WORDS[lang]['within']} {_days(rule.then.due_days, lang)}"
        rows = []
        for r in range(len(idx)):
            text = WORDS[lang]["and"].join(clause_text(c, float(v[r]), state.pathway, lang) for c, v in zip(clauses(rule), vals))
            rows.append(text[:1].upper() + text[1:] + action)
        out[lang] = rows
    return out
