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


class MatchRecord(BaseModel):
    """One compact match from the /players/{id}/matches list (no parse needed)."""
    match_id: int
    start_time: int | None = None
    duration: int | None = None
    win: bool | None = None
    hero: str | None = None
    kills: int | None = None
    deaths: int | None = None
    assists: int | None = None
    party_size: int | None = None
    game_mode: int | None = None
    lobby_type: int | None = None
    average_rank: int | None = None


class PersonalStats(BaseModel):
    has_data: bool
    account_id: int | None = None
    # hero_key -> HeroWR
    heroes: dict[str, HeroWR] = Field(default_factory=dict)
    # hero_key -> {item_key -> ItemWR}
    items: dict[str, dict[str, ItemWR]] = Field(default_factory=dict)
    # newest-first compact per-match history (trends dashboard)
    match_history: list[MatchRecord] = Field(default_factory=list)


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
        history = []
        for rec in raw.get("match_history", []):
            try:
                history.append(MatchRecord.model_validate(rec))
            except Exception:
                continue  # skip malformed rows, keep the rest
        return PersonalStats(
            has_data=bool(heroes or items),
            account_id=raw.get("account_id"),
            heroes=heroes,
            items=items,
            match_history=history,
        )
    except Exception:
        return PersonalStats(has_data=False)
