from pydantic import BaseModel, Field
from app.state import GameState
from app.modules.timings import TimingHit
from app.advisors.context import AdviceContext
from app.advisors import timings as timings_advisor
from app.advisors import build_coach
from app.advisors import draft as draft_advisor
from app.advisors import macro as macro_advisor
from app.advisors import farm as farm_advisor
from app.advisors import abilities as abilities_advisor
from app.advisors.abilities import SpellsAdvice
from app.advisors.build_coach import BuildAdvice
from app.advisors.draft import DraftAdvice
from app.advisors.macro import MacroAdvice
from app.advisors.farm import FarmAdvice
from app.build_data import load_build_data
from app.matchups import load_matchups
from app.winprob import load_winprob
from app.item_builds import load_item_builds
from app.hero_meta import load_hero_meta
from app.personal_stats import load_personal_stats

BUILD_DATA = load_build_data()
MATCHUP_DATA = load_matchups()
WINPROB_TABLE = load_winprob()
ITEM_BUILDS = load_item_builds()
HERO_META = load_hero_meta()
PERSONAL_STATS = load_personal_stats()


class AdvicePayload(BaseModel):
    clock_time: int | None = None
    connected: bool = True
    timings: list[TimingHit] = Field(default_factory=list)
    build: BuildAdvice | None = None
    draft: DraftAdvice | None = None
    macro: MacroAdvice | None = None
    farm: FarmAdvice | None = None
    spells: SpellsAdvice | None = None


def build_advice(state: GameState, *, horizon_s: int = 600, limit: int = 6) -> AdvicePayload:
    ctx = AdviceContext(
        state=state, horizon_s=horizon_s, limit=limit,
        enemy_heroes=state.enemy_heroes,
        ally_heroes=state.ally_heroes,
        build_db=BUILD_DATA.builds,
        trait_db=BUILD_DATA.traits,
        item_names=BUILD_DATA.item_names,
        hero_names=BUILD_DATA.hero_names,
        matchup_data=MATCHUP_DATA,
        net_worth_lead=state.net_worth_lead,
        roshan_dead_clock=state.roshan_dead_clock,
        winprob_table=WINPROB_TABLE,
        item_build_db=ITEM_BUILDS.heroes,
        item_costs=ITEM_BUILDS.item_costs,
        hero_meta_db=HERO_META.heroes,
        personal_hero_db=PERSONAL_STATS.heroes,
        personal_item_db=PERSONAL_STATS.items,
    )
    return AdvicePayload(
        clock_time=state.clock_time,
        timings=timings_advisor.advise(ctx),
        build=build_coach.advise(ctx),
        draft=draft_advisor.advise(ctx),
        macro=macro_advisor.advise(ctx),
        farm=farm_advisor.advise(ctx),
        spells=abilities_advisor.advise(ctx),
    )
