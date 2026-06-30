from fastapi.testclient import TestClient
from app.main import app, STATE


def test_gsi_accepts_post_and_updates_clock():
    client = TestClient(app)
    payload = {"map": {"clock_time": 95}}
    resp = client.post("/gsi", json=payload)
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    assert STATE.clock_time == 95
