from pydantic import BaseModel, Field
from app.advisors.context import AdviceContext


class CoreItem(BaseModel):
    item: str
    display: str
    owned: bool


class SituationalItem(BaseModel):
    item: str
    display: str
    note: str
    trait: str
    triggered_by: list[str] = Field(default_factory=list)


class BuildAdvice(BaseModel):
    has_build: bool
    hero: str | None = None
    hero_display: str | None = None
    next_core: CoreItem | None = None
    core: list[CoreItem] = Field(default_factory=list)
    skill_next: str | None = None
    talent_next: str | None = None
    situational: list[SituationalItem] = Field(default_factory=list)


def _talent_for_level(talents: dict[str, str], level: int) -> str | None:
    brackets = sorted(int(k) for k in talents)
    chosen = brackets[0]
    for b in brackets:
        if level >= b:
            chosen = b
    return f"L{chosen}: {talents[str(chosen)]}"


def advise(ctx: AdviceContext) -> BuildAdvice:
    hero = ctx.state.hero.name
    build = ctx.build_db.get(hero) if hero else None
    if build is None:
        return BuildAdvice(has_build=False, hero=hero)

    owned = set(ctx.state.items)
    core = [
        CoreItem(item=i, display=ctx.item_names.get(i, i), owned=i in owned)
        for i in build.core_items
    ]
    next_core = next((c for c in core if not c.owned), None)

    # enemy trait -> list of triggering enemy display names
    trait_to_enemies: dict[str, list[str]] = {}
    for ek in ctx.enemy_heroes:
        for t in ctx.trait_db.get(ek, []):
            trait_to_enemies.setdefault(t, []).append(ctx.hero_names.get(ek, ek))

    situational = [
        SituationalItem(
            item=s.item, display=ctx.item_names.get(s.item, s.item),
            note=s.note, trait=s.trait,
            triggered_by=trait_to_enemies.get(s.trait, []),
        )
        for s in build.situational
    ]
    situational.sort(key=lambda s: (len(s.triggered_by) == 0, s.item))

    return BuildAdvice(
        has_build=True, hero=hero, hero_display=build.display,
        next_core=next_core, core=core,
        skill_next=build.skill_order,
        talent_next=_talent_for_level(build.talents, ctx.state.hero.level or 0),
        situational=situational,
    )
