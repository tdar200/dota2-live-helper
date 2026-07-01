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
    metric: str
    value: float
    percentile: int
    label: str


class FarmAdvice(BaseModel):
    has_data: bool = False
    hero_display: str | None = None
    metrics: list[FarmMetric] = Field(default_factory=list)
    summary: str | None = None


def advise(ctx: AdviceContext) -> FarmAdvice:
    hero = ctx.state.hero.name
    ib = ctx.item_build_db.get(hero)
    clock = ctx.state.clock_time

    if ib is None or clock is None or clock < 300:
        return FarmAdvice(has_data=False)

    bm = ib.benchmarks
    lh_rate = (ctx.state.player.last_hits / (clock / 60)) if ctx.state.player.last_hits is not None else None

    metrics: list[FarmMetric] = []
    for key, name, value in (
        ("gold_per_min", "GPM", ctx.state.player.gpm),
        ("xp_per_min", "XPM", ctx.state.player.xpm),
        ("last_hits_per_min", "LH/min", lh_rate),
    ):
        pct = _pct(value, bm.percentiles, getattr(bm, key))
        if value is None or pct is None:
            continue
        metrics.append(FarmMetric(metric=name, value=round(value, 1), percentile=pct, label=_band(pct)))

    if not metrics:
        return FarmAdvice(has_data=False)

    gpm_m = next((m for m in metrics if m.metric == "GPM"), None)
    summary = (
        f"GPM {gpm_m.percentile}th pct vs all players of {ib.display} — {gpm_m.label}"
        if gpm_m else None
    )
    return FarmAdvice(has_data=True, hero_display=ib.display, metrics=metrics, summary=summary)
