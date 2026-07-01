from app.winprob import win_probability, bucket_minute, bucket_lead, load_winprob
from pathlib import Path


def test_logistic_fallback_even_at_zero_lead():
    p = win_probability(0, 600, None)
    assert abs(p - 0.5) < 1e-9


def test_logistic_monotonic_in_lead():
    lo = win_probability(-6000, 1200, None)
    hi = win_probability(6000, 1200, None)
    assert lo < 0.5 < hi


def test_empirical_bucket_used_when_dense():
    table = {"buckets": {"15": {"4000": {"wins": 70, "total": 100}}}}
    # clock 15:20 -> minute bucket 15; lead 4100 -> lead bucket 4000
    assert bucket_minute(920) == 15
    assert bucket_lead(4100) == 4000
    assert win_probability(4100, 920, table) == 0.70


def test_sparse_bucket_falls_back_to_logistic():
    table = {"buckets": {"15": {"4000": {"wins": 3, "total": 5}}}}
    p = win_probability(4100, 920, table, min_total=20)
    assert p != 0.6  # not the empirical 3/5; used logistic instead


def test_missing_cache_returns_none():
    assert load_winprob(Path("/nonexistent/winprob.json")) is None
