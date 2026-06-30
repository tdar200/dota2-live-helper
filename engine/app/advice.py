from pydantic import BaseModel, Field
from app.state import GameState
from app.modules.timings import TimingHit, next_occurrences
from app.timing_constants import GAME_EVENTS


class AdvicePayload(BaseModel):
    clock_time: int | None = None
    connected: bool = True
    timings: list[TimingHit] = Field(default_factory=list)


def build_advice(state: GameState, *, horizon_s: int = 600, limit: int = 6) -> AdvicePayload:
    if state.clock_time is None:
        return AdvicePayload(clock_time=None, timings=[])
    hits = next_occurrences(state.clock_time, GAME_EVENTS)
    hits = [h for h in hits if h.seconds_until <= horizon_s][:limit]
    return AdvicePayload(clock_time=state.clock_time, timings=hits)
