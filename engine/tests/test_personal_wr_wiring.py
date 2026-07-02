"""Personal win-rate flows through build_coach onto the header + item chips."""
from app.state import GameState, HeroState
from app.advisors.context import AdviceContext
from app.advisors import build_coach
from app.build_data import HeroBuild
from app.item_builds import HeroItemBuild, PhaseItem
from app.personal_stats import HeroWR, ItemWR


def _jugg_ib() -> HeroItemBuild:
    return HeroItemBuild(
        hero_id=8, display="Juggernaut",
        builds={
            "start_game": [PhaseItem(id=44, key="item_quelling_blade", display="Quelling Blade", count=1)],
            "mid_game":   [PhaseItem(id=152, key="item_bfury", display="Battle Fury", count=1)],
        },
    )


def test_opendota_path_populates_hero_and_item_wr():
    state = GameState(items=[], clock_time=0)
    state.hero = HeroState(name="npc_dota_hero_juggernaut")
    ctx = AdviceContext(
        state=state,
        item_build_db={"npc_dota_hero_juggernaut": _jugg_ib()},
        personal_hero_db={"npc_dota_hero_juggernaut": HeroWR(games=30, wins=18, winrate=0.6)},
        personal_item_db={"npc_dota_hero_juggernaut": {
            "item_bfury": ItemWR(games=12, wins=9, winrate=0.75),
        }},
    )
    adv = build_coach.advise(ctx)
    # header
    assert adv.personal_winrate == 0.6
    assert adv.personal_games == 30
    # item chip carrying personal WR
    bfury = next(c for c in adv.phases["mid_game"] if c.item == "item_bfury")
    assert bfury.personal_winrate == 0.75
    assert bfury.personal_games == 12
    # item with no personal history stays None
    qb = next(c for c in adv.phases["start_game"] if c.item == "item_quelling_blade")
    assert qb.personal_winrate is None
    assert qb.personal_games is None


def test_curated_path_populates_personal_wr():
    build = HeroBuild(
        hero="npc_dota_hero_skeleton_king", display="Wraith King", source="t", verified=False,
        skill_order="Max Q", talents={"10": "a", "15": "b", "20": "c", "25": "d"},
        starting_items=["item_tango"], core_items=["item_radiance"], situational=[],
    )
    state = GameState(items=[], clock_time=300)
    state.hero = HeroState(name="npc_dota_hero_skeleton_king", level=15)
    ctx = AdviceContext(
        state=state,
        build_db={"npc_dota_hero_skeleton_king": build},
        item_names={"item_radiance": "Radiance"},
        personal_hero_db={"npc_dota_hero_skeleton_king": HeroWR(games=8, wins=5, winrate=0.625)},
        personal_item_db={"npc_dota_hero_skeleton_king": {
            "item_radiance": ItemWR(games=6, wins=4, winrate=0.6667),
        }},
    )
    adv = build_coach.advise(ctx)
    assert adv.source == "curated"
    assert adv.personal_winrate == 0.625
    assert adv.personal_games == 8
    rad = next(c for c in adv.core if c.item == "item_radiance")
    assert rad.personal_winrate == 0.6667
    assert rad.personal_games == 6


def test_absent_personal_db_is_none():
    """No personal dbs -> header + chips carry None, nothing breaks."""
    state = GameState(items=[], clock_time=0)
    state.hero = HeroState(name="npc_dota_hero_juggernaut")
    ctx = AdviceContext(
        state=state,
        item_build_db={"npc_dota_hero_juggernaut": _jugg_ib()},
    )
    adv = build_coach.advise(ctx)
    assert adv.personal_winrate is None
    assert adv.personal_games is None
    bfury = next(c for c in adv.phases["mid_game"] if c.item == "item_bfury")
    assert bfury.personal_winrate is None
