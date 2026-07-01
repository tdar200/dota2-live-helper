from app.state import GameState, HeroState, PlayerState, MapState
from app.advisors.context import AdviceContext
from app.advisors import macro


def _ctx(*, alive=True, respawn=0, gold=1000, buyback_cost=300, buyback_cd=0,
         gpm=500, daytime=True, items=None, clock=1200, lead=None, rosh_dead=None):
    state = GameState(clock_time=clock, items=items or [])
    state.hero = HeroState(name="npc_dota_hero_skeleton_king", level=16, alive=alive,
                           respawn_seconds=respawn, buyback_cost=buyback_cost, buyback_cooldown=buyback_cd)
    state.player = PlayerState(gold=gold, gpm=gpm)
    state.map = MapState(clock_time=clock, daytime=daytime)
    return AdviceContext(state=state, net_worth_lead=lead, roshan_dead_clock=rosh_dead, winprob_table=None)


def test_dead_without_buyback_plays_safe():
    adv = macro.advise(_ctx(alive=False, respawn=45, gold=100, buyback_cost=1200))
    assert adv.buyback_ready is False
    assert adv.recommendation == "PLAY_SAFE"


def test_high_winprob_and_itemized_pushes():
    adv = macro.advise(_ctx(lead=12000, clock=2400, items=["item_black_king_bar"]))
    assert adv.win_prob is not None and adv.win_prob >= 0.6
    assert adv.recommendation == "PUSH"


def test_roshan_window_take_rosh():
    # rosh died at 1000s; now 1500s -> within [1480,1660] window -> contestable
    adv = macro.advise(_ctx(clock=1500, rosh_dead=1000))
    assert adv.roshan is not None
    assert adv.roshan.status == "contestable"
    assert adv.recommendation == "TAKE_ROSH"


def test_low_winprob_defends():
    adv = macro.advise(_ctx(lead=-12000, clock=2400))
    assert adv.win_prob is not None and adv.win_prob <= 0.4
    assert adv.recommendation == "DEFEND"


def test_behind_farm():
    adv = macro.advise(_ctx(gpm=300))
    assert adv.recommendation == "FARM"
