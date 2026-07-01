"""
Task 5 — advice.py wiring tests.
Verifies that item_build_db and farm advice are correctly wired into
AdviceContext and AdvicePayload.
"""
import pytest
from app.state import GameState, HeroState, PlayerState
from app.item_builds import ItemBuildData, HeroItemBuild, PhaseItem, Benchmarks
import app.advice as advice_module
from app.advice import build_advice


_NONCURATED = "npc_dota_hero_silencer"


def _make_silencer_ib() -> HeroItemBuild:
    """Minimal HeroItemBuild fixture for npc_dota_hero_silencer (not in curated 11)."""
    return HeroItemBuild(
        hero_id=75,
        display="Silencer",
        builds={
            "start_game": [PhaseItem(id=44, key="item_quelling_blade", display="Quelling Blade", count=21000)],
            "early_game": [PhaseItem(id=63, key="item_power_treads", display="Power Treads", count=19000)],
            "mid_game":   [PhaseItem(id=108, key="item_orchid", display="Orchid Malevolence", count=14000)],
            "late_game":  [PhaseItem(id=116, key="item_manta", display="Manta Style", count=9000)],
        },
        benchmarks=Benchmarks(
            percentiles=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99],
            gold_per_min=[312, 378, 431, 479, 527, 578, 634, 701, 792, 861, 988],
            xp_per_min=[402, 468, 521, 569, 617, 668, 724, 791, 882, 951, 1078],
            last_hits_per_min=[3.1, 4.0, 4.7, 5.3, 5.9, 6.5, 7.2, 8.0, 9.1, 9.9, 11.4],
        ),
    )


def _make_state_with_farm_data() -> GameState:
    """Non-curated hero + clock >= 300 + player stats so farm.has_data is True."""
    state = GameState(clock_time=600)
    state.hero = HeroState(name=_NONCURATED)
    state.player = PlayerState(gpm=500, xpm=600, last_hits=60)
    return state


def test_payload_has_farm_and_build_fields(monkeypatch):
    """
    With ITEM_BUILDS populated for a non-curated hero:
    - build.source == 'opendota'
    - farm is not None (and has_data True given clock>=300 + stats set)
    """
    populated = ItemBuildData(
        has_data=True,
        heroes={_NONCURATED: _make_silencer_ib()},
    )
    monkeypatch.setattr(advice_module, "ITEM_BUILDS", populated)

    state = _make_state_with_farm_data()
    payload = build_advice(state)

    assert payload.build is not None
    assert payload.build.source == "opendota"
    assert payload.farm is not None


def test_payload_degrades_without_cache(monkeypatch):
    """
    With ITEM_BUILDS empty (heroes={}), non-curated hero:
    - build.source in {"none", "curated"} (no opendota data)
    - farm is None or farm.has_data is False
    - no exception raised (fresh-clone boot must work)
    """
    empty = ItemBuildData(has_data=False)
    monkeypatch.setattr(advice_module, "ITEM_BUILDS", empty)

    state = _make_state_with_farm_data()
    payload = build_advice(state)

    assert payload.build is not None
    assert payload.build.source in {"none", "curated"}
    assert payload.farm is None or payload.farm.has_data is False


def _make_yasha_manta_ib() -> HeroItemBuild:
    """Non-curated hero whose mid_game holds a stepping-stone (item_yasha)
    ahead of a real final (item_manta). build_coach must demote the yasha."""
    return HeroItemBuild(
        hero_id=75,
        display="Silencer",
        builds={
            "mid_game": [
                PhaseItem(id=10, key="item_yasha", display="Yasha", count=20000),
                PhaseItem(id=116, key="item_manta", display="Manta Style", count=15000),
            ],
        },
        benchmarks=Benchmarks(),
    )


def test_intermediate_dropped_and_next_is_manta(monkeypatch):
    """build_coach.INTERMEDIATE_KEYS drops item_yasha from phases, so a
    first-unowned scan for suggested_next skips the stepping stone and lands
    on item_manta (regression guard for the no-stepping-stone-NEXT fix)."""
    from app.advisors.build_coach import INTERMEDIATE_KEYS

    assert INTERMEDIATE_KEYS == {"item_yasha", "item_sange", "item_kaya"}

    populated = ItemBuildData(
        has_data=True,
        heroes={_NONCURATED: _make_yasha_manta_ib()},
    )
    monkeypatch.setattr(advice_module, "ITEM_BUILDS", populated)

    state = GameState(clock_time=600)  # mid_game phase
    state.hero = HeroState(name=_NONCURATED)
    payload = build_advice(state)

    assert payload.build.source == "opendota"
    mid_keys = [c.item for c in payload.build.phases["mid_game"]]
    assert "item_yasha" not in mid_keys
    assert "item_manta" in mid_keys
    assert payload.build.suggested_next is not None
    assert payload.build.suggested_next.item == "item_manta"


def test_model_dump_serializes(monkeypatch):
    """
    build_advice(state).model_dump() must succeed, confirming new fields
    serialise correctly over WS/HTTP without any main.py change.
    """
    populated = ItemBuildData(
        has_data=True,
        heroes={_NONCURATED: _make_silencer_ib()},
    )
    monkeypatch.setattr(advice_module, "ITEM_BUILDS", populated)

    state = _make_state_with_farm_data()
    result = build_advice(state).model_dump()

    assert isinstance(result, dict)
    assert "farm" in result
    assert "build" in result
