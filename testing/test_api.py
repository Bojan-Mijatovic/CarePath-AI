"""API on the real tick (step 2.1): a small demo, scenario 2 only, opening on day 3."""

import json
import time

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from engine import pathway as pathway_model
from engine import story
from engine.tick import Demo

START, DAYS = 3, 30


def make_client(tmp_path, demo=None):
    (tmp_path / "index.html").write_text("<title>CarePath AI</title>", encoding="utf-8")
    return TestClient(create_app(demo=demo, tick_seconds=0.05, ui_dir=tmp_path))


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    demo = Demo(tmp_path_factory.mktemp("api_runs"), scenarios=(2,), start_day=START, days=DAYS)
    with make_client(tmp_path_factory.mktemp("ui"), demo) as c:
        deadline = time.monotonic() + 120
        while c.get("/api/kpi").status_code == 503:
            assert time.monotonic() < deadline, "the demo runs were not ready in 120 s"
            time.sleep(0.2)
        yield c


def test_health(tmp_path):
    assert make_client(tmp_path).get("/api/health").json() == {"status": "ok"}


def test_built_console_is_served_at_root(tmp_path):
    resp = make_client(tmp_path).get("/")
    assert resp.status_code == 200
    assert "CarePath AI" in resp.text


def test_api_works_without_built_console():
    client = TestClient(create_app(ui_dir=None))
    assert client.get("/api/health").status_code == 200


def test_pathway_is_the_spec_file(tmp_path):
    # C22: no runs needed; the file in spec/pathways/ is the response and its fixture.
    client = make_client(tmp_path)
    expected = json.loads((pathway_model.PATHWAYS_DIR / "hf_lombardia_v1.json").read_text(encoding="utf-8"))
    assert client.get("/api/pathways/hf_lombardia_v1").json() == expected
    for missing in ("copd_v1", "pathway.schema", "..%2Fpathways%2Fhf_lombardia_v1"):
        assert client.get(f"/api/pathways/{missing}").status_code == 404


def test_whatif_reads_the_grid_without_the_runs(tmp_path):
    # C27, D48: the precomputed grid of the scenario on screen (scenario 1 by default); no run is needed.
    client = make_client(tmp_path)
    out = client.post("/api/whatif", json={"levers": {"extra_slots": 2}, "months": 6}).json()
    assert out["scenario"] == 1 and out["levers"] == {"extra_slots": 2} and out["precomputed"] is True
    assert out["avoided_readmissions"] == out["baseline"]["readmissions"] - out["lever"]["readmissions"]
    assert "kpi" not in out["lever"]
    assert client.post("/api/whatif", json={"levers": {"extra_slots": 9}}).status_code == 422
    assert client.post("/api/whatif", json={"months": 3}).status_code == 422
    assert client.post("/api/whatif", json={"levers": {"echo": 1}}).status_code == 422
    empty = TestClient(create_app(ui_dir=None, whatif_dir=tmp_path / "none"))
    assert empty.post("/api/whatif", json={}).status_code == 503


def test_data_waits_for_the_runs(tmp_path):
    client = make_client(tmp_path)  # no lifespan, so the runs are never built
    assert client.get("/api/kpi").status_code == 503
    assert client.post("/api/sim/start").status_code == 503


def test_opens_paused_on_the_start_day(client):
    with client.websocket_connect("/api/stream") as ws:
        first = ws.receive_json()
    assert (first["type"], first["scenario"], first["day"]) == ("tick", 2, START)
    assert first["payload"]["speed"] == 0
    assert first["payload"]["kpi"]["pathway_id"] == "hf_lombardia_v1"
    assert client.post("/api/sim/scenario/2").json() == {"scenario": 2, "day": START, "speed": 0}
    assert client.post("/api/sim/scenario/1").status_code == 422  # not one of this demo's scenarios


def test_start_advances_and_pause_stops(client):
    with client.websocket_connect("/api/stream") as ws:
        ws.receive_json()
        assert client.post("/api/sim/start").json()["speed"] == 1
        days = []
        while len(days) < 3:  # alerts from Monitoring come between the ticks
            msg = ws.receive_json()
            if msg["type"] == "tick":
                days.append(msg["day"])
        stopped = client.post("/api/sim/pause").json()
    assert days == list(range(days[0], days[0] + 3))
    assert days[0] == START + 1
    assert stopped["speed"] == 0
    assert client.post("/api/sim/speed", json={"factor": 3}).status_code == 422


def test_jump_back_replays_the_same_days(client):
    client.post("/api/sim/pause")
    client.post(f"/api/sim/jump/{START + 4}")
    before = client.get("/api/kpi", params={"level": "ats"}).json()
    assert client.post(f"/api/sim/jump/{START + 1}").json()["day"] == START + 1
    assert client.post(f"/api/sim/jump/{START + 4}").json()["day"] == START + 4
    assert client.get("/api/kpi", params={"level": "ats"}).json() == before
    assert [r["day"] for r in before] == list(range(START + 5))
    assert client.post(f"/api/sim/jump/{DAYS}").status_code == 422


def test_a_question_nobody_warmed_has_no_answer(client):
    # Step 2.10: POST /api/ask in cache_only (D14); no template stands in for the Investigator.
    resp = client.post("/api/ask", json={"question": "Una domanda che nessuno ha mai fatto?"})
    assert resp.status_code == 503
    assert "no answer" in resp.json()["detail"]
    assert client.post("/api/ask", json={"question": ""}).status_code == 422


def test_sankey_and_map(client):
    sankey = client.get("/api/sankey").json()
    assert list(sankey[0]) == ["pathway_id", "from_step", "to_step", "status", "patients"]
    day = client.post("/api/sim/pause").json()["day"]
    ats = client.get("/api/kpi", params={"level": "ats"}).json()[-1]
    assert ats["day"] == day
    assert sum(r["patients"] for r in sankey) == ats["patients"]
    comuni = client.get("/api/map", params={"pathway_id": "hf_lombardia_v1"}).json()
    assert {r["comune_istat"] for r in comuni} == {
        r["key"] for r in client.get("/api/kpi", params={"level": "comune"}).json() if r["day"] == day}


def test_worklist_by_day(client):
    day = client.post("/api/sim/pause").json()["day"]
    today = client.get("/api/worklist").json()
    assert today == client.get("/api/worklist", params={"day": day}).json()
    assert [r["rank"] for r in today] == list(range(1, len(today) + 1))
    assert client.get("/api/worklist", params={"day": day - 1}).json()  # earlier lists stay (demo step 9a)
    assert client.get("/api/worklist", params={"run": "s2_baseline"}).json() == []


def test_patient_actions_and_story(client):
    maria = client.get("/api/patients/p_00001", params={"run": "s2_baseline"}).json()
    assert maria["patient"]["comune_name"] == "Poggio Rusco"
    assert max(i["day"] for i in maria["timeline"]) <= client.post("/api/sim/pause").json()["day"]
    assert client.get("/api/patients/p_99999").status_code == 404
    assert client.get("/api/kpi", params={"run": "s3_agents"}).status_code == 404
    assert client.get("/api/actions", params={"status": "proposed"}).json() == []  # no agents until 2.12
    recorded = client.get("/api/patients/p_00001", params={"run": "s2_baseline", "day": 62}).json()
    assert recorded == json.loads(story.path("p_00001", "s2_baseline", 62).read_text(encoding="utf-8"))
    assert client.get("/api/patients/p_00001", params={"run": "s2_baseline", "day": 61}).status_code == 404


def _waiting(demo: Demo, action_id: str, day: int) -> None:
    """A proposed action as Intervention will create it (step 2.13), written here by the test."""
    demo.read("s2_agents", lambda cur: cur.execute("""
        INSERT INTO actions VALUES ($id, 'intervention', 'reschedule', 'p_00001', NULL, 'hf_lombardia_v1', '{}',
            '{"it": "x", "en": "x"}', '[{"tool": "free_slots"}]', 2, 'proposed', $d, NULL, NULL)""",
                                                    {"id": action_id, "d": day}))


def _audit(demo: Demo) -> list[tuple]:
    return demo.read("s2_agents", lambda cur: cur.execute(
        "SELECT ts_day, action_id, event, actor, details FROM audit_log ORDER BY rowid").fetchall())


def test_approvals_and_autonomy_write_the_audit_log(client):
    # Steps 2.18 and 2.12: the console's decisions go through the action service and land in the audit log
    # (SPEC §7); an approved action is executed at once and pushed on the stream.
    demo = client.app.state.demo
    day = client.post("/api/sim/pause").json()["day"]
    settings = client.get("/api/settings").json()["autonomy"]
    assert settings["reschedule"] == {"level": 2, "default": 2, "fixed": False}
    assert settings["rule_proposal"] == {"level": 1, "default": 1, "fixed": True}

    raised = client.put("/api/settings/autonomy", json={"type": "reschedule", "level": 3}).json()["autonomy"]
    assert raised["reschedule"]["level"] == 3 == client.get("/api/settings").json()["autonomy"]["reschedule"]["level"]
    assert client.put("/api/settings/autonomy", json={"type": "rule_proposal", "level": 3}).status_code == 422
    assert client.put("/api/settings/autonomy", json={"type": "reschedule", "level": 4}).status_code == 422
    assert client.put("/api/settings/autonomy", json={"type": "diagnosis", "level": 3}).status_code == 422

    _waiting(demo, "act_test_1", day)
    _waiting(demo, "act_test_2", day)
    assert [a["action_id"] for a in client.get("/api/actions", params={"status": "proposed"}).json()] == [
        "act_test_1", "act_test_2"]
    with client.websocket_connect("/api/stream") as ws:
        ws.receive_json()  # the opening tick
        assert client.post("/api/actions/act_test_1/approve").json()["status"] == "executed"  # step 2.12: at once
        pushed = ws.receive_json()
    assert (pushed["type"], pushed["payload"]["action_id"], pushed["payload"]["status"]) == ("action", "act_test_1", "executed")
    assert client.post("/api/actions/act_test_2/reject").json()["status"] == "rejected"
    assert client.post("/api/actions/act_test_1/reject").status_code == 422  # decided already
    assert client.post("/api/actions/act_none/approve").status_code == 404
    assert client.post("/api/actions/act_test_2/undo").status_code == 422  # only an executed action
    assert client.get("/api/actions", params={"status": "proposed"}).json() == []
    decided = {a["action_id"]: (a["status"], a["decided_by"]) for a in client.get("/api/actions").json()}
    assert decided == {"act_test_1": ("executed", "manager"), "act_test_2": ("rejected", "manager")}
    assert client.post("/api/actions/act_test_1/undo").json()["status"] == "undone"

    log = _audit(demo)
    assert [(d, e, a) for d, _, e, a, _ in log] == [
        (day, "config_changed", "manager"), (day, "approved", "manager"), (day, "executed", "action_service"),
        (day, "rejected", "manager"), (day, "undone", "manager")]
    assert json.loads(log[0][4]) == {"setting": "autonomy", "type": "reschedule", "level": 3, "before": 2}
    baseline = demo.read("s2_baseline", lambda cur: cur.execute("SELECT count(*) FROM audit_log").fetchall()[0][0])
    assert baseline == 0  # the arm without CarePath has no agents and no settings
