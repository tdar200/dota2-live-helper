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


def test_match_history_parses_and_skips_malformed(tmp_path):
    p = tmp_path / "personal_stats.json"
    p.write_text(json.dumps({
        "account_id": 1,
        "heroes": {"npc_dota_hero_sniper": {"games": 5, "wins": 3, "winrate": 0.6}},
        "items": {},
        "match_history": [
            {"match_id": 9, "start_time": 100, "win": True, "hero": "npc_dota_hero_sniper",
             "kills": 5, "deaths": 2, "assists": 4},
            {"no_match_id": True},  # malformed -> skipped, rest still loads
        ],
    }))
    ps = load_personal_stats(p)
    assert len(ps.match_history) == 1
    assert ps.match_history[0].match_id == 9
    assert ps.match_history[0].win is True


def test_missing_match_history_is_empty_list(tmp_path):
    p = tmp_path / "personal_stats.json"
    p.write_text(json.dumps({"account_id": 1,
                             "heroes": {"npc_dota_hero_x": {"games": 1, "wins": 1, "winrate": 1.0}},
                             "items": {}}))
    ps = load_personal_stats(p)
    assert ps.match_history == []
