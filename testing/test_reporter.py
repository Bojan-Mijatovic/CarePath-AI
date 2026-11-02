"""Reporter (delivery plan step 2.14, C36): the report's numbers equal the views' (the step's "done when"), on the
fixture run; the model's prose is used only when its numbers and names are the template's; the code-only tool
is not offered to the model."""

import json
import re

import duckdb
import pytest

from agents import llm, reporter, tools, verifier
from engine import pathway as pathway_model
from engine import queries

HF = pathway_model.load("hf_lombardia_v1")
DAY = 59


@pytest.fixture(scope="module")
def made(fixture_scenario):
    runs, _ = fixture_scenario
    ctx = tools.Context.for_run("s2_agents", runs, day=DAY)
    try:
        f, evidence = reporter.figures(ctx, HF, DAY)
    finally:
        ctx.close()
    with duckdb.connect(runs / "s2_agents.duckdb", read_only=True) as con:
        kpi = {(r["day"], r["level"], r["key"]): r for r in queries.kpi(con, HF.pathway_id, None, None)}
        stored = queries.reports(con)
    return f, evidence, kpi, stored


def test_a_report_on_the_last_day_of_each_month():
    assert [d for d in range(91) if reporter.due(d)] == [29, 59, 89]


def test_the_report_numbers_equal_the_views(made):
    f, evidence, kpi, _ = made
    ats, before = kpi[DAY, "ats", "ats"], kpi[29, "ats", "ats"]
    for k in tools.KPI_FIELDS:
        assert f["ats"][k] == pytest.approx(ats[k], abs=5e-5), k
    assert f["readmissions_month"] == ats["readmissions_30d"] - before["readmissions_30d"]
    assert f["actions_month"] == ats["actions_executed"] - before["actions_executed"]
    assert set(f["assts"]) == {key for (d, level, key) in kpi if d == DAY and level == "asst"}
    for a, v in f["assts"].items():
        assert v["readmission_rate_30d"] == pytest.approx(kpi[DAY, "asst", a]["readmission_rate_30d"], abs=5e-5)
    assert {s["tool"] for s in evidence} == {"pathway_kpi", "compliance_by_step", "wait_by_hospital"}


def test_every_number_of_the_text_is_a_figure(made):
    f, *_ = made
    text = reporter.template(f, HF)
    values = verifier.leaves(f) + [f["month"], f["from_day"], f["to_day"], 90, 30, 0]
    values += [float(n) for n in re.findall(r"\d+", f["reference"]["label"]["it"])]  # "Italia, PNE 2025"
    for lang in ("it", "en"):
        assert verifier.unsupported(text[lang], values) == [], lang
    assert "ASST Cremona" in text["it"] and "Ospedale B" in text["it"]


def test_the_tick_stores_the_months_reports(made):
    *_, stored = made
    assert [(r["day"], r["month"], r["from_day"]) for r in stored] == [(59, 2, 30), (29, 1, 0)]
    assert all(r["wording"] in ("model", "template") and r["text"]["it"] and r["text"]["en"] for r in stored)


class FakeClient:
    def __init__(self, *answers):
        self.answers = list(answers)

    def chat(self, **kwargs):
        return {"message": {"role": "assistant", "content": json.dumps(self.answers.pop(0))}}


@pytest.mark.parametrize("italian, english, used", [
    ("Ospedale A attende 2,0 giorni, Ospedale B 47,7; il tasso è 11,2%.",
     "PH_1 waits N_1 days, PH_2 N_2; the rate is N_3%.", True),
    ("Ospedale A attende 2,0 giorni, Ospedale B 48 e il tasso è 13,5%.",
     "PH_1 waits N_1 days, PH_2 N_2; the rate is N_3%.", False),  # 13,5% is no number of the report
    ("Ospedale A attende 2,0 giorni, Ospedale B 47,7.", "Hospital A waits N_1 days, PH_2 N_2.", False),  # renamed
    ("Gli Ospedali A e B attendono 2,0 e 47,7 giorni.", "Hospitals A and B wait N_1 and N_2 days.", False),  # merged
])
def test_the_model_s_prose_only_with_the_template_s_numbers(tmp_path, italian, english, used):
    """The translation sees placeholders for the facilities and the numbers, and code puts them back."""
    text = {"it": "Ospedale A 2,0, Ospedale B 47,7 giorni; tasso 11,2%.", "en": "Ospedale A 2.0, Ospedale B 47.7 days; rate 11.2%."}
    llm.configure(mode="live", cache_dir=tmp_path, log_path=None, client=FakeClient({"testo": italian}, {"text": english}))
    try:
        got = reporter._prose(text, ["Ospedale A", "Ospedale B"])
    finally:
        llm.configure()
    assert (got is not None) == used
    if used:
        assert got == {"it": italian, "en": "Ospedale A waits 2.0 days, Ospedale B 47.7; the rate is 11.2%."}


def test_the_code_only_tool_is_not_offered_to_the_model():
    names = [d["function"]["name"] for d in tools.definitions()]
    assert "pathway_kpi" not in names and "pathway_kpi" in tools.TOOLS
    assert names == [n for n in tools.TOOLS if n not in tools.CODE_ONLY]
