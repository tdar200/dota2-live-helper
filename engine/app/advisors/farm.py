from pydantic import BaseModel, Field
from app.advisors.context import AdviceContext


def _pct(value, pcts, vals):
    """Map value onto percentile curve (ascending vals). Returns int percentile or None."""
    if not vals or value is None:
        return None
    if value <= vals[0]:
        return round(pcts[0] * 100)
    if value >= vals[-1]:
        return round(pcts[-1] * 100)
    for i in range(1, len(vals)):
        if value <= vals[i]:
            lo_v, hi_v, lo_p, hi_p = vals[i - 1], vals[i], pcts[i - 1], pcts[i]
            frac = (value - lo_v) / (hi_v - lo_v) if hi_v > lo_v else 0
            return round((lo_p + frac * (hi_p - lo_p)) * 100)
    return round(pcts[-1] * 100)


def _band(p: int) -> str:
    if p < 30:
        return "behind"
    if p < 60:
        return "on track"
    if p < 85:
        return "ahead"
    return "dominating"


class FarmMetric(BaseModel):
    """A rate metric (per-minute) with a percentile vs all players of this hero."""
    metric: str
    value: float
    percentile: int
    label: str


class ScoreStat(BaseModel):
    """A raw live stat with no percentile curve (K/D/A, denies, net worth)."""
    metric: str
    value: float
    display: str


class FarmAdvice(BaseModel):
    has_data: bool = False
    hero_display: str | None = None
    metrics: list[FarmMetric] = Field(default_factory=list)   # percentile'd rate metrics
    combat: list[ScoreStat] = Field(default_factory=list)     # raw live scorecard stats
    net_worth: int | None = None                              # computed (gold + items) or GSI
    net_worth_estimated: bool = False                         # True when we summed item costs
    verdict: str | None = None
    summary: str | None = None


def _compute_net_worth(ctx: AdviceContext):
    """(net_worth, estimated?) — prefer GSI's field, else gold + owned item costs.

    Returns (None, False) when we have neither gold nor a cost table.
    """
    p = ctx.state.player
    if p.net_worth is not None:  # spectator payloads carry it directly
        return p.net_worth, False
    if p.gold is None:
        return None, False
    if not ctx.item_costs:
        return None, False  # can't estimate without costs; UI falls back to gold
    items_value = sum(ctx.item_costs.get(k, 0) for k in ctx.state.items)
    return int(p.gold + items_value), True


def _fmt_thousands(n: float) -> str:
    return f"{n / 1000:.1f}k" if n >= 1000 else f"{int(n)}"


def advise(ctx: AdviceContext) -> FarmAdvice:
    hero = ctx.state.hero.name
    ib = ctx.item_build_db.get(hero)
    clock = ctx.state.clock_time
    p = ctx.state.player

    if ib is None or clock is None or clock < 300:
        return FarmAdvice(has_data=False)

    bm = ib.benchmarks
    minutes = clock / 60
    lh_rate = (p.last_hits / minutes) if p.last_hits is not None else None
    hd_rate = (p.hero_damage / minutes) if p.hero_damage is not None else None
    k_rate = (p.kills / minutes) if p.kills is not None else None

    # Rate metrics with a percentile curve. hero_damage/kills only appear once a
    # benchmark re-pull has populated their arrays (empty -> _pct returns None).
    metrics: list[FarmMetric] = []
    for key, name, value in (
        ("gold_per_min", "GPM", p.gpm),
        ("xp_per_min", "XPM", p.xpm),
        ("last_hits_per_min", "LH/min", lh_rate),
        ("hero_damage_per_min", "HeroDmg/min", hd_rate),
        ("kills_per_min", "Kills/min", k_rate),
    ):
        pct = _pct(value, bm.percentiles, getattr(bm, key))
        if value is None or pct is None:
            continue
        metrics.append(FarmMetric(metric=name, value=round(value, 1), percentile=pct, label=_band(pct)))

    if not metrics:
        return FarmAdvice(has_data=False)

    # Raw live scorecard stats (no bracket curve exists for these).
    net_worth, nw_est = _compute_net_worth(ctx)
    combat: list[ScoreStat] = []
    if p.kills is not None and p.deaths is not None and p.assists is not None:
        combat.append(ScoreStat(metric="KDA", value=float(p.kills - p.deaths),
                                display=f"{p.kills}/{p.deaths}/{p.assists}"))
    if p.last_hits is not None:
        ld = f"{p.last_hits}" + (f"/{p.denies}" if p.denies is not None else "")
        combat.append(ScoreStat(metric="LH/DN", value=float(p.last_hits), display=ld))
    if p.hero_damage is not None:
        combat.append(ScoreStat(metric="HeroDmg", value=float(p.hero_damage),
                                display=_fmt_thousands(p.hero_damage)))
    if net_worth is not None:
        combat.append(ScoreStat(metric="Net Worth", value=float(net_worth),
                                display=_fmt_thousands(net_worth) + ("~" if nw_est else "")))
    elif p.gold is not None:
        combat.append(ScoreStat(metric="Gold", value=float(p.gold), display=_fmt_thousands(p.gold)))

    gpm_m = next((m for m in metrics if m.metric == "GPM"), None)
    summary = (
        f"GPM {gpm_m.percentile}th pct vs all players of {ib.display} — {gpm_m.label}"
        if gpm_m else None
    )
    verdict = _verdict(metrics, p)
    return FarmAdvice(
        has_data=True, hero_display=ib.display, metrics=metrics, combat=combat,
        net_worth=net_worth, net_worth_estimated=nw_est, verdict=verdict, summary=summary,
    )


def _verdict(metrics: list[FarmMetric], p) -> str | None:
    """One-line synthesis from farm percentile + a rough combat read."""
    gpm_m = next((m for m in metrics if m.metric == "GPM"), None)
    if gpm_m is None:
        return None
    farm_word = "ahead on farm" if gpm_m.percentile >= 55 else (
        "behind on farm" if gpm_m.percentile < 40 else "even on farm")
    # deaths read: only if we have KDA
    if p.deaths is not None and p.kills is not None:
        if p.deaths >= 6 and p.deaths > p.kills:
            return f"{farm_word}, but feeding — play safer"
        if p.kills >= p.deaths + 3:
            return f"{farm_word}, winning fights"
    return farm_word
