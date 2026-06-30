# Dota 2 Live Helper — P2 Build Coach Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a live build-coach pillar — next core item, skill/talent, and enemy-aware situational items — driven by curated per-hero builds, on top of the P0+P1 backbone.

**Architecture:** Refactor the advice aggregator into per-pillar advisor functions over a shared `AdviceContext`. Add curated JSON build data (builds, hero→traits, item/hero display names) loaded once at startup. A `build_coach` advisor reads the player's hero+items (GSI) and the entered enemy lineup and emits a `BuildAdvice`. A new `POST /enemies` inbound endpoint sets the lineup; `GET /heroes` feeds the dashboard's enemy picker; a second dashboard panel renders it.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, pytest (engine); Vite + vanilla JS (dashboard). No new runtime deps. Curated data as JSON.

## Global Constraints

- **Patch 7.41d.** Curated build/trait/name data lives ONLY under `engine/app/data/` as JSON — never inline in logic. Advisors contain logic; data files contain data.
- **VAC-safe:** engine consumes Valve GSI + the user's manual enemy entry only. No game-process access.
- **Display-agnostic engine:** advisors return Pydantic advice objects; they must not import HTTP/WebSocket/DOM. `main.py` is the only HTTP/WS layer.
- **Pydantic v2** API (`BaseModel`, `Field`, `model_dump`). **Python 3.11+** (`X | None` unions).
- **GSI hero/item names are exact internal keys.** Several heroes use LEGACY internal names that differ from their display name — verify every hero key against `../dota2-knowledge-base/raw-data/heroes.json` and every item key against `../dota2-knowledge-base/raw-data/items.json`. Known traps: **Wraith King = `npc_dota_hero_skeleton_king`**, **Zeus = `npc_dota_hero_zuus`**, **Necrophos = `npc_dota_hero_necrolyte`**, **Windranger = `npc_dota_hero_windrunner`**. Battle Fury = `item_bfury`, Aghanim's Scepter = `item_ultimate_scepter`.
- **Trait taxonomy is a fixed set of 8:** `heavy_magic`, `evasion`, `illusions_summons`, `invisibility`, `high_armor`, `healing_regen`, `lockdown_silence`, `tanky_hp`.
- **Engine self-contained:** vendor hero/item display names into `engine/app/data/`; no runtime dependency on the sibling KB repo.
- **Run pytest from `engine/` using `engine/.venv/bin/python`.** Existing suite is 13 tests; it must stay green.
- **Project root:** `/home/tahseen-dar/Projects/dota2-live-helper`.

---

## File Structure

```
engine/app/
  advisors/
    __init__.py
    context.py          # AdviceContext (shared input to every advisor)
    timings.py          # advise(ctx) -> list[TimingHit]   (logic moved out of advice.py)
    build_coach.py      # advise(ctx) -> BuildAdvice
  build_data.py         # HeroBuild/Situational models + load_build_data() -> BuildData
  data/
    builds/<hero>.json  # one curated build per Herald climber (~11)
    hero_traits.json    # enemy_hero_key -> [trait]
    item_names.json     # item_key -> display name
    heroes.json         # [{key, display}] full hero list (generated from KB)
  advice.py             # AdvicePayload (+ build field) + build_advice() aggregator
  state.py              # GameState gains enemy_heroes
  main.py               # + POST /enemies, GET /heroes
engine/tests/
  test_advisors_timings.py
  test_build_data.py
  test_build_coach.py
  test_enemies_endpoint.py
dashboard/src/
  panels/build.js       # render payload.build
  panels/enemies.js     # enemy picker (GET /heroes, POST /enemies)
  main.js, index.html, style.css   # wire in the new panels
```

---

### Task 1: Refactor aggregator into advisor functions over a shared context

Pure refactor: move the timings logic out of `build_advice` into `advisors/timings.advise(ctx)`, introduce `AdviceContext`. No behavior change; the 13 existing tests stay green.

**Files:**
- Create: `engine/app/advisors/__init__.py` (empty)
- Create: `engine/app/advisors/context.py`
- Create: `engine/app/advisors/timings.py`
- Modify: `engine/app/advice.py`
- Test: `engine/tests/test_advisors_timings.py`

**Interfaces:**
- Consumes: `GameState` (`app.state`), `TimingHit`/`next_occurrences` (`app.modules.timings`), `GAME_EVENTS` (`app.timing_constants`).
- Produces:
  - `app.advisors.context.AdviceContext` — a dataclass with `state: GameState`, `horizon_s: int = 600`, `limit: int = 6`. (Extended in Task 4.)
  - `app.advisors.timings.advise(ctx: AdviceContext) -> list[TimingHit]`.
  - `app.advice.build_advice(state, *, horizon_s=600, limit=6) -> AdvicePayload` unchanged signature/behavior, now delegating to the advisor.

- [ ] **Step 1: Write the context dataclass**

`engine/app/advisors/context.py`:
```python
from dataclasses import dataclass
from app.state import GameState


@dataclass
class AdviceContext:
    state: GameState
    horizon_s: int = 600
    limit: int = 6
```

- [ ] **Step 2: Write the failing test for the timings advisor**

`engine/tests/test_advisors_timings.py`:
```python
from app.state import GameState
from app.advisors.context import AdviceContext
from app.advisors import timings


def test_timings_advise_returns_sorted_within_horizon():
    ctx = AdviceContext(state=GameState(clock_time=300), horizon_s=600, limit=6)
    hits = timings.advise(ctx)
    assert hits == sorted(hits, key=lambda h: h.seconds_until)
    assert all(h.seconds_until <= 600 for h in hits)
    assert len(hits) <= 6


def test_timings_advise_empty_when_no_clock():
    ctx = AdviceContext(state=GameState())
    assert timings.advise(ctx) == []
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd engine && .venv/bin/python -m pytest tests/test_advisors_timings.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.advisors.timings'`.

- [ ] **Step 4: Implement the timings advisor**

`engine/app/advisors/timings.py`:
```python
from app.advisors.context import AdviceContext
from app.modules.timings import TimingHit, next_occurrences
from app.timing_constants import GAME_EVENTS


def advise(ctx: AdviceContext) -> list[TimingHit]:
    if ctx.state.clock_time is None:
        return []
    hits = next_occurrences(ctx.state.clock_time, GAME_EVENTS)
    return [h for h in hits if h.seconds_until <= ctx.horizon_s][: ctx.limit]
```

- [ ] **Step 5: Refactor `build_advice` to use the advisor**

Replace the whole body of `engine/app/advice.py` with:
```python
from pydantic import BaseModel, Field
from app.state import GameState
from app.modules.timings import TimingHit
from app.advisors.context import AdviceContext
from app.advisors import timings as timings_advisor


class AdvicePayload(BaseModel):
    clock_time: int | None = None
    connected: bool = True
    timings: list[TimingHit] = Field(default_factory=list)


def build_advice(state: GameState, *, horizon_s: int = 600, limit: int = 6) -> AdvicePayload:
    ctx = AdviceContext(state=state, horizon_s=horizon_s, limit=limit)
    return AdvicePayload(clock_time=state.clock_time, timings=timings_advisor.advise(ctx))
```

- [ ] **Step 6: Run the full suite to verify no regression**

Run: `cd engine && .venv/bin/python -m pytest tests -v`
Expected: PASS — all 15 tests (13 existing + 2 new). The existing `test_advice.py` cases still pass because behavior is identical.

- [ ] **Step 7: Commit**

```bash
cd /home/tahseen-dar/Projects/dota2-live-helper
git add engine/app/advisors engine/app/advice.py engine/tests/test_advisors_timings.py
git commit -m "refactor(engine): advisor functions over shared AdviceContext"
```

---

### Task 2: Curated build data + loader + validation

**Files:**
- Create: `engine/app/data/heroes.json` (generated), `engine/app/data/item_names.json`, `engine/app/data/hero_traits.json`
- Create: `engine/app/data/builds/skeleton_king.json`, `spectre.json`, `phantom_assassin.json`, and one JSON for each remaining Herald climber (see source table)
- Create: `engine/app/build_data.py`
- Test: `engine/tests/test_build_data.py`

**Interfaces:**
- Produces:
  - `app.build_data.Situational(BaseModel)` — `item: str`, `trait: str`, `note: str`.
  - `app.build_data.HeroBuild(BaseModel)` — `hero: str`, `display: str`, `source: str`, `verified: bool`, `skill_order: str`, `talents: dict[str, str]`, `starting_items: list[str]`, `core_items: list[str]`, `situational: list[Situational]`.
  - `app.build_data.BuildData(BaseModel)` — `builds: dict[str, HeroBuild]` (keyed by hero), `traits: dict[str, list[str]]`, `item_names: dict[str, str]`, `hero_names: dict[str, str]`, `heroes: list[dict]` (`[{key, display}]`).
  - `app.build_data.TRAITS: frozenset[str]` — the 8 allowed traits.
  - `app.build_data.load_build_data() -> BuildData` — loads everything from `app/data/`.

- [ ] **Step 1: Generate the full hero list from the KB (deterministic)**

Run from project root:
```bash
mkdir -p engine/app/data/builds
jq '[.[] | {key: .name, display: .localized_name}]' \
  ../dota2-knowledge-base/raw-data/heroes.json 2>/dev/null \
  || jq '[.[] | {key: .name, display: .localized_name}]' \
  dota2-knowledge-base/raw-data/heroes.json \
  > engine/app/data/heroes.json
# sanity: should be ~120+ heroes, each {key, display}
jq 'length' engine/app/data/heroes.json
```
(If the KB path differs, locate `raw-data/heroes.json` under the `dota2-knowledge-base` repo and adjust. This file is vendored so the engine has no runtime KB dependency.)

- [ ] **Step 2: Write `item_names.json`**

`engine/app/data/item_names.json`:
```json
{
  "item_power_treads": "Power Treads",
  "item_phase_boots": "Phase Boots",
  "item_armlet": "Armlet of Mordiggian",
  "item_radiance": "Radiance",
  "item_assault": "Assault Cuirass",
  "item_abyssal": "Abyssal Blade",
  "item_black_king_bar": "Black King Bar",
  "item_monkey_king_bar": "Monkey King Bar",
  "item_nullifier": "Nullifier",
  "item_manta": "Manta Style",
  "item_skadi": "Eye of Skadi",
  "item_butterfly": "Butterfly",
  "item_bfury": "Battle Fury",
  "item_desolator": "Desolator",
  "item_ultimate_scepter": "Aghanim's Scepter"
}
```
(Add entries here as later builds reference more items — the validation test in Step 6 will flag any missing name.)

- [ ] **Step 3: Write `hero_traits.json` (curated enemy→trait map)**

`engine/app/data/hero_traits.json`:
```json
{
  "npc_dota_hero_zuus": ["heavy_magic"],
  "npc_dota_hero_lina": ["heavy_magic"],
  "npc_dota_hero_lion": ["heavy_magic", "lockdown_silence"],
  "npc_dota_hero_phantom_assassin": ["evasion"],
  "npc_dota_hero_windrunner": ["evasion"],
  "npc_dota_hero_naga_siren": ["illusions_summons"],
  "npc_dota_hero_broodmother": ["illusions_summons"],
  "npc_dota_hero_riki": ["invisibility"],
  "npc_dota_hero_bounty_hunter": ["invisibility"],
  "npc_dota_hero_bristleback": ["high_armor", "healing_regen"],
  "npc_dota_hero_timbersaw": ["high_armor"],
  "npc_dota_hero_necrolyte": ["healing_regen"],
  "npc_dota_hero_huskar": ["healing_regen"],
  "npc_dota_hero_shadow_shaman": ["lockdown_silence"],
  "npc_dota_hero_silencer": ["lockdown_silence"],
  "npc_dota_hero_pudge": ["tanky_hp"],
  "npc_dota_hero_centaur": ["tanky_hp"]
}
```
Every key must exist in `heroes.json` and every trait must be in the 8-trait taxonomy (Step 6 enforces both).

- [ ] **Step 4: Write the three KB-derived reference builds**

`engine/app/data/builds/skeleton_king.json`:
```json
{
  "hero": "npc_dota_hero_skeleton_king",
  "display": "Wraith King",
  "source": "KB herald-climbing-heroes.md",
  "verified": false,
  "skill_order": "Max Wraithfire Blast (Q); value Vampiric Spirit (E); Reincarnation at 6/12/18",
  "talents": {"10": "+8 Strength", "15": "+30 Movement Speed", "20": "+90 Skeleton Charge Damage", "25": "+2 Skeletons per Death"},
  "starting_items": ["item_tango", "item_quelling_blade", "item_gauntlets", "item_circlet"],
  "core_items": ["item_power_treads", "item_armlet", "item_radiance", "item_assault", "item_abyssal"],
  "situational": [
    {"item": "item_black_king_bar", "trait": "heavy_magic", "note": "vs heavy magic burst"},
    {"item": "item_monkey_king_bar", "trait": "evasion", "note": "vs evasion"},
    {"item": "item_nullifier", "trait": "tanky_hp", "note": "vs tanky / save items"}
  ]
}
```

`engine/app/data/builds/spectre.json`:
```json
{
  "hero": "npc_dota_hero_spectre",
  "display": "Spectre",
  "source": "KB spectre-desolate-dispersion-build.md",
  "verified": false,
  "skill_order": "Max Spectral Dagger (Q); value Desolate; Dispersion as able; Haunt at 6/12/18",
  "talents": {"10": "+15 Attack Speed", "15": "+12 Strength", "20": "-30s Haunt Cooldown", "25": "+1.5s Dagger Path Duration"},
  "starting_items": ["item_tango", "item_quelling_blade", "item_circlet", "item_branches"],
  "core_items": ["item_power_treads", "item_manta", "item_radiance", "item_skadi", "item_abyssal"],
  "situational": [
    {"item": "item_black_king_bar", "trait": "heavy_magic", "note": "vs heavy magic burst"},
    {"item": "item_nullifier", "trait": "tanky_hp", "note": "vs tanky / save items"},
    {"item": "item_butterfly", "trait": "evasion", "note": "vs right-click / evasion"}
  ]
}
```

`engine/app/data/builds/phantom_assassin.json`:
```json
{
  "hero": "npc_dota_hero_phantom_assassin",
  "display": "Phantom Assassin",
  "source": "KB phantom-assassin-deadly-focus-build.md",
  "verified": true,
  "skill_order": "Max Stifling Dagger (Q); value Phantom Strike; Fan of Knives for Break; Coup de Grace 6/12/18",
  "talents": {"10": "-1.5s Stifling Dagger Cooldown", "15": "+25% Stifling Dagger Damage", "20": "+40 Phantom Strike Attack Speed", "25": "Triple Strike Stifling Dagger"},
  "starting_items": ["item_tango", "item_quelling_blade", "item_slippers", "item_circlet"],
  "core_items": ["item_phase_boots", "item_bfury", "item_desolator", "item_ultimate_scepter", "item_abyssal"],
  "situational": [
    {"item": "item_black_king_bar", "trait": "heavy_magic", "note": "vs heavy magic burst"},
    {"item": "item_monkey_king_bar", "trait": "evasion", "note": "vs evasion (Butterfly/Halberd/PA mirror)"},
    {"item": "item_nullifier", "trait": "tanky_hp", "note": "vs heavy armor / passives (+Break)"}
  ]
}
```

- [ ] **Step 5: Author the remaining Herald-climber builds**

Create one JSON per hero below, following the exact schema above. Distill each from its KB source where one exists; for the three without a KB build, research a standard 7.41d core and set `"verified": false`. Verify every `hero` and item key against `../dota2-knowledge-base/raw-data/heroes.json` / `raw-data/items.json`. Add any new item to `item_names.json` (Step 2). Use the legacy keys noted in Global Constraints.

| File | hero key | display | KB source | verified |
|---|---|---|---|---|
| `riki.json` | `npc_dota_hero_riki` | Riki | riki-max-damage.md | true |
| `zeus.json` | `npc_dota_hero_zuus` | Zeus | zeus-caster-refresher-build.md | true |
| `sniper.json` | `npc_dota_hero_sniper` | Sniper | sniper-keen-scope-build.md | true |
| `techies.json` | `npc_dota_hero_techies` | Techies | techies-max-mine-damage.md | true |
| `medusa.json` | `npc_dota_hero_medusa` | Medusa | medusa-mana-stack-build.md | true |
| `necrophos.json` | `npc_dota_hero_necrolyte` | Necrophos | (research) | false |
| `bristleback.json` | `npc_dota_hero_bristleback` | Bristleback | (research) | false |
| `juggernaut.json` | `npc_dota_hero_juggernaut` | Juggernaut | (research) | false |

Each build needs: `skill_order`, four `talents` keys (`"10"/"15"/"20"/"25"`), `starting_items`, `core_items` (5–6 items in buy order), and 2–3 `situational` entries whose `trait` is in the taxonomy. Keep situational triggers honest (e.g. a hero that doesn't want MKB shouldn't list `evasion`).

- [ ] **Step 6: Write the loader + the validation test (TDD: test first)**

`engine/tests/test_build_data.py`:
```python
from app.build_data import load_build_data, TRAITS


def test_load_build_data_parses_and_validates():
    data = load_build_data()
    # core climbers present
    assert "npc_dota_hero_skeleton_king" in data.builds
    assert data.builds["npc_dota_hero_skeleton_king"].display == "Wraith King"
    assert len(data.builds) >= 11

    # every build's items have display names; every situational trait is valid
    for hero, build in data.builds.items():
        for item in build.core_items + build.starting_items:
            assert item in data.item_names, f"{hero}: no name for {item}"
        for s in build.situational:
            assert s.trait in TRAITS, f"{hero}: bad trait {s.trait}"
            assert s.item in data.item_names, f"{hero}: no name for {s.item}"
        assert set(build.talents) == {"10", "15", "20", "25"}, f"{hero}: talents"

    # trait map references real heroes and valid traits
    keys = {h["key"] for h in data.heroes}
    for ehero, traits in data.traits.items():
        assert ehero in keys, f"unknown enemy hero {ehero}"
        for t in traits:
            assert t in TRAITS, f"bad trait {t} for {ehero}"


def test_hero_names_derived_from_heroes_list():
    data = load_build_data()
    assert data.hero_names["npc_dota_hero_zuus"] == "Zeus"
```

- [ ] **Step 7: Run test to verify it fails**

Run: `cd engine && .venv/bin/python -m pytest tests/test_build_data.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.build_data'`.

- [ ] **Step 8: Implement the loader**

`engine/app/build_data.py`:
```python
import json
from pathlib import Path
from pydantic import BaseModel, Field

_DATA = Path(__file__).parent / "data"

TRAITS = frozenset({
    "heavy_magic", "evasion", "illusions_summons", "invisibility",
    "high_armor", "healing_regen", "lockdown_silence", "tanky_hp",
})


class Situational(BaseModel):
    item: str
    trait: str
    note: str


class HeroBuild(BaseModel):
    hero: str
    display: str
    source: str
    verified: bool
    skill_order: str
    talents: dict[str, str]
    starting_items: list[str] = Field(default_factory=list)
    core_items: list[str] = Field(default_factory=list)
    situational: list[Situational] = Field(default_factory=list)


class BuildData(BaseModel):
    builds: dict[str, HeroBuild]
    traits: dict[str, list[str]]
    item_names: dict[str, str]
    hero_names: dict[str, str]
    heroes: list[dict]


def load_build_data() -> BuildData:
    item_names = json.loads((_DATA / "item_names.json").read_text())
    traits = json.loads((_DATA / "hero_traits.json").read_text())
    heroes = json.loads((_DATA / "heroes.json").read_text())
    hero_names = {h["key"]: h["display"] for h in heroes}

    builds: dict[str, HeroBuild] = {}
    for path in sorted((_DATA / "builds").glob("*.json")):
        build = HeroBuild.model_validate_json(path.read_text())
        builds[build.hero] = build

    return BuildData(
        builds=builds, traits=traits, item_names=item_names,
        hero_names=hero_names, heroes=heroes,
    )
```

- [ ] **Step 9: Run the validation test until green**

Run: `cd engine && .venv/bin/python -m pytest tests/test_build_data.py -v`
Expected: PASS. If it fails on a missing item name or bad trait/hero key, fix the offending data file (this is exactly what the test is for). Then run the full suite: `.venv/bin/python -m pytest tests -q` — all green.

- [ ] **Step 10: Commit**

```bash
cd /home/tahseen-dar/Projects/dota2-live-helper
git add engine/app/data engine/app/build_data.py engine/tests/test_build_data.py
git commit -m "feat(engine): curated build data (11 climbers) + loader + validation"
```

---

### Task 3: The `build_coach` advisor

**Files:**
- Create: `engine/app/advisors/build_coach.py`
- Modify: `engine/app/advisors/context.py` (extend `AdviceContext`)
- Test: `engine/tests/test_build_coach.py`

**Interfaces:**
- Consumes: `AdviceContext`, `HeroBuild`/`BuildData` types.
- Produces (in `app.advisors.build_coach`):
  - `CoreItem(BaseModel)` — `item: str`, `display: str`, `owned: bool`.
  - `SituationalItem(BaseModel)` — `item: str`, `display: str`, `note: str`, `trait: str`, `triggered_by: list[str]`.
  - `BuildAdvice(BaseModel)` — `has_build: bool`, `hero: str | None`, `hero_display: str | None`, `next_core: CoreItem | None`, `core: list[CoreItem]`, `skill_next: str | None`, `talent_next: str | None`, `situational: list[SituationalItem]`.
  - `advise(ctx: AdviceContext) -> BuildAdvice`.
- Extends `AdviceContext` with: `enemy_heroes: list[str] = field(default_factory=list)`, `build_db: dict = field(default_factory=dict)`, `trait_db: dict = field(default_factory=dict)`, `item_names: dict = field(default_factory=dict)`, `hero_names: dict = field(default_factory=dict)`.

- [ ] **Step 1: Extend the context**

Replace `engine/app/advisors/context.py` with:
```python
from dataclasses import dataclass, field
from app.state import GameState


@dataclass
class AdviceContext:
    state: GameState
    horizon_s: int = 600
    limit: int = 6
    enemy_heroes: list[str] = field(default_factory=list)
    build_db: dict = field(default_factory=dict)
    trait_db: dict = field(default_factory=dict)
    item_names: dict = field(default_factory=dict)
    hero_names: dict = field(default_factory=dict)
```

- [ ] **Step 2: Write the failing tests**

`engine/tests/test_build_coach.py`:
```python
from app.state import GameState, HeroState
from app.advisors.context import AdviceContext
from app.advisors import build_coach
from app.build_data import HeroBuild


def _build():
    return HeroBuild(
        hero="npc_dota_hero_skeleton_king", display="Wraith King", source="t", verified=False,
        skill_order="Max Q", talents={"10": "a", "15": "b", "20": "c", "25": "d"},
        starting_items=["item_tango"],
        core_items=["item_power_treads", "item_armlet", "item_radiance"],
        situational=[
            {"item": "item_black_king_bar", "trait": "heavy_magic", "note": "vs magic"},
            {"item": "item_monkey_king_bar", "trait": "evasion", "note": "vs evasion"},
        ],
    )


def _ctx(items, level=15, enemies=None):
    state = GameState(items=items)
    state.hero = HeroState(name="npc_dota_hero_skeleton_king", level=level)
    return AdviceContext(
        state=state, enemy_heroes=enemies or [],
        build_db={"npc_dota_hero_skeleton_king": _build()},
        trait_db={"npc_dota_hero_zuus": ["heavy_magic"]},
        item_names={"item_power_treads": "Power Treads", "item_armlet": "Armlet",
                    "item_radiance": "Radiance", "item_black_king_bar": "Black King Bar",
                    "item_monkey_king_bar": "Monkey King Bar"},
        hero_names={"npc_dota_hero_zuus": "Zeus"},
    )


def test_no_build_for_unknown_hero():
    ctx = _ctx([])
    ctx.state.hero.name = "npc_dota_hero_unknown"
    adv = build_coach.advise(ctx)
    assert adv.has_build is False


def test_next_core_is_first_unowned():
    adv = build_coach.advise(_ctx(items=["item_power_treads"]))
    assert adv.has_build is True
    assert adv.next_core.item == "item_armlet"
    assert [c.owned for c in adv.core] == [True, False, False]


def test_situational_triggered_by_enemy_trait():
    adv = build_coach.advise(_ctx(items=[], enemies=["npc_dota_hero_zuus"]))
    bkb = next(s for s in adv.situational if s.item == "item_black_king_bar")
    mkb = next(s for s in adv.situational if s.item == "item_monkey_king_bar")
    assert bkb.triggered_by == ["Zeus"]      # Zeus = heavy_magic
    assert mkb.triggered_by == []            # no evasion enemy
    # triggered items sort ahead of untriggered
    assert adv.situational[0].item == "item_black_king_bar"


def test_talent_for_current_level():
    adv = build_coach.advise(_ctx(items=[], level=15))
    assert adv.talent_next == "L15: b"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd engine && .venv/bin/python -m pytest tests/test_build_coach.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.advisors.build_coach'`.

- [ ] **Step 4: Implement the advisor**

`engine/app/advisors/build_coach.py`:
```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd engine && .venv/bin/python -m pytest tests/test_build_coach.py -v`
Expected: PASS (4 passed).

- [ ] **Step 6: Commit**

```bash
cd /home/tahseen-dar/Projects/dota2-live-helper
git add engine/app/advisors/build_coach.py engine/app/advisors/context.py engine/tests/test_build_coach.py
git commit -m "feat(engine): build_coach advisor (next item, skill/talent, situational)"
```

---

### Task 4: Wire build_coach into the aggregator + `/enemies` and `/heroes` endpoints

**Files:**
- Modify: `engine/app/state.py` (add `enemy_heroes`)
- Modify: `engine/app/advice.py` (add `build` field; load data; call build_coach)
- Modify: `engine/app/main.py` (POST `/enemies`, GET `/heroes`)
- Test: `engine/tests/test_enemies_endpoint.py`

**Interfaces:**
- Consumes: `build_coach.advise`/`BuildAdvice`, `load_build_data`, the extended `AdviceContext`.
- Produces:
  - `GameState.enemy_heroes: list[str]` (default empty; NOT overwritten by `update_from_raw`).
  - `AdvicePayload.build: BuildAdvice | None`.
  - `POST /enemies` body `{"heroes": [...]}` → sets `STATE.enemy_heroes`, rebuilds advice, broadcasts; returns `{"ok": True, "count": N}`.
  - `GET /heroes` → `list[{key, display}]` from the loaded data.

- [ ] **Step 1: Add `enemy_heroes` to GameState**

In `engine/app/state.py`, add the field to `GameState` (after `items`):
```python
    items: list[str] = Field(default_factory=list)
    enemy_heroes: list[str] = Field(default_factory=list)
    raw: dict = Field(default_factory=dict)
```
`update_from_raw` is unchanged — it never touches `enemy_heroes`, so the lineup persists across GSI updates. (Verify by reading: the method only assigns `clock_time`, `map`, `hero`, `player`, `items`, `raw`.)

- [ ] **Step 2: Wire build_coach into `build_advice`**

Replace `engine/app/advice.py` with:
```python
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
```

- [ ] **Step 3: Write the failing endpoint test**

`engine/tests/test_enemies_endpoint.py`:
```python
import json
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app, STATE

FIX = Path(__file__).parent / "fixtures" / "gsi_early_game.json"


def setup_function():
    STATE.enemy_heroes = []


def test_heroes_endpoint_lists_heroes():
    client = TestClient(app)
    resp = client.get("/heroes")
    assert resp.status_code == 200
    heroes = resp.json()
    assert any(h["key"] == "npc_dota_hero_zuus" and h["display"] == "Zeus" for h in heroes)


def test_enemies_then_gsi_yields_build_with_triggered_situational():
    client = TestClient(app)
    # Sniper fixture hero has no curated build -> set hero to Wraith King via a tweaked payload
    raw = json.loads(FIX.read_text())
    raw["hero"]["name"] = "npc_dota_hero_skeleton_king"
    raw["items"] = {"slot0": {"name": "item_power_treads"}}

    r1 = client.post("/enemies", json={"heroes": ["npc_dota_hero_zuus"]})
    assert r1.status_code == 200 and r1.json()["count"] == 1

    with client.websocket_connect("/ws") as ws:
        client.post("/gsi", json=raw)
        data = ws.receive_json()

    build = data["build"]
    assert build["has_build"] is True
    assert build["hero_display"] == "Wraith King"
    assert build["next_core"]["item"] == "item_armlet"  # treads owned -> next is armlet
    bkb = next(s for s in build["situational"] if s["item"] == "item_black_king_bar")
    assert bkb["triggered_by"] == ["Zeus"]
```

- [ ] **Step 4: Run test to verify it fails**

Run: `cd engine && .venv/bin/python -m pytest tests/test_enemies_endpoint.py -v`
Expected: FAIL — `/heroes` and `/enemies` return 404 (routes not defined yet).

- [ ] **Step 5: Add the endpoints to main.py**

In `engine/app/main.py`, add these two routes immediately AFTER the `/ws` handler and BEFORE the `if _DIST.exists():` static mount (the mount must remain last). Also import the loaded data at the top by adding `from app.advice import build_advice, BUILD_DATA` (replace the existing `from app.advice import build_advice`):
```python
@app.post("/enemies")
async def enemies(request: Request) -> dict:
    body = await request.json()
    STATE.enemy_heroes = list(body.get("heroes", []))
    await HUB.broadcast(build_advice(STATE).model_dump())
    return {"ok": True, "count": len(STATE.enemy_heroes)}


@app.get("/heroes")
async def heroes() -> list[dict]:
    return BUILD_DATA.heroes
```

- [ ] **Step 6: Run the focused test, then the full suite**

Run: `cd engine && .venv/bin/python -m pytest tests/test_enemies_endpoint.py -v`
Expected: PASS (2 passed).
Run: `cd engine && .venv/bin/python -m pytest tests -q`
Expected: PASS (all — existing 13 + advisor/build-data/build-coach/enemies tests).

- [ ] **Step 7: Commit**

```bash
cd /home/tahseen-dar/Projects/dota2-live-helper
git add engine/app/state.py engine/app/advice.py engine/app/main.py engine/tests/test_enemies_endpoint.py
git commit -m "feat(engine): build advice in payload + /enemies and /heroes endpoints"
```

---

### Task 5: Dashboard build panel + enemy picker

**Files:**
- Create: `dashboard/src/panels/build.js`
- Create: `dashboard/src/panels/enemies.js`
- Modify: `dashboard/index.html`, `dashboard/src/main.js`, `dashboard/src/style.css`

**Interfaces:**
- Consumes: WebSocket `AdvicePayload.build` (`{has_build, hero_display, next_core{item,display,owned}, core[], skill_next, talent_next, situational[]{item,display,note,trait,triggered_by[]}}`); `GET /heroes`; `POST /enemies`.
- Produces: a build panel and an enemy-entry bar rendered on the dashboard. The engine host base is derived as in P1 (`ENGINE_HOST`).

- [ ] **Step 1: Add panel markup to index.html**

In `dashboard/index.html`, inside `<main>`, add after the existing `#timings-panel` section:
```html
      <section id="enemies-panel" class="panel">
        <h2>Enemy lineup</h2>
        <div id="enemy-chips"></div>
        <input id="enemy-search" list="hero-list" placeholder="add enemy hero…" autocomplete="off" />
        <datalist id="hero-list"></datalist>
      </section>
      <section id="build-panel" class="panel">
        <h2>Build coach</h2>
        <div id="build-body"><em>waiting for game…</em></div>
      </section>
```

- [ ] **Step 2: Create the build panel renderer**

`dashboard/src/panels/build.js`:
```js
export function renderBuild(payload) {
  const el = document.getElementById("build-body");
  const b = payload.build;
  if (!b) {
    el.innerHTML = "<em>waiting for game…</em>";
    return;
  }
  if (!b.has_build) {
    el.innerHTML = `<em>No curated build for ${b.hero || "this hero"} yet — timings still active.</em>`;
    return;
  }
  const core = b.core
    .map((c) => `<span class="core ${c.owned ? "owned" : ""}">${c.owned ? "✓" : "•"} ${c.display}</span>`)
    .join(" ");
  const sit = b.situational
    .map((s) => {
      const on = s.triggered_by.length > 0;
      const who = on ? ` ← ${s.triggered_by.join(", ")}` : "";
      return `<li class="sit ${on ? "on" : ""}">${on ? "⚠ " : "· "}${s.display}<span class="why">${who} (${s.note})</span></li>`;
    })
    .join("");
  el.innerHTML = `
    <div class="hero">${b.hero_display}</div>
    <div class="next">NEXT: <strong>${b.next_core ? b.next_core.display : "build complete"}</strong></div>
    <div class="coreline">${core}</div>
    <div class="skill">Skill: ${b.skill_next || ""}</div>
    <div class="talent">Talent: ${b.talent_next || ""}</div>
    <ul class="situational">${sit}</ul>`;
}
```

- [ ] **Step 3: Create the enemy picker**

`dashboard/src/panels/enemies.js`:
```js
// Enemy picker: loads the hero list, lets the user add/remove enemies,
// and POSTs the current lineup to the engine.
export function initEnemies(engineHost) {
  const base = `http://${engineHost}`;
  const chips = document.getElementById("enemy-chips");
  const search = document.getElementById("enemy-search");
  const datalist = document.getElementById("hero-list");
  let heroes = [];
  let selected = [];

  const displayToKey = () => Object.fromEntries(heroes.map((h) => [h.display, h.key]));
  const keyToDisplay = () => Object.fromEntries(heroes.map((h) => [h.key, h.display]));

  function render() {
    const names = keyToDisplay();
    chips.innerHTML = selected
      .map((k) => `<span class="chip" data-key="${k}">${names[k] || k} ✕</span>`)
      .join("");
    chips.querySelectorAll(".chip").forEach((c) =>
      c.addEventListener("click", () => {
        selected = selected.filter((k) => k !== c.dataset.key);
        push();
        render();
      })
    );
  }

  async function push() {
    await fetch(`${base}/enemies`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ heroes: selected }),
    });
  }

  search.addEventListener("change", () => {
    const key = displayToKey()[search.value];
    if (key && !selected.includes(key)) {
      selected.push(key);
      push();
      render();
    }
    search.value = "";
  });

  fetch(`${base}/heroes`)
    .then((r) => r.json())
    .then((list) => {
      heroes = list;
      datalist.innerHTML = list.map((h) => `<option value="${h.display}"></option>`).join("");
    });
}
```

- [ ] **Step 4: Wire the panels into main.js**

Replace `dashboard/src/main.js` with:
```js
import { connect } from "./ws.js";
import { renderTimings, renderClock } from "./panels/timings.js";
import { renderBuild } from "./panels/build.js";
import { initEnemies } from "./panels/enemies.js";

// Single-process: the engine serves this page, so the WS shares its host:port.
// Vite dev mode (port 5173) is the exception — the engine runs separately on :3000.
const ENGINE_HOST = location.port === "5173" ? `${location.hostname}:3000` : location.host;
const WS_URL = `ws://${ENGINE_HOST}/ws`;
const statusEl = document.getElementById("status");

function onStatus(up) {
  statusEl.textContent = up ? "connected" : "disconnected";
  statusEl.className = `status ${up ? "on" : "off"}`;
}

function onMessage(payload) {
  renderClock(payload);
  renderTimings(payload);
  renderBuild(payload);
}

initEnemies(ENGINE_HOST);
connect(WS_URL, onMessage, onStatus);
```

- [ ] **Step 5: Add styles**

Append to `dashboard/src/style.css`:
```css
#enemy-chips { display: flex; flex-wrap: wrap; gap: .3rem; margin-bottom: .4rem; }
.chip { background: #3a2330; color: #ffb3c8; padding: .15rem .5rem; border-radius: 999px; cursor: pointer; font-size: .85rem; }
#enemy-search { width: 100%; box-sizing: border-box; background: #0b0d11; color: #e6e6e6; border: 1px solid #20242c; border-radius: 6px; padding: .4rem; }
#build-panel .hero { font-weight: 600; margin-bottom: .2rem; }
#build-panel .next { font-size: 1.15rem; margin: .2rem 0; }
#build-panel .next strong { color: #9ee7a0; }
.coreline { display: flex; flex-wrap: wrap; gap: .35rem; margin: .3rem 0; }
.core { padding: .1rem .4rem; border-radius: 6px; background: #20242c; font-size: .85rem; }
.core.owned { color: #6ee787; }
#build-panel .skill, #build-panel .talent { font-size: .85rem; color: #b8c0cc; }
ul.situational { list-style: none; margin: .4rem 0 0; padding: 0; }
.sit { padding: .2rem 0; color: #6b7280; }
.sit.on { color: #ffd479; }
.sit .why { color: #8a93a0; font-size: .8rem; }
```

- [ ] **Step 6: Build the dashboard (headless verification)**

Run: `cd dashboard && npm run build`
Expected: build succeeds, no errors. (The in-browser visual smoke — open the page, add an enemy, watch the build panel — is deferred to the user; you have no browser.)

- [ ] **Step 7: Commit**

```bash
cd /home/tahseen-dar/Projects/dota2-live-helper
git add dashboard
git commit -m "feat(dashboard): build coach panel + enemy picker"
```

---

## Self-Review

- **Spec coverage:** module-registry refactor (Task 1, spec §3) ✓; curated JSON builds for all ~11 climbers + traits + item names + loader/validation (Task 2, spec §4/§7) ✓; `build_coach` logic incl. next-core, ownership match, talent-by-level, situational triggering (Task 3, spec §5) ✓; `GameState.enemy_heroes` + `POST /enemies` + `GET /heroes` + payload `build` field (Task 4, spec §3/§6) ✓; dashboard build panel + enemy picker, text chips (Task 5, spec §6) ✓; VAC-safe (no game-process access); honest notes (verified flags, partial trait map) carried in data. Live OpenDota deliberately out of scope (spec §1 non-goal).
- **Placeholder scan:** no TBD/TODO; every code step is complete. Task 2 Step 5 authors data with a concrete per-hero source table + exact schema + the validation test as the gate — content, not a code placeholder.
- **Type consistency:** `AdviceContext` (extended in Task 3 used in Task 4), `BuildAdvice`/`CoreItem`/`SituationalItem`, `HeroBuild`/`Situational`/`BuildData`, `load_build_data`, `BUILD_DATA`, and the dashboard's consumption of `payload.build.*` field names all match across tasks. `build_advice(state)` keeps its signature so `main.py`'s existing `/gsi` call is unaffected.
```
