"""Verifier (SPEC §6, C33): numbers, comparisons and scope on hand-made claims; the repeated calls, the
stored claims and the stream messages of one investigation."""

import json

import pytest

from agents import verifier
from agents.investigator import Investigation
from engine import pathway as pathway_model

HF = pathway_model.load("hf_lombardia_v1")
FACILITIES = [("Ospedale A", "hospital", "asst_mantova"), ("Ospedale B", "hospital", "asst_cremona"),
              ("Ospedale C", "hospital", "asst_crema"), ("Poliambulatorio 5", "clinic", "asst_mantova")]
QUESTION = {"it": "Allarme regionale del giorno 33: Ospedale B · Ecocardiogramma: attesa media 30,4 giorni sulle "
                  "prenotazioni degli ultimi 7 giorni (soglia PDTA 30 giorni)",
            "en": "Regional alarm on day 33: Ospedale B · Echocardiogram: mean wait 30.4 days (PDTA threshold 30 days)"}
WAIT = {"data": {"Ospedale A": 2.1, "Ospedale B": 30.4, "Ospedale C": 2.0, "Poliambulatorio 5": 2.2},
        "source": {"tool": "wait_by_hospital", "args": {"pathway_id": HF.pathway_id, "step": "echo", "period_days": 7},
                   "run_id": "s2_agents", "day": 33}}
COMPLIANCE = {"data": {"telemon": 0.5509, "cardio_visit": 0.798, "echo": 0.8365, "lab_bnp": 0.754},
              "source": {"tool": "compliance_by_step", "args": {"pathway_id": HF.pathway_id, "asst": "asst_cremona"},
                         "run_id": "s2_agents", "day": 33}}


def issues(it: str, result: dict, en: str | None = None) -> list[str]:
    return [i["kind"] for i in verifier.check({"it": it, "en": en or it}, result, QUESTION, HF, FACILITIES)]


@pytest.mark.parametrize("token, expected", [
    ("87,31", [(87.31, 2)]), ("87.31", [(87.31, 2)]), ("2.400", [(2400.0, 0), (2.4, 3)]),
    ("-11,83", [(-11.83, 2)]), ("30", [(30.0, 0)])])
def test_readings(token, expected):
    assert verifier.readings(token) == expected


def test_a_number_may_be_rounded_or_cut_or_a_percentage():
    assert verifier.matches(83.65, 2, 0.8365) and verifier.matches(83.7, 1, 0.8365) and verifier.matches(83, 0, 0.8365)
    assert verifier.matches(30.4, 1, 30.4) and not verifier.matches(30.5, 1, 30.4) and not verifier.matches(31, 0, 29.9)


def test_numbers_of_the_data_the_call_and_the_question_pass():
    assert issues("L'Ospedale B ha un'attesa di 30,4 giorni negli ultimi 7 giorni, oltre la soglia PDTA di 30 giorni; "
                  "l'Ospedale A 2,1 e l'Ospedale C 2,0.", WAIT) == []
    assert issues("Poliambulatorio 5 ha un tempo di 2,2 giorni.", WAIT) == []  # 5 is in the name


def test_a_number_next_to_a_name_must_be_that_names_value():
    assert issues("L'Ospedale B ha un'attesa di 2,0 giorni.", WAIT) == ["number"]  # Ospedale C's value
    assert issues("L'Ospedale B ha un'attesa di 34,0 giorni.", WAIT) == ["number"]


def test_a_made_up_threshold_is_a_number_issue():
    assert issues("L'attesa all'Ospedale B è di 30,4 giorni, oltre la media regionale di 12 giorni.", WAIT) == ["number"]


def test_a_slip_of_the_translation_is_caught_in_the_english_text():
    got = verifier.check({"it": "L'Ospedale B ha un'attesa di 30,4 giorni.", "en": "Ospedale B has a wait of 3.4 days."},
                         WAIT, QUESTION, HF, FACILITIES)
    assert [i["kind"] for i in got] == ["number"] and got[0]["text"]["en"].endswith("(English text)")


def test_a_comparison_stated_backwards():
    # step 2.9: "83,65% … inferiore al 79,8%" over ASST Cremona's compliance
    claim = "La compliance per l'ASST è del 83,65% per l'ecocardiogramma, inferiore al 79,8% per la visita cardiologica."
    assert issues(claim, COMPLIANCE) == ["comparison"]
    assert issues(claim.replace("inferiore", "superiore"), COMPLIANCE) == []
    assert issues("Il tasso è inferiore di 3,85 punti.", {**COMPLIANCE, "data": {"a": 0.798, "b": 0.8365,
                                                                                "difference": -0.0385}}) == []


def test_a_hospital_named_on_an_asst_figure():
    got = verifier.check({"it": "La compliance all'Ospedale B è del 83,65% per l'ecocardiogramma.", "en": "83.65%"},
                         COMPLIANCE, QUESTION, HF, FACILITIES)
    assert [i["kind"] for i in got] == ["scope"]
    assert got[0]["text"]["it"] == "compliance_by_step dà il dato di ASST Cremona, non di Ospedale B"
    assert issues("L'Ospedale B ha un'attesa di 30,4 giorni.", WAIT) == []  # a per-facility tool


def test_a_correction_names_the_right_value():
    (issue,) = verifier.check({"it": "L'Ospedale B ha un'attesa di 34,0 giorni.", "en": "Ospedale B: 30.4 days."},
                              WAIT, QUESTION, HF, FACILITIES)
    assert issue["text"] == {"it": "34,0: per Ospedale B wait_by_hospital dà 30,4",
                             "en": "34.0: wait_by_hospital gives 30.4 for Ospedale B"}


def test_verify_repeats_each_call_and_marks_the_steps(monkeypatch):
    calls = []
    results = {"wait_by_hospital": WAIT, "free_slots": {"error": {"code": "empty_result", "message": ""}}}
    monkeypatch.setattr(verifier.tools, "call", lambda ctx, name, args: calls.append((name, args)) or results[name])
    inv = Investigation("inv_s2_agents_3", 33, HF.pathway_id, QUESTION, steps=[
        {"step": 1, "tool": "wait_by_hospital", "args": WAIT["source"]["args"], "result": {}, "result_summary": {}},
        {"step": 2, "tool": "free_slots", "args": {"service": "echo"}, "result": {}, "result_summary": {}},
        {"step": 3, "tool": "risk_drivers", "args": {}, "result": {}, "result_summary": {}}],
        claims=[{"text": {"it": "Ospedale B 30,4 giorni.", "en": "Ospedale B 30.4 days."}, "step": 1},
                {"text": {"it": "Ospedale A 9 giorni.", "en": "Ospedale A 9 days."}, "step": 1},
                {"text": {"it": "Ospedale A 118 posti.", "en": "Ospedale A 118 slots."}, "step": 2}])
    verifier.verify(None, HF, inv, FACILITIES)
    assert calls == [("wait_by_hospital", WAIT["source"]["args"]), ("free_slots", {"service": "echo"})]  # not step 3
    assert [c["verified"] for c in inv.claims] == [True, False, None]
    assert [m["payload"]["verified"] for m in inv.messages(2)] == [False, None, None]
    assert json.loads(inv.row()["claims"])[1]["issues"][0]["kind"] == "number"
