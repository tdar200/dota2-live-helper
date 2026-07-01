from pydantic import BaseModel, Field
from app.advisors.context import AdviceContext

_STRONG = 0.53
_WEAK = 0.47
_SYNERGY = 0.52
_REFRESH_NOTE = "Run scripts/refresh_matchups.py (needs STRATZ_API_KEY) for counter/synergy."


class DraftPick(BaseModel):
    hero: str
    display: str
    score: float
    base_winrate: float | None = None
    counter: float | None = None
    synergy: float | None = None
    reasons: list[str] = Field(default_factory=list)
    countered: bool = False


class DraftAdvice(BaseModel):
    has_data: bool
    bracket: str | None = None
    note: str | None = None
    picks: list[DraftPick] = Field(default_factory=list)


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _pct(x: float) -> str:
    return f"{round(x * 100)}%"


def advise(ctx: AdviceContext) -> DraftAdvice:
    md = ctx.matchup_data
    if md is None:
        return DraftAdvice(has_data=False, note=_REFRESH_NOTE)

    picks: list[DraftPick] = []
    for hero in ctx.build_db:
        base = md.base_winrates.get(hero)
        hm = md.heroes.get(hero)
        vs = hm.vs if hm else {}
        wth = hm.with_ if hm else {}

        enemy_wrs = [vs[e] for e in ctx.enemy_heroes if e in vs]
        ally_wrs = [wth[a] for a in ctx.ally_heroes if a in wth]
        counter = _mean(enemy_wrs)
        synergy = _mean(ally_wrs)

        score = (base if base is not None else 0.5)
        if counter is not None:
            score += counter - 0.5
        if synergy is not None:
            score += synergy - 0.5

        reasons: list[str] = []
        for e in ctx.enemy_heroes:
            if e in vs:
                name = ctx.hero_names.get(e, e)
                if vs[e] >= _STRONG:
                    reasons.append(f"strong vs {name} ({_pct(vs[e])})")
                elif vs[e] < _WEAK:
                    reasons.append(f"weak vs {name} ({_pct(vs[e])})")
        for a in ctx.ally_heroes:
            if a in wth and wth[a] >= _SYNERGY:
                reasons.append(f"synergy w/ {ctx.hero_names.get(a, a)} ({_pct(wth[a])})")

        countered = any(vs[e] < _WEAK for e in ctx.enemy_heroes if e in vs)
        picks.append(DraftPick(
            hero=hero, display=ctx.hero_names.get(hero, hero),
            score=round(score, 4), base_winrate=base,
            counter=counter, synergy=synergy, reasons=reasons, countered=countered,
        ))

    picks.sort(key=lambda p: p.score, reverse=True)
    return DraftAdvice(
        has_data=md.has_data, bracket=md.bracket,
        note=None if md.has_data else _REFRESH_NOTE, picks=picks,
    )
