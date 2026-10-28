"""Tools v1 (delivery plan step 1.24, SPEC §6): the SELECT-only guard (D29), the envelope, the errors, and
agreement with the state engine and the fixtures."""

import json
from pathlib import Path

import duckdb
import pytest

from agents import tools
from engine.db import create_run, open_run, tool_cursor
from fixtures.scenario import FIXTURES
from sim.truth import TRUTH_DIR

PW = "hf_lombardia_v1"
SPEC_TOOLS = ["compliance_by_step", "wait_by_hospital", "patients_overdue", "free_slots", "adherence_by_group",
              "readmissions_by_comune", "risk_drivers", "compare_segments"]  # SPEC §6, without the gated two


@pytest.fixture(scope="module")
def ctx(fixture_scenario):
    runs, _ = fixture_scenario
    c = tools.Context.for_run("s2_agents", runs)
    yield c
    c.close()


@pytest.fixture
def tick(tmp_path):
    """The simulation process's connection to a live run and the tools' cursor of it (D29)."""
    create_run("s2_agents", runs_dir=tmp_path)
    con = open_run("s2_agents", tmp_path)
    con.execute("INSERT INTO mmg VALUES ('mmg_001', 'coop_3', 'cs_3', '019035')")
    yield con, tools.Query(tool_cursor(con))
    con.close()


@pytest.mark.parametrize("sql", [
    "INSERT INTO mmg VALUES ('mmg_002', 'coop_3', 'cs_3', '019035')",
    "DELETE FROM mmg",
    "UPDATE mmg SET coop_id = 'x'",
    "DROP TABLE mmg",
    "CREATE TABLE x (a INTEGER)",
    "SELECT 1; DELETE FROM mmg",
    "WITH x AS (SELECT 1 AS a) INSERT INTO mmg SELECT 'm', 'c', 's', 'x' FROM x",
    "COPY mmg TO 'out.csv'",
    "PRAGMA table_info('mmg')",
    "CALL pragma_version()",
    "SET threads = 1",
    "ATTACH 'other.duckdb' AS o",
    "EXPLAIN SELECT 1",
])
def test_guard_runs_select_only(tick, sql):
    con, q = tick
    with pytest.raises(PermissionError):
        q.rows(sql)
    assert con.execute("SELECT coop_id FROM mmg").fetchall() == [("coop_3",)]


def test_guard_lets_selects_through_and_the_cursor_cannot_reach_files(tick):
    _, q = tick
    assert q.rows("WITH x AS (SELECT coop_id FROM mmg) SELECT * FROM x") == [("coop_3",)]
    with pytest.raises(duckdb.Error):  # a SELECT that reads a file: blocked by the connection (open_run)
        q.rows(f"SELECT * FROM read_json_auto('{(TRUTH_DIR / 'scenario_2.json').as_posix()}')")


def test_definitions_are_the_spec_tools_with_flat_schemas():
    defs = tools.definitions()
    assert [d["function"]["name"] for d in defs] == SPEC_TOOLS
    for d in defs:
        assert d["type"] == "function"
        assert d["function"]["description"]
        assert "$ref" not in json.dumps(d) and "$defs" not in json.dumps(d)
        params = d["function"]["parameters"]
        assert params["type"] == "object"
        assert params["additionalProperties"] is False


@pytest.mark.parametrize("name, args", [
    ("compliance_by_step", {"pathway_id": PW}),
    ("compliance_by_step", {"pathway_id": PW, "asst": "asst_cremona"}),
    ("wait_by_hospital", {"pathway_id": PW, "step": "echo"}),
    ("patients_overdue", {"pathway_id": PW, "step": "telemon", "asst": "asst_mantova"}),
    ("free_slots", {"service": "echo", "asst": "asst_cremona"}),
    ("adherence_by_group", {"pathway_id": PW, "grouping": "mmg"}),
    ("adherence_by_group", {"pathway_id": PW, "grouping": "age_band", "measure": "telemonitoring"}),
    ("readmissions_by_comune", {"pathway_id": PW}),
    ("compare_segments", {"pathway_id": PW, "a": {"lives_alone": True, "age_min": 75}, "b": {}, "metric": "on_time_fraction"}),
    ("compare_segments", {"pathway_id": PW, "a": {"lives_alone": True}, "b": {}, "metric": "risk_mean"}),
    ("risk_drivers", {"pathway_id": PW}),
    ("risk_drivers", {"pathway_id": PW, "segment": {"asst_id": "asst_mantova", "age_min": 75}}),
])
def test_envelope(ctx, name, args):
    result = tools.call(ctx, name, args)
    assert list(result) == ["data", "source"], result
    src = result["source"]
    assert (src["tool"], src["run_id"], src["day"]) == (name, "s2_agents", 62)
    assert args.items() <= src["args"].items()  # defaults are filled in, so a re-run repeats the same call
    assert tools.call(ctx, name, src["args"]) == result  # the Verifier's re-run (C5)


@pytest.mark.parametrize("name, args, code", [
    ("wait_by_hospital", {"pathway_id": "copd_v1", "step": "echo"}, "unknown_pathway"),
    ("wait_by_hospital", {"pathway_id": PW, "step": "ecg"}, "unknown_step"),
    ("wait_by_hospital", {"pathway_id": PW, "step": "telemon"}, "bad_argument"),  # not booked
    ("patients_overdue", {"pathway_id": PW, "step": "discharge"}, "bad_argument"),  # no deadline
    ("free_slots", {"service": "mri"}, "bad_argument"),
    ("free_slots", {"service": "echo", "asst": "asst_milano"}, "bad_argument"),
    ("adherence_by_group", {"pathway_id": PW, "grouping": "street"}, "bad_argument"),
    ("compare_segments", {"pathway_id": PW, "a": {"colour": "red"}, "b": {}, "metric": "dispensing"}, "bad_argument"),
    ("compare_segments", {"pathway_id": PW, "a": {"age_min": 120}, "b": {}, "metric": "dispensing"}, "empty_result"),
    ("risk_drivers", {"pathway_id": PW, "segment": {"age_max": 40}}, "empty_result"),  # nobody at high risk
    ("wait_by_hospital", {"pathway_id": "../../demo/truth/scenario_2", "step": "echo"}, "bad_argument"),
    ("text_to_sql", {"sql": "SELECT 1"}, "bad_argument"),
])
def test_errors(ctx, name, args, code):
    result = tools.call(ctx, name, args)
    assert list(result) == ["error"]
    assert result["error"]["code"] == code, result


@pytest.mark.parametrize("step", ["telemon", "cardio_visit", "echo", "lab_bnp"])
def test_patients_overdue_agrees_with_the_state_engine(ctx, step):
    # Same rules (SPEC §5.1) in SQL and in engine.state, on the day pathway_state was last updated.
    result = tools.call(ctx, "patients_overdue", {"pathway_id": PW, "step": step, "limit": 100})["data"]
    engine = ctx.db.rows("SELECT count(*) FROM pathway_state WHERE list_contains(overdue_steps, $s)", {"s": step})[0][0]
    assert result["count"] == engine
    top = result["patients"][0]
    due = ctx.db.rows("SELECT list_contains(overdue_steps, $s) FROM pathway_state WHERE patient_id = $p",
                      {"s": step, "p": top["patient_id"]})[0][0]
    assert due
    assert [p["days_overdue"] for p in result["patients"]] == sorted((p["days_overdue"] for p in result["patients"]),
                                                                    reverse=True)


def test_tools_see_the_patterns_of_scenario_2(ctx):
    late = tools.Context("s2_agents", ctx.db, 35)
    wait = tools.call(late, "wait_by_hospital", {"pathway_id": PW, "step": "echo", "period_days": 7})["data"]
    assert max(wait, key=wait.get) == "Ospedale B"  # pattern 1
    groups = tools.call(late, "adherence_by_group", {"pathway_id": PW, "grouping": "mmg_group"})["data"]
    assert next(iter(groups)) == "coop_3"  # pattern 2
    comuni = tools.call(late, "adherence_by_group", {"pathway_id": PW, "grouping": "comune",
                                                     "measure": "telemonitoring"})["data"]
    assert {"Poggio Rusco", "Borgocarbonara", "Sermide e Felonica"} <= set(comuni)  # pattern 3
    assert list(comuni)[-1] == "rest_of_ats"
    assert len(comuni) == tools.GROUPS_SHOWN + 1


def test_wait_by_hospital_reproduces_the_fixture(ctx):
    # The fixture was made by the same call on the live run on day 35; bookings are events, so a finished
    # run gives the same answer for that day.
    fixture = json.loads((FIXTURES / "tools" / "wait_by_hospital.json").read_text(encoding="utf-8"))
    again = tools.call(tools.Context("s2_agents", ctx.db, 35), "wait_by_hospital", fixture["source"]["args"])
    assert again["data"] == fixture["data"]


def test_risk_tools_read_what_risk_wrote(ctx):
    data = tools.call(ctx, "risk_drivers", {"pathway_id": PW})["data"]
    high = ctx.db.rows("SELECT count(*) FROM pathway_state WHERE risk_score >= $h", {"h": tools.HIGH_RISK})[0][0]
    assert data["patients"] == high > 0
    weights = [d["weight"] for d in data["drivers"]]
    assert weights == sorted(weights, reverse=True)
    assert 0 < weights[-1] <= weights[0] <= 1
    mean = tools.call(ctx, "compare_segments", {"pathway_id": PW, "a": {}, "b": {}, "metric": "risk_mean"})["data"]["a"]
    assert mean == ctx.db.rows("SELECT round(avg(risk_score), 4) FROM pathway_state")[0][0]


def test_risk_tools_say_when_risk_never_ran(tick):
    _, q = tick  # an empty run: nobody scored
    ctx = tools.Context("s2_agents", q, 0)
    for name, args in [("risk_drivers", {"pathway_id": PW}),
                       ("compare_segments", {"pathway_id": PW, "a": {}, "b": {}, "metric": "risk_mean"})]:
        assert tools.call(ctx, name, args)["error"]["code"] == "empty_result"


def test_agents_reach_the_database_only_through_query():
    source = Path(tools.__file__).read_text(encoding="utf-8")
    assert source.count(".execute(") == 1  # inside Query.rows
