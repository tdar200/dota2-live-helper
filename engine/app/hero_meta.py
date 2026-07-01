"""Degrade-safe loader for the OpenDota Herald-winrate cache.

The engine ONLY reads this cache (written by scripts/refresh_hero_meta.py).
Missing / malformed / absent cache -> has_data=False and an empty hero map,
so every consumer can `.get(hero)` and quietly render nothing.
"""
import json
from pathlib import Path
from pydantic import BaseModel, Field

CACHE_PATH = Path(__file__).parent / "cache" / "hero_meta.json"


class HeroMeta(BaseModel):
    herald_winrate: float | None = None
    herald_pick: int = 0
    herald_win: int = 0


class HeroMetaData(BaseModel):
    has_data: bool
    heroes: dict[str, HeroMeta] = Field(default_factory=dict)


def load_hero_meta(path: Path | None = None) -> HeroMetaData:
    cache = path if path is not None else CACHE_PATH
    if not cache.exists():
        return HeroMetaData(has_data=False)
    try:
        raw = json.loads(cache.read_text())
        heroes = {
            k: HeroMeta.model_validate(v)
            for k, v in raw.get("heroes", {}).items()
        }
        return HeroMetaData(has_data=bool(heroes), heroes=heroes)
    except Exception:
        return HeroMetaData(has_data=False)
