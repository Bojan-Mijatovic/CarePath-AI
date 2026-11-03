"""Bed Finder (delivery plan Phase 3, D64; SPEC C42): where a patient goes once a doctor has decided to admit.

Whether to admit stays the doctor's decision (SPEC §7.3); the agent only answers where. Code ranks, no LLM:
the wards that take the admission diagnosis (`ward_by_diagnosis` of the pathway file), a bed free today first,
then the emergency department's own hospital, then the nearest, then the wards in the file's order. The first
becomes one `bed_assignment` through the action service (SPEC §7): at level 3 it is executed at once and the
doctor can undo it; at level 2 it waits for the doctor's confirmation, and a bed only proposed stays free
(AC19). A doctor who picks one of the alternatives has decided, so that one is confirmed at once.

The action names the ward and the bed, never the diagnosis (the guardrail of SPEC §7.3), and its rationale is a
template filled by code (D17). It is no simulation event: the simulator admits its patients where it already
does (C42). The demo calls it on request, POST /api/admissions (D64), never from the tick.
"""

from agents import actions, tools
from engine.db import tool_cursor
from engine.pathway import Pathway

AGENT = "bed_finder"
ACTION = "bed_assignment"
DOCTOR = "doctor"  # who confirms, chooses or undoes a bed; the demo has no login
SHOWN = 3  # the choice and two alternatives (prototype step 9c)
WARDS = {"cardiologia": {"it": "Cardiologia", "en": "Cardiology"},
         "medicina_interna": {"it": "Medicina interna", "en": "Internal medicine"},
         "endocrinologia": {"it": "Endocrinologia", "en": "Endocrinology"}}


def ward_label(ward: str) -> dict[str, str]:
    return WARDS.get(ward, {"it": ward, "en": ward})


def ranked(found: dict, from_facility: str) -> list[dict]:
    """free_beds' wards with a bed free today or in 2 days, best first."""
    order = found["wards"]
    beds = [b | {"same_facility": b["facility_id"] == from_facility, "ward_label": ward_label(b["ward"])}
            for b in found["beds"] if b["free_now"] or b["free_in_2d"]]
    return sorted(beds, key=lambda b: (b["free_now"] == 0, not b["same_facility"], b["distance_km"],
                                       order.index(b["ward"]), b["facility_id"]))


def _km(km: float) -> dict[str, str]:
    return {"it": f"{km:.1f}".replace(".", ","), "en": f"{km:.1f}"}


def rationale(pick: dict, from_name: str, chosen_by_doctor: bool) -> dict[str, str]:
    ward, name, bed = pick["ward_label"], pick["name"], pick["bed"]
    if pick["same_facility"]:
        where = {"it": f"Letto {bed} in {ward['it'].lower()}, {name}: libero ora, nello stesso ospedale del pronto "
                       "soccorso, quindi senza trasferimento.",
                 "en": f"Bed {bed} in {ward['en'].lower()}, {name}: free now, in the emergency department's own "
                       "hospital, so no transfer."}
    else:
        km = _km(pick["distance_km"])
        where = {"it": f"Letto {bed} in {ward['it'].lower()}, {name}, a {km['it']} km da {from_name}: libero ora; "
                       "serve un trasferimento.",
                 "en": f"Bed {bed} in {ward['en'].lower()}, {name}, {km['en']} km from {from_name}: free now; a "
                       "transfer is needed."}
    why = ({"it": "Scelto dal medico tra le alternative.", "en": "Chosen by the doctor among the alternatives."}
           if chosen_by_doctor else
           {"it": "Il reparto accoglie la diagnosi di ricovero del medico.",
            "en": "The ward takes the doctor's admission diagnosis."})
    return {lang: f"{where[lang]} {why[lang]}" for lang in ("it", "en")}


def admit(con, run_id: str, pathway: Pathway, day: int, patient_id: str, diagnosis: str, from_facility: str,
          choice: int = 0) -> dict:
    """A bed for a patient the doctor admits on `day` through the emergency department of `from_facility`.
    `choice` is the doctor's pick among the candidates, 0 for the agent's own. Returns {"candidates": the first
    SHOWN, best first, "action": the stored row, or None when no ward has a bed free today}. ValueError for a
    diagnosis without a ward, an unknown facility or a choice without a bed free today."""
    with tool_cursor(con) as cur:
        found = tools.call(tools.Context(run_id, tools.Query(cur), day), "free_beds",
                           {"pathway_id": pathway.pathway_id, "diagnosis": diagnosis, "from_facility": from_facility,
                            "patient_id": patient_id})
    if "error" in found:
        raise ValueError(found["error"]["message"])
    candidates = ranked(found["data"], from_facility)[:SHOWN]
    if not 0 <= choice < max(len(candidates), 1):
        raise ValueError(f"choice is between 0 and {len(candidates) - 1}")
    if not candidates or not candidates[choice]["free_now"]:
        if choice:
            raise ValueError("no bed is free today in that ward")
        return {"candidates": candidates, "action": None}
    pick = candidates[choice]
    from_name = next((b["name"] for b in found["data"]["beds"] if b["facility_id"] == from_facility), from_facility)
    no_event = lambda rows: None  # a bed is not a simulation event (C42)
    row = actions.create(con, run_id, day, {
        "agent": AGENT, "type": ACTION, "patient_id": patient_id, "scope": {"facility_id": pick["facility_id"]},
        "pathway_id": pathway.pathway_id,
        "payload": {"day": day, "from_facility": from_facility, "facility_id": pick["facility_id"],
                    "facility_name": pick["name"], "ward": pick["ward"], "ward_label": pick["ward_label"],
                    "bed": pick["bed"], "choice": choice, "candidates": candidates},
        "rationale": rationale(pick, from_name, choice > 0), "evidence": [found["source"]]}, no_event)
    if choice and row["status"] == "proposed":
        row = actions.decide(con, day, row["action_id"], True, no_event, actor=DOCTOR)
    return {"candidates": candidates, "action": row}
