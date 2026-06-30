# Dota 2 Live Helper — P2 Build Coach Design Spec

**Date:** 2026-07-01
**Patch context:** 7.41d
**Status:** Design — awaiting user review before implementation planning
**Builds on:** P0+P1 (backbone + timings), shipped to `master`.

## 1. Goal

Add the **build coach** pillar: a live, second-monitor panel that tells the player what to
build next — the next core item, skill/talent to take, and which situational items to buy
against the actual enemy lineup — to help climb out of Herald. Recommendations come from
**curated structured builds** distilled from the user's `dota2-knowledge-base`, with an
**enemy-aware situational layer**.

### Non-goals
- No live OpenDota/Stratz calls in P2 (curated data only; the aggregate route was considered
  and deferred).
- No hero image assets in v1 (text chips for the enemy picker).
- Still VAC-safe: GSI + the user's manual enemy entry only; no game-process access.

## 2. Decisions (from brainstorming)

- **Build data source:** curated structured builds (not OpenDota aggregate, not hybrid).
- **Enemy layer:** included in P2 — enemy quick-entry UI + hero→trait mapping + auto-selection
  of situational items.
- **Hero coverage:** all Herald climbers from `herald-climbing-heroes.md` (~11). Heroes with a
  detailed KB guide are high-fidelity; the rest (Necrophos, Bristleback, Juggernaut) are
  authored from general knowledge, flagged `verified:false`, verify in-client.
- **Aggregator:** refactor `build_advice` into a module registry before adding the second
  pillar (per the P0+P1 final-review recommendation).

## 3. Architecture & data flow

P2 introduces a **dashboard → engine inbound channel** (P0+P1 was one-way Dota→engine→dashboard).

```
  Dota ──GSI POST──► /gsi ─┐
                            ├─► GameState {hero, items, level, enemy_heroes}
  Dashboard ─POST /enemies─┘            │
  (enemy picker)                        ▼
                       module registry: timings.advise() + build_coach.advise()
                                         │
  Dashboard ◄──WebSocket── AdvicePayload {clock_time, connected, timings[], build{...}}
  GET /heroes ──► hero list (key + display) for the enemy picker
```

- **`POST /enemies`** `{"heroes": ["npc_dota_hero_lina", ...]}` → sets `GameState.enemy_heroes`
  → recompute advice → broadcast. Symmetric with `/gsi`.
- **`GET /heroes`** → `[{key, display}]` so the picker is engine-authoritative.
- Curated data is editable JSON under `engine/app/data/` — isolated from logic.

### Module registry
`build_advice` becomes a thin aggregator over a list of modules. Each module exposes
`advise(context) -> dict`, where `context` carries the `GameState`, the enemy list, and the
loaded data sets. `AdvicePayload` gains a `build` field alongside `timings`. `timings` keeps
working unchanged (its logic moves behind a `timings.advise(context)` wrapper around the
existing `next_occurrences` + `GAME_EVENTS`).

## 4. Data model (`engine/app/data/`)

### 4.1 `builds/<hero_key>.json` (one per covered hero)
```json
{
  "hero": "npc_dota_hero_wraith_king",
  "display": "Wraith King",
  "source": "KB herald-climbing-heroes.md",
  "verified": false,
  "skill_order": "Max Wraithfire Blast (Q); value Vampiric Spirit; Reincarnation 6/12/18",
  "talents": { "10": "...", "15": "...", "20": "...", "25": "..." },
  "starting_items": ["item_tango", "item_quelling_blade", "item_gauntlets"],
  "core_items": ["item_power_treads", "item_armlet", "item_radiance", "item_assault", "item_abyssal"],
  "situational": [
    { "item": "item_black_king_bar", "trait": "heavy_magic", "note": "vs heavy magic burst" },
    { "item": "item_monkey_king_bar", "trait": "evasion", "note": "vs evasion" }
  ]
}
```

### 4.2 `hero_traits.json` — `enemy_hero_key → [trait]`, from a fixed taxonomy
| trait | counters with | example enemies |
|---|---|---|
| `heavy_magic` | BKB | Zeus, Lina, Lion |
| `evasion` | MKB | Phantom Assassin, Windranger |
| `illusions_summons` | Mjollnir / cleave | Naga Siren, Broodmother |
| `invisibility` | detection (Sentry/Dust/Gem) | Riki, Bounty Hunter |
| `high_armor` | armor reduction (Desolator) | Bristleback, Timbersaw |
| `healing_regen` | Spirit Vessel / break | Necrophos, Huskar |
| `lockdown_silence` | BKB / Lotus Orb / Manta | Shadow Shaman, Silencer |
| `tanky_hp` | %-damage / Nullifier | Pudge, Centaur |

The taxonomy is a fixed enum (the 8 above). Unmapped enemies trigger no situationals (safe
degradation). The map covers common Herald enemies, not every hero.

### 4.3 `item_names.json` — `item_key → display` for referenced items
Vendored so the engine is self-contained (no runtime dependency on the KB repo).

### 4.4 Validation
A test asserts: every build parses; every `situational.trait` ∈ taxonomy; every referenced
item key (core/starting/situational) has an entry in `item_names.json`.

## 5. The `build_coach` module

`build_coach.advise(state, enemy_heroes, build_db, trait_db) -> BuildAdvice`, pure, unit-tested.

- **`has_build`** — false when the hero isn't covered → panel shows timings-only note.
- **`next_core`** — first `core_items` entry not in `state.items` (exact-key set membership;
  GSI item names are exact keys like `item_power_treads`).
- **`core_progress`** — full core order, each flagged owned/not.
- **`skill_next` / `talents`** — from the build; talent selected for `state.hero.level` bracket.
- **`situational_active`** — union the traits of all entered enemies; surface each `situational`
  whose trait is present, annotated with the triggering enemy display names. Non-triggered
  situationals returned as a dim "menu" list.

`BuildAdvice` is a Pydantic model; `build_coach` imports only state + the data types (no HTTP/DOM).

## 6. Dashboard (build panel + enemy picker)

Text chips, no image assets in v1.
- **Enemy-entry bar:** searchable picker populated from `GET /heroes`; selecting/removing
  updates a local list and `POST /enemies`. The list persists across the match and survives a
  reload by re-fetching the engine's stored list.
- **Build panel:** re-renders from `payload.build` each tick — `next_core` prominent; core order
  with ✓ (owned) / ⮕ (next) markers; `skill_next` + current-level talent; `situational_active`
  highlighted with triggering enemies; unmatched situationals dimmed. When `has_build` is false,
  shows "No curated build for <hero> yet — timings still active."

## 7. Testing

- **Data validation:** all builds valid, traits in taxonomy, items have display names.
- **`build_coach` unit tests:** next-core detection, ownership matching, situational triggering
  by enemy traits — pure, synthetic `build_db`/`trait_db` fixtures.
- **Registry test:** aggregator merges `timings` + `build` into one payload; `timings` output
  unchanged from P1.
- **Endpoint tests:** `POST /enemies` then `POST /gsi` → broadcast `AdvicePayload.build` shows
  the correct `next_core` + triggered situationals; `GET /heroes` returns the list.

## 8. Internal build order

1. Refactor aggregator into module registry (timings behind `timings.advise`; payload gains
   `build` placeholder). Tests stay green.
2. Data files (builds for all ~11 climbers, `hero_traits.json`, `item_names.json`) + loader +
   validation test.
3. `build_coach.advise` module + unit tests.
4. `POST /enemies` + `GET /heroes` endpoints + `GameState.enemy_heroes`; wire `build_coach` into
   the registry.
5. Dashboard build panel + enemy picker.

Each step ends with a working, tested increment.

## 9. Honest notes / open items

- The 3 non-KB heroes' builds are lower-fidelity (`verified:false`); verify in-client.
- The trait map is a curated starting set; expanding hero coverage is a data-only edit.
- Item display names are vendored for referenced items only; adding heroes may require adding
  names.
- Exact current-patch item keys (e.g. `item_power_treads`) should be confirmed against the KB
  `raw-data/items.json` / in-client during authoring.
