from pydantic import BaseModel, Field
from app.state import GameState
from app.modules.timings import TimingHit
from app.advisors.context import AdviceContext
from app.advisors import timings as timings_advisor
from app.advisors import build_coach
from app.advisors.build_coach import BuildAdvice
from app.build_data import load_build_data

BUILD_DATA = load_build_data()


class AdvicePayload(BaseModel):
    clock_time: int | None = None
    connected: bool = True
    timings: list[TimingHit] = Field(default_factory=list)
    build: BuildAdvice | None = None


def build_advice(state: GameState, *, horizon_s: int = 600, limit: int = 6) -> AdvicePayload:
    ctx = AdviceContext(
        state=state, horizon_s=horizon_s, limit=limit,
        enemy_heroes=state.enemy_heroes,
        build_db=BUILD_DATA.builds,
        trait_db=BUILD_DATA.traits,
        item_names=BUILD_DATA.item_names,
        hero_names=BUILD_DATA.hero_names,
    )
    return AdvicePayload(
        clock_time=state.clock_time,
        timings=timings_advisor.advise(ctx),
        build=build_coach.advise(ctx),
    )
