from app.state import GameState
from app.advisors.context import AdviceContext
from app.advisors import timings


def test_timings_advise_returns_sorted_within_horizon():
    ctx = AdviceContext(state=GameState(clock_time=300), horizon_s=600, limit=6)
    hits = timings.advise(ctx)
    assert hits == sorted(hits, key=lambda h: h.seconds_until)
    assert all(h.seconds_until <= 600 for h in hits)
    assert len(hits) <= 6


def test_timings_advise_empty_when_no_clock():
    ctx = AdviceContext(state=GameState())
    assert timings.advise(ctx) == []
