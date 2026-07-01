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


def test_parse_gsi_abilities_and_aghs():
    raw = json.loads(FIX.read_text())
    state = parse_gsi(raw)
    # aghs ints normalised to bool
    assert state.hero.aghanims_scepter is False
    assert state.hero.aghanims_shard is True
    names = [a.name for a in state.hero.abilities]
    # empty/hidden slots skipped; talents + passives kept faithfully
    assert "generic_hidden" not in names
    assert "sniper_assassinate" in names
    assert any(a.name.startswith("special_bonus") for a in state.hero.abilities)
    ult = next(a for a in state.hero.abilities if a.ultimate)
    assert ult.name == "sniper_assassinate"
    assert ult.cooldown == 0
    shrap = next(a for a in state.hero.abilities if a.name == "sniper_shrapnel")
    assert shrap.charges == 3


def test_parse_gsi_no_abilities_block_degrades():
    raw = json.loads(FIX.read_text())
    raw.pop("abilities", None)
    raw["hero"].pop("aghanims_scepter", None)
    raw["hero"].pop("aghanims_shard", None)
    state = parse_gsi(raw)
    assert state.hero.abilities == []
    assert state.hero.aghanims_scepter is None
    assert state.hero.aghanims_shard is None
