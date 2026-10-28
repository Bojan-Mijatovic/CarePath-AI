from fastapi.testclient import TestClient

from api.main import create_app


def make_client(tmp_path, fixtures=False):
    (tmp_path / "index.html").write_text("<title>CarePath AI</title>", encoding="utf-8")
    kw = {} if fixtures else {"fixtures_dir": None}
    return TestClient(create_app(tick_seconds=0.001, scenario=2, ui_dir=tmp_path, **kw))


def test_health(tmp_path):
    assert make_client(tmp_path).get("/api/health").json() == {"status": "ok"}


def test_built_console_is_served_at_root(tmp_path):
    resp = make_client(tmp_path).get("/")
    assert resp.status_code == 200
    assert "CarePath AI" in resp.text


def test_api_works_without_built_console():
    client = TestClient(create_app(ui_dir=None))
    assert client.get("/api/health").status_code == 200


def test_stream_sends_tick_envelope(tmp_path):
    with make_client(tmp_path).websocket_connect("/api/stream") as ws:
        first, second = ws.receive_json(), ws.receive_json()
    assert first == {"type": "tick", "scenario": 2, "day": 0, "payload": {}}
    assert second["day"] == 1


def test_without_a_data_source_the_endpoints_say_so(tmp_path):
    assert make_client(tmp_path).get("/api/kpi").status_code == 503


# Fixture mode (step 1.25): the SPEC §10 paths answered from testing/fixtures/.

def test_kpi_from_fixtures(tmp_path):
    client = make_client(tmp_path, fixtures=True)
    rows = client.get("/api/kpi", params={"level": "ats"}).json()
    assert [r["day"] for r in rows] == list(range(63))
    assert {r["key"] for r in rows} == {"ats"}
    asst = client.get("/api/kpi", params={"level": "asst"}).json()
    assert {r["key"] for r in asst} == {"asst_mantova", "asst_cremona", "asst_crema"}
    baseline = client.get("/api/kpi", params={"run": "s2_baseline", "level": "ats"}).json()
    assert baseline[-1]["actions_executed"] == 0


def test_patient_and_actions_from_fixtures(tmp_path):
    client = make_client(tmp_path, fixtures=True)
    maria = client.get("/api/patients/p_00001", params={"run": "s2_baseline"}).json()
    assert maria["patient"]["comune_name"] == "Poggio Rusco"
    assert client.get("/api/patients/p_09999").status_code == 404
    pending = client.get("/api/actions", params={"status": "proposed"}).json()
    assert [a["type"] for a in pending] == ["reschedule"]


def test_choose_scenario(tmp_path):
    client = make_client(tmp_path, fixtures=True)
    assert client.post("/api/sim/scenario/3").json() == {"scenario": 3}
    assert client.post("/api/sim/scenario/4").status_code == 422


def test_stream_replays_the_fixtures_from_day_23(tmp_path):
    with make_client(tmp_path, fixtures=True).websocket_connect("/api/stream") as ws:
        msgs = [ws.receive_json() for _ in range(40 + 6)]  # 40 ticks (days 23-62), 2 alerts, 2 actions, 2 steps
    ticks = [m for m in msgs if m["type"] == "tick"]
    assert [m["day"] for m in ticks] == list(range(23, 63))
    assert set(ticks[0]["payload"]) == {"speed", "kpi"}
    others = [(m["day"], m["type"]) for m in msgs if m["type"] != "tick"]
    assert others == [(31, "alert"), (31, "action"), (35, "alert"), (35, "action"), (35, "investigation"),
                      (35, "investigation")]
    days = [m["day"] for m in msgs]
    assert days == sorted(days)
    assert msgs[days.index(31)]["type"] == "tick"  # a day starts with its tick
