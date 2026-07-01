"""Offline tests for the degrade-safe hero-meta loader."""
import json
from pathlib import Path

from app.hero_meta import load_hero_meta


def test_missing_cache_degrades(tmp_path):
    data = load_hero_meta(tmp_path / "nope.json")
    assert data.has_data is False
    assert data.heroes == {}


def test_malformed_cache_degrades(tmp_path):
    p = tmp_path / "hero_meta.json"
    p.write_text("{ not json")
    data = load_hero_meta(p)
    assert data.has_data is False


def test_empty_heroes_has_data_false(tmp_path):
    p = tmp_path / "hero_meta.json"
    p.write_text(json.dumps({"heroes": {}}))
    assert load_hero_meta(p).has_data is False


def test_valid_cache_loads(tmp_path):
    p = tmp_path / "hero_meta.json"
    p.write_text(json.dumps({
        "heroes": {
            "npc_dota_hero_antimage": {
                "herald_winrate": 0.508, "herald_pick": 31796, "herald_win": 16151,
            }
        }
    }))
    data = load_hero_meta(p)
    assert data.has_data is True
    am = data.heroes["npc_dota_hero_antimage"]
    assert am.herald_winrate == 0.508
    assert am.herald_pick == 31796


def test_null_winrate_tolerated(tmp_path):
    p = tmp_path / "hero_meta.json"
    p.write_text(json.dumps({
        "heroes": {"npc_dota_hero_x": {"herald_winrate": None,
                                       "herald_pick": 0, "herald_win": 0}}
    }))
    data = load_hero_meta(p)
    assert data.heroes["npc_dota_hero_x"].herald_winrate is None
