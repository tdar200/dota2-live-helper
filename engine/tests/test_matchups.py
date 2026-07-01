import json
from pathlib import Path
from app.matchups import load_matchups, MatchupData, HeroMatchups


def test_missing_cache_still_loads_seed():
    md = load_matchups(cache_path=Path("/nonexistent/matchups.json"))
    assert md.has_data is False
    assert md.heroes == {}
    assert md.base_winrates["npc_dota_hero_skeleton_king"] == 0.561


def test_cache_parses_with_and_vs(tmp_path):
    cache = tmp_path / "matchups.json"
    cache.write_text(json.dumps({
        "bracket": "HERALD",
        "generated": "2026-07-01",
        "heroes": {
            "npc_dota_hero_skeleton_king": {
                "vs": {"npc_dota_hero_zuus": 0.58},
                "with": {"npc_dota_hero_lion": 0.55},
            }
        },
    }))
    md = load_matchups(cache_path=cache)
    assert md.has_data is True
    assert md.bracket == "HERALD"
    hm = md.heroes["npc_dota_hero_skeleton_king"]
    assert hm.vs["npc_dota_hero_zuus"] == 0.58
    assert hm.with_["npc_dota_hero_lion"] == 0.55
    assert md.base_winrates["npc_dota_hero_zuus"] == 0.514
