"""Fixtures for every contract (delivery plan step 1.23): up to date, deterministic and in the SPEC's shape."""

import json

import duckdb
import pytest

from api.main import StreamMessage
from engine.db import connect_for_tools
from fixtures.scenario import FIXTURES, MARIA

TOOL_ERRORS = {"unknown_pathway", "unknown_step", "bad_argument", "empty_result"}  # SPEC §6
EVENT_ITEM = ["day", "kind", "event_id", "event_type", "code", "value", "facility_id", "facility_name", "source",
              "action_id"]
ACTION_ITEM = ["day", "kind", "action_id", "type", "agent", "status", "rationale"]


@pytest.fixture(scope="module")
def built(fixture_scenario):
    runs, files = fixture_scenario
    return runs, {path: json.loads(text) for path, text in files.items()}


def columns(runs, table):
    with duckdb.connect(runs / "s2_agents.duckdb", read_only=True) as con:
        return [r[0] for r in con.execute(f"DESCRIBE {table}").fetchall()]


def bilingual(text):
    assert set(text) == {"it", "en"}, text
    assert all(isinstance(v, str) and v for v in text.values()), text


def test_committed_fixtures_match_the_builder(fixture_scenario):
    # Regenerate with: uv run python testing/fixtures/scenario.py
    _, files = fixture_scenario
    committed = {p.relative_to(FIXTURES).as_posix() for p in FIXTURES.rglob("*.json")}
    assert committed == set(files)
    for path, text in files.items():
        assert (FIXTURES / path).read_text(encoding="utf-8") == text, path


def test_table_rows_have_the_table_columns(built):
    runs, f = built
    for path, table in [("api/kpi_ats_s2_agents.json", "kpi_daily"), ("api/kpi_s2_agents_day62.json", "kpi_daily"),
                        ("api/actions_s2_agents.json", "actions")]:
        assert f[path], path
        for row in f[path]:
            assert list(row) == columns(runs, table), path
    for a in f["api/actions_s2_agents.json"]:
        bilingual(a["rationale"])
        assert a["evidence"], "an action without a tool source is rejected (SPEC §7.3)"
    levels = {(r["level"]) for r in f["api/kpi_s2_agents_day62.json"]}
    assert levels == {"ats", "asst", "comune"}


def test_patient_360(built):
    runs, f = built
    for arm in ("s2_agents", "s2_baseline"):
        p = f[f"api/patient_{MARIA}_{arm}.json"]
        assert list(p) == ["patient", "pathways", "timeline"]
        assert list(p["patient"]) == columns(runs, "patients") + ["comune_name"]
        assert [list(s) for s in p["pathways"]] == [columns(runs, "pathway_state")]
        for item in p["timeline"]:
            assert list(item) == (EVENT_ITEM if item["kind"] == "event" else ACTION_ITEM), item
        assert [i["day"] for i in p["timeline"]] == sorted(i["day"] for i in p["timeline"])
    # Day 62. With the call on day 31 Maria stays on track; without it her weight rises on day 43, the
    # weight_gain rule pulls the cardiology visit to day 50 (step 2.8), and she is readmitted on day 47
    # instead. Her discharge on day 55 starts the visit's clock again, which ends the pull: due on day 85.
    agents_state = f[f"api/patient_{MARIA}_s2_agents.json"]["pathways"][0]
    baseline_state = f[f"api/patient_{MARIA}_s2_baseline.json"]["pathways"][0]
    assert agents_state["status"] == "on_track"
    assert (baseline_state["status"], baseline_state["overdue_steps"], baseline_state["next_due_day"]) == (
        "on_track", [], 55 + 30)
    days = lambda arm, t: [i["day"] for i in f[f"api/patient_{MARIA}_{arm}.json"]["timeline"] if i.get("event_type") == t]
    assert days("s2_baseline", "ADMISSION") == [-8, 47]
    assert days("s2_agents", "ADMISSION") == [-8]
    agents = f[f"api/patient_{MARIA}_s2_agents.json"]["timeline"]
    call = [i for i in agents if i["day"] == 31 and i["action_id"] == "act_s2_agents_1"]
    assert [i["kind"] for i in call] == ["action", "event"]  # the action, then the CALL that records it
    bilingual(call[0]["rationale"])


def test_stream_messages(built):
    runs, f = built
    payload_keys = {"tick": ["speed", "kpi"],
                    "alert": ["alert_id", "level", "facility_id", "group_key", "investigation_id", "text"],
                    "action": columns(runs, "actions"),
                    "investigation": ["investigation_id", "step", "tool", "args", "result_summary", "verified", "final"]}
    messages = [m for path, m in f.items() if path.startswith("stream/")]
    messages = [x for m in messages for x in (m if isinstance(m, list) else [m])]
    assert {m["type"] for m in messages} == set(payload_keys)
    for m in messages:
        StreamMessage.model_validate(m)  # the envelope the API sends
        assert list(m["payload"]) == payload_keys[m["type"]], m["type"]
    for m in messages:
        if m["type"] == "alert":
            bilingual(m["payload"]["text"])
        if m["type"] == "investigation":
            bilingual(m["payload"]["result_summary"])
    assert list(f["stream/tick.json"]["payload"]["kpi"]) == [c for c in columns(runs, "kpi_daily")
                                                            if c not in ("day", "level", "key")]
    steps = f["stream/investigation.json"]  # the Investigator on the alarm's tick, from the cache (C25)
    assert [s["payload"]["step"] for s in steps] == list(range(1, len(steps) + 1))
    assert [s["payload"]["final"] for s in steps] == [False] * (len(steps) - 1) + [True]
    assert f["stream/alert_regional.json"]["payload"]["investigation_id"] == steps[0]["payload"]["investigation_id"]
    stored = f["api/investigations_s2_agents.json"]  # the two group alarms' of day 0 (C26), then the echo alarm's
    assert len(stored) == 3
    assert steps[0]["payload"]["investigation_id"] in [i["investigation_id"] for i in stored]
    for inv in stored:
        assert all(c["step"] in {s["step"] for s in inv["steps"]} for c in inv["claims"])


def test_tool_envelopes(built):
    _, f = built
    for name in ("wait_by_hospital", "free_slots"):
        result = f[f"tools/{name}.json"]
        assert list(result) == ["data", "source"]
        assert list(result["source"]) == ["tool", "args", "run_id", "day"]
        assert result["source"]["tool"] == name
    err = f["tools/error.json"]["error"]
    assert list(err) == ["code", "message"]
    assert err["code"] in TOOL_ERRORS
    wait = f["tools/wait_by_hospital.json"]["data"]
    assert max(wait, key=wait.get) == "Ospedale B"  # scenario 2's echo bottleneck (pattern 1)


def test_views_have_the_spec_columns(built):
    _, f = built
    assert [list(r) for r in f["api/sankey_s2_agents.json"]][0] == ["pathway_id", "from_step", "to_step", "status", "patients"]
    ats = next(r for r in f["api/kpi_s2_agents_day62.json"] if r["level"] == "ats")
    assert sum(r["patients"] for r in f["api/sankey_s2_agents.json"]) == ats["patients"]
    assert list(f["api/map_s2_agents.json"][0]) == ["comune_istat", "pathway_id", "adherence_pct", "risk_mean",
                                                    "high_risk_patients", "readmission_rate_30d", "alarm"]
    worklist = f["api/worklist_s2_agents.json"]
    assert [r["rank"] for r in worklist] == list(range(1, 21))
    assert list(worklist[0]) == ["rank", "patient_id", "risk_score", "reasons", "pathways", "escalation_step", "script",
                                 "outcome"]
    for r in worklist:
        bilingual(r["reasons"])


def test_fixture_runs_open_through_the_tool_connection(fixture_scenario):
    # Step 1.24 tests its tools on these runs; they read them the way tools do (SPEC §6).
    runs, _ = fixture_scenario
    for run_id in ("s2_baseline", "s2_agents"):
        con = connect_for_tools(run_id, runs_dir=runs)
        try:
            assert con.execute("SELECT max(day) FROM kpi_daily").fetchall() == [(62,)]
            assert con.execute("SELECT count(*) FROM pathway_state").fetchall()[0][0] > 9900
        finally:
            con.close()
