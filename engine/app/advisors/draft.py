from pydantic import BaseModel, Field
from app.advisors.context import AdviceContext

_STRONG = 0.53
_WEAK = 0.47
_SYNERGY = 0.52
_REFRESH_NOTE = "Run scripts/refresh_matchups.py (needs STRATZ_API_KEY) for counter/synergy."

# All-hero ranking is shown top-N; 127 rows would be noise.
DRAFT_LIMIT = 12
# Your personal per-hero WR nudges the score (comfort matters) but must not
# dominate meta/matchup. Only counted once you have a real sample, and the
# contribution is shrunk toward zero for small samples (Bayesian shrinkage:
# games/(games+K)) so a 5-0 fluke can't outweigh a genuine meta counter.
_PERSONAL_WEIGHT = 0.4
_PERSONAL_MIN_GAMES = 5
_PERSONAL_SHRINK_K = 20


class DraftPick(BaseModel):
    hero: str
    display: str
    score: float
    base_winrate: float | None = None
    counter: float | None = None
    synergy: float | None = None
    personal_winrate: float | None = None
    personal_games: int | None = None
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


def _hero_universe(ctx: AdviceContext, md) -> list[str]:
    """Every hero we can rank. Prefer the full all-hero Herald-meta set; fall
    back to the seed base_winrates (degraded / no meta cache)."""
    if ctx.hero_meta_db:
        return list(ctx.hero_meta_db.keys())
    if md is not None and md.base_winrates:
        return list(md.base_winrates.keys())
    return list(ctx.build_db.keys())


def _base_winrate(ctx: AdviceContext, md, hero: str) -> float | None:
    """Herald pub win-rate for this hero (all 127 via hero_meta), else the seed."""
    hm = ctx.hero_meta_db.get(hero)
    if hm is not None and hm.herald_winrate is not None:
        return hm.herald_winrate
    if md is not None:
        return md.base_winrates.get(hero)
    return None


def advise(ctx: AdviceContext) -> DraftAdvice:
    md = ctx.matchup_data
    matchup_ok = md is not None and md.has_data

    # Heroes already locked in (either team) are not draftable — never suggest them.
    drafted = set(ctx.enemy_heroes) | set(ctx.ally_heroes)

    picks: list[DraftPick] = []
    for hero in _hero_universe(ctx, md):
        if hero in drafted:
            continue
        base = _base_winrate(ctx, md, hero)
        if base is None:
            continue  # no Herald win-rate for this hero -> can't rank it fairly
        hm = md.heroes.get(hero) if md is not None else None
        vs = hm.vs if hm else {}
        wth = hm.with_ if hm else {}

        enemy_wrs = [vs[e] for e in ctx.enemy_heroes if e in vs]
        ally_wrs = [wth[a] for a in ctx.ally_heroes if a in wth]
        counter = _mean(enemy_wrs)
        synergy = _mean(ally_wrs)

        score = base  # guaranteed non-None (skipped above otherwise)
        if counter is not None:
            score += counter - 0.5
        if synergy is not None:
            score += synergy - 0.5

        # Personalization — your own comfort on this hero (keyless personal cache),
        # shrunk by sample size so a tiny sample contributes proportionally little.
        p_wr = p_games = None
        pers = ctx.personal_hero_db.get(hero)
        if pers is not None and (pers.games or 0) >= _PERSONAL_MIN_GAMES and pers.winrate is not None:
            p_wr, p_games = pers.winrate, pers.games
            shrink = p_games / (p_games + _PERSONAL_SHRINK_K)
            score += (p_wr - 0.5) * _PERSONAL_WEIGHT * shrink

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
        if p_wr is not None:
            reasons.append(f"you {_pct(p_wr)} ({p_games}g)")

        countered = any(vs[e] < _WEAK for e in ctx.enemy_heroes if e in vs)
        picks.append(DraftPick(
            hero=hero, display=ctx.hero_names.get(hero, hero),
            score=round(score, 4), base_winrate=base,
            counter=counter, synergy=synergy,
            personal_winrate=p_wr, personal_games=p_games,
            reasons=reasons, countered=countered,
        ))

    picks.sort(key=lambda p: p.score, reverse=True)
    picks = picks[:DRAFT_LIMIT]

    has_data = bool(ctx.hero_meta_db) or matchup_ok
    return DraftAdvice(
        has_data=has_data, bracket=(md.bracket if md is not None else None),
        note=None if matchup_ok else _REFRESH_NOTE, picks=picks,
    )
