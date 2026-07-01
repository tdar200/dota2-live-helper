from pydantic import BaseModel, Field
from app.advisors.context import AdviceContext

# Pure advisor: reads ctx.state.hero only, returns Pydantic, no I/O, no network.
# Filtering of passives/talents and the ULT headline live here (offline-tested)
# so the browser renders payload.spells verbatim.


class SpellReady(BaseModel):
    name: str
    ready: bool
    cooldown: int | None = None
    charges: int | None = None
    ultimate: bool = False


class SpellsAdvice(BaseModel):
    available: bool
    ultimate: SpellReady | None = None
    key_spells: list[SpellReady] = Field(default_factory=list)
    aghanims_scepter: bool | None = None
    aghanims_shard: bool | None = None
    headline: str | None = None


def _castable(a) -> bool:
    """A real, learned, active spell — not a talent (special_bonus_*), not a passive."""
    return bool(
        a.name
        and not a.name.startswith("special_bonus")
        and not a.passive
        and (a.level or 0) > 0
    )


def _to_ready(a) -> SpellReady:
    # Charge spells: ready while any charge is banked.
    if a.charges is not None:
        ready = a.charges > 0
    elif a.can_cast is not None:
        ready = bool(a.can_cast)
    else:
        ready = a.cooldown in (0, None)
    return SpellReady(
        name=a.name,
        ready=ready,
        cooldown=a.cooldown,
        charges=a.charges,
        ultimate=bool(a.ultimate),
    )


def advise(ctx: AdviceContext) -> SpellsAdvice:
    hero = ctx.state.hero
    abilities = hero.abilities or []
    scepter = hero.aghanims_scepter
    shard = hero.aghanims_shard

    # Degrade: nothing to say at all.
    if not abilities and scepter is None and shard is None:
        return SpellsAdvice(
            available=False, aghanims_scepter=scepter, aghanims_shard=shard
        )

    castable = [a for a in abilities if _castable(a)]
    ult_ability = next((a for a in castable if a.ultimate), None)
    ultimate = _to_ready(ult_ability) if ult_ability is not None else None
    key_spells = [_to_ready(a) for a in castable if not a.ultimate][:3]

    headline = None
    if ultimate is not None:
        if ultimate.ready:
            headline = "ULT READY"
        elif ultimate.cooldown:
            headline = f"ULT {ultimate.cooldown}s"

    return SpellsAdvice(
        available=True,
        ultimate=ultimate,
        key_spells=key_spells,
        aghanims_scepter=scepter,
        aghanims_shard=shard,
        headline=headline,
    )
