"""Degrade-safe loader for the personal win-rate cache.

The engine ONLY reads this cache (written by scripts/refresh_personal_stats.py).
Missing / malformed / absent cache -> has_data=False with empty maps, so every
consumer can `.get(hero)` and quietly render nothing.
"""
import json
from pathlib import Path
from pydantic import BaseModel, Field

CACHE_PATH = Path(__file__).parent / "cache" / "personal_stats.json"


class HeroWR(BaseModel):
    games: int = 0
    wins: int = 0
    winrate: float | None = None
    last_played: int | None = None


class ItemWR(BaseModel):
    games: int = 0
    wins: int = 0
    winrate: float | None = None


class PersonalStats(BaseModel):
    has_data: bool
    account_id: int | None = None
    # hero_key -> HeroWR
    heroes: dict[str, HeroWR] = Field(default_factory=dict)
    # hero_key -> {item_key -> ItemWR}
    items: dict[str, dict[str, ItemWR]] = Field(default_factory=dict)


def load_personal_stats(path: Path | None = None) -> PersonalStats:
    cache = path if path is not None else CACHE_PATH
    if not cache.exists():
        return PersonalStats(has_data=False)
    try:
        raw = json.loads(cache.read_text())
        heroes = {
            k: HeroWR.model_validate(v)
            for k, v in raw.get("heroes", {}).items()
        }
        items = {
            hk: {ik: ItemWR.model_validate(iv) for ik, iv in bucket.items()}
            for hk, bucket in raw.get("items", {}).items()
        }
        return PersonalStats(
            has_data=bool(heroes or items),
            account_id=raw.get("account_id"),
            heroes=heroes,
            items=items,
        )
    except Exception:
        return PersonalStats(has_data=False)
