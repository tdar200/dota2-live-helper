from app.state import GameState, HeroState
from app.advisors.context import AdviceContext
from app.advisors import build_coach
from app.build_data import HeroBuild


def _build():
    return HeroBuild(
        hero="npc_dota_hero_skeleton_king", display="Wraith King", source="t", verified=False,
        skill_order="Max Q", talents={"10": "a", "15": "b", "20": "c", "25": "d"},
        starting_items=["item_tango"],
        core_items=["item_power_treads", "item_armlet", "item_radiance"],
        situational=[
            {"item": "item_black_king_bar", "trait": "heavy_magic", "note": "vs magic"},
            {"item": "item_monkey_king_bar", "trait": "evasion", "note": "vs evasion"},
        ],
    )


def _ctx(items, level=15, enemies=None):
    state = GameState(items=items)
    state.hero = HeroState(name="npc_dota_hero_skeleton_king", level=level)
    return AdviceContext(
        state=state, enemy_heroes=enemies or [],
        build_db={"npc_dota_hero_skeleton_king": _build()},
        trait_db={"npc_dota_hero_zuus": ["heavy_magic"]},
        item_names={"item_power_treads": "Power Treads", "item_armlet": "Armlet",
                    "item_radiance": "Radiance", "item_black_king_bar": "Black King Bar",
                    "item_monkey_king_bar": "Monkey King Bar"},
        hero_names={"npc_dota_hero_zuus": "Zeus"},
    )


def test_no_build_for_unknown_hero():
    ctx = _ctx([])
    ctx.state.hero.name = "npc_dota_hero_unknown"
    adv = build_coach.advise(ctx)
    assert adv.has_build is False


def test_next_core_is_first_unowned():
    adv = build_coach.advise(_ctx(items=["item_power_treads"]))
    assert adv.has_build is True
    assert adv.next_core.item == "item_armlet"
    assert [c.owned for c in adv.core] == [True, False, False]


def test_situational_triggered_by_enemy_trait():
    adv = build_coach.advise(_ctx(items=[], enemies=["npc_dota_hero_zuus"]))
    bkb = next(s for s in adv.situational if s.item == "item_black_king_bar")
    mkb = next(s for s in adv.situational if s.item == "item_monkey_king_bar")
    assert bkb.triggered_by == ["Zeus"]      # Zeus = heavy_magic
    assert mkb.triggered_by == []            # no evasion enemy
    # triggered items sort ahead of untriggered
    assert adv.situational[0].item == "item_black_king_bar"


def test_talent_for_current_level():
    adv = build_coach.advise(_ctx(items=[], level=15))
    assert adv.talent_next == "L15: b"
