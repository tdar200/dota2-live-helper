from fastapi.testclient import TestClient
from app.main import app, STATE, HUB


def setup_function():
    STATE.enemy_heroes = []
    STATE.ally_heroes = []
    HUB.last = None


def test_allies_sets_state_and_returns_count():
    client = TestClient(app)
    r = client.post("/allies", json={"heroes": ["npc_dota_hero_lion"]})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "count": 1}
    assert STATE.ally_heroes == ["npc_dota_hero_lion"]


def test_draft_present_in_payload_after_enemies():
    client = TestClient(app)
    client.post("/enemies", json={"heroes": ["npc_dota_hero_zuus"]})
    HUB.last = None
    with client.websocket_connect("/ws") as ws:
        client.post("/gsi", json={"map": {"clock_time": 60}})
        data = ws.receive_json()
    assert "draft" in data and data["draft"] is not None
    assert isinstance(data["draft"]["picks"], list)
    assert len(data["draft"]["picks"]) >= 1  # pocket heroes ranked
