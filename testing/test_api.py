from fastapi.testclient import TestClient

from api.main import create_app


def make_client(tmp_path):
    (tmp_path / "index.html").write_text("<title>CarePath AI</title>", encoding="utf-8")
    return TestClient(create_app(tick_seconds=0.01, scenario=2, ui_dir=tmp_path))


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
