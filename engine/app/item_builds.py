import json
from pathlib import Path
from pydantic import BaseModel, Field

CACHE_PATH = Path(__file__).parent / "cache" / "item_builds.json"


class PhaseItem(BaseModel):
    id: int
    key: str
    display: str
    count: int


class Benchmarks(BaseModel):
    percentiles: list[float] = []
    gold_per_min: list[float] = []
    xp_per_min: list[float] = []
    last_hits_per_min: list[float] = []
    # Added for the live performance scorecard; empty until a benchmark re-pull.
    hero_damage_per_min: list[float] = []
    kills_per_min: list[float] = []


class HeroItemBuild(BaseModel):
    hero_id: int
    display: str
    builds: dict[str, list[PhaseItem]] = Field(default_factory=dict)
    benchmarks: Benchmarks = Field(default_factory=Benchmarks)


class ItemBuildData(BaseModel):
    has_data: bool
    heroes: dict[str, HeroItemBuild] = Field(default_factory=dict)
    # {"item_blink": 2250, ...} — populated on a benchmark re-pull; used to
    # compute live net worth (gold + owned-item costs). Empty is degrade-safe.
    item_costs: dict[str, int] = Field(default_factory=dict)


def load_item_builds(path: Path | None = None) -> ItemBuildData:
    cache = path if path is not None else CACHE_PATH
    if not cache.exists():
        return ItemBuildData(has_data=False)
    try:
        raw = json.loads(cache.read_text())
        heroes = {k: HeroItemBuild.model_validate(v) for k, v in raw.get("heroes", {}).items()}
        costs = {k: int(v) for k, v in (raw.get("item_costs") or {}).items() if v is not None}
        return ItemBuildData(has_data=True, heroes=heroes, item_costs=costs)
    except Exception:
        return ItemBuildData(has_data=False)
