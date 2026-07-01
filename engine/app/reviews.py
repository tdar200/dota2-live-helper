import json
from pathlib import Path

REVIEWS_DIR = Path(__file__).parent / "cache" / "reviews"


def load_review(match_id: int, dir: Path = REVIEWS_DIR) -> dict | None:
    path = dir / f"{match_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def list_reviews(dir: Path = REVIEWS_DIR) -> list[dict]:
    if not dir.exists():
        return []
    out: list[dict] = []
    for path in sorted(dir.glob("*.json")):
        try:
            r = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        out.append({
            "match_id": r.get("match_id"),
            "your_side": r.get("your_side"),
            "you_won": r.get("you_won"),
            "duration_s": r.get("duration_s"),
        })
    return out
