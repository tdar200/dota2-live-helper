from fastapi.testclient import TestClient
from app.main import app, STATE, HUB


def setup_function():
    STATE.net_worth_lead = None
    STATE.roshan_dead_clock = None
    STATE.clock_time = None
    HUB.last = None


def test_networth_sets_lead_and_returns():
    client = TestClient(app)
    r = client.post("/networth", json={"lead": 5000})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "lead": 5000}
    assert STATE.net_worth_lead == 5000


def test_roshan_records_current_clock_and_clear():
    client = TestClient(app)
    client.post("/gsi", json={"map": {"clock_time": 1000}})
    r = client.post("/roshan", json={})
    assert r.json() == {"ok": True, "roshan_dead_clock": 1000}
    assert STATE.roshan_dead_clock == 1000
    r2 = client.post("/roshan", json={"clear": True})
    assert r2.json() == {"ok": True, "roshan_dead_clock": None}


def test_macro_present_in_payload():
    client = TestClient(app)
    client.post("/networth", json={"lead": 3000})
    HUB.last = None
    with client.websocket_connect("/ws") as ws:
        client.post("/gsi", json={"map": {"clock_time": 1200}, "hero": {"alive": True}})
        data = ws.receive_json()
    assert data["macro"] is not None
    assert data["macro"]["recommendation"]
    assert data["macro"]["win_prob"] is not None
