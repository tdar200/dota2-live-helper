from app.state import GameState
from app.advice import build_advice


def test_build_advice_returns_upcoming_timings():
    state = GameState(clock_time=300)
    state.map.clock_time = 300
    payload = build_advice(state, horizon_s=600, limit=6)
    assert payload.clock_time == 300
    assert len(payload.timings) <= 6
    assert payload.timings == sorted(payload.timings, key=lambda h: h.seconds_until)
    assert all(h.seconds_until <= 600 for h in payload.timings)


def test_build_advice_no_clock_yields_empty():
    payload = build_advice(GameState())
    assert payload.clock_time is None
    assert payload.timings == []
