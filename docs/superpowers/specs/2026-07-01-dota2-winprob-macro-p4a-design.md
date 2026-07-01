# Dota 2 Live Helper — P4a Live Win-Prob / Macro Design Spec

**Date:** 2026-07-01
**Patch context:** 7.41d
**Status:** Design — awaiting user review before implementation planning
**Builds on:** P0-P3 (timings, build coach, draft helper), all merged to `master`.

## 1. Goal

Add the **live win-probability + macro advisor** pillar: a "what to do now" coach driven by the
player's observable game state, plus a truthful win-probability meter fed by a manually-entered
net-worth lead and an OpenDota-fit model. Completes the live in-game helper.

### Decomposition
P4 splits into **P4a (this spec) — live win-prob/macro** and **P4b — post-game review** (a
later spec: match-ID → OpenDota parsed match → win-prob graph + key-moment analysis; a distinct
non-live modality). P4a is built first.

### Non-goals
- No calibrated live win% from hidden data: GSI player-mode does not expose enemy net worth, so
  the win% is computed from a **manually-entered net-worth lead**, not inferred.
- The engine never calls the network; only the fit script does. Engine stays keyless.
- VAC-safe: GSI + the user's manual inputs + a cached model only. No game-process access, no
  enemy vision the player couldn't legitimately see.

## 2. Decisions (from brainstorming)

- **Scope:** macro advisor + manual-lead win% meter (P4a). Post-game review deferred to P4b.
- **Win model:** fit from OpenDota data — an **empirical win-rate table** bucketed by
  (game-minute, net-worth-lead), built by a fit script; the engine reads the cached table and
  falls back to a **documented logistic** when the cache is absent.
- **Keyless offline engine / refresh-script / graceful-degradation**, same shape as P3.
- **Two manual inputs**, both GSI-clock-based: net-worth lead and Roshan death.

## 3. Architecture & data flow

```
  scripts/fit_winprob.py ──OpenDota (parsed matches: radiant_gold_adv + radiant_win)──► engine/app/cache/winprob.json (gitignored)
       (run occasionally)                                                                 │ empirical win% by (minute, lead) bucket
                                                                                          ▼
  Dashboard ─POST /networth─►┐   engine/app/winprob.py: load_winprob() + win_probability(lead, clock)  [logistic fallback]
  Dashboard ─POST /roshan───►┤► GameState {..., net_worth_lead, roshan_dead_clock}
  Dota ─GSI─► /gsi ──────────┘                    │
                          advisor registry: timings + build_coach + draft + macro
                                                   │
  Dashboard ◄─WS─ AdvicePayload {..., macro{win_prob, recommendation, reasons, roshan{}}}
```

- **`fit_winprob.py`** is the only network caller for this pillar (OpenDota, no key). Pure
  samples→table transform + a thin fetch wrapper.
- **`macro` advisor** reads GSI observables + the manual inputs → recommendation + reasons + win%.
- **Manual inputs:** `POST /networth {lead}` sets the net-worth lead; `POST /roshan` records the
  current GSI clock as Roshan's death (respawn window = +8..11 min); `POST /roshan {clear:true}`
  resets it.
- Engine stays keyless/offline/VAC-safe.

## 4. Win-probability (fit + table + fallback)

### 4.1 `scripts/fit_winprob.py`
Fetch recent parsed matches from OpenDota (those exposing `radiant_gold_adv`), emit samples
`(minute, gold_adv, radiant_win)`, and bucket them. The **pure** `build_table(samples) -> dict`
is unit-tested; the fetch wrapper (`urllib`, timeout + HTTP-error handling) is not.

### 4.2 `engine/app/cache/winprob.json` (gitignored)
```json
{
  "generated": "2026-07-01T...",
  "minute_bucket": 5,
  "lead_bucket": 2000,
  "buckets": { "15": { "4000": {"wins": 61, "total": 100} } }
}
```
Minute buckets of 5 minutes; lead buckets of 2000 gold (signed, from the player's perspective).

### 4.3 `engine/app/winprob.py`
- `load_winprob(path=CACHE) -> dict | None` (offline; `None` when absent).
- `win_probability(lead: int, clock_s: int, table: dict | None, *, min_total: int = 20) -> float`:
  if `table` has a bucket for (minute, lead) with `total >= min_total`, return `wins/total`;
  else the **documented logistic fallback** `sigmoid(lead / scale(t))`, where `scale(t)` decreases
  with game time (a lead matters more late). Both paths pure and unit-tested; `lead=0 → ~0.5`;
  monotonic increasing in `lead`.

## 5. The `macro` advisor

`macro.advise(ctx) -> MacroAdvice`, pure. Signals from GSI observables + manual inputs:
- **Buyback:** `buyback_ready` = hero alive-context, `buyback_cooldown == 0`, and `player.gold >=
  hero.buyback_cost`.
- **Death:** `hero.alive` false + `respawn_seconds` → "dead Ns — don't force".
- **Farm standing:** `player.gpm` vs a target → ahead / on-track / behind.
- **Power spike:** owns key items (e.g. `item_black_king_bar`) → "BKB up — fight through magic".
- **Night:** `map.daytime` false → "night — group for pickoffs".
- **Roshan:** from `roshan_dead_clock` + live clock → window `[+480s, +660s]`; status = counting /
  contestable / unknown.
- **Win%:** `win_probability(net_worth_lead, clock)` when a lead is entered.

**Primary recommendation** via a documented priority ladder → one of
`PLAY_SAFE / FARM / DEFEND / GROUP / PUSH / TAKE_ROSH / SMOKE`:
1. dead with no buyback → `PLAY_SAFE`
2. high win% (≥ 0.6) and itemized → `PUSH`
3. Roshan window contestable and not-behind → `TAKE_ROSH`
4. low win% (≤ 0.4) → `DEFEND`
5. behind on farm → `FARM`
6. night → `GROUP`
7. default → `FARM`

### `MacroAdvice` (Pydantic)
`win_prob: float | None`, `net_worth_lead: int | None`, `recommendation: str`,
`reasons: list[str]`, `buyback_ready: bool`,
`roshan: RoshanState | None` where `RoshanState` = `dead_clock: int`, `window_start_s: int`,
`window_end_s: int`, `status: str`.

## 6. Dashboard

- **Win% meter:** a horizontal bar + number, with a small **net-worth-lead number input** that
  posts `POST /networth {lead}` on change.
- **Macro panel:** the big `recommendation` + `reasons`; a buyback indicator; a **"Rosh died"
  button** posting `POST /roshan` (and a clear), showing the respawn countdown from `roshan`.
- Renders from `payload.macro` each tick; text/chips, consistent with the other panels.

## 7. Testing

- **Fit transform test:** samples → bucket table (pure, no network).
- **`win_probability` tests:** empirical-bucket path (dense bucket → its rate); logistic-fallback
  path (`lead=0 → ~0.5`, monotonic in lead, sparse bucket falls back).
- **`macro` advisor tests:** the recommendation ladder per scenario (dead/no-buyback, high-win%
  itemized, Roshan window, behind, night), Roshan-window math, buyback logic — synthetic state.
- **Endpoint tests:** `POST /networth` + `POST /roshan` set state; `macro` present in the payload.

## 8. Internal build order

1. `winprob.py` loader + logistic fallback + `win_probability` + tests.
2. `scripts/fit_winprob.py` (OpenDota fetch + pure `build_table` transform) + transform test.
3. `macro` advisor (+ extend `AdviceContext` with `net_worth_lead`, `roshan_dead_clock`, and the
   loaded win-prob table) + tests.
4. `GameState` fields (`net_worth_lead`, `roshan_dead_clock`) + `POST /networth` + `POST /roshan`
   + wire `macro` into the aggregator + `AdvicePayload.macro`.
5. Dashboard macro panel + win meter + net-worth entry + Rosh button.

## 9. Honest notes / open items

- The win% is only as good as the **manually-entered net-worth lead** (glance at the top bar).
- The empirical table needs the **fit run** (`python scripts/fit_winprob.py`); until then the
  **logistic fallback** is used — the meter works out of the box, just less empirically grounded.
- Macro nudges are **heuristics** over the player's observable state; the priority ladder and the
  thresholds (win% 0.6/0.4, GPM target, Roshan 8–11 min) are tunable constants.
- OpenDota parsed-match availability varies; the fit script keeps only matches exposing
  `radiant_gold_adv`, and logs how many samples it gathered.
