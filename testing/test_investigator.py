"""Investigator (delivery plan step 2.9, SPEC C24): the loop with a fake model on the fixture run, and pattern 1
in all 3 scenarios replayed from the cache that `testing/investigation_run.py --live` fills."""

import json

import pytest

import investigation_run
from agents import investigator, llm, tools
from api.main import StreamMessage
from engine import pathway as pathway_model
from engine.db import create_run, open_run
from engine.tick import Population

HF = pathway_model.load("hf_lombardia_v1")
ALARM = {"it": "Ospedale B · Ecocardiogramma: attesa media 31,0 giorni", "en": "Ospedale B · Echocardiogram: mean wait 31.0 days"}
FACILITIES = [("Ospedale A", "hospital", "asst_mantova"), ("Ospedale B", "hospital", "asst_cremona")]


class FakeClient:
    """Answers with the given messages in turn; records every call."""

    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        return {"message": self.answers.pop(0)}


def calls(*named):
    return {"role": "assistant", "content": "",
            "tool_calls": [{"function": {"name": n, "arguments": a}} for n, a in named]}


def text(content):
    return {"role": "assistant", "content": content if isinstance(content, str) else json.dumps(content)}


RISK = ("risk_drivers", {"pathway_id": HF.pathway_id})
TRANSLATION = text({"claims": ["Ospedale B: 41 days", "Free slots at Ospedale C"], "conclusion": "Move patients."})


@pytest.fixture
def ctx(fixture_scenario):
    runs, _ = fixture_scenario
    c = tools.Context.for_run("s2_agents", runs)
    yield c
    c.close()


@pytest.fixture
def fake(tmp_path):
    def use(*answers):
        client = FakeClient(*answers)
        llm.configure(mode="live", cache_dir=tmp_path / "cache", log_path=None, client=client)
        return client
    yield use
    llm.configure()  # back to the default gateway, cache_only


def investigate(ctx):
    return investigator.investigate(ctx, HF, ctx.day, ALARM, "inv_s2_agents_1", FACILITIES, step_id="echo")


def test_opening_then_model_tools_then_claims_on_their_steps(ctx, fake):
    final = {"claims": [{"text": "Ospedale B: 41 giorni", "step": 1}, {"text": "Posti liberi all'Ospedale C", "step": 2},
                        {"text": "Un numero inventato", "step": 9}], "conclusion": "Spostare i pazienti."}
    client = fake(calls(RISK), text("Ho abbastanza dati."), text(final), TRANSLATION)
    inv = investigate(ctx)

    # The alarm's own evidence comes first, for the whole ATS: the alarm's window and the step's service.
    assert [(s["tool"], s["args"]) for s in inv.steps] == [
        ("wait_by_hospital", {"pathway_id": HF.pathway_id, "step": "echo", "period_days": 7}),
        ("free_slots", {"service": "echo"}), RISK]
    assert all("data" in s["result"] for s in inv.steps)
    assert inv.claims == [{"text": {"it": "Ospedale B: 41 giorni", "en": "Ospedale B: 41 days"}, "step": 1},
                          {"text": {"it": "Posti liberi all'Ospedale C", "en": "Free slots at Ospedale C"}, "step": 2}]
    assert inv.conclusion == {"it": "Spostare i pazienti.", "en": "Move patients."}
    assert inv.question["it"] == f"Allarme regionale del giorno {ctx.day}: {ALARM['it']}"
    # Tools only, the large model for the investigation, the small one for the translation (D11, D31).
    assert all(c["tools"] == tools.definitions() for c in client.calls[:2])
    assert [c["model"] for c in client.calls] == [llm.LARGE] * 3 + [llm.SMALL]
    assert client.calls[2]["format"] == investigator.Answer.model_json_schema()
    first = client.calls[0]["messages"]
    assert first[2]["tool_calls"] == investigator.opening(HF, "echo")  # shown to the model as its own calls
    tool_messages = [m for m in client.calls[1]["messages"] if m["role"] == "tool"]
    assert [json.loads(m["content"])["passo"] for m in tool_messages] == [1, 2, 3]  # the model cites steps by number
    assert "- Ospedale A, ospedale, asst_mantova" in first[0]["content"]  # reference data, no guessing of ASST ids
    assert "Ospedale B" not in first[0]["content"].split("Strutture")[0]  # and no hint where to look


def test_at_most_six_tool_calls(ctx, fake):
    five = calls(*[RISK] * 5)
    final = {"claims": [{"text": "x", "step": 6}], "conclusion": "y"}
    client = fake(five, text(final), text({"claims": ["x"], "conclusion": "y"}))
    inv = investigate(ctx)
    assert [s["step"] for s in inv.steps] == [1, 2, 3, 4, 5, 6]
    refused = json.loads([m for m in client.calls[1]["messages"] if m["role"] == "tool"][-1]["content"])
    assert refused["error"]["code"] == "bad_argument"  # 2 opening steps + 5 asked, 6 allowed
    assert len(client.calls) == 3  # one turn of tools, the answer, the translation


def test_no_supported_claim_is_a_failure(ctx, fake):
    fake(calls(("wait_by_hospital", {"pathway_id": HF.pathway_id, "step": "nope"})), text("Fine."),
         text({"claims": [{"text": "x", "step": 3}], "conclusion": "y"}))
    with pytest.raises(investigator.InvestigationFailed):  # step 3 returned an error, so it supports nothing
        investigate(ctx)


def test_row_and_stream_messages(ctx, fake, tmp_path):
    final = {"claims": [{"text": "Ospedale B: 41 giorni", "step": 1}], "conclusion": "z"}
    fake(text("Fine."), text(final), text({"claims": ["Ospedale B: 41 days"], "conclusion": "z"}))
    inv = investigate(ctx)
    create_run("s2_agents", runs_dir=tmp_path)
    con = open_run("s2_agents", tmp_path)
    row = inv.row("al_s2_agents_1")
    con.execute(f"INSERT INTO investigations BY NAME SELECT {', '.join(f'${k} AS {k}' for k in row)}", row)
    steps, claims = con.execute("SELECT steps, claims FROM investigations").fetchone()
    con.close()
    assert [s["tool"] for s in json.loads(steps)] == ["wait_by_hospital", "free_slots"]
    assert "result" not in json.loads(steps)[0]  # the Verifier repeats the call from tool and args (C5)
    assert json.loads(claims)[0]["step"] == 1
    messages = inv.messages(scenario=2)
    assert [StreamMessage.model_validate(m).payload["final"] for m in messages] == [False, True]
    assert messages[0]["payload"]["result_summary"]["it"].startswith("Ospedale")


def test_a_question_has_no_opening_and_its_own_prompt(ctx, fake):
    # Step 2.10: the model chooses the tools for a free question; the alarm prompt (v5) is untouched.
    question = {"it": "Quale ospedale ha l'attesa più lunga?", "en": "Which hospital has the longest wait?"}
    wait = ("wait_by_hospital", {"pathway_id": HF.pathway_id, "step": "echo", "period_days": 7})
    final = {"claims": [{"text": "Ospedale B: 41 giorni", "step": 1}], "conclusion": "Ospedale B."}
    client = fake(calls(wait), text("Fine."), text(final), text({"claims": ["Ospedale B: 41 days"],
                                                                  "conclusion": "Ospedale B."}))
    inv = investigator.ask(ctx, HF, ctx.day, question, "inv_s2_agents_9", FACILITIES)
    assert [(s["tool"], s["args"]) for s in inv.steps] == [wait]
    assert inv.question == question
    assert inv.conclusion == {"it": "Ospedale B.", "en": "Ospedale B."}
    assert inv.row()["prompt_version"] == investigator.ASK_VERSION != investigator.PROMPT_VERSION
    first = client.calls[0]["messages"]
    assert [m["role"] for m in first] == ["system", "user"]  # no opening
    assert first[0]["content"].startswith("Sei l'Investigator di CarePath AI per l'ATS della Val Padana. Ricevi una domanda")
    assert "scegli lo strumento e gli argomenti" in first[0]["content"]
    assert client.calls[2]["format"] == investigator.AskAnswer.model_json_schema()
    assert investigator.FINAL_ASK in client.calls[2]["messages"][-1]["content"]
    assert investigator.SYSTEM_ASK != investigator.SYSTEM and "Ricevi un allarme" in investigator.SYSTEM


@pytest.mark.parametrize("question, yes_no", [
    ("Quale ospedale ha l'attesa più lunga?", False), ("In quali comuni i pazienti smettono?", False),
    ("Quanti pazienti sono in ritardo?", False), ("Dove ci sono posti liberi?", False),
    ("L'Ospedale A ha un problema di attese?", True), ("I pazienti del gruppo coop_3 ritirano meno?", True),
])
def test_code_tells_a_yes_no_question(question, yes_no):
    assert investigator.yes_no(question) is yes_no


@pytest.mark.parametrize("field, sentence, conclusion", [
    ("No", "Sì, l'Ospedale A ha 2,1 giorni.", "No. L'Ospedale A ha 2,1 giorni."),  # the field decides, not the sentence
    ("Sì", "il gruppo ritira meno: 52%.", "Sì. Il gruppo ritira meno: 52%."),
])
def test_the_yes_no_answer_comes_first(ctx, fake, field, sentence, conclusion):
    question = {"it": "L'Ospedale A ha un problema?", "en": "Does Ospedale A have a problem?"}
    final = {"risposta": field, "claims": [{"text": "x", "step": 1}], "conclusion": sentence}
    wait = ("wait_by_hospital", {"pathway_id": HF.pathway_id, "step": "echo", "period_days": 7})
    client = fake(calls(wait), text("Fine."), text(final), text({"claims": ["x"], "conclusion": "-"}))
    inv = investigator.ask(ctx, HF, ctx.day, question, "inv_s2_agents_9", FACILITIES)
    assert inv.conclusion["it"] == conclusion
    assert client.calls[2]["format"] == investigator.YesNoAnswer.model_json_schema()
    assert list(investigator.YesNoAnswer.model_fields)[0] == "risposta"  # decided before the sentences


def test_a_missed_investigation_does_not_reuse_an_id(tmp_path, monkeypatch):
    # Found in step 2.10: a cache miss on one alarm, then two stored investigations, gave the same id twice and
    # stopped the tick on the primary key; a miss must leave only its alarm without an investigation (AC9).
    from agents.monitoring import ALERT_COLUMNS
    from engine import investigations
    create_run("s2_agents", runs_dir=tmp_path)
    con = open_run("s2_agents", tmp_path)
    alert = lambda i, day: [f"al_s2_agents_{i}", day, "regional", HF.pathway_id, None, None, "echo", None, None,
                            json.dumps(ALARM)]
    con.executemany(f"INSERT INTO alerts ({', '.join(ALERT_COLUMNS)}) VALUES ({', '.join('?' * 10)})",
                    [alert(1, 5), alert(2, 5), alert(3, 6)])
    outcomes = iter([llm.LLMUnavailable("miss"), None, None])

    def fake_investigate(ctx, pathway, day, alarm, investigation_id, facilities, **kw):
        if (e := next(outcomes)) is not None:
            raise e
        return investigator.Investigation(investigation_id, day, pathway.pathway_id, alarm)

    monkeypatch.setattr(investigator, "investigate", fake_investigate)
    investigations.on_alarms(con, "s2_agents", HF, 5, 2, [])
    investigations.on_alarms(con, "s2_agents", HF, 6, 2, [])
    rows = con.execute("SELECT alert_id, investigation_id FROM alerts ORDER BY alert_id").fetchall()
    con.close()
    assert rows == [("al_s2_agents_1", None), ("al_s2_agents_2", "inv_s2_agents_1"), ("al_s2_agents_3", "inv_s2_agents_2")]


def test_summary_from_the_data():
    result = {"data": {"Ospedale A": 22.5, "Ospedale B": 41, "rest_of_ats": None}}
    assert investigator.summary(result) == {"it": "Ospedale A 22,5 · Ospedale B 41 · rest_of_ats –",
                                            "en": "Ospedale A 22.5 · Ospedale B 41 · rest_of_ats –"}
    assert investigator.summary({"error": {"code": "empty_result", "message": ""}})["en"] == "no data (empty_result)"


@pytest.fixture(scope="module")
def population():
    return Population()


@pytest.mark.parametrize("scenario", [1, 2, 3])
def test_the_tick_finds_pattern_1_from_the_cache(scenario, population, tmp_path):
    # Done-when of step 2.9 (AC1, pattern 1), on the tick as in the demo (step 2.17, C25), in cache_only (D14).
    llm.configure(mode="cache_only", log_path=None)
    run, alarms, seconds = investigation_run.run_to_alarm(scenario, population, tmp_path)
    alarm = alarms[-1]  # the echo alarm; group alarms (C26) open earlier
    try:
        names = dict(run.con.execute("SELECT facility_id, name FROM facilities").fetchall())
        linked = run.con.execute("SELECT investigation_id FROM alerts WHERE alert_id = $a",
                                 {"a": alarm["payload"]["alert_id"]}).fetchall()[0][0]
        inv = investigation_run.stored(run, alarm)
    finally:
        run.close()
        llm.configure()
    assert inv is not None and linked == alarm["payload"]["investigation_id"] == inv["investigation_id"]
    assert investigation_run.pattern_1(inv, scenario, names)["found"]
    assert seconds < 2  # the alarm's whole tick, investigation included (AC5 measures it from the cache)
