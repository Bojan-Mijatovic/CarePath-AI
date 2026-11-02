"""Intervention agent (SPEC §9 step 6; delivery plan step 2.13): rules choose the action, the action service
runs it within the autonomy levels (SPEC §7). No LLM: every rationale is a template filled by code from the
pathway's names and the values behind the deviation (D17, AC17).

Each day, on the agents arm, after Monitoring and the worklist:

- **Escalation ladder** (the pathway's `escalation`, SPEC §4) for every open problem of a patient: a flag rule
  that holds (a drug not collected) or a step overdue and not booked. When it opens: a reminder, or at once a
  Centro Servizi call for a high-risk patient. Still open `call_after_days` later: a call. Still open
  `mmg_after_days` later: the patient goes into one proposal a day to notify the MMGs (level 2, it waits for
  the manager). A problem that closes starts the ladder again next time.
- **Warning sign**: a step rule that starts to hold (a weight gain that pulls a visit) gets a call that day.
- **Wait alarm** (D53): only after Monitoring has opened a regional wait alarm, one proposal a day to move
  the facility's patients booked beyond the step's `max_wait_days` to the hospital with the most free slots.
- **Capacity** (D45, step 2.27): on the day the wait alarm of the engine's proposed lever opens, one proposal
  to add that many slots a day at the facility. The lever is code's choice over the what-if grid
  (`whatif.proposed_lever`), handed in by the engine; buying is the manager's decision outside the system,
  so the proposal always waits (fixed level 1) and changes nothing in the run when approved (C34). Its
  rationale is a template; the demo shows the 30B model's sentence from the cache when every number and
  the facility in it are the template's (D17), and the template otherwise.

Each action's payload names the effect the simulator gives it (`collect`, `book`, `start`, `review`, SPEC §7.1,
C32). `escalation_step` in pathway_state follows the ladder: 1 reminder, 2 call, 3 MMG notified.
"""

import json
import logging
import re

import numpy as np
import pandas as pd
from pydantic import BaseModel

from agents import actions, llm, tools, verifier
from engine import rules
from engine.db import tool_cursor
from engine.pathway import Pathway
from engine.risk import HIGH_RISK
from engine.state import NEVER, NO_DAY, StateEngine

AGENT = "intervention"
log = logging.getLogger("carepath.intervention")
# v1, measured on the 3 scenarios (2 Nov 2026): all 3 failed the check and fell to the template; the Italian
# of scenario 1 left out the hospital, and the translation of 2 and 3 wrote "Hospital B" for "Ospedale B".
# v2: the sentence opens with the facility's name, and the translation keeps facility names in Italian: the
# Italian passed in all 3, the translation still wrote "Hospital A/B/C" in all 3. Translate v3: code puts a
# placeholder for the name before the 4B model and the name back after it.
CAPACITY_VERSION = "capacity-proposal-v2"
TRANSLATE_VERSION = "capacity-translate-v3"
PLACEHOLDER = "OSP_1"
CAPACITY_SYSTEM = """Sei l'agente Intervention di CarePath AI per l'ATS della Val Padana. Scrivi per il \
management una proposta di due frasi in italiano: il problema di attesa e l'aumento di capacità che la \
simulazione indica. La prima parola è il nome della struttura, scritto come nei dati. Usa solo i nomi e i \
numeri dei dati, scritti come sono; non aggiungere numeri, cause, costi o diagnosi. Chiudi dicendo che la \
decisione spetta al management."""
CAPACITY_TRANSLATE = f"""Traduci in inglese questo testo. Mantieni i numeri e la sigla {PLACEHOLDER} \
esattamente come sono.

{{text}}"""
FREE_DAYS = 21  # free_slots' default horizon, the "next three weeks" of the proposal
# A booking further ahead than this is moved after a wait alarm: only those beyond the step's max_wait_days
# were 3 a day in scenario 2, too few to shorten the queue (step 2.13)
MOVE_AFTER_DAYS = 14
STREAM_ACTIONS = 10  # action messages pushed per tick; GET /api/actions has every one (C32)
PRIORITY = {"reschedule": 0, "notify_mmg": 1, "call_task": 2, "reminder": 3}
PHRASE = {
    "call_high": {"it": "Rischio alto: chiamata del Centro Servizi, senza promemoria.",
                  "en": "High risk: Centro Servizi call, no reminder first."},
    "call_late": {"it": "Ancora aperto {n} giorni dopo il promemoria: chiamata del Centro Servizi.",
                  "en": "Still open {n} days after the reminder: Centro Servizi call."},
    "call_sign": {"it": "Chiamata del Centro Servizi oggi.", "en": "Centro Servizi call today."},
}


class Wording(BaseModel):
    testo: str


class Translation(BaseModel):
    text: str


class Reason:
    """One kind of open problem: a flag rule or an overdue step, with the effect an action has on it."""

    def __init__(self, key: str, effect: str | None, step: str | None = None, rule=None, j: int | None = None):
        self.key, self.effect, self.step, self.rule, self.j = key, effect, step, rule, j

    def tag(self) -> dict:
        """What an action's payload says about the problem: the rule or step id, and the effect (C32)."""
        return ({"rule": self.rule.id} if self.rule is not None else {"step": self.step}) | (
            {"effect": self.effect} if self.effect else {})

    def evidence(self, run_id: str, day: int) -> list[dict]:
        """Monitoring's rule or deadline behind the action, the source of a patient action (C32)."""
        return [({"rule": self.rule.id} if self.rule is not None else {"step": self.step}) | {"run_id": run_id, "day": day}]


class Intervention:
    def __init__(self, pathway: Pathway, run_id: str, facility_names: dict[str, str], n: int,
                 proposal: dict | None = None):
        """`proposal` is the engine's proposed lever (`whatif.proposed_lever`), None without one."""
        self.pathway, self.run_id, self.names = pathway, run_id, facility_names
        self.proposal = proposal
        self.esc = pathway.escalation
        self.reasons: list[Reason] = []
        for r in pathway.rules:
            if r.then.flag:  # a drug not collected: the effect is a collection; another flag: a contact only
                drug = any(rules.NO_DISPENSE.match(c) for c in rules.clauses(r))
                self.reasons.append(Reason(f"rule:{r.id}", "collect" if drug else None, rule=r))
        for j, s in enumerate(pathway.steps):
            if s.service or s.event == "TELEMON_START":
                self.reasons.append(Reason(f"step:{s.id}", "book" if s.service else "start", step=s.id, j=j))
        self.signs = [r for r in pathway.rules if r.then.step]  # a step rule is a warning sign
        self.opened = {r.key: np.full(n, NO_DAY) for r in self.reasons}  # day the problem opened, per patient
        self.called = {r.key: np.zeros(n, bool) for r in self.reasons}
        self.offered = {r.key: np.zeros(n, bool) for r in self.reasons}  # put in an MMG proposal
        self.esc_written = np.zeros(n, np.int64)

    def run(self, con, state: StateEngine, risk: np.ndarray, monitoring, day: int, emit) -> list[dict]:
        """One tick. Returns the action rows created today (SPEC §7.1)."""
        out_of_hospital = (state.enrolled_day <= day) & ~state.in_hospital()
        high = (risk >= HIGH_RISK) & self.esc.high_risk_skips_reminder
        items, mmg = [], []
        for r in self.reasons:
            open_now = out_of_hospital & self._open(r, state, monitoring, day)
            opened, called, offered = self.opened[r.key], self.called[r.key], self.offered[r.key]
            closed = ~open_now
            opened[closed], called[closed], offered[closed] = NO_DAY, False, False
            new = open_now & (opened == NO_DAY)
            opened[new] = day
            age = day - opened
            call_now = (new & high) | (open_now & ~called & (age == self.esc.call_after_days))
            remind = new & ~high
            called |= call_now
            items += self._reminders(state, day, r, np.flatnonzero(remind))
            for idx, kind in ((np.flatnonzero(new & high), "call_high"), (np.flatnonzero(call_now & ~new), "call_late")):
                items += self._patient_actions(state, risk, day, r, idx, kind)
            due = np.flatnonzero(open_now & ~offered & (age >= self.esc.mmg_after_days))
            mmg += [(i, r) for i in due]
        for rule in self.signs:
            idx = np.flatnonzero(monitoring.new_rules.get(rule.id, np.zeros(len(state.ids), bool)) & out_of_hospital)
            items += self._patient_actions(state, risk, day, Reason(f"rule:{rule.id}", "review", rule=rule), idx, "call_sign")
        items += self._mmg_proposal(con, state, day, mmg)
        items += self._reschedules(con, monitoring, day)
        items += self._capacity_proposal(con, monitoring, day)
        rows = actions.create_many(con, self.run_id, day, items, emit)
        self._write_escalation(con, state)
        return rows

    def _open(self, r: Reason, state: StateEngine, monitoring, day: int) -> np.ndarray:
        if r.rule is not None:
            return monitoring.fired.get(r.rule.id, np.zeros(len(state.ids), bool))
        late = (state.due[r.j] < day) & (state.due[r.j] < NEVER)
        return late & (state.booked_for[r.j] <= day)  # overdue and not booked for a coming day

    def _reminders(self, state: StateEngine, day: int, r: Reason, idx: np.ndarray) -> list[dict]:
        """One reminder action a day per kind of problem, for all its patients: a few hundred SMS a day as one
        row each cost the tick about 40 ms (step 2.13). Each patient still gets a REMINDER event."""
        if not len(idx):
            return []
        if r.rule is not None:
            why = {lang: rules.clause_text(rules.clauses(r.rule)[0], np.nan, self.pathway, lang) for lang in ("it", "en")}
        else:
            label = self.pathway.steps[r.j].label
            why = {"it": f"{label.it} in ritardo", "en": f"{label.en} overdue"}
        k = len(idx)
        return [{"agent": AGENT, "type": "reminder", "pathway_id": self.pathway.pathway_id, "scope": {"patients": k},
                 "payload": r.tag() | {"patients": list(state.ids[idx])},
                 "rationale": {"it": f"{why['it']}: {k} pazienti. Promemoria SMS a ciascuno.",
                               "en": f"{why['en']}: {k} patients. An SMS reminder to each."},
                 "evidence": r.evidence(self.run_id, day)}]

    def _patient_actions(self, state, risk, day: int, r: Reason, idx: np.ndarray, kind: str) -> list[dict]:
        if not len(idx):
            return []
        if r.rule is not None:
            why = rules.texts(r.rule, state, risk, day, idx)
        else:
            s = self.pathway.steps[r.j]
            n = day - state.due[r.j, idx]
            why = {"it": [f"{s.label.it} in ritardo di {k} giorni" for k in n],
                   "en": [f"{s.label.en} {k} days overdue" for k in n]}
        phrase, payload, evidence = PHRASE[kind], r.tag(), r.evidence(self.run_id, day)
        return [{"agent": AGENT, "type": "call_task",
                 "patient_id": state.ids[i], "pathway_id": self.pathway.pathway_id, "payload": payload,
                 "rationale": {lang: f"{why[lang][k]}. {phrase[lang].format(n=self.esc.call_after_days)}"
                               for lang in ("it", "en")}, "evidence": evidence}
                for k, i in enumerate(idx)]

    def _mmg_proposal(self, con, state: StateEngine, day: int, due: list[tuple[int, Reason]]) -> list[dict]:
        """One proposal a day for every patient still open after mmg_after_days, unless one is waiting."""
        if not due or con.execute("SELECT count(*) FROM actions WHERE type = 'notify_mmg' AND status = 'proposed'").fetchall()[0][0]:
            return []
        for i, r in due:
            self.offered[r.key][i] = True
        patients = [{"patient_id": state.ids[i]} | r.tag() for i, r in due]
        k, d = len({p["patient_id"] for p in patients}), self.esc.mmg_after_days
        return [{"agent": AGENT, "type": "notify_mmg", "pathway_id": self.pathway.pathway_id,
                 "scope": {"patients": k}, "payload": {"patients": patients},
                 "rationale": {"it": f"{k} pazienti con un problema aperto da almeno {d} giorni, dopo promemoria e "
                                     "chiamata: avvisare il loro MMG.",
                               "en": f"{k} patients with a problem open for at least {d} days, after a reminder and a "
                                     "call: notify their MMG."},
                 "evidence": [{"open_days": d, "run_id": self.run_id, "day": day}]}]

    def _reschedules(self, con, monitoring, day: int) -> list[dict]:
        """D53: for each open regional wait alarm, one proposal to move the patients booked there more than
        MOVE_AFTER_DAYS ahead to the hospital with the most free slots, as many as it has, unless one is
        waiting. The simulator moves a booking only to an earlier slot."""
        out = []
        for (facility, step_id), _ in sorted(monitoring.open.items()):
            if facility == "group":
                continue
            s = next(x for x in self.pathway.steps if x.id == step_id)
            if con.execute("""SELECT count(*) FROM actions WHERE type = 'reschedule' AND status = 'proposed'
                              AND json_extract_string(payload, '$.from_facility') = $f""", {"f": facility}).fetchall()[0][0]:
                continue
            with tool_cursor(con) as cur:
                free = tools.call(tools.Context(self.run_id, tools.Query(cur), day), "free_slots",
                                  {"service": s.service, "horizon_days": FREE_DAYS})
            ids = {name: fid for fid, name in self.names.items()}
            options = {n: v for n, v in free.get("data", {}).items() if ids.get(n) != facility and v > 0}
            wait = monitoring.waits.get(step_id, {})
            if not options or "data" not in wait:
                continue
            to_name = max(sorted(options), key=options.get)
            patients = [p for (p,) in con.execute("""
                SELECT patient_id FROM (
                    SELECT patient_id, arg_max(facility_id, day) AS f, arg_max(value, day) AS v FROM events
                    WHERE event_type = 'BOOKING' AND code = $service AND day >= $d - 60 GROUP BY 1)
                WHERE f = $f AND v > $d + $after ORDER BY v DESC, patient_id LIMIT $k""",
                {"service": s.service, "d": day, "f": facility, "after": MOVE_AFTER_DAYS, "k": options[to_name]}).fetchall()]
            if not patients:
                continue
            from_name, w = self.names[facility], wait["data"][self.names[facility]]
            out.append({
                "agent": AGENT, "type": "reschedule", "pathway_id": self.pathway.pathway_id,
                "scope": {"facility_id": facility, "patients": len(patients)},
                "payload": {"from_facility": facility, "to_facility": ids[to_name], "service": s.service,
                            "patients": sorted(patients)},
                "rationale": {
                    "it": f"{from_name}: attesa media per {s.label.it} {f'{w:.1f}'.replace('.', ',')} giorni, oltre i "
                          f"{s.max_wait_days} del PDTA; {to_name} ha {options[to_name]} posti liberi nei prossimi "
                          f"{FREE_DAYS} giorni. Spostare {len(patients)} pazienti con l'appuntamento tra più di "
                          f"{MOVE_AFTER_DAYS} giorni, dove {to_name} offre un posto prima.",
                    "en": f"{from_name}: mean wait for {s.label.en} {w:.1f} days, over the PDTA's {s.max_wait_days}; "
                          f"{to_name} has {options[to_name]} free slots in the next {FREE_DAYS} days. Move "
                          f"{len(patients)} patients whose appointment is more than {MOVE_AFTER_DAYS} days away, "
                          f"where {to_name} has an earlier slot."},
                "evidence": [wait["source"], free["source"]]})
        return out

    def _capacity_proposal(self, con, monitoring, day: int) -> list[dict]:
        """Once a run, while the proposed lever's wait alarm is open: add its slots at the facility (D45)."""
        p = self.proposal
        if p is None or (p["lever"].facility_id, p["step"]) not in monitoring.open or "data" not in monitoring.waits.get(p["step"], {}):
            return []
        if con.execute("SELECT count(*) FROM actions WHERE type = 'capacity_proposal'").fetchall()[0][0]:
            return []
        s = next(x for x in self.pathway.steps if x.id == p["step"])
        wait, lever, k = monitoring.waits[p["step"]], p["lever"], p["extra_slots"]
        name, w, b = p["facility"], wait["data"][p["facility"]], p["base_slots"]
        it = lambda x: f"{x:.1f}".replace(".", ",")
        one = k == 1
        slots = {"it": "posto" if one else "posti", "en": "slot" if one else "slots"}
        verb = {"it": "porta" if one else "portano", "en": "brings" if one else "bring"}
        template = {
            "it": f"{name}: attesa media per {s.label.it} {it(w)} giorni, oltre i {p['limit']} del PDTA. Nella "
                  f"simulazione a {p['months']} mesi con gli agenti, {k} {slots['it']} in più al giorno (da {b} a "
                  f"{b + k}) dal giorno {lever.from_day} {verb['it']} l'attesa media da {it(p['wait_days_without'])} a "
                  f"{it(p['wait_days'])} giorni. La decisione di aggiungere la capacità spetta al management.",
            "en": f"{name}: mean wait for {s.label.en} {w:.1f} days, over the PDTA's {p['limit']}. In the "
                  f"{p['months']}-month simulation with agents, {k} more {slots['en']} a day (from {b} to {b + k}) "
                  f"from day {lever.from_day} {verb['en']} the mean wait from {p['wait_days_without']:.1f} to "
                  f"{p['wait_days']:.1f} days. Adding the capacity is the management's decision."}
        facts = {"struttura": name, "esame": s.label.it, "attesa_media_ultimi_7_giorni": w, "soglia_PDTA_giorni": p["limit"],
                 "posti_in_piu_al_giorno": k, "posti_al_giorno_oggi": b, "posti_al_giorno_dopo": b + k,
                 "dal_giorno": lever.from_day, "mesi_simulati": p["months"],
                 "attesa_media_nei_mesi_senza": p["wait_days_without"], "attesa_media_nei_mesi_con": p["wait_days"]}
        rationale, wording = self._wording(facts, template)
        return [{"agent": AGENT, "type": "capacity_proposal", "pathway_id": self.pathway.pathway_id,
                 "scope": {"facility_id": lever.facility_id},
                 "payload": {"facility_id": lever.facility_id, "service": lever.service, "extra_slots": k,
                             "slots_per_day": lever.slots_per_day, "from_day": lever.from_day, "lever_run": p["run_id"],
                             "wait_days": p["wait_days"], "wait_days_without": p["wait_days_without"],
                             "months": p["months"], "wording": wording},
                 "rationale": rationale,
                 "evidence": [wait["source"], {"whatif": p["run_id"], "levers": {"extra_slots": k}, "months": p["months"],
                                               "run_id": self.run_id, "day": day}]}]

    def _wording(self, facts: dict, template: dict) -> tuple[dict, str]:
        """The 30B model's sentence and the 4B translation (D31), from the cache in the demo, when every number
        in both is one of the facts' and both name the facility; the template otherwise (CLAUDE.md rule 1)."""
        messages = [{"role": "system", "content": CAPACITY_SYSTEM},
                    {"role": "user", "content": json.dumps(facts, ensure_ascii=False)}]
        try:
            text = llm.complete(AGENT, CAPACITY_VERSION, messages, schema=Wording, model=llm.LARGE).data.testo
            prompt = CAPACITY_TRANSLATE.format(text=text.replace(facts["struttura"], PLACEHOLDER))
            english = llm.complete(AGENT, TRANSLATE_VERSION, [{"role": "user", "content": prompt}],
                                   schema=Translation, model=llm.SMALL).data.text.replace(PLACEHOLDER, facts["struttura"])
        except llm.LLMUnavailable as e:
            log.info("capacity proposal from the template: %s", e)
            return template, "template"
        values = verifier.leaves(facts) + [float(n) for n in re.findall(r"\d+", " ".join(facts))]  # "ultimi_7_giorni"
        wrong = [t for t in (text, english) if facts["struttura"] not in t or verifier.unsupported(t, values)]
        if wrong:
            log.warning("capacity proposal from the template: the model's sentence %r has a number or a name "
                        "that is not in the facts", wrong[0])
            return template, "template"
        return {"it": text, "en": english}, "model"

    def _write_escalation(self, con, state: StateEngine) -> None:
        """escalation_step (SPEC §5.1): the highest rung any open problem of the patient has reached."""
        esc = np.zeros(len(state.ids), np.int64)
        for r in self.reasons:
            open_ = self.opened[r.key] != NO_DAY
            esc = np.maximum(esc, np.where(self.offered[r.key], 3, np.where(self.called[r.key], 2, np.where(open_, 1, 0))))
        changed = np.flatnonzero(esc != self.esc_written)
        self.esc_written = esc
        if len(changed):
            con.register("esc_rows", pd.DataFrame({"patient_id": state.ids[changed], "step": esc[changed]}))
            con.execute("UPDATE pathway_state s SET escalation_step = r.step FROM esc_rows r "
                        "WHERE s.patient_id = r.patient_id AND s.pathway_id = $pw", {"pw": self.pathway.pathway_id})
            con.unregister("esc_rows")
