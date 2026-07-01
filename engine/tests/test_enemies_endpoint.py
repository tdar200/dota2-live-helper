import json
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app, STATE, HUB

FIX = Path(__file__).parent / "fixtures" / "gsi_early_game.json"


def setup_function():
    STATE.enemy_heroes = []
    HUB.last = None


def test_heroes_endpoint_lists_heroes():
    client = TestClient(app)
    resp = client.get("/heroes")
    assert resp.status_code == 200
    heroes = resp.json()
    assert any(h["key"] == "npc_dota_hero_zuus" and h["display"] == "Zeus" for h in heroes)


def test_enemies_then_gsi_yields_build_with_triggered_situational():
    client = TestClient(app)
    # Sniper fixture hero has no curated build -> set hero to Wraith King via a tweaked payload
    raw = json.loads(FIX.read_text())
    raw["hero"]["name"] = "npc_dota_hero_skeleton_king"
    raw["items"] = {"slot0": {"name": "item_power_treads"}}

    r1 = client.post("/enemies", json={"heroes": ["npc_dota_hero_zuus"]})
    assert r1.status_code == 200 and r1.json()["count"] == 1
    HUB.last = None  # clear /enemies replay so WS connect won't receive stale state

    with client.websocket_connect("/ws") as ws:
        client.post("/gsi", json=raw)
        data = ws.receive_json()

    build = data["build"]
    assert build["has_build"] is True
    assert build["hero_display"] == "Wraith King"
    assert build["next_core"]["item"] == "item_armlet"  # treads owned -> next is armlet
    bkb = next(s for s in build["situational"] if s["item"] == "item_black_king_bar")
    assert bkb["triggered_by"] == ["Zeus"]
