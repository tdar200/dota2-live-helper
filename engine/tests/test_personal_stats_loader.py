"""Tests for the degrade-safe personal-stats cache loader."""
import json
from app.personal_stats import load_personal_stats, PersonalStats


def test_absent_cache_degrades(tmp_path):
    ps = load_personal_stats(tmp_path / "nope.json")
    assert isinstance(ps, PersonalStats)
    assert ps.has_data is False
    assert ps.heroes == {}
    assert ps.items == {}


def test_malformed_cache_degrades(tmp_path):
    p = tmp_path / "personal_stats.json"
    p.write_text("{ this is not json")
    ps = load_personal_stats(p)
    assert ps.has_data is False


def test_valid_cache_parses(tmp_path):
    p = tmp_path / "personal_stats.json"
    p.write_text(json.dumps({
        "account_id": 42,
        "heroes": {
            "npc_dota_hero_silencer": {
                "games": 40, "wins": 24, "winrate": 0.6, "last_played": 111,
            },
        },
        "items": {
            "npc_dota_hero_silencer": {
                "item_manta": {"games": 11, "wins": 7, "winrate": 0.6364},
            },
        },
    }))
    ps = load_personal_stats(p)
    assert ps.has_data is True
    assert ps.account_id == 42
    assert ps.heroes["npc_dota_hero_silencer"].winrate == 0.6
    assert ps.heroes["npc_dota_hero_silencer"].games == 40
    assert ps.items["npc_dota_hero_silencer"]["item_manta"].winrate == 0.6364


def test_empty_maps_has_no_data(tmp_path):
    p = tmp_path / "personal_stats.json"
    p.write_text(json.dumps({"account_id": 1, "heroes": {}, "items": {}}))
    ps = load_personal_stats(p)
    assert ps.has_data is False
