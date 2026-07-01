import json
import math
from pathlib import Path

CACHE_PATH = Path(__file__).parent / "cache" / "winprob.json"
MINUTE_BUCKET = 5
LEAD_BUCKET = 2000


def bucket_minute(clock_s: int) -> int:
    minutes = max(0, clock_s) // 60
    return (minutes // MINUTE_BUCKET) * MINUTE_BUCKET


def bucket_lead(lead: int) -> int:
    return round(lead / LEAD_BUCKET) * LEAD_BUCKET


def _scale(clock_s: int) -> float:
    minutes = max(0, clock_s) // 60
    return max(2500.0, 12000.0 - 250.0 * minutes)


def _logistic(lead: int, clock_s: int) -> float:
    return 1.0 / (1.0 + math.exp(-lead / _scale(clock_s)))


def load_winprob(path: Path = CACHE_PATH) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text())


def win_probability(lead: int, clock_s: int, table: dict | None, *, min_total: int = 20) -> float:
    if table:
        cell = (
            table.get("buckets", {})
            .get(str(bucket_minute(clock_s)), {})
            .get(str(bucket_lead(lead)))
        )
        if cell and cell.get("total", 0) >= min_total:
            return cell.get("wins", 0) / cell["total"]
    return _logistic(lead, clock_s)
