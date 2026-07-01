import json
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict

CACHE_PATH = Path(__file__).parent / "cache" / "matchups.json"
SEED_PATH = Path(__file__).parent / "data" / "herald_winrates.json"


class HeroMatchups(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    vs: dict[str, float] = Field(default_factory=dict)
    with_: dict[str, float] = Field(default_factory=dict, alias="with")


class MatchupData(BaseModel):
    has_data: bool
    bracket: str | None = None
    heroes: dict[str, HeroMatchups] = Field(default_factory=dict)
    base_winrates: dict[str, float] = Field(default_factory=dict)


def load_matchups(cache_path: Path = CACHE_PATH, seed_path: Path = SEED_PATH) -> MatchupData:
    base = json.loads(seed_path.read_text())
    if not cache_path.exists():
        return MatchupData(has_data=False, base_winrates=base)
    raw = json.loads(cache_path.read_text())
    heroes = {k: HeroMatchups.model_validate(v) for k, v in raw.get("heroes", {}).items()}
    return MatchupData(
        has_data=True, bracket=raw.get("bracket"),
        heroes=heroes, base_winrates=base,
    )
