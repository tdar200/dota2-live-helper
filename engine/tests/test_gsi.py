import json
from pathlib import Path
from app.gsi import parse_gsi

FIX = Path(__file__).parent / "fixtures" / "gsi_early_game.json"


def test_parse_gsi_populates_state():
    raw = json.loads(FIX.read_text())
    state = parse_gsi(raw)
    assert state.map.clock_time == 95
    assert state.clock_time == 95
    assert state.map.daytime is True
    assert state.hero.name == "npc_dota_hero_sniper"
    assert state.hero.level == 6
    assert state.hero.buyback_cost == 300
    assert state.player.gold == 1500
    assert state.items == ["item_phase_boots", "item_magic_wand"]
