import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from review_match import analyze


def _match():
    # radiant pulls ahead to +10k by minute 3, then a swing down at minute 4
    return {
        "match_id": 42,
        "radiant_win": True,
        "duration": 300,
        "players": [{"account_id": 111, "isRadiant": True}, {"account_id": 222, "isRadiant": False}],
        "radiant_gold_adv": [0, 3000, 9000, 12000, 2000],
        "objectives": [{"time": 245, "type": "CHAT_MESSAGE_ROSHAN_KILL"}],
        "teamfights": [{"start": 230, "end": 260, "deaths": 4}],
    }


def test_radiant_perspective_curve_and_won():
    r = analyze(_match(), account_id=111, table=None)
    assert r["your_side"] == "radiant"
    assert r["you_won"] is True
    assert r["curve"][3]["lead"] == 12000
    assert r["curve"][3]["win_prob"] > 0.5


def test_dire_perspective_negates_lead():
    r = analyze(_match(), account_id=222, table=None)
    assert r["your_side"] == "dire"
    assert r["you_won"] is False
    assert r["curve"][3]["lead"] == -12000
    assert r["curve"][3]["win_prob"] < 0.5


def test_threw_moment_detected_and_labelled():
    r = analyze(_match(), account_id=111, table=None)
    # minute 4: big drop from a winning position -> "threw", labelled from objectives/teamfights
    m = next(x for x in r["moments"] if x["minute"] == 4)
    assert m["kind"] == "threw"
    assert m["delta"] < 0
    assert m["label"] != "big swing"  # Roshan/teamfight nearby


def test_missing_events_degrade_to_big_swing():
    match = _match()
    del match["objectives"]
    del match["teamfights"]
    r = analyze(match, account_id=111, table=None)
    m = next(x for x in r["moments"] if x["minute"] == 4)
    assert m["label"] == "big swing"


def test_no_account_id_defaults_radiant_with_note():
    r = analyze(_match(), account_id=None, table=None)
    assert r["your_side"] == "radiant"
    assert "note" in r
