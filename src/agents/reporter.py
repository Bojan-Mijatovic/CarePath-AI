"""Reporter (delivery plan step 2.14, SPEC C36): the monthly report on the pathway, in the style of Agenas' PNE.

At the end of each simulated month (days 29, 59, ...) code reads the month's numbers through the tools, as
every agent reads (CLAUDE.md rule 3): `pathway_kpi` for the ATS and per ASST (30-day readmissions from day 0,
the PNE year, on-track share, overdue steps, agent actions), `compliance_by_step` and `wait_by_hospital` for
the step with a wait threshold over the month. It writes them into a template, in Italian and English, which
is the report; `figures` keeps every number, so the console can show them as a table.

The 30B model may rewrite the Italian template as prose and the 4B model translate it (D11, D31), only for a
report the demo shows (D17, the cache manifest); its text is used when every number in both languages is
one of the template's and the facilities keep their names, else the template stands, as for Intervention's
capacity proposal (step 2.27). The Reporter only reads; whoever runs it stores `Report.row()`.
"""

import json
import logging
import re
from dataclasses import dataclass, field

from pydantic import BaseModel

from agents import llm, tools, verifier
from engine.pathway import Pathway

AGENT = "reporter"
log = logging.getLogger("carepath.reporter")
MONTH_DAYS = 30
WAIT_DAYS = MONTH_DAYS  # the month's bookings
# v1, scenario 2 day 59 (2 Nov 2026): the Italian kept every number but read as a list ("Riammissioni nel mese:
# 24. ASST Crema: 12,0%, ..."), and the 4B translation split one ("10. 1%"), so the check kept the template.
# v2: complete sentences; translate v2: code puts a placeholder for every number as well as for every facility.
# v2 passed the number check, but read by hand: "2773 azioni, di cui 3 in attesa" (the 3 are not among the
# 2773), PAI spelled out wrongly ("Piano di Assistenza Integrata"), the 90-day window of the deadlines dropped,
# and "Ospedali A e C". v3 says each of these; code now also wants every facility of the report, by its name.
PROSE_VERSION = "reporter-v3"
TRANSLATE_VERSION = "reporter-translate-v2"
PROSE = """Sei il Reporter di CarePath AI per l'ATS della Val Padana. Riscrivi il rapporto mensile qui sotto come un \
testo breve per la direzione, nello stile dei rapporti PNE di Agenas: 4 o 5 frasi complete, con soggetto e verbo, \
non un elenco. Regole:
- Usa solo i numeri e i nomi del rapporto, scritti come sono; non aggiungere numeri, cause, giudizi clinici o terapie.
- Non sciogliere le sigle (PAI, PNE, ASST, BNP).
- Ogni numero mantiene il suo periodo: le scadenze rispettate sono degli ultimi 90 giorni, le riammissioni a 30 \
giorni sono dal giorno 0.
- Le azioni eseguite e quelle in attesa di approvazione sono due gruppi distinti.
- Nomina ogni struttura con il suo nome completo, una per una (per esempio "Ospedale A").

{report}"""
TRANSLATE = """Traduci in inglese questo testo. Mantieni le sigle {placeholders} esattamente come sono, una per una.

{text}"""


class Prose(BaseModel):
    testo: str


class Translation(BaseModel):
    text: str


@dataclass
class Report:
    report_id: str
    day: int
    month: int
    from_day: int
    pathway_id: str
    figures: dict
    text: dict  # {"it", "en"}
    wording: str = "template"  # or "model"
    evidence: list = field(default_factory=list)  # the tools' source blocks

    def row(self) -> dict:
        dump = lambda x: json.dumps(x, ensure_ascii=False)
        return {"report_id": self.report_id, "day": self.day, "month": self.month, "from_day": self.from_day,
                "pathway_id": self.pathway_id, "figures": dump(self.figures), "text": dump(self.text),
                "wording": self.wording, "evidence": dump(self.evidence)}

    def message(self, scenario: int) -> dict:
        """The `report` stream message (SPEC §10, C36)."""
        title = {"it": f"Rapporto del mese {self.month}", "en": f"Report for month {self.month}"}
        return {"type": "report", "scenario": scenario, "day": self.day,
                "payload": {"report_id": self.report_id, "month": self.month, "from_day": self.from_day,
                            "title": title, "wording": self.wording}}


def due(day: int) -> bool:
    """The last day of a simulated month."""
    return (day + 1) % MONTH_DAYS == 0


def _call(ctx: tools.Context, evidence: list, name: str, args: dict) -> dict | None:
    result = tools.call(ctx, name, args)
    if "data" not in result:
        log.info("reporter: %s gave %s", name, result["error"])
        return None
    evidence.append(result["source"])
    return result["data"]


def _pct(x: float | None, lang: str, digits: int = 1) -> str:
    if x is None:
        return "–"
    text = f"{100 * x:.{digits}f}%"
    return text.replace(".", ",") if lang == "it" else text


def _num(x: float, lang: str) -> str:
    return f"{x:.1f}".replace(".", ",") if lang == "it" else f"{x:.1f}"


def asst_name(asst_id: str) -> str:
    return f"ASST {asst_id.removeprefix('asst_').title()}"


def figures(ctx: tools.Context, pathway: Pathway, day: int) -> tuple[dict, list]:
    """The month's numbers, each from a tool call, and the calls' sources."""
    evidence: list = []
    month = (day + 1) // MONTH_DAYS
    from_day = day + 1 - MONTH_DAYS
    pw = pathway.pathway_id
    ats = _call(ctx, evidence, "pathway_kpi", {"pathway_id": pw})["ats"]
    before = _call(ctx, evidence, "pathway_kpi", {"pathway_id": pw, "day": from_day - 1})["ats"] if from_day > 0 else None
    assts = _call(ctx, evidence, "pathway_kpi", {"pathway_id": pw, "level": "asst"}) or {}
    compliance = _call(ctx, evidence, "compliance_by_step", {"pathway_id": pw}) or {}
    step = next((s for s in pathway.steps if s.service and s.max_wait_days is not None), None)
    waits = (_call(ctx, evidence, "wait_by_hospital", {"pathway_id": pw, "step": step.id, "period_days": WAIT_DAYS})
             if step else None) or {}
    reference = pathway.readmission_reference
    return {"month": month, "from_day": from_day, "to_day": day, "ats": ats,
            "readmissions_month": ats["readmissions_30d"] - (before["readmissions_30d"] if before else 0),
            "actions_month": ats["actions_executed"] - (before["actions_executed"] if before else 0),
            "assts": {a: {"name": asst_name(a), **v} for a, v in assts.items()},
            "compliance": compliance, "wait": {"step": step.id if step else None, "days": WAIT_DAYS, "by_facility": waits},
            "reference": reference.model_dump() if reference else None}, evidence


def template(f: dict, pathway: Pathway) -> dict:
    """The report in both languages, every number from `f`."""
    labels = {s.id: s.label for s in pathway.steps}
    out = {}
    for lang in ("it", "en"):
        ats, ref = f["ats"], f["reference"]
        it = lang == "it"
        lines = [
            (f"{pathway.label.it}: rapporto del mese {f['month']} (giorni {f['from_day']}–{f['to_day']})." if it else
             f"{pathway.label.en}: report for month {f['month']} (days {f['from_day']}–{f['to_day']})."),
            (f"Riammissioni a 30 giorni dal giorno 0: {_pct(ats['readmission_rate_30d'], lang)}" if it else
             f"30-day readmissions since day 0: {_pct(ats['readmission_rate_30d'], lang)}")
            + ((f", riferimento {ref['label']['it']} {_pct(ref['rate'], lang, 2)}" if it else
                f", reference {ref['label']['en']} {_pct(ref['rate'], lang, 2)}") if ref else "")
            + (f". Nel mese: {f['readmissions_month']} riammissioni." if it else
               f". In the month: {f['readmissions_month']} readmissions."),
        ]
        if f["assts"]:
            per = ", ".join(f"{a['name']} {_pct(a['readmission_rate_30d'], lang)}" for a in f["assts"].values())
            lines.append(f"Per ASST: {per}." if it else f"By ASST: {per}.")
        lines.append(
            f"In linea con il PAI: {_pct(ats['on_track_pct'], lang)} dei {ats['patients']} pazienti; "
            f"{ats['overdue']} passi in ritardo." if it else
            f"On track with the PAI: {_pct(ats['on_track_pct'], lang)} of {ats['patients']} patients; "
            f"{ats['overdue']} steps overdue.")
        if f["compliance"]:
            per = ", ".join(f"{labels[s].it if it else labels[s].en} {_pct(v, lang)}"
                            for s, v in f["compliance"].items() if v is not None)
            lines.append(f"Scadenze rispettate negli ultimi 90 giorni: {per}." if it else
                         f"Deadlines met in the last 90 days: {per}.")
        if f["wait"]["by_facility"]:
            label = labels[f["wait"]["step"]]
            per = ", ".join(f"{n} {_num(w, lang)}" for n, w in f["wait"]["by_facility"].items())
            lines.append(f"Attesa media per {label.it} nel mese, in giorni: {per}." if it else
                         f"Mean wait for {label.en} in the month, in days: {per}.")
        lines.append(f"Azioni degli agenti nel mese: {f['actions_month']} eseguite; {ats['actions_pending']} in attesa "
                     "di approvazione." if it else
                     f"Agent actions in the month: {f['actions_month']} executed; {ats['actions_pending']} waiting for "
                     "approval.")
        out[lang] = "\n".join(lines)
    return out


def _prose(text: dict, names: list[str]) -> dict | None:
    """The model's prose and its translation, or None when it has a number or a name the template has not.
    Facility names go through the translation as placeholders: the 4B model renamed "Ospedale B" (step 2.27)."""
    try:
        italian = llm.complete(AGENT, PROSE_VERSION, [{"role": "user", "content": PROSE.format(report=text["it"])}],
                               schema=Prose, model=llm.LARGE).data.testo
        marks = {n: f"PH_{k + 1}" for k, n in enumerate(names)}
        masked = italian
        for n, m in marks.items():
            masked = masked.replace(n, m)
        numbers: dict[str, str] = {}  # placeholder -> the number in English writing (decimal point)

        def hide(t: re.Match) -> str:
            key = f"N_{len(numbers) + 1}"
            numbers[key] = t.group().replace(",", ".")
            return key
        masked = verifier.NUMBER.sub(hide, masked)
        prompt = TRANSLATE.format(text=masked, placeholders=", ".join([*marks.values(), *numbers]) or "-")
        english = llm.complete(AGENT, TRANSLATE_VERSION, [{"role": "user", "content": prompt}], schema=Translation,
                               model=llm.SMALL).data.text
        for key in sorted(numbers, key=lambda k: -int(k[2:])):  # N_12 before N_1
            english = english.replace(key, numbers[key])
        for n, m in marks.items():
            english = english.replace(m, n)
    except llm.LLMUnavailable as e:
        log.info("reporter: the template stands: %s", e)
        return None
    values = [x for lang in ("it", "en") for t in verifier.NUMBER.finditer(text[lang])
              for x, _ in verifier.readings(t.group())]
    values += [float(n) for n in re.findall(r"\d+", " ".join(names))]
    wrong = [t for t in (italian, english) if verifier.unsupported(t, values)]
    lost = [n for n in names if n not in italian or n not in english]  # each facility, by its name, in both
    if wrong or lost:
        log.warning("reporter: the template stands; the model's text has numbers or names not in the report: %r %r",
                    wrong[:1], lost)
        return None
    return {"it": italian, "en": english}


def report(ctx: tools.Context, pathway: Pathway, day: int, report_id: str, prose: bool = False) -> Report:
    """The report of the month ending on `day` (`due(day)`), on `ctx` (the run on that day). `prose` asks the
    model, for a report the demo shows (D17): the caller decides, from the cache manifest."""
    f, evidence = figures(ctx, pathway, day)
    text = template(f, pathway)
    prose = _prose(text, sorted(f["wait"]["by_facility"])) if prose else None
    return Report(report_id, day, f["month"], f["from_day"], pathway.pathway_id, f, prose or text,
                  "model" if prose else "template", evidence)
