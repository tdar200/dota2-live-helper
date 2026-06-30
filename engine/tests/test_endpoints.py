import json
from pathlib import Path

from fastapi.testclient import TestClient
from app.main import app, STATE

FIX = Path(__file__).parent / "fixtures" / "gsi_early_game.json"


def test_gsi_accepts_post_and_updates_clock():
    client = TestClient(app)
    payload = {"map": {"clock_time": 95}}
    resp = client.post("/gsi", json=payload)
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    assert STATE.clock_time == 95


def test_ws_receives_advice_after_gsi_post():
    client = TestClient(app)
    with client.websocket_connect("/ws") as websocket:
        raw = json.loads(FIX.read_text())
        resp = client.post("/gsi", json=raw)
        assert resp.status_code == 200
        data = websocket.receive_json()
        assert data["clock_time"] == 95
        assert isinstance(data["timings"], list)
        assert len(data["timings"]) >= 1


def test_replay_shape_clock_override_changes_advice():
    client = TestClient(app)
    raw = json.loads(FIX.read_text())
    raw["map"]["clock_time"] = 360  # power rune is due now
    client.post("/gsi", json=raw)
    with client.websocket_connect("/ws") as websocket:
        data = websocket.receive_json()
        assert data["clock_time"] == 360
        names = [t["name"] for t in data["timings"]]
        assert "Power rune" in names
