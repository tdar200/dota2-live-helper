from app.state import GameState
from app.advisors.context import AdviceContext
from app.advisors import draft
from app.matchups import MatchupData, HeroMatchups


def _ctx(enemies=None, allies=None, has_data=True):
    heroes = {
        "npc_dota_hero_skeleton_king": HeroMatchups(
            vs={"npc_dota_hero_zuus": 0.58, "npc_dota_hero_phantom_assassin": 0.45},
            **{"with": {"npc_dota_hero_lion": 0.55}},
        ),
        "npc_dota_hero_riki": HeroMatchups(
            vs={"npc_dota_hero_zuus": 0.49}, **{"with": {}},
        ),
    }
    md = MatchupData(
        has_data=has_data, bracket="HERALD", heroes=(heroes if has_data else {}),
        base_winrates={"npc_dota_hero_skeleton_king": 0.561, "npc_dota_hero_riki": 0.520},
    )
    return AdviceContext(
        state=GameState(),
        build_db={"npc_dota_hero_skeleton_king": None, "npc_dota_hero_riki": None},
        hero_names={"npc_dota_hero_skeleton_king": "Wraith King", "npc_dota_hero_riki": "Riki",
                    "npc_dota_hero_zuus": "Zeus", "npc_dota_hero_phantom_assassin": "Phantom Assassin",
                    "npc_dota_hero_lion": "Lion"},
        enemy_heroes=enemies or [], ally_heroes=allies or [], matchup_data=md,
    )


def test_ranks_pocket_heroes_by_score():
    adv = draft.advise(_ctx(enemies=["npc_dota_hero_zuus"]))
    assert adv.has_data is True
    assert [p.hero for p in adv.picks][0] == "npc_dota_hero_skeleton_king"  # 0.561 base + strong vs zeus
    assert adv.picks[0].counter == 0.58


def test_countered_flag_and_reason():
    adv = draft.advise(_ctx(enemies=["npc_dota_hero_phantom_assassin"]))
    wk = next(p for p in adv.picks if p.hero == "npc_dota_hero_skeleton_king")
    assert wk.countered is True  # vs PA 0.45 < 0.47
    assert any("weak vs Phantom Assassin" in r for r in wk.reasons)


def test_synergy_included():
    adv = draft.advise(_ctx(allies=["npc_dota_hero_lion"]))
    wk = next(p for p in adv.picks if p.hero == "npc_dota_hero_skeleton_king")
    assert wk.synergy == 0.55
    assert any("synergy w/ Lion" in r for r in wk.reasons)


def test_degraded_without_cache_ranks_by_base():
    adv = draft.advise(_ctx(enemies=["npc_dota_hero_zuus"], has_data=False))
    assert adv.has_data is False
    assert adv.note is not None
    assert adv.picks[0].hero == "npc_dota_hero_skeleton_king"  # base 0.561 > 0.520
    assert adv.picks[0].counter is None
