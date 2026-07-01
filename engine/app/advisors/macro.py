from pydantic import BaseModel, Field
from app.advisors.context import AdviceContext
from app.winprob import win_probability

_WIN_HIGH = 0.6
_WIN_LOW = 0.4
_GPM_TARGET = 450
_ROSH_MIN = 480   # 8:00 after death
_ROSH_MAX = 660   # 11:00 after death


class RoshanState(BaseModel):
    dead_clock: int
    window_start_s: int
    window_end_s: int
    status: str


class MacroAdvice(BaseModel):
    win_prob: float | None = None
    net_worth_lead: int | None = None
    recommendation: str
    reasons: list[str] = Field(default_factory=list)
    buyback_ready: bool = False
    roshan: RoshanState | None = None


def _roshan(ctx: AdviceContext) -> RoshanState | None:
    dc = ctx.roshan_dead_clock
    now = ctx.state.clock_time
    if dc is None or now is None:
        return None
    ws, we = dc + _ROSH_MIN, dc + _ROSH_MAX
    if now < ws:
        status = "counting"
    elif now <= we:
        status = "contestable"
    else:
        status = "likely_up"
    return RoshanState(dead_clock=dc, window_start_s=ws, window_end_s=we, status=status)


def advise(ctx: AdviceContext) -> MacroAdvice:
    hero = ctx.state.hero
    player = ctx.state.player
    clock = ctx.state.clock_time

    buyback_ready = bool(
        hero.alive
        and hero.buyback_cooldown == 0
        and hero.buyback_cost is not None
        and player.gold is not None
        and player.gold >= hero.buyback_cost
    )

    win_prob = None
    if ctx.net_worth_lead is not None and clock is not None:
        win_prob = win_probability(ctx.net_worth_lead, clock, ctx.winprob_table)

    rosh = _roshan(ctx)
    dead = hero.alive is False
    behind = player.gpm is not None and player.gpm < _GPM_TARGET
    night = ctx.state.map.daytime is False
    itemized = "item_black_king_bar" in ctx.state.items

    reasons: list[str] = []
    if dead and hero.respawn_seconds:
        reasons.append(f"dead {hero.respawn_seconds}s — don't force")
    reasons.append("buyback up" if buyback_ready else "no buyback — avoid risky fights")
    if player.gpm is not None:
        reasons.append(f"GPM {player.gpm} — {'behind' if behind else 'on track'}")
    if night:
        reasons.append("night — group for pickoffs")
    if itemized:
        reasons.append("BKB up — fight through magic")
    if rosh is not None:
        reasons.append(f"Roshan {rosh.status}")
    if win_prob is not None:
        reasons.append(f"win {round(win_prob * 100)}%")

    rec = _recommend(dead, buyback_ready, win_prob, rosh, behind, night, itemized)
    return MacroAdvice(
        win_prob=win_prob, net_worth_lead=ctx.net_worth_lead, recommendation=rec,
        reasons=reasons, buyback_ready=buyback_ready, roshan=rosh,
    )


def _recommend(dead, buyback_ready, win_prob, rosh, behind, night, itemized) -> str:
    if dead and not buyback_ready:
        return "PLAY_SAFE"
    if win_prob is not None and win_prob >= _WIN_HIGH and itemized:
        return "PUSH"
    if rosh is not None and rosh.status in ("contestable", "likely_up") \
            and not (win_prob is not None and win_prob <= _WIN_LOW):
        return "TAKE_ROSH"
    if win_prob is not None and win_prob <= _WIN_LOW:
        return "DEFEND"
    if behind:
        return "FARM"
    if night:
        return "GROUP"
    return "FARM"
