from app.state import GameState
from app.advisors.context import AdviceContext
from app.advisors import draft
from app.matchups import MatchupData, HeroMatchups
from app.hero_meta import HeroMeta
from app.personal_stats import HeroWR


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


# ---------------------------------------------------------------------------
# All-hero ranking off hero_meta + personal comfort
# ---------------------------------------------------------------------------

def _allhero_ctx(*, enemies=None, hero_meta=None, personal=None, matchup=True):
    heroes = {
        "npc_dota_hero_skeleton_king": HeroMatchups(vs={"npc_dota_hero_zuus": 0.58}, **{"with": {}}),
    } if matchup else {}
    md = MatchupData(
        has_data=matchup, bracket="HERALD", heroes=heroes,
        base_winrates={"npc_dota_hero_skeleton_king": 0.561},
    )
    return AdviceContext(
        state=GameState(),
        build_db={},  # no curated dependency
        hero_names={
            "npc_dota_hero_skeleton_king": "Wraith King", "npc_dota_hero_zuus": "Zeus",
            "npc_dota_hero_antimage": "Anti-Mage", "npc_dota_hero_pudge": "Pudge",
        },
        enemy_heroes=enemies or [], matchup_data=md,
        hero_meta_db=hero_meta or {},
        personal_hero_db=personal or {},
    )


def test_ranks_all_heroes_from_hero_meta_without_stratz():
    # No STRATZ matchup, but hero_meta gives Herald WR for many heroes.
    meta = {
        "npc_dota_hero_antimage": HeroMeta(herald_winrate=0.52),
        "npc_dota_hero_pudge": HeroMeta(herald_winrate=0.49),
        "npc_dota_hero_skeleton_king": HeroMeta(herald_winrate=0.561),
    }
    adv = draft.advise(_allhero_ctx(hero_meta=meta, matchup=False))
    heroes = [p.hero for p in adv.picks]
    assert adv.has_data is True                       # meta alone is enough
    assert "npc_dota_hero_antimage" in heroes         # ranked despite no curated build
    assert adv.picks[0].hero == "npc_dota_hero_skeleton_king"  # 0.561 top
    assert adv.note is not None                        # still nudges to run STRATZ


def test_personal_comfort_boosts_and_annotates():
    meta = {
        "npc_dota_hero_antimage": HeroMeta(herald_winrate=0.50),
        "npc_dota_hero_pudge": HeroMeta(herald_winrate=0.50),
    }
    personal = {"npc_dota_hero_pudge": HeroWR(games=40, wins=26, winrate=0.65)}
    adv = draft.advise(_allhero_ctx(hero_meta=meta, personal=personal, matchup=False))
    pudge = next(p for p in adv.picks if p.hero == "npc_dota_hero_pudge")
    assert pudge.personal_winrate == 0.65
    assert pudge.personal_games == 40
    assert any("you 65%" in r for r in pudge.reasons)
    # equal meta, but personal comfort lifts Pudge above Anti-Mage
    assert adv.picks[0].hero == "npc_dota_hero_pudge"


def test_personal_below_min_games_ignored():
    meta = {"npc_dota_hero_pudge": HeroMeta(herald_winrate=0.50)}
    personal = {"npc_dota_hero_pudge": HeroWR(games=2, wins=2, winrate=1.0)}
    adv = draft.advise(_allhero_ctx(hero_meta=meta, personal=personal, matchup=False))
    pudge = next(p for p in adv.picks if p.hero == "npc_dota_hero_pudge")
    assert pudge.personal_winrate is None  # 2 games < min sample


def test_draft_caps_at_limit():
    meta = {f"npc_dota_hero_h{i}": HeroMeta(herald_winrate=0.5 + i / 1000) for i in range(30)}
    ctx = _allhero_ctx(hero_meta=meta, matchup=False)
    adv = draft.advise(ctx)
    assert len(adv.picks) == draft.DRAFT_LIMIT


def test_drafted_heroes_are_not_recommended():
    # A hero the enemy (or your team) has already locked must never be suggested.
    meta = {
        "npc_dota_hero_zuus": HeroMeta(herald_winrate=0.60),      # enemy's pick
        "npc_dota_hero_antimage": HeroMeta(herald_winrate=0.52),  # your ally
        "npc_dota_hero_pudge": HeroMeta(herald_winrate=0.50),
    }
    ctx = _allhero_ctx(enemies=["npc_dota_hero_zuus"], hero_meta=meta, matchup=False)
    ctx.ally_heroes = ["npc_dota_hero_antimage"]
    heroes = [p.hero for p in draft.advise(ctx).picks]
    assert "npc_dota_hero_zuus" not in heroes       # enemy pick excluded
    assert "npc_dota_hero_antimage" not in heroes   # ally pick excluded
    assert "npc_dota_hero_pudge" in heroes


def test_small_personal_sample_cannot_outweigh_meta_counter():
    # Hero A: real meta counter. Hero B: 5-0 fluke. A must stay above B.
    meta = {
        "npc_dota_hero_a": HeroMeta(herald_winrate=0.55),
        "npc_dota_hero_b": HeroMeta(herald_winrate=0.47),
    }
    heroes = {"npc_dota_hero_a": HeroMatchups(vs={"npc_dota_hero_zuus": 0.60}, **{"with": {}})}
    md = MatchupData(has_data=True, bracket="HERALD", heroes=heroes, base_winrates={})
    ctx = AdviceContext(
        state=GameState(), build_db={},
        hero_names={"npc_dota_hero_a": "A", "npc_dota_hero_b": "B", "npc_dota_hero_zuus": "Zeus"},
        enemy_heroes=["npc_dota_hero_zuus"], matchup_data=md, hero_meta_db=meta,
        personal_hero_db={"npc_dota_hero_b": HeroWR(games=5, wins=5, winrate=1.0)},
    )
    picks = draft.advise(ctx).picks
    assert picks[0].hero == "npc_dota_hero_a"  # meta counter beats 5-game fluke


def test_hero_without_base_winrate_is_skipped():
    meta = {
        "npc_dota_hero_pudge": HeroMeta(herald_winrate=0.50),
        "npc_dota_hero_newhero": HeroMeta(herald_winrate=None),  # e.g. brand-new hero
    }
    heroes = [p.hero for p in draft.advise(_allhero_ctx(hero_meta=meta, matchup=False)).picks]
    assert "npc_dota_hero_newhero" not in heroes
    assert "npc_dota_hero_pudge" in heroes
