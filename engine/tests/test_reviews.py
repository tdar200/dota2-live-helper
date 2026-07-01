import json
from fastapi.testclient import TestClient
from app.reviews import load_review, list_reviews
from app.main import app


def test_load_review_missing(tmp_path):
    assert load_review(123, dir=tmp_path) is None


def test_load_review_present(tmp_path):
    (tmp_path / "7.json").write_text(json.dumps({"match_id": 7, "you_won": True}))
    assert load_review(7, dir=tmp_path)["match_id"] == 7


def test_list_reviews_absent_dir_is_empty(tmp_path):
    assert list_reviews(dir=tmp_path / "nope") == []


def test_list_reviews_metadata(tmp_path):
    (tmp_path / "7.json").write_text(json.dumps(
        {"match_id": 7, "your_side": "radiant", "you_won": True, "duration_s": 2400, "curve": []}))
    assert list_reviews(dir=tmp_path) == [
        {"match_id": 7, "your_side": "radiant", "you_won": True, "duration_s": 2400}]


def test_review_endpoint_404_when_absent():
    assert TestClient(app).get("/review/999999999").status_code == 404


def test_reviews_endpoint_returns_list():
    resp = TestClient(app).get("/reviews")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
