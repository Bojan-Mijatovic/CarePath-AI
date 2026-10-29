"""AC17: Same tools, KPIs and console work for both pathways without code changes.

Measured by: test with two pathway models. Owner: R2. Layer: core. Spec: SPEC.md §11.
The second model is the HF pathway with every id and name changed and its codes kept, so the same
simulated events feed it (delivery plan step 2.21; the diabetes pathway of option B replaces it if that
layer enters). Replayed through the state engine, Risk, Monitoring, the views, the worklist and the tools,
it must give the HF numbers with only the names changed. The console must name nothing the pathway file
names; Maria's story, a scripted narrative about one patient, is exempt (D41).
"""

import re
import shutil
from pathlib import Path

import duckdb
import pytest

from agents import tools
from agents.monitoring import Monitoring
from engine import pathway as pathway_model
from engine import worklist
from engine.db import open_run, tool_cursor
from engine.risk import HIGH_RISK, MODELS_DIR, RiskModel
from engine.state import StateEngine

HF = pathway_model.load("hf_lombardia_v1")
RUN = "s2_agents"
LAST_DAY = 45  # past the echo alarm (day 33) and the weight-gain pulls of the 40s
IDS = {"hf_lombardia_v1": "other_v1", "discharge": "step_a", "telemon": "step_b", "cardio_visit": "step_c",
       "echo": "step_d", "lab_bnp": "step_e", "weight_gain": "rule_a", "no_furosemide": "rule_b",
       "adherence_risk": "flag_a"}
DERIVED = ("pathway_state", "kpi_daily", "map_comuni", "deviations", "alerts", "worklist_today")
UI = Path(__file__).resolve().parents[1] / "src" / "ui" / "src"
UI_EXEMPT = {"lib/story.ts", "screens/MariaStory.tsx"}  # Maria's story (D41)
UI_EXEMPT_KEYS = re.compile(r"^\s*'(maria|condition)\.")  # its strings in i18n.ts


def renamed() -> pathway_model.Pathway:
    """HF with new ids, step labels, drug name and pathway label; codes, services and timings unchanged."""
    p = HF.model_dump(by_alias=True)
    p["pathway_id"], p["name"] = IDS[p["pathway_id"]], "PDTA altro percorso"
    p["label"] = {"it": "Altro percorso", "en": "Other pathway"}
    p["readmission_reference"] = None
    p["eligibility"]["drug_names"] = {atc: {"it": "zetamide", "en": "zetamide"} for atc in p["eligibility"]["drug_names"]}
    for s in p["steps"]:
        s["id"], s["after"] = IDS[s["id"]], IDS.get(s["after"])
        letter = s["id"][-1].upper()
        s["label"] = {"it": f"Passo {letter}", "en": f"Step {letter}"}
    for r in p["rules"]:
        r["id"] = IDS[r["id"]]
        r["if"] = re.sub(r"overdue\('(\w+)'", lambda m: f"overdue('{IDS[m[1]]}'", r["if"])
        r["then"] = {k: IDS.get(v, v) if k in ("step", "flag") else v for k, v in r["then"].items()}
    return pathway_model.Pathway.model_validate(p)


OTHER = renamed()
BACK = {new: old for old, new in IDS.items()}
# Names in texts, back to HF: step labels and the drug, also with a capital first letter as rule texts start.
TEXT_BACK = {o.label.it: h.label.it for o, h in zip(OTHER.steps, HF.steps)} | {
    o.label.en: h.label.en for o, h in zip(OTHER.steps, HF.steps)} | {"zetamide": "furosemide", "Zetamide": "Furosemide"}


def back(x):
    """A result of the renamed pathway with HF's ids, recursively."""
    if isinstance(x, dict):
        return {back(k): back(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return type(x)(back(v) for v in x)
    return BACK.get(x, x) if isinstance(x, str) else x


def text_back(s: str) -> str:
    for new, old in TEXT_BACK.items():
        s = s.replace(new, old)
    return s


def replay(fixture_runs: Path, directory: Path, p: pathway_model.Pathway) -> duckdb.DuckDBPyConnection:
    """The fixture run's events through every per-day component for pathway `p`, days 0 to LAST_DAY, in the
    tick's order (SPEC §9) without the simulator."""
    shutil.copy(fixture_runs / f"{RUN}.duckdb", directory / f"{RUN}.duckdb")
    con = open_run(RUN, directory)
    for table in DERIVED:
        con.execute(f"DELETE FROM {table}")
    con.execute("UPDATE actions SET pathway_id = $p", {"p": p.pathway_id})  # the fixture's actions follow the pathway
    state = StateEngine(con, p)
    risk = RiskModel(p, MODELS_DIR / "risk_hf_lombardia_v1.json")  # features are named from codes, not ids
    monitoring = Monitoring(p, RUN, dict(con.execute("SELECT name, facility_id FROM facilities").fetchall()))
    for day in range(LAST_DAY + 1):
        state.update(con, day)
        risk.update(con, state, day)
        monitoring.run(con, state, risk, day, 2)
        state.refresh_kpi(con, day)
        state.refresh_map(con, day, risk.risk, HIGH_RISK)
        worklist.refresh(con, state, risk, day, monitoring.fired)
    return con


@pytest.fixture(scope="module")
def runs(fixture_scenario, tmp_path_factory):
    fixture_runs, _ = fixture_scenario
    pathways = tmp_path_factory.mktemp("pathways")  # both files where the tools look, as a second pathway would be
    for p in (HF, OTHER):
        (pathways / f"{p.pathway_id}.json").write_text(p.model_dump_json(by_alias=True), encoding="utf-8")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(tools, "PATHWAYS_DIR", pathways)
        cons = {p.pathway_id: replay(fixture_runs, tmp_path_factory.mktemp(p.pathway_id), p) for p in (HF, OTHER)}
        yield cons["hf_lombardia_v1"], cons["other_v1"]
    for con in cons.values():
        con.close()


def rows(con, sql: str) -> list[tuple]:
    return sorted(con.execute(sql).fetchall(), key=repr)


TABLES = {
    "pathway_state": "SELECT * EXCLUDE (pathway_id) FROM pathway_state",
    "kpi_daily": "SELECT * EXCLUDE (pathway_id) FROM kpi_daily",
    "map_comuni": "SELECT * EXCLUDE (pathway_id) FROM map_comuni",
    "sankey_flows": "SELECT * EXCLUDE (pathway_id) FROM sankey_flows",
    "deviations": "SELECT * EXCLUDE (pathway_id) FROM deviations",
    "alerts": "SELECT * EXCLUDE (pathway_id, text), text->>'it', text->>'en' FROM alerts",
    "worklist_today": "SELECT * EXCLUDE (pathways, reasons), reasons->>'it', reasons->>'en' FROM worklist_today",
}


@pytest.mark.acceptance
@pytest.mark.parametrize("table", TABLES)
def test_ac17_engine_views_and_monitoring(runs, table):
    hf, other = runs
    expected = rows(hf, TABLES[table])
    got = sorted((tuple(text_back(v) if isinstance(v, str) else v for v in back(r)) for r in rows(other, TABLES[table])),
                 key=repr)
    assert got == expected
    assert expected, table  # not comparing two empty tables
    for r in rows(other, TABLES[table]):  # no HF name reached the other pathway's rows
        for v in r:
            assert not (isinstance(v, str) and any(old in v for old in TEXT_BACK.values() if len(old) > 3)), (table, v)


CALLS = [
    ("compliance_by_step", {}),
    ("wait_by_hospital", {"step": "echo"}),
    ("patients_overdue", {"step": "cardio_visit"}),
    ("free_slots", {"service": "echo"}),
    ("adherence_by_group", {"grouping": "mmg"}),
    ("adherence_by_group", {"grouping": "age_band", "measure": "telemonitoring"}),
    ("readmissions_by_comune", {}),
    ("risk_drivers", {}),
    ("compare_segments", {"a": {"lives_alone": True}, "b": {}, "metric": "on_time_fraction"}),
]


@pytest.mark.acceptance
@pytest.mark.parametrize("name, args", CALLS, ids=[f"{n}-{i}" for i, (n, _) in enumerate(CALLS)])
def test_ac17_tools(runs, name, args):
    hf, other = runs
    results = []
    for con, p in ((hf, HF), (other, OTHER)):
        a = dict(args, **({"step": IDS[args["step"]] if p is OTHER else args["step"]} if "step" in args else {}))
        if name != "free_slots":
            a["pathway_id"] = p.pathway_id
        with tool_cursor(con) as cur:
            results.append(tools.call(tools.Context(RUN, tools.Query(cur), LAST_DAY), name, a))
    expected, got = results
    assert "error" not in expected, expected
    assert back(got["data"]) == expected["data"]


def console_files():
    for path in sorted(UI.rglob("*")):
        rel = path.relative_to(UI).as_posix()
        if path.suffix in (".ts", ".tsx", ".css") and rel not in UI_EXEMPT:
            lines = path.read_text(encoding="utf-8").splitlines()
            yield rel, "\n".join(line for line in lines if not UI_EXEMPT_KEYS.match(line)).lower()


def file_names(p: pathway_model.Pathway) -> set[str]:
    """What the pathway file names: the pathway, its steps, drugs and codes."""
    names = {p.pathway_id, p.name, p.label.it, p.label.en, *p.eligibility.any_drug_atc}
    names |= {c.rstrip("*") for c in p.eligibility.any_diagnosis}
    names |= {n for d in p.eligibility.drug_names.values() for n in (d.it, d.en)}
    for s in p.steps:
        names |= {s.label.it, s.label.en, *(s.codes or []), *(s.loinc or [])}
        names |= {s.id} if "_" in s.id else set()  # plain words such as "echo" are not names
    return {n.lower() for n in names if len(n) >= 4}


@pytest.mark.acceptance
def test_ac17_console_names_no_pathway():
    names = file_names(HF)
    found = [(rel, n) for rel, text in console_files() for n in names if n in text]
    assert not found, found
