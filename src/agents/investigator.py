"""Investigator: looks for the cause of a regional alarm with the tools only (SPEC §6, §8, C24; delivery plan 2.9).

`investigate(...)` first runs the alarm's own evidence (`opening`: the step's wait in every hospital and its
service's free slots in the whole ATS), then gives the model the alarm's text, the pathway's steps, the
facilities and the tools, and lets it call tools up to MAX_STEPS in all, one gateway call per turn. Tools
answer from the run up to `ctx.day`; the model never writes SQL and gets no hint of where a problem is, only
a general method in the system prompt. Then it writes claims in Italian, each pointing at the step (tool call) that supports it,
and a conclusion; the small model translates them into English (D31). Claims that point at no successful
step are dropped, so every claim keeps the tool call the Verifier can repeat (C5).

The result summary of each step, shown on the stream, is filled by code from the tool's data, not by the
model. Every model call goes through the gateway, so the demo replays the investigation from the cache
(D14); there is no template to fall back on (Solution Plan §8), and the cache completeness check guards it.

The Investigator only reads: whoever runs it stores `Investigation.row()` in `investigations`.
"""

import json
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from agents import llm, tools
from agents.monitoring import WAIT_WINDOW_DAYS
from engine.pathway import Pathway

AGENT = "investigator"
# Pattern 1 found in v1 0/3 (free_slots kept to the alarm's ASST), v2 1/3 (steps lost guessing ASST ids),
# v3 0/3 (facilities given, still the alarm's ASST only); v4 opens with the alarm's evidence (`opening`).
# v5: the same prompt with the adherence_by_area tool, and group alarms (C26).
PROMPT_VERSION = "investigator-v5"
TRANSLATE_VERSION = "investigator-translate-v1"
MAX_STEPS = 6
SUMMARY_ITEMS = 6  # entries of a tool's data in a step's result summary

SYSTEM = """Sei l'Investigator di CarePath AI per l'ATS della Val Padana. Ricevi un allarme e ne cerchi le cause \
con gli strumenti, che leggono i dati fino a oggi, giorno {day}.

Regole:
- Usa solo gli strumenti. Ogni numero che scrivi deve venire dal risultato di uno strumento.
- Nessuna diagnosi e nessuna modifica di terapia.
- Al massimo {max_steps} chiamate di strumenti. Quando hai abbastanza dati, smetti di chiamarli.

Metodo: verifica il dato dell'allarme; confrontalo con gli altri ospedali o gruppi; cerca dove c'e' margine \
per intervenire in tutta l'ATS, non solo dove c'e' l'allarme; guarda quali pazienti ne sono colpiti.

Strutture dell'ATS (nome, tipo, ASST):
{facilities}

Percorso {pathway_id} ({label}). Step del percorso:
{steps}"""
FACILITY_TYPES = {"hospital": "ospedale", "clinic": "ambulatorio"}

QUESTION = {"it": "Allarme regionale del giorno {day}: {text}", "en": "Regional alarm on day {day}: {text}"}

FINAL = """Ora riassumi in JSON. Per ogni risultato utile scrivi un'affermazione con tutti i numeri rilevanti che \
lo strumento ha restituito, compresi i luoghi dove c'e' margine per intervenire, e indica il numero del passo \
che la sostiene. Riporta i numeri come li ha restituiti lo strumento: non calcolare medie, intervalli o totali. \
Poi una conclusione con l'azione che i dati suggeriscono."""

TRANSLATE = """Traduci in inglese questo JSON. Mantieni la struttura, i numeri e i nomi propri (ospedali, \
comuni, cooperative) esattamente come sono.

{json}"""


class Claim(BaseModel):
    text: str = Field(description="affermazione in italiano con i numeri restituiti dallo strumento")
    step: int = Field(ge=1, description="numero del passo, cioe' della chiamata di strumento, che la sostiene")


class Answer(BaseModel):
    claims: list[Claim] = Field(min_length=1)
    conclusion: str = Field(description="conclusione in italiano con l'azione suggerita dai dati")


class Translation(BaseModel):
    claims: list[str]
    conclusion: str


class InvestigationFailed(llm.LLMUnavailable):
    """The model answered, but no claim points at a tool call that returned data."""


@dataclass
class Investigation:
    investigation_id: str
    day: int
    pathway_id: str
    question: dict  # {"it", "en"}: the alarm
    steps: list[dict] = field(default_factory=list)  # {"step", "tool", "args", "result", "result_summary"}
    claims: list[dict] = field(default_factory=list)  # {"text": {"it", "en"}, "step"}
    conclusion: dict = field(default_factory=dict)  # {"it", "en"}

    def row(self, alert_id: str | None = None) -> dict:
        """The `investigations` row (C24). Steps keep the tool and its arguments, not the data: the Verifier
        repeats the call (C5)."""
        steps = [{k: s[k] for k in ("step", "tool", "args", "result_summary")} for s in self.steps]
        dump = lambda x: json.dumps(x, ensure_ascii=False)
        return {"investigation_id": self.investigation_id, "day": self.day, "pathway_id": self.pathway_id,
                "alert_id": alert_id, "question": dump(self.question), "steps": dump(steps),
                "claims": dump(self.claims), "conclusion": dump(self.conclusion), "prompt_version": PROMPT_VERSION}

    def messages(self, scenario: int) -> list[dict]:
        """The `investigation` stream messages, one per step (SPEC §10); the last one is final."""
        return [{"type": "investigation", "scenario": scenario, "day": self.day,
                 "payload": {"investigation_id": self.investigation_id, "step": s["step"], "tool": s["tool"],
                             "args": s["args"], "result_summary": s["result_summary"], "verified": None,
                             "final": i == len(self.steps) - 1}}
                for i, s in enumerate(self.steps)]


def _number(x: float, lang: str) -> str:
    text = f"{x:.2f}".rstrip("0").rstrip(".") if isinstance(x, float) else str(x)
    return text.replace(".", ",") if lang == "it" else text


def summary(result: dict) -> dict:
    """A step's result in one line per language, from the data alone: "Ospedale A 22 · Ospedale B 41"."""
    if "error" in result:
        return {"it": f"nessun dato ({result['error']['code']})", "en": f"no data ({result['error']['code']})"}
    data = result["data"]
    out = {}
    for lang in ("it", "en"):
        parts = []
        for k, v in list(data.items())[:SUMMARY_ITEMS]:
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                parts.append(f"{k} {_number(v, lang)}")
            elif isinstance(v, list) and v and isinstance(v[0], dict) and "comuni" in v[0]:  # adherence_by_area
                parts += [f"{', '.join(a['comuni'])} {_number(a['value'], lang)}" for a in v]
            elif isinstance(v, list):
                parts.append(f"{k}: {len(v)}")
            elif v is None:
                parts.append(f"{k} –")
        more = len(data) - SUMMARY_ITEMS
        out[lang] = " · ".join(parts) + (f" · +{more}" if more > 0 else "")
    return out


def system_prompt(pathway: Pathway, day: int, facilities: list[tuple[str, str, str]]) -> str:
    steps = "\n".join(f"- {s.id}: {s.label.it}" + (f" (servizio {s.service})" if s.service else "")
                      for s in pathway.steps)
    places = "\n".join(f"- {name}, {FACILITY_TYPES.get(kind, kind)}, {asst}" for name, kind, asst in facilities)
    return SYSTEM.format(day=day, max_steps=MAX_STEPS, pathway_id=pathway.pathway_id, label=pathway.label.it,
                         steps=steps, facilities=places)


def opening(pathway: Pathway, step_id: str | None = None, group_alarm: str | None = None) -> list[dict]:
    """The alarm's own evidence, called by code before the model. A wait alarm: the wait for the alarm's
    step in every hospital over the alarm's window, and the free slots of its service in the whole ATS. In
    three prompt versions the model kept free_slots to the alarm's ASST and never saw capacity elsewhere
    (0, 1 and 0 of 3 scenarios); which data backs a move of patients is code's choice (CLAUDE.md rule 1),
    not the model's. A group alarm (C26): the call Monitoring made, over the whole ATS."""
    if group_alarm is not None:
        g = next(g for g in pathway.group_alarms if g.id == group_alarm)
        return [{"function": {"name": g.tool, "arguments": {"pathway_id": pathway.pathway_id, **g.args}}}]
    step = next(s for s in pathway.steps if s.id == step_id)
    calls = [{"function": {"name": "wait_by_hospital",
                           "arguments": {"pathway_id": pathway.pathway_id, "step": step.id, "period_days": WAIT_WINDOW_DAYS}}}]
    if step.service:
        calls.append({"function": {"name": "free_slots", "arguments": {"service": step.service}}})
    return calls


def _run(ctx: tools.Context, inv: Investigation, calls: list[dict]) -> list[dict]:
    """Runs a turn's tool calls as steps, up to MAX_STEPS; returns the tool messages for the model."""
    out = []
    for call in calls:
        name, args = call["function"]["name"], dict(call["function"]["arguments"])
        if len(inv.steps) == MAX_STEPS:  # the turn asked for more than the steps left
            result = {"error": {"code": "bad_argument", "message": f"limite di {MAX_STEPS} passi raggiunto"}}
        else:
            result = tools.call(ctx, name, args)
            inv.steps.append({"step": len(inv.steps) + 1, "tool": name, "args": args, "result": result,
                              "result_summary": summary(result)})
            result = {"passo": len(inv.steps), **result}
        out.append({"role": "tool", "tool_name": name, "content": tools.canonical(result)})
    return out


def investigate(ctx: tools.Context, pathway: Pathway, day: int, alarm: dict, investigation_id: str,
                facilities: list[tuple[str, str, str]], step_id: str | None = None,
                group_alarm: str | None = None) -> Investigation:
    """One investigation of a regional alarm: `alarm` is its text ({"it", "en"}), and `step_id` its pathway
    step (a wait alarm) or `group_alarm` its id in the pathway's group_alarms. `facilities` are the run's
    (name, type, asst_id), reference data the caller reads: without them the model guessed ASST ids and
    lost steps to errors. The first steps are `opening`; the model has the rest. Raises llm.LLMUnavailable
    when the model gives no usable answer; there is no template (Solution Plan §8)."""
    inv = Investigation(investigation_id, day, pathway.pathway_id,
                        {lang: q.format(day=day, text=alarm[lang]) for lang, q in QUESTION.items()})
    definitions = tools.definitions()
    first = opening(pathway, step_id, group_alarm)
    messages = [{"role": "system", "content": system_prompt(pathway, day, facilities)},
                {"role": "user", "content": inv.question["it"]},
                {"role": "assistant", "content": "", "tool_calls": first}]
    messages += _run(ctx, inv, first)
    while len(inv.steps) < MAX_STEPS:
        reply = llm.complete(AGENT, PROMPT_VERSION, messages, tools=definitions, model=llm.LARGE).message
        calls = reply.get("tool_calls") or []
        if not calls:
            break
        messages.append(reply)
        messages += _run(ctx, inv, calls)
    messages.append({"role": "user", "content": FINAL})
    answer = llm.complete(AGENT, PROMPT_VERSION, messages, schema=Answer, model=llm.LARGE).data
    supported = {s["step"] for s in inv.steps if "data" in s["result"]}
    claims = [c for c in answer.claims if c.step in supported]
    if not claims:
        raise InvestigationFailed(f"{AGENT}: no claim points at a tool call with data")
    italian = {"claims": [c.text for c in claims], "conclusion": answer.conclusion}
    english = llm.complete(AGENT, TRANSLATE_VERSION,
                           [{"role": "user", "content": TRANSLATE.format(json=json.dumps(italian, ensure_ascii=False))}],
                           schema=Translation, model=llm.SMALL).data
    if len(english.claims) != len(claims):
        raise llm.LLMInvalid(f"{AGENT}: the translation has {len(english.claims)} claims, not {len(claims)}")
    inv.claims = [{"text": {"it": c.text, "en": en}, "step": c.step} for c, en in zip(claims, english.claims)]
    inv.conclusion = {"it": answer.conclusion, "en": english.conclusion}
    return inv
