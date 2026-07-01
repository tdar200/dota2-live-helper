from pathlib import Path
from app.item_builds import load_item_builds, ItemBuildData

FIXTURE = Path(__file__).parent / "fixtures" / "item_builds_sample.json"


def test_loads_sample():
    data = load_item_builds(FIXTURE)
    assert data.has_data is True
    assert "npc_dota_hero_juggernaut" in data.heroes
    jug = data.heroes["npc_dota_hero_juggernaut"]
    assert jug.builds["mid_game"][0].display == "Battle Fury"
    assert len(jug.benchmarks.gold_per_min) == 11


def test_missing_cache_degrades():
    data = load_item_builds(Path("/does/not/exist.json"))
    assert data.has_data is False
    assert data.heroes == {}
