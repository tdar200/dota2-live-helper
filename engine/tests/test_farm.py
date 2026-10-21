import pytest
from app.item_builds import Benchmarks, HeroItemBuild
from app.state import GameState, PlayerState, MapState, HeroState
from app.advisors.context import AdviceContext
from app.advisors.farm import _pct, _band, FarmAdvice, advise

# ---------------------------------------------------------------------------
# Benchmark fixture matching the item_builds_sample.json Juggernaut data
# ---------------------------------------------------------------------------
PCTS = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99]
GPM_VALS = [312, 378, 431, 479, 527, 578, 634, 701, 792, 861, 988]
XPM_VALS = [402, 468, 521, 569, 617, 668, 724, 791, 882, 951, 1078]
LH_VALS = [3.1, 4.0, 4.7, 5.3, 5.9, 6.5, 7.2, 8.0, 9.1, 9.9, 11.4]

HERO_KEY = "npc_dota_hero_juggernaut"

BENCHMARKS = Benchmarks(
    percentiles=PCTS,
    gold_per_min=GPM_VALS,
    xp_per_min=XPM_VALS,
    last_hits_per_min=LH_VALS,
)

HERO_BUILD = HeroItemBuild(
    hero_id=8,
    display="Juggernaut",
    builds={},
    benchmarks=BENCHMARKS,
)

ITEM_BUILD_DB = {HERO_KEY: HERO_BUILD}


def _make_ctx(clock, gpm=None, xpm=None, last_hits=None, hero=HERO_KEY, db=None):
    player = PlayerState(gold=1000, gpm=gpm, xpm=xpm, last_hits=last_hits)
    state = GameState(
        clock_time=clock,
        map=MapState(clock_time=clock),
        hero=HeroState(name=hero),
        player=player,
    )
    return AdviceContext(
        state=state,
        item_build_db=db if db is not None else ITEM_BUILD_DB,
    )


# ---------------------------------------------------------------------------
# _pct unit tests
# ---------------------------------------------------------------------------

def test_pct_interpolation():
    # Between buckets: 312 (10th) and 378 (20th), midpoint=345 → 15th pct
    result = _pct(345, PCTS, GPM_VALS)
    assert result == 15

    # Exactly at a bucket boundary
    assert _pct(578, PCTS, GPM_VALS) == 60

    # Below minimum → clamp to first pct (10th)
    assert _pct(300, PCTS, GPM_VALS) == 10

    # Above maximum → clamp to last pct (99th)
    assert _pct(1000, PCTS, GPM_VALS) == 99


def test_pct_none_value():
    assert _pct(None, PCTS, GPM_VALS) is None


def test_pct_empty_vals():
    assert _pct(500, PCTS, []) is None


# ---------------------------------------------------------------------------
# _band tests
# ---------------------------------------------------------------------------

def test_band():
    assert _band(29) == "behind"
    assert _band(30) == "on track"
    assert _band(59) == "on track"
    assert _band(60) == "ahead"
    assert _band(84) == "ahead"
    assert _band(85) == "dominating"


# ---------------------------------------------------------------------------
# Gate: clock < 300 → has_data False
# ---------------------------------------------------------------------------

def test_gate_before_300():
    ctx = _make_ctx(clock=120, gpm=634, xpm=724, last_hits=70)
    result = advise(ctx)
    assert result.has_data is False


def test_gate_exactly_300():
    ctx = _make_ctx(clock=300, gpm=634, xpm=724, last_hits=70)
    result = advise(ctx)
    # clock==300 is still < 300 threshold — plan says "clock<300" gate, so 300 should pass
    assert result.has_data is True


def test_gate_clock_none():
    ctx = _make_ctx(clock=None, gpm=634, xpm=724, last_hits=70)
    result = advise(ctx)
    assert result.has_data is False


# ---------------------------------------------------------------------------
# Three metrics at clock 600
# ---------------------------------------------------------------------------

def test_metrics_after_300():
    # clock=600 (10 min), gpm=634 (70th), xpm=724 (70th)
    # last_hits=70 → rate=70/10=7.0 LH/min
    #   7.0 is between 6.5 (60th) and 7.2 (70th):
    #   frac=(7.0-6.5)/(7.2-6.5)=0.5/0.7≈0.714 → (0.6+0.0714)*100≈67 → "ahead"
    ctx = _make_ctx(clock=600, gpm=634, xpm=724, last_hits=70)
    result = advise(ctx)
    assert result.has_data is True
    assert result.hero_display == "Juggernaut"
    assert len(result.metrics) == 3

    metrics_by_name = {m.metric: m for m in result.metrics}
    assert "GPM" in metrics_by_name
    assert "XPM" in metrics_by_name
    assert "LH/min" in metrics_by_name

    assert metrics_by_name["GPM"].percentile == 70
    assert metrics_by_name["GPM"].label == "ahead"
    assert metrics_by_name["XPM"].percentile == 70
    assert metrics_by_name["XPM"].label == "ahead"

    assert result.summary is not None
    assert "vs all players" in result.summary
    assert "Juggernaut" in result.summary


# ---------------------------------------------------------------------------
# Skip None metric — no ValidationError, GPM absent → no GPM metric
# ---------------------------------------------------------------------------

def test_skip_none_metric():
    # gpm=None → no GPM metric; XPM and LH/min still built
    ctx = _make_ctx(clock=600, gpm=None, xpm=724, last_hits=70)
    result = advise(ctx)
    assert result.has_data is True
    metrics_by_name = {m.metric: m for m in result.metrics}
    assert "GPM" not in metrics_by_name
    assert "XPM" in metrics_by_name
    assert "LH/min" in metrics_by_name
    # summary is None since no GPM
    assert result.summary is None


# ---------------------------------------------------------------------------
# Empty benchmark arrays → _pct returns None → skip → has_data False
# ---------------------------------------------------------------------------

def test_empty_benchmarks_no_crash():
    empty_hero = HeroItemBuild(
        hero_id=99,
        display="TestHero",
        builds={},
        benchmarks=Benchmarks(),  # all empty lists
    )
    db = {"npc_dota_hero_test": empty_hero}
    ctx = _make_ctx(clock=600, gpm=500, xpm=600, last_hits=50,
                    hero="npc_dota_hero_test", db=db)
    result = advise(ctx)
    assert result.has_data is False


# ---------------------------------------------------------------------------
# No hero in db → has_data False
# ---------------------------------------------------------------------------

def test_hero_not_in_db():
    ctx = _make_ctx(clock=600, gpm=634, xpm=724, last_hits=70,
                    hero="npc_dota_hero_unknown", db={})
    result = advise(ctx)
    assert result.has_data is False


# ---------------------------------------------------------------------------
# Live performance scorecard: combat stats, net worth, extra percentiles, verdict
# ---------------------------------------------------------------------------

def _scorecard_ctx(*, kills=6, deaths=2, assists=5, last_hits=180, denies=8,
                   hero_damage=15000, net_worth=None, gold=1200, item_costs=None,
                   items=None, benchmarks=BENCHMARKS):
    player = PlayerState(
        gold=gold, gpm=634, xpm=724, last_hits=last_hits, denies=denies,
        kills=kills, deaths=deaths, assists=assists, hero_damage=hero_damage,
        net_worth=net_worth,
    )
    build = HeroItemBuild(hero_id=8, display="Juggernaut", builds={}, benchmarks=benchmarks)
    state = GameState(
        clock_time=600, map=MapState(clock_time=600),
        hero=HeroState(name=HERO_KEY), player=player,
        items=items if items is not None else [],
    )
    return AdviceContext(
        state=state, item_build_db={HERO_KEY: build},
        item_costs=item_costs if item_costs is not None else {},
    )


def test_scorecard_combat_stats_present():
    result = advise(_scorecard_ctx())
    by = {c.metric: c for c in result.combat}
    assert by["KDA"].display == "6/2/5"
    assert by["LH/DN"].display == "180/8"
    assert by["HeroDmg"].display == "15.0k"


def test_scorecard_net_worth_from_item_costs():
    # gold 1150 + blink 2250 + manta 4600 = 8000, flagged estimated
    ctx = _scorecard_ctx(gold=1150, items=["item_blink", "item_manta"],
                         item_costs={"item_blink": 2250, "item_manta": 4600})
    result = advise(ctx)
    assert result.net_worth == 8000
    assert result.net_worth_estimated is True
    nw = next(c for c in result.combat if c.metric == "Net Worth")
    assert nw.display == "8.0k~"


def test_scorecard_net_worth_prefers_gsi_field():
    ctx = _scorecard_ctx(net_worth=12345, gold=1200,
                         items=["item_blink"], item_costs={"item_blink": 2250})
    result = advise(ctx)
    assert result.net_worth == 12345
    assert result.net_worth_estimated is False


def test_scorecard_falls_back_to_gold_without_costs():
    ctx = _scorecard_ctx(gold=1500, items=["item_blink"], item_costs={})
    result = advise(ctx)
    assert result.net_worth is None
    metrics = {c.metric for c in result.combat}
    assert "Gold" in metrics
    assert "Net Worth" not in metrics


def test_scorecard_extra_percentiles_when_benchmarks_present():
    bm = Benchmarks(
        percentiles=PCTS, gold_per_min=GPM_VALS, xp_per_min=XPM_VALS,
        last_hits_per_min=LH_VALS,
        hero_damage_per_min=[300, 450, 600, 750, 900, 1100, 1350, 1650, 2100, 2500, 3200],
        kills_per_min=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.1, 1.5],
    )
    # hero_damage 15000 over 10 min = 1500/min; kills 6 over 10 = 0.6/min
    result = advise(_scorecard_ctx(benchmarks=bm))
    names = {m.metric for m in result.metrics}
    assert "HeroDmg/min" in names
    assert "Kills/min" in names


def test_scorecard_verdict_flags_feeding():
    result = advise(_scorecard_ctx(kills=1, deaths=8, assists=1))
    assert result.verdict is not None
    assert "feeding" in result.verdict


def test_scorecard_verdict_winning_fights():
    result = advise(_scorecard_ctx(kills=9, deaths=2, assists=4))
    assert "winning fights" in result.verdict
