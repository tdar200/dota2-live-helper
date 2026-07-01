from app.advisors.context import AdviceContext
from app.modules.timings import TimingHit, next_occurrences
from app.timing_constants import GAME_EVENTS


def advise(ctx: AdviceContext) -> list[TimingHit]:
    if ctx.state.clock_time is None:
        return []
    hits = next_occurrences(ctx.state.clock_time, GAME_EVENTS)
    return [h for h in hits if h.seconds_until <= ctx.horizon_s][: ctx.limit]
