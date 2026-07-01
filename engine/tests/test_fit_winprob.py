import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from fit_winprob import build_table


def test_build_table_buckets_and_counts():
    # three samples at ~15 min, lead ~4000: two radiant wins, one loss
    samples = [
        (900, 4100, True),
        (905, 3900, True),
        (910, 4000, False),
    ]
    table = build_table(samples)
    assert table["minute_bucket"] == 5
    assert table["lead_bucket"] == 2000
    cell = table["buckets"]["15"]["4000"]
    assert cell == {"wins": 2, "total": 3}
