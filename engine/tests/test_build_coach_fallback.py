"""
Task 3 — build_coach all-hero OpenDota fallback tests.
Non-curated heroes get a BuildAdvice from item_build_db;
curated heroes remain untouched.
"""
from app.state import GameState, HeroState
from app.advisors.context import AdviceContext
from app.advisors import build_coach
from app.build_data import HeroBuild
from app.item_builds import HeroItemBuild, PhaseItem


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_juggernaut_ib() -> HeroItemBuild:
    """A minimal HeroItemBuild fixture for npc_dota_hero_juggernaut."""
    return HeroItemBuild(
        hero_id=8,
        display="Juggernaut",
        builds={
            "start_game": [PhaseItem(id=44, key="item_quelling_blade", display="Quelling Blade", count=41233)],
            "early_game": [PhaseItem(id=63, key="item_power_treads", display="Power Treads", count=38771)],
            "mid_game":   [PhaseItem(id=152, key="item_bfury", display="Battle Fury", count=29344)],
            "late_game":  [PhaseItem(id=116, key="item_manta", display="Manta Style", count=21002)],
        },
    )


def _curated_build() -> HeroBuild:
    return HeroBuild(
        hero="npc_dota_hero_skeleton_king", display="Wraith King", source="t", verified=False,
        skill_order="Max Q", talents={"10": "a", "15": "b", "20": "c", "25": "d"},
        starting_items=["item_tango"],
        core_items=["item_power_treads", "item_armlet", "item_radiance"],
        situational=[],
    )


def _ctx_fallback(
    items=None,
    clock_time=None,
    hero="npc_dota_hero_juggernaut",
    item_build_db=None,
):
    """Context with no curated build — forces the fallback branch."""
    state = GameState(items=items or [], clock_time=clock_time)
    state.hero = HeroState(name=hero)
    if item_build_db is None:
        item_build_db = {"npc_dota_hero_juggernaut": _make_juggernaut_ib()}
    return AdviceContext(
        state=state,
        item_build_db=item_build_db,
        # build_db intentionally empty — no curated build for juggernaut
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_none_clock_no_crash():
    """clock_time=None must not raise; fallback returns source='opendota'."""
    ctx = _ctx_fallback(clock_time=None)
    adv = build_coach.advise(ctx)
    assert adv.source == "opendota"
    assert adv.has_build is True


def test_fallback_phases_and_owned():
    """Owned item is marked True; absent items are False."""
    ctx = _ctx_fallback(items=["item_power_treads"], clock_time=0)
    adv = build_coach.advise(ctx)
    assert adv.has_build is True
    assert adv.source == "opendota"

    early_chips = adv.phases["early_game"]
    pt = next(c for c in early_chips if c.item == "item_power_treads")
    assert pt.owned is True

    start_chips = adv.phases["start_game"]
    qb = next(c for c in start_chips if c.item == "item_quelling_blade")
    assert qb.owned is False


def test_suggested_next_first_unowned_from_current_phase():
    """
    clock=700 → mid_game phase.
    power_treads (early) owned; scan mid onward → first unowned = Battle Fury.
    """
    ctx = _ctx_fallback(items=["item_power_treads"], clock_time=700)
    adv = build_coach.advise(ctx)
    assert adv.suggested_next is not None
    assert adv.suggested_next.item == "item_bfury"


def test_suggested_next_none_when_all_owned():
    """All phase items owned → suggested_next is None, has_build still True."""
    all_items = ["item_quelling_blade", "item_power_treads", "item_bfury", "item_manta"]
    ctx = _ctx_fallback(items=all_items, clock_time=0)
    adv = build_coach.advise(ctx)
    assert adv.has_build is True
    assert adv.suggested_next is None


def test_no_data_returns_none_source():
    """Empty item_build_db → has_build False, source='none'."""
    ctx = _ctx_fallback(item_build_db={})
    adv = build_coach.advise(ctx)
    assert adv.has_build is False
    assert adv.source == "none"


def test_none_source_uses_display_name():
    """hero with no curated build AND empty item_build_db, but hero_names has a display."""
    state = GameState(items=[], clock_time=None)
    state.hero = HeroState(name="npc_dota_hero_silencer")
    ctx = AdviceContext(
        state=state,
        item_build_db={},
        hero_names={"npc_dota_hero_silencer": "Silencer"},
    )
    adv = build_coach.advise(ctx)
    assert adv.source == "none" and adv.has_build is False
    assert adv.hero_display == "Silencer"


def test_curated_unchanged():
    """Curated hero ignores item_build_db; returns source='curated' with next_core."""
    state = GameState(items=[], clock_time=300)
    state.hero = HeroState(name="npc_dota_hero_skeleton_king", level=15)
    ctx = AdviceContext(
        state=state,
        build_db={"npc_dota_hero_skeleton_king": _curated_build()},
        item_names={
            "item_power_treads": "Power Treads",
            "item_armlet": "Armlet",
            "item_radiance": "Radiance",
        },
        hero_names={},
        # item_build_db present but must be ignored for curated heroes
        item_build_db={"npc_dota_hero_skeleton_king": _make_juggernaut_ib()},
    )
    adv = build_coach.advise(ctx)
    assert adv.source == "curated"
    assert adv.next_core is not None
    assert adv.next_core.item == "item_power_treads"
