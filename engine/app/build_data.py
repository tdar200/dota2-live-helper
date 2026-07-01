import json
from pathlib import Path
from pydantic import BaseModel, Field

_DATA = Path(__file__).parent / "data"

TRAITS = frozenset({
    "heavy_magic", "evasion", "illusions_summons", "invisibility",
    "high_armor", "healing_regen", "lockdown_silence", "tanky_hp",
})


class Situational(BaseModel):
    item: str
    trait: str
    note: str


class HeroBuild(BaseModel):
    hero: str
    display: str
    source: str
    verified: bool
    skill_order: str
    talents: dict[str, str]
    starting_items: list[str] = Field(default_factory=list)
    core_items: list[str] = Field(default_factory=list)
    situational: list[Situational] = Field(default_factory=list)


class BuildData(BaseModel):
    builds: dict[str, HeroBuild]
    traits: dict[str, list[str]]
    item_names: dict[str, str]
    hero_names: dict[str, str]
    heroes: list[dict]


def load_build_data() -> BuildData:
    item_names = json.loads((_DATA / "item_names.json").read_text())
    traits = json.loads((_DATA / "hero_traits.json").read_text())
    heroes = json.loads((_DATA / "heroes.json").read_text())
    hero_names = {h["key"]: h["display"] for h in heroes}

    builds: dict[str, HeroBuild] = {}
    for path in sorted((_DATA / "builds").glob("*.json")):
        build = HeroBuild.model_validate_json(path.read_text())
        builds[build.hero] = build

    return BuildData(
        builds=builds, traits=traits, item_names=item_names,
        hero_names=hero_names, heroes=heroes,
    )
