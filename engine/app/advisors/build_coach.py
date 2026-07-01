from pydantic import BaseModel, Field
from app.advisors.context import AdviceContext

# Assembled stat items that are ALWAYS a stepping stone to a final item
# (Yasha/Sange/Kaya -> Manta / Sange-and-Yasha / Diffusal / Kaya-and-Sange /
# Yasha-and-Kaya). OpenDota's itemPopularity counts them because players held
# them mid-assembly; Dota Plus never renders them as a build step. Purely
# structural rules can't catch these (they have components, like real finals
# such as Force Staff), so this is a curated read-time demotion. Keys are the
# engine's "item_<name>" form (PhaseItem.key). Dropping them from phases means
# suggested_next (a first-unowned scan over the filtered phases) can never land
# on a stepping stone.
INTERMEDIATE_KEYS = {"item_yasha", "item_sange", "item_kaya"}


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
    source: str = "curated"
    phases: dict[str, list[CoreItem]] = Field(default_factory=dict)
    suggested_next: CoreItem | None = None


def _phase_for_clock(clock) -> str:
    """Return the build phase name for a given clock_time (seconds).

    Guards clock_time=None and negative values (menu / replay frames).
    """
    if clock is None or clock < 0:
        return "start_game"
    if clock < 600:
        return "early_game"
    if clock < 1500:
        return "mid_game"
    return "late_game"


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
        ib = ctx.item_build_db.get(hero) if hero else None
        if ib is None:
            return BuildAdvice(has_build=False, source="none", hero=hero,
                               hero_display=ctx.hero_names.get(hero, hero))
        owned = set(ctx.state.items)
        order = ["start_game", "early_game", "mid_game", "late_game"]
        phases = {
            ph: [
                CoreItem(item=pi.key, display=pi.display, owned=pi.key in owned)
                for pi in ib.builds.get(ph, [])
                if pi.key not in INTERMEDIATE_KEYS
            ]
            for ph in order
        }
        cur = _phase_for_clock(ctx.state.clock_time)
        suggested = None
        for ph in order[order.index(cur):]:
            suggested = next((c for c in phases[ph] if not c.owned), None)
            if suggested:
                break
        return BuildAdvice(
            has_build=True, source="opendota", hero=hero,
            hero_display=ib.display, phases=phases, suggested_next=suggested,
        )

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
