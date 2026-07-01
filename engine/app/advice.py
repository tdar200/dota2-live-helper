from pydantic import BaseModel, Field
from app.state import GameState
from app.modules.timings import TimingHit
from app.advisors.context import AdviceContext
from app.advisors import timings as timings_advisor


class AdvicePayload(BaseModel):
    clock_time: int | None = None
    connected: bool = True
    timings: list[TimingHit] = Field(default_factory=list)


def build_advice(state: GameState, *, horizon_s: int = 600, limit: int = 6) -> AdvicePayload:
    ctx = AdviceContext(state=state, horizon_s=horizon_s, limit=limit)
    return AdvicePayload(clock_time=state.clock_time, timings=timings_advisor.advise(ctx))
