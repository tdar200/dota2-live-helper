# All-Hero Live Item Builds + Live Farm Benchmarking — FINAL Spec & Plan

Reconciliation note: this supersedes the draft design. All MUST-FIX items from the three critiques are applied; the two YAGNI cuts (vendored id-map + speculative GSI fields) are accepted; the "Dota Plus parity" claim for farm is downgraded to "Dota-Plus-style, un-bracketed" and moved into Honest Gaps. Rejections are listed at the end of Part A with reasons.

---

# PART A — SPEC

## Goal
Close the "nothing like Dota Plus" gap for the ~116 heroes outside the curated 11:
1. **Live item build** for *any* hero — per-phase popular items (start/early/mid/late) with owned ticks and a single "NEXT" suggestion, sourced from OpenDota `itemPopularity`.
2. **Live farm benchmark** — map the player's live GSI GPM/XPM/LH-per-min onto OpenDota per-hero percentile curves ("your GPM is 60th pct for this hero").

Both must be keyless, offline at runtime, VAC-safe, and degrade to today's behaviour on a fresh clone.

## Non-goals (out of scope for v1)
- Skill/ability build order for non-curated heroes (no keyless aggregate source — see Honest Gaps).
- Ward suggestions, death summary, lane assignment (no keyless realtime source; VAC boundary).
- Bracket-filtered (Herald-scoped) benchmarks/meta — OpenDota exposes neither. See Honest Gaps.
- Curated-hero OpenDota supplement (second source of truth for the 11) — deferred, YAGNI (all 3 critiques agree).

## Architecture (keyless / offline / VAC-safe) — unchanged pattern from `matchups.py`
- **Network lives only in `scripts/refresh_item_builds.py`** (urllib, throttle, writes JSON to `engine/app/cache/`). Sole caller of OpenDota for this feature. Mirrors `refresh_matchups.py`.
- **Engine reads a pre-baked cache once at import.** New `engine/app/item_builds.py` mirrors `matchups.py`: `load_item_builds()` → Pydantic `ItemBuildData(has_data=...)`, degrading to `has_data=False, heroes={}` when the cache is absent.
- **Advisors stay pure.** `build_coach.advise` gains a fallback branch; new `farm.advise` maps rates → percentiles. Both take only `AdviceContext`, return Pydantic, no I/O.
- **No `main.py` change.** `main.py` already does `build_advice(STATE).model_dump()` over WS/HTTP; new optional payload fields ride along. The two POST endpoints (`/networth`, `/roshan`) re-broadcast and pick up the new fields for free.
- **Runtime is offline; refresh is the only networked step.** After a refresh the engine must be restarted (cache loads once at import) — same operational note as matchups.

### Id → display resolution (REJECTED the vendored map — see below)
Resolved **at refresh time only**, fully self-contained, no `../dota2-knowledge-base` sibling dependency and no committed 500-entry file:
- `GET /api/constants/item_ids` → `{ "<numeric_id>": "<short_name>" }`
- `GET /api/constants/items` → `{ "<short_name>": {dname, qual, cost, ...} }`

`numeric_id → short_name → {dname, qual}`. Cache `key = "item_" + short_name` (GSI slot names are `item_`-prefixed — confirmed in `gsi.py`), `display = dname`. Display names are pre-baked into the cache, so **the engine never needs any id map at all**.

## Cache schema — `engine/app/cache/item_builds.json` (gitignored)
Keyed by GSI `hero.name` (`npc_dota_hero_*`) for direct engine lookup.

```json
{
  "generated_at": "2026-06-30T12:00:00Z",
  "source": "opendota",
  "note": "un-bracketed all-MMR aggregate",
  "heroes": {
    "npc_dota_hero_juggernaut": {
      "hero_id": 8,
      "display": "Juggernaut",
      "builds": {
        "start_game": [{"id": 44,  "key": "item_quelling_blade", "display": "Quelling Blade", "count": 41233}],
        "early_game": [{"id": 63,  "key": "item_power_treads",   "display": "Power Treads",   "count": 38771}],
        "mid_game":   [{"id": 152, "key": "item_bfury",          "display": "Battle Fury",    "count": 29344}],
        "late_game":  [{"id": 116, "key": "item_manta",          "display": "Manta Style",    "count": 21002}]
      },
      "benchmarks": {
        "percentiles":       [0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9,0.95,0.99],
        "gold_per_min":      [312,378,431,479,527,578,634,701,792,861,988],
        "xp_per_min":        [402,468,521,569,617,668,724,791,882,951,1078],
        "last_hits_per_min": [3.1,4.0,4.7,5.3,5.9,6.5,7.2,8.0,9.1,9.9,11.4]
      }
    }
  }
}
```

Notes baked in at refresh time (all MUST-FIX from critiques):
- **Phase-key translation** (C1 #3): OpenDota returns `start_game_items / early_game_items / mid_game_items / late_game_items`. Refresh maps `<phase>_items → <phase>`.
- **Null-dname skip** (C1 #4): recipes/tokens have `dname: null`; skip on `dname is None`, not just missing id — otherwise `PhaseItem.display: str` validation fails and the whole cache degrades.
- **Mandatory noise filter** (C1/C2/C3, promoted from optional): drop items whose `qual ∈ {"component", "consumable"}` and an explicit blocklist of ward/stat tokens (`ward_observer, ward_sentry, tpscroll, dust, smoke_of_deceit, tango, clarity, flask, enchanted_mango, faerie_fire, branches, ...`). This removes both components (Broadsword/Yasha) and consumables (tango/branch/clarity) so `suggested_next` and chips show finished items only.
- **Cross-phase dedup** (C2): iterate phases start→late with a global seen-set; keep an item only in the earliest phase it appears (so `power_treads` shows once). 
- **Cap** (C3): store **top 8** per phase after filter+dedup, sorted desc by count. Dashboard renders ≤4 per phase to stay scroll-free.
- **Benchmarks lean** (C2 YAGNI): store `percentiles`, `gold_per_min`, `xp_per_min`, `last_hits_per_min` only. `hero_damage_per_min` dropped (nothing reads it).
- **Iterate the 127 real ids from `heroes.json`** (non-contiguous — never `range(1,128)`), skip+log unresolved ids, throttle **~1.1 s + jitter** (C2 — 1.0 s hits the 60/min ceiling exactly), backoff on HTTP 429 **and** Cloudflare 521.

Engine Pydantic mirror (`item_builds.py`):
```python
class PhaseItem(BaseModel):
    id: int; key: str; display: str; count: int
class Benchmarks(BaseModel):
    percentiles: list[float] = []
    gold_per_min: list[float] = []
    xp_per_min: list[float] = []
    last_hits_per_min: list[float] = []
class HeroItemBuild(BaseModel):
    hero_id: int; display: str
    builds: dict[str, list[PhaseItem]] = Field(default_factory=dict)
    benchmarks: Benchmarks = Field(default_factory=Benchmarks)
class ItemBuildData(BaseModel):
    has_data: bool
    heroes: dict[str, HeroItemBuild] = Field(default_factory=dict)
```
`load_item_builds()`: cache missing/unreadable → `ItemBuildData(has_data=False)`.

## Fallback-build logic (`build_coach.advise`)
Curated 11 untouched (richer `core`/`situational`/`skill_next`/`talent_next`). Change only the `build is None` branch: instead of `has_build=False`, try the OpenDota fallback.

`BuildAdvice` gains:
```python
source: str = "curated"          # "curated" | "opendota" | "none"
phases: dict[str, list[CoreItem]] = Field(default_factory=dict)  # opendota only
suggested_next: CoreItem | None = None
```

**Clock guard (C1 #1 — MUST-FIX, prevents a new crash on menu/replay frames where `clock_time is None`):**
```python
def _phase_for_clock(clock):
    if clock is None or clock < 0: return "start_game"
    if clock < 600:  return "early_game"
    if clock < 1500: return "mid_game"
    return "late_game"
```

Fallback branch:
```python
ib = ctx.item_build_db.get(hero)          # HeroItemBuild or None
if build is None:
    if ib is None:
        return BuildAdvice(has_build=False, source="none", hero=hero)
    owned = set(ctx.state.items)          # item_-prefixed GSI names; PhaseItem.key is item_<short> → direct diff
    order = ["start_game", "early_game", "mid_game", "late_game"]
    phases = {
        ph: [CoreItem(item=pi.key, display=pi.display, owned=pi.key in owned)
             for pi in ib.builds.get(ph, [])]
        for ph in order
    }
    cur = _phase_for_clock(ctx.state.clock_time)
    suggested = None
    for ph in order[order.index(cur):]:
        suggested = next((c for c in phases[ph] if not c.owned), None)
        if suggested: break
    return BuildAdvice(
        has_build=True, source="opendota", hero=hero,
        hero_display=ib.display, phases=phases, suggested_next=suggested,
    )
```
Because components/consumables are filtered at refresh, `suggested_next` never points at a recipe part (fixes the C1/C2/C3 "NEXT: Broadsword" bug). `suggested_next` may still be `None` when everything is owned — dashboard null-guards (C2 #3).

## Farm-percentile logic (`farm.py`)
Pure advisor. GSI `gpm`/`xpm` are per-minute running averages → map directly onto the ascending benchmark arrays. `last_hits` is cumulative → convert to a rate. **All three metrics gated on `clock_time >= 300`** (C2/C3 — mapping a 2-minute snapshot onto whole-game benchmarks reads falsely "behind"; gate GPM/XPM the same as LH).

```python
def _pct(value, pcts, vals):          # vals ascending
    if not vals or value is None: return None
    if value <= vals[0]:  return round(pcts[0]  * 100)
    if value >= vals[-1]: return round(pcts[-1] * 100)
    for i in range(1, len(vals)):
        if value <= vals[i]:
            lo_v, hi_v, lo_p, hi_p = vals[i-1], vals[i], pcts[i-1], pcts[i]
            frac = (value - lo_v) / (hi_v - lo_v) if hi_v > lo_v else 0
            return round((lo_p + frac * (hi_p - lo_p)) * 100)
    return round(pcts[-1] * 100)

def _band(p):
    if p < 30: return "behind"
    if p < 60: return "on track"
    if p < 85: return "ahead"
    return "dominating"

class FarmMetric(BaseModel):
    metric: str; value: float; percentile: int; label: str
class FarmAdvice(BaseModel):
    has_data: bool = False
    hero_display: str | None = None
    metrics: list[FarmMetric] = Field(default_factory=list)
    summary: str | None = None
```
`advise`:
```python
ib = ctx.item_build_db.get(hero)
clock = ctx.state.clock_time
if ib is None or clock is None or clock < 300:
    return FarmAdvice(has_data=False)
bm = ib.benchmarks
lh_rate = (ctx.state.last_hits / (clock / 60)) if ctx.state.last_hits is not None else None
metrics = []
for key, name, value in (("gold_per_min","GPM",ctx.state.gpm),
                         ("xp_per_min","XPM",ctx.state.xpm),
                         ("last_hits_per_min","LH/min",lh_rate)):
    pct = _pct(value, bm.percentiles, getattr(bm, key))
    if value is None or pct is None:         # C1 #2 MUST-FIX: skip, never build FarmMetric(percentile=None)
        continue
    metrics.append(FarmMetric(metric=name, value=round(value,1), percentile=pct, label=_band(pct)))
if not metrics:
    return FarmAdvice(has_data=False)
gpm_m = next((m for m in metrics if m.metric == "GPM"), None)
summary = (f"GPM {gpm_m.percentile}th pct vs all players of {ib.display} — {gpm_m.label}"
           if gpm_m else None)
return FarmAdvice(has_data=True, hero_display=ib.display, metrics=metrics, summary=summary)
```
`FarmMetric` is only ever constructed when both `value` and `pct` are non-None, so no Pydantic `ValidationError` on a hero with empty benchmark arrays (C1 #2). Summary is guarded when GPM is absent.

## AdvicePayload additions (`advice.py`)
- Module load: `ITEM_BUILDS = load_item_builds()`.
- `AdviceContext(..., item_build_db=ITEM_BUILDS.heroes)`.
- `AdvicePayload`: add `farm: FarmAdvice | None = None`; existing `build: BuildAdvice | None` now carries `source`/`phases`/`suggested_next`.
- `build_advice(...)`: `..., build=build_coach.advise(ctx), farm=farm_advisor.advise(ctx)`.
- `AdviceContext` gains `item_build_db: dict = field(default_factory=dict)` (empty default → advisors silently return `has_data=False`/`source="none"` if wiring is ever missed).

## Dashboard changes (no `grid-template-areas` edit — C3 blocker resolved without touching the HUD contract)
The live view is a fixed 3×3 CSS grid with `overflow:hidden`. Adding a 7th tile would overflow the viewport. **Fold the farm readout into the existing macro tile** (the "how am I doing" cell), which already owns performance feedback and has vertical room. This satisfies "visible without scrolling" with **no `grid-template-areas` change** — sidestepping the confirm-before-editing-`style.css`-layout rule. (If the macro tile proves too cramped in practice, a grid rework is the documented fallback and requires explicit user confirmation.)

- **`index.html`**: add `<div id="farm-body"></div>` **inside the existing macro `<section>`**, below the macro content. No new grid cell.
- **`farm.js`** (new): `renderFarm(payload)` writes into `#farm-body`. One row per metric: label + percentile bar (reuse macro's `win-fill` width idiom) + band word; plus `summary`. Hidden (`#farm-body` emptied) when `!payload.farm || !payload.farm.has_data`.
- **`build.js`**: branch on `b.source`.
  - `curated` → existing renderer unchanged.
  - `opendota` → compact single sequence with phase separators (start › early › mid › late), **≤4 chips per phase** to match curated `coreline` density and stay scroll-free (C3 #2); each chip reuses `.core.owned` styling; a `NEXT: …` line **null-guarded** like the curated `next_core` (`b.suggested_next ? b.suggested_next.display : "build complete"`) (C2 #3). Add "(vs all-bracket meta)" micro-label.
  - `none`/`!has_build` → keep today's "no build, timings still active" message (removes the Silencer wall).
- **`main.js`** (explicitly Modified — C3): import `renderFarm`; call it inside `onMessage` alongside `renderBuild`/`renderMacro`.
- **`style.css`**: add farm-bar class styles only (bar track/fill/label) — **not** `grid-template-areas`.

## Honest gaps (set expectations truthfully)
- **Un-bracketed benchmarks & meta (C1/C2/C3 — the headline honesty fix).** OpenDota `itemPopularity` and `/benchmarks` are **global all-MMR aggregates**; the rest of this app is deliberately Herald-scoped. A Herald player benchmarks against a ~Archon/Legend-skewed population and will read pessimistically; the item meta reflects higher-MMR play. This is *not* keyless-closable. UI says "vs all players of this hero"; farm is "Dota-Plus-**style**", not parity.
- **Ability/skill order** — no keyless per-hero aggregate ("popular skill build") endpoint. Curated 11 keep `skill_next`; the fallback build has **no** skill line. A future Stratz refresh-snapshot (key, cached offline like matchups) could add it — lower priority.
- **LH/min basis mismatch (soft).** Cumulative-so-far rate vs full-game-average benchmark; the `clock>=300` gate reduces but does not eliminate the skew. Labelled, not promised as exact.
- **Ward/death-summary/lane** — no keyless realtime source (GSI emits no map coords / per-instance damage; VAC boundary). Out of scope; timings + P4b review are the nearest analogs.

## Invariants (all verified against the code by critiques 1 & 2)
- Engine/tests never touch network — network confined to `scripts/`; tests use fixtures. ✔
- Caches gitignored + loaded once at import → restart-after-refresh required. ✔
- Advisors pure (only `AdviceContext` in, Pydantic out). ✔
- VAC-safe — all GSI fields (lh/gpm/xpm/clock) are the player's own HUD; OpenDota is public aggregate. ✔
- Graceful degradation — no cache → `has_data=False` → build shows "no build" message, farm panel hidden → fresh clone boots working. ✔

## Rejected critique items (with reason)
- **Vendored `item_id_map.json` + `build_item_id_map.py` (original design) — REJECTED / removed** per C2 #5. Refresh is already networked (254 calls); two extra keyless `GET /api/constants/*` calls resolve display names inline. Removes a committed ~500-entry file and a dual-path generator. Engine never needed the map (displays are pre-baked into the cache).
- **`denies/kills/deaths/assists` on `PlayerState` — REJECTED** per C2 #6 / C3. Nothing reads them in v1. Only `last_hits` is added. Add the rest when a KDA readout ships.
- **`hero_damage_per_min` in cache — REJECTED** (YAGNI, unread).
- **Adding a 7th grid tile for farm — REJECTED** per C3 #1; fold into macro tile instead (no `grid-template-areas` edit, no scroll).
- **`grid-template-areas` rework in v1 — DEFERRED** (kept as documented fallback requiring user confirmation; not needed given the macro-fold).
- **Curated-hero OpenDota supplement — DEFERRED** (all 3 critiques: second source of truth for 8% of heroes, UI clutter).

---

# PART B — IMPLEMENTATION PLAN (bite-sized TDD, each task ends green)

Repo patterns to follow exactly: pure advisors (`AdviceContext` in, Pydantic out), offline pytest with fixtures, gitignored `engine/app/cache/`, vanilla-JS dashboard panels, mirror `matchups.py`/`refresh_matchups.py`.

---

### Task 1 — `item_builds` loader + models
**Create:** `engine/app/item_builds.py`, `engine/app/tests/fixtures/item_builds_sample.json`, `engine/app/tests/test_item_builds.py`
**Interfaces:** `PhaseItem`, `Benchmarks`, `HeroItemBuild`, `ItemBuildData` (schemas above); `load_item_builds(path: Path | None = None) -> ItemBuildData`.
**Failing test:**
- `test_loads_sample()` — load fixture → `data.has_data is True`, `"npc_dota_hero_juggernaut" in data.heroes`, `builds["mid_game"][0].display == "Battle Fury"`, `benchmarks.gold_per_min` len 11.
- `test_missing_cache_degrades()` — `load_item_builds(Path("/does/not/exist.json"))` → `has_data is False and heroes == {}`.
**Impl sketch:** mirror `load_matchups`: resolve default path to `engine/app/cache/item_builds.json`; `if not path.exists(): return ItemBuildData(has_data=False)`; `json.loads`; `ItemBuildData(has_data=True, heroes={k: HeroItemBuild(**v) for k,v in raw["heroes"].items()})`; wrap parse errors → `has_data=False`.
**Commit:** `feat(item-builds): add degrade-safe item_builds cache loader + models`

---

### Task 2 — `refresh_item_builds.py` pure transform (+ thin network wrappers)
**Create:** `scripts/refresh_item_builds.py`, `engine/app/tests/test_refresh_item_builds_transform.py`
**Interfaces (pure, tested):**
```python
CONSUMABLE_BLOCKLIST: set[str]   # ward_observer, ward_sentry, tpscroll, dust, smoke_of_deceit,
                                 # tango, clarity, flask, enchanted_mango, faerie_fire, branches
PHASE_MAP = {"start_game_items":"start_game", "early_game_items":"early_game",
             "mid_game_items":"mid_game", "late_game_items":"late_game"}
def resolve_item(numeric_id, item_ids, items) -> dict | None    # {id,key,display} or None (null dname / unknown / filtered)
def transform_item_popularity(item_pop, item_ids, items, top_n=8) -> dict[str, list[dict]]
def transform_benchmarks(bench_result) -> dict                  # {percentiles, gold_per_min, xp_per_min, last_hits_per_min}
def build_hero_entry(hero, item_pop, bench_result, item_ids, items) -> dict
```
Network wrappers (thin, untested): `_get_json(url)` (urllib + 1.1s+jitter throttle + 429/521 backoff), `fetch_constants()`, `fetch_item_popularity(hid)`, `fetch_benchmarks(hid)`, `main()` iterating the 127 ids from `heroes.json`, writing `engine/app/cache/item_builds.json`.
**Failing test (offline, small dicts):**
- Phase-key translation: input `{"mid_game_items": {"152": 30}}` → output has key `"mid_game"` (not `mid_game_items`).
- Null-dname skip: `items["recipe_x"]["dname"] is None` → `resolve_item` returns `None`; item absent from output.
- Component/consumable filter: an id resolving to `qual=="component"` (yasha) and one in `CONSUMABLE_BLOCKLIST` (tango) are both dropped.
- Cross-phase dedup: `power_treads` present in early+mid+late input → appears only in `early_game` output.
- Cap: >8 finished items in a phase → exactly 8, sorted desc by count.
- `key` prefixing: `blink` → `item_blink`.
- `transform_benchmarks`: extracts 4 ascending arrays len 11 from the `{percentile,value}` list shape.
**Impl sketch:** `resolve_item`: `name = item_ids.get(str(id))`; `meta = items.get(name)`; return None if no name/meta, `meta.get("dname") is None`, `meta.get("qual") in {"component","consumable"}`, or `name in CONSUMABLE_BLOCKLIST`; else `{"id":id,"key":f"item_{name}","display":meta["dname"]}`. `transform_item_popularity`: for each `<phase>_items` via `PHASE_MAP`, sort id→count desc, resolve, skip None, dedup against a running global `seen` set, take `top_n`.
**Commit:** `feat(item-builds): add refresh_item_builds fetch + pure transform (filter/dedup/phase-map)`

---

### Task 3 — build_coach all-hero fallback + context field
**Modify:** `engine/app/advisors/context.py` (add `item_build_db: dict = field(default_factory=dict)`), `engine/app/advisors/build_coach.py` (BuildAdvice fields + `_phase_for_clock` + fallback branch)
**Create/extend test:** `engine/app/tests/test_build_coach_fallback.py`
**Failing test:**
- `test_none_clock_no_crash()` — non-curated hero, `state.clock_time=None`, `item_build_db` populated → returns `source=="opendota"`, no exception (guards C1 #1).
- `test_fallback_phases_and_owned()` — `state.items=["item_power_treads"]` → that chip `owned is True`, others False.
- `test_suggested_next_first_unowned_from_current_phase()` — clock 700 (early), power_treads owned → `suggested_next` is first unowned early/mid/late item.
- `test_suggested_next_none_when_all_owned()` → `suggested_next is None`, `has_build is True`.
- `test_no_data_returns_none_source()` — empty `item_build_db` → `has_build is False, source=="none"`.
- `test_curated_unchanged()` — a curated hero still returns `source=="curated"` with existing `next_core`.
**Impl sketch:** exactly the fallback branch above; add `_phase_for_clock` with the `None`/`<0` guard; extend `BuildAdvice` with `source`/`phases`/`suggested_next`.
**Commit:** `feat(build-coach): all-hero OpenDota fallback build with clock-safe suggested_next`

---

### Task 4 — farm advisor (+ GSI/state `last_hits`)
**Modify:** `engine/app/state.py` (add `last_hits: int | None = None` to `PlayerState`), `engine/app/gsi.py` (parse `last_hits` from `p`)
**Create:** `engine/app/advisors/farm.py`, `engine/app/tests/test_farm.py`, `engine/app/tests/test_gsi_last_hits.py`
**Interfaces:** `_pct`, `_band`, `FarmMetric`, `FarmAdvice`, `advise(ctx) -> FarmAdvice` (all above).
**Failing test:**
- `test_gsi_parses_last_hits()` — existing GSI fixture → `parse_gsi(...).player.last_hits == 20`.
- `test_pct_interpolation()` — value between buckets interpolates; below-min → 10; above-max → 99.
- `test_gate_before_300()` — `clock_time=120` → `has_data is False` (GPM/XPM gated too, C2/C3).
- `test_metrics_after_300()` — clock 600, gpm/xpm/last_hits set → 3 metrics, correct bands, `summary` mentions "vs all players".
- `test_skip_none_metric()` — `gpm=None` → no GPM metric built, **no ValidationError** (C1 #2); XPM/LH still present.
- `test_empty_benchmarks_no_crash()` — hero with empty benchmark arrays → `_pct` None → metric skipped → `has_data is False` when nothing survives.
**Impl sketch:** as spec; `gsi.py` adds `last_hits=p.get("last_hits")` alongside existing player fields.
**Commit:** `feat(farm): hero-relative farm percentile advisor + GSI last_hits`

---

### Task 5 — advice.py wiring (payload + context)
**Modify:** `engine/app/advice.py`
**Extend test:** `engine/app/tests/test_advice_payload.py`
**Failing test:**
- `test_payload_has_farm_and_build_fields()` — with a stubbed loaded `ITEM_BUILDS` (monkeypatch or fixture cache), `build_advice(state)` for a non-curated hero → `payload.build.source=="opendota"`, `payload.farm` present.
- `test_payload_degrades_without_cache()` — no cache → `payload.build.source in {"none","curated"}`, `payload.farm is None or payload.farm.has_data is False`; no exception (fresh-clone boot).
- `test_model_dump_serializes()` — `build_advice(state).model_dump()` succeeds (confirms new fields ride WS/HTTP without `main.py` change).
**Impl sketch:** `from .item_builds import load_item_builds`; `ITEM_BUILDS = load_item_builds()`; pass `item_build_db=ITEM_BUILDS.heroes` into `AdviceContext`; add `farm: FarmAdvice | None = None` to `AdvicePayload`; `build_advice` returns `..., build=build_coach.advise(ctx), farm=farm_advisor.advise(ctx)`.
**Commit:** `feat(advice): wire item_build_db + farm into AdviceContext/AdvicePayload`

---

### Task 6 — dashboard: build fallback rendering + farm readout
**Modify:** `dashboard/index.html` (add `<div id="farm-body">` inside the macro `<section>`), `dashboard/src/panels/build.js` (opendota branch), `dashboard/src/main.js` (import + call `renderFarm`), `dashboard/src/style.css` (farm-bar classes only — **no** `grid-template-areas`)
**Create:** `dashboard/src/panels/farm.js`
**Failing check (no JS test harness in repo → manual + build gate):**
- `renderBuild` opendota branch: renders ≤4 chips/phase with separators, owned ticks, `NEXT: …` null-guarded (`build complete` when `suggested_next` null), "(vs all-bracket meta)" micro-label; `none` path keeps today's message.
- `renderFarm`: 3 labelled percentile bars + summary into `#farm-body`; clears `#farm-body` when `!farm || !farm.has_data`.
- `main.js onMessage` calls `renderFarm(payload)` alongside `renderBuild`/`renderMacro`.
**Verify:** run `npm run build` in `dashboard/` (must exit 0); load with a captured Silencer payload and confirm build tile shows phase chips (no internal scroll at ≤4/phase) and farm rows render inside the macro cell with the page not scrolling.
**Impl sketch:** `farm.js` mirrors macro's `win-fill` bar (`width: pct%`); build opendota branch builds a single `.coreline`-style sequence with ` › ` phase separators.
**Commit:** `feat(dashboard): render all-hero fallback build + farm benchmark (macro-tile fold)`

---

### Operational note (document in refresh script header)
After running `python scripts/refresh_item_builds.py` (~5 min: 127 heroes × 2 endpoints + 2 constants at ~1.1 s/req), **restart the engine** — `ITEM_BUILDS` loads once at import. Refresh cadence is per-patch, not per-game (meta is static). Cache is gitignored; a fresh clone runs with `has_data=False` until first refresh.

**Load-bearing files:** `/home/tahseen-dar/Projects/dota2-live-helper/engine/app/item_builds.py`, `/home/tahseen-dar/Projects/dota2-live-helper/engine/app/advisors/farm.py`, `/home/tahseen-dar/Projects/dota2-live-helper/engine/app/advisors/build_coach.py`, `/home/tahseen-dar/Projects/dota2-live-helper/engine/app/advisors/context.py`, `/home/tahseen-dar/Projects/dota2-live-helper/engine/app/gsi.py`, `/home/tahseen-dar/Projects/dota2-live-helper/engine/app/state.py`, `/home/tahseen-dar/Projects/dota2-live-helper/engine/app/advice.py`, `/home/tahseen-dar/Projects/dota2-live-helper/scripts/refresh_item_builds.py`, `/home/tahseen-dar/Projects/dota2-live-helper/dashboard/src/panels/build.js`, `/home/tahseen-dar/Projects/dota2-live-helper/dashboard/src/panels/farm.js`, `/home/tahseen-dar/Projects/dota2-live-helper/dashboard/src/main.js`, `/home/tahseen-dar/Projects/dota2-live-helper/dashboard/index.html`, `/home/tahseen-dar/Projects/dota2-live-helper/dashboard/src/style.css`.
