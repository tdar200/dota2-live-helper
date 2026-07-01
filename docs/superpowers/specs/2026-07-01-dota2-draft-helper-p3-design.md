# Dota 2 Live Helper — P3 Draft Helper Design Spec

**Date:** 2026-07-01
**Patch context:** 7.41d
**Status:** Design — awaiting user review before implementation planning
**Builds on:** P0+P1 (timings) and P2 (build coach), both merged to `master`.

## 1. Goal

Add the **draft helper** pillar: at hero-select, rank the player's pocket heroes against the
entered enemy lineup and factor allied picks, so the player picks the hero best positioned to
win — using real Herald-bracket counter (`vs`) and synergy (`with`) win rates from Stratz.

### Non-goals
- Not a full any-hero drafting AI; it ranks the player's *pocket heroes* (those with builds).
- The engine never calls Stratz; only an offline refresh script does. Engine stays keyless.
- Still VAC-safe: GSI + the user's manual enemy/ally entry + cached public stats only.

## 2. Decisions (from brainstorming)

- **Data source:** Stratz (GraphQL) for BOTH counter (`vs`) and synergy (`with`) win rates,
  Herald-bracket-specific. Requires a free Stratz API key (one-time user setup).
- **Scope:** rank pocket heroes vs the enemy lineup, factoring ally synergy.
- **Keyless offline engine:** a refresh script fetches Stratz data into a local JSON cache; the
  engine and draft advisor read the cache only, never the network (tests stay offline; a draft
  never blocks on an API call).
- **Graceful degradation:** if the cache is missing, rank by base win rate only with a
  "run refresh" note.

## 3. Architecture & data flow

```
  scripts/refresh_matchups.py ──Stratz GraphQL (STRATZ_API_KEY)──► engine/app/cache/matchups.json (gitignored)
       (run occasionally / per patch)                                  │ Herald vs + with + base winrate, keyed by hero key
                                                                       ▼
  Dashboard ─POST /enemies─►┐        engine/app/matchups.py: load_matchups() (offline, at import)
  Dashboard ─POST /allies──►┤► GameState {hero, items, enemy_heroes, ally_heroes}
  Dota ─GSI─► /gsi ─────────┘                     │
                              advisor registry: timings + build_coach + draft
                                                   │
  Dashboard ◄─WS─ AdvicePayload {clock_time, timings[], build{}, draft{}}
  GET /heroes ─► hero list for both pickers
```

- The **refresh script** is the only Stratz client; the **Stratz key lives only in its
  environment** (`STRATZ_API_KEY`). The engine is keyless.
- **`matchups.py`** loads the cache at import (offline); the **`draft` advisor** ranks pocket
  heroes from it. Registry pattern from P2 extends naturally (add `draft`).
- **`POST /allies`** mirrors the existing `/enemies`; adds `GameState.ally_heroes`.

## 4. Cache schema, Stratz query, hero-id mapping

### 4.1 `engine/app/cache/matchups.json` (gitignored, key-keyed)
```json
{
  "bracket": "HERALD",
  "generated": "2026-07-01",
  "heroes": {
    "npc_dota_hero_skeleton_king": {
      "base_winrate": 0.561,
      "vs":   { "npc_dota_hero_zuus": 0.58, "npc_dota_hero_phantom_assassin": 0.47 },
      "with": { "npc_dota_hero_lion": 0.55 }
    }
  }
}
```

### 4.2 Stratz query
For each pocket hero, query `heroStats.matchUp` filtered to the Herald bracket, taking `vs`
(counter) and `with` (synergy) win rates plus the hero's base Herald win rate. The **exact
GraphQL field names and bracket enum must be verified against the live schema**
(`https://api.stratz.com/graphiql`) during implementation. The response→cache transform is a
**pure function** fed a saved sample response and unit-tested; the network wrapper is thin.

### 4.3 Hero-id mapping
Stratz keys by numeric `hero_id`; the pickers use string keys. `engine/app/data/heroes.json`
is regenerated to also include `id` (from dotaconstants). The refresh script converts ids →
keys before writing, so the cache and advisor are key-only. Adding `id` is additive; the P2
`test_build_data` assertions (which use `key`/`display`) are unaffected.

## 5. The `draft` advisor

`draft.advise(ctx) -> DraftAdvice`, pure, offline, unit-tested. Candidates = pocket hero keys
(keys of the build DB).

For each candidate, from cache + entered enemies/allies:
- **base** = Herald base win rate.
- **counter** = mean of `vs[enemy]` over entered enemies.
- **synergy** = mean of `with[ally]` over entered allies.
- **score** = `base + (counter - 0.5) + (synergy - 0.5)` (documented weighting; win rates as
  fractions). Enemies/allies absent from the cache contribute nothing (safe).
- **reasons** = top contributors, e.g. `"strong vs Zeus (58%)"`, `"synergy w/ Lion (55%)"`,
  `"weak vs PA (47%)"`.
- **countered** = true if any `vs[enemy] < 0.47`.

Candidates ranked by score desc.

### `DraftAdvice` (Pydantic)
- `has_data: bool` (cache present)
- `bracket: str | None`
- `note: str | None` (e.g. the "run refresh" hint when `has_data` is false)
- `picks: list[DraftPick]` where `DraftPick` = `hero`, `display`, `score`, `base_winrate`,
  `counter`, `synergy`, `reasons: list[str]`, `countered: bool`.

**Graceful degradation:** cache absent → `has_data=false`, rank by `base_winrate` only using a
small seed of KB Herald win rates, with the run-refresh `note`.

## 6. Dashboard (draft panel + ally picker)

- **Ally picker:** a second chip bar mirroring the enemy picker, posting to `POST /allies`;
  both reuse `GET /heroes`.
- **Draft panel:** ranked pocket heroes — score, a ✓ best-pick highlight on top, per-hero
  reasons, and a ⚠ countered badge. Text/chips (consistent with P2). Renders from
  `payload.draft` each update.

## 7. Testing

- **Refresh transform test:** feed a saved sample Stratz response to the pure transform →
  assert the cache structure. No live network in tests.
- **Draft advisor unit tests:** ranking order, counter/synergy averaging, countered flag,
  degradation when cache absent (synthetic cache).
- **Endpoint tests:** `POST /allies` sets `ally_heroes`; `draft` present in `AdvicePayload`.

## 8. Internal build order

1. Regenerate `heroes.json` with `id`; add `matchups.py` loader + cache-dir scaffold + a
   graceful "no cache" path.
2. `scripts/refresh_matchups.py` (Stratz client + pure transform) + transform test + README
   setup for the API key.
3. `draft` advisor + unit tests.
4. `GameState.ally_heroes` + `POST /allies` + wire `draft` into the aggregator + `AdvicePayload.draft`.
5. Dashboard draft panel + ally picker.

## 9. Honest notes / open items

- **Stratz API key** is a one-time user setup (register at stratz.com, set `STRATZ_API_KEY`);
  documented in the README. The engine works offline without it (degraded draft).
- The **cache is gitignored** — the user runs the refresh once and per patch.
- The exact **Stratz GraphQL schema** (field names, bracket enum) is verified during
  implementation against the live GraphiQL; the transform is isolated and unit-tested so a
  schema tweak is a one-function change.
- The 5 `verified:false` builds don't affect the draft helper (draft uses Stratz data; it only
  uses the build set to define the *pocket* candidate list).
