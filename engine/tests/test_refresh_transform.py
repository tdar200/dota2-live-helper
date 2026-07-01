import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from refresh_matchups import transform_matchup


def test_transform_maps_ids_to_keys_and_computes_winrate():
    matchup = {
        "vs": [
            {"heroId2": 22, "winCount": 58, "matchCount": 100},
            {"heroId2": 44, "winCount": 47, "matchCount": 100},
            {"heroId2": 99, "winCount": 5, "matchCount": 0},      # skip: no matches
            {"heroId2": 777, "winCount": 1, "matchCount": 2},     # skip: unknown id
        ],
        "with": [{"heroId2": 26, "winCount": 55, "matchCount": 100}],
    }
    id_to_key = {
        22: "npc_dota_hero_zuus",
        44: "npc_dota_hero_phantom_assassin",
        26: "npc_dota_hero_lion",
    }
    out = transform_matchup(matchup, id_to_key)
    assert out["vs"] == {
        "npc_dota_hero_zuus": 0.58,
        "npc_dota_hero_phantom_assassin": 0.47,
    }
    assert out["with"] == {"npc_dota_hero_lion": 0.55}
