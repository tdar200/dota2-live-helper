# Dota 2 Live Helper — P4a Win-Prob / Macro Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a live win-probability meter (manual net-worth lead → OpenDota-fit empirical curve, logistic fallback) and a macro advisor ("what to do now" from observable GSI state) as the fourth advisor pillar.

**Architecture:** A fit script (only network caller) buckets OpenDota parsed-match gold-lead-vs-time into an empirical win-rate table cached to `winprob.json`; the keyless engine reads it via `winprob.py` and falls back to a documented logistic. A `macro` advisor reads GSI observables + two manual clock-based inputs (net-worth lead, Roshan death) and emits a recommendation + reasons + win%. New `POST /networth` and `POST /roshan` endpoints; a dashboard macro panel + win meter.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, pytest (engine); Vite + vanilla JS (dashboard). Fit script uses stdlib `urllib` (no new deps).

## Global Constraints

- **Patch 7.41d.** The win-prob empirical table is the gitignored cache `engine/app/cache/winprob.json`; when absent, a documented logistic fallback is used. Tuning constants (win% 0.6/0.4, GPM target, Roshan 8–11 min, bucket sizes) live in code as named constants.
- **VAC-safe & keyless engine:** the engine/advisors NEVER call the network. Only `scripts/fit_winprob.py` calls OpenDota (no key needed). Inputs are GSI + the user's manual net-worth/Roshan entry + the cached table. No game-process access; no enemy info the player couldn't legitimately see.
- **Offline tests:** no test performs a live network call. The OpenDota samples→table `build_table` is a pure function tested on synthetic samples.
- **Display-agnostic engine:** advisors return Pydantic advice objects; no HTTP/WebSocket/DOM imports. `main.py` is the only HTTP/WS layer.
- **Single source of time:** all timing/Roshan logic uses GSI `clock_time` (seconds), never wall-clock. Manual inputs record the live `clock_time`.
- **Graceful degradation:** no cache → logistic win%; no net-worth lead entered → `win_prob=None`; no Roshan entered → `roshan=None`.
- **Bucketing is DRY:** the fit script imports `bucket_minute`/`bucket_lead` from `app.winprob` so the engine and the fit produce identical buckets.
- **Pydantic v2**, **Python 3.11+**. **Run pytest from `engine/` via `.venv/bin/python`.** Post-P3 suite is 32 tests; must stay green.
- **Project root:** `/home/tahseen-dar/Projects/dota2-live-helper`.

---

## File Structure

```
engine/app/
  winprob.py                # bucket helpers + load_winprob() + win_probability() (+ logistic fallback)
  cache/winprob.json        # gitignored, written by the fit script
  state.py                  # HeroState + respawn_seconds; GameState + net_worth_lead, roshan_dead_clock
  gsi.py                    # parse hero.respawn_seconds
  advisors/
    context.py              # + net_worth_lead, roshan_dead_clock, winprob_table
    macro.py                # RoshanState/MacroAdvice + advise(ctx)
  advice.py                 # load WINPROB_TABLE; AdvicePayload + macro; call macro advisor
  main.py                   # + POST /networth, POST /roshan
scripts/fit_winprob.py      # OpenDota fetch + pure build_table
engine/tests/
  test_winprob.py
  test_fit_winprob.py
  test_macro.py
  test_networth_roshan_endpoint.py
dashboard/src/
  panels/macro.js
  main.js, index.html, style.css
```

---

### Task 1: `winprob.py` — bucket helpers, loader, `win_probability` + logistic fallback

**Files:**
- Create: `engine/app/winprob.py`
- Test: `engine/tests/test_winprob.py`

**Interfaces:**
- Produces (in `app.winprob`):
  - `MINUTE_BUCKET = 5`, `LEAD_BUCKET = 2000`, `CACHE_PATH: Path`.
  - `bucket_minute(clock_s: int) -> int`, `bucket_lead(lead: int) -> int`.
  - `load_winprob(path: Path = CACHE_PATH) -> dict | None` (offline; `None` when absent).
  - `win_probability(lead: int, clock_s: int, table: dict | None, *, min_total: int = 20) -> float` — empirical bucket rate when the (minute, lead) bucket has `total >= min_total`, else the logistic fallback `sigmoid(lead / scale(clock_s))`.

- [ ] **Step 1: Write the failing tests**

`engine/tests/test_winprob.py`:
```python
from app.winprob import win_probability, bucket_minute, bucket_lead, load_winprob
from pathlib import Path


def test_logistic_fallback_even_at_zero_lead():
    p = win_probability(0, 600, None)
    assert abs(p - 0.5) < 1e-9


def test_logistic_monotonic_in_lead():
    lo = win_probability(-6000, 1200, None)
    hi = win_probability(6000, 1200, None)
    assert lo < 0.5 < hi


def test_empirical_bucket_used_when_dense():
    table = {"buckets": {"15": {"4000": {"wins": 70, "total": 100}}}}
    # clock 15:20 -> minute bucket 15; lead 4100 -> lead bucket 4000
    assert bucket_minute(920) == 15
    assert bucket_lead(4100) == 4000
    assert win_probability(4100, 920, table) == 0.70


def test_sparse_bucket_falls_back_to_logistic():
    table = {"buckets": {"15": {"4000": {"wins": 3, "total": 5}}}}
    p = win_probability(4100, 920, table, min_total=20)
    assert p != 0.6  # not the empirical 3/5; used logistic instead


def test_missing_cache_returns_none():
    assert load_winprob(Path("/nonexistent/winprob.json")) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd engine && .venv/bin/python -m pytest tests/test_winprob.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.winprob'`.

- [ ] **Step 3: Implement `winprob.py`**

`engine/app/winprob.py`:
```python
import json
import math
from pathlib import Path

CACHE_PATH = Path(__file__).parent / "cache" / "winprob.json"
MINUTE_BUCKET = 5
LEAD_BUCKET = 2000


def bucket_minute(clock_s: int) -> int:
    minutes = max(0, clock_s) // 60
    return (minutes // MINUTE_BUCKET) * MINUTE_BUCKET


def bucket_lead(lead: int) -> int:
    return round(lead / LEAD_BUCKET) * LEAD_BUCKET


def _scale(clock_s: int) -> float:
    minutes = max(0, clock_s) // 60
    return max(2500.0, 12000.0 - 250.0 * minutes)


def _logistic(lead: int, clock_s: int) -> float:
    return 1.0 / (1.0 + math.exp(-lead / _scale(clock_s)))


def load_winprob(path: Path = CACHE_PATH) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text())


def win_probability(lead: int, clock_s: int, table: dict | None, *, min_total: int = 20) -> float:
    if table:
        cell = (
            table.get("buckets", {})
            .get(str(bucket_minute(clock_s)), {})
            .get(str(bucket_lead(lead)))
        )
        if cell and cell.get("total", 0) >= min_total:
            return cell["wins"] / cell["total"]
    return _logistic(lead, clock_s)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd engine && .venv/bin/python -m pytest tests/test_winprob.py -v`
Expected: PASS (5 passed). Then full suite: `.venv/bin/python -m pytest tests -q` — all green.

- [ ] **Step 5: Commit**

```bash
cd /home/tahseen-dar/Projects/dota2-live-helper
git add engine/app/winprob.py engine/tests/test_winprob.py
git commit -m "feat(engine): win_probability with empirical table + logistic fallback"
```

---

### Task 2: `fit_winprob.py` — OpenDota fetch + pure `build_table`

**Files:**
- Create: `scripts/fit_winprob.py`
- Test: `engine/tests/test_fit_winprob.py`

**Interfaces:**
- Produces (in `scripts/fit_winprob.py`, importable for the transform test):
  - `build_table(samples: list[tuple[int, int, bool]]) -> dict` — samples are `(clock_s, lead, radiant_win)`; returns `{"minute_bucket": 5, "lead_bucket": 2000, "buckets": {minute: {lead: {"wins", "total"}}}}`, bucketed via `app.winprob.bucket_minute`/`bucket_lead`.
  - `fetch_json(url) -> dict|list`, `main()` (network — not unit-tested) writing `engine/app/cache/winprob.json`.

- [ ] **Step 1: Write the failing transform test**

`engine/tests/test_fit_winprob.py`:
```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from fit_winprob import build_table


def test_build_table_buckets_and_counts():
    # three samples at ~15 min, lead ~4000: two radiant wins, one loss
    samples = [
        (900, 4100, True),
        (905, 3900, True),
        (910, 4000, False),
    ]
    table = build_table(samples)
    assert table["minute_bucket"] == 5
    assert table["lead_bucket"] == 2000
    cell = table["buckets"]["15"]["4000"]
    assert cell == {"wins": 2, "total": 3}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && .venv/bin/python -m pytest tests/test_fit_winprob.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fit_winprob'`.

- [ ] **Step 3: Implement the fit script**

`scripts/fit_winprob.py`:
```python
#!/usr/bin/env python3
"""Fit an empirical win-probability table from OpenDota parsed matches.

Only network caller for this pillar. OpenDota public API needs no key.
Writes engine/app/cache/winprob.json (win% by (game-minute, net-worth-lead) bucket).
"""
import datetime
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
from app.winprob import bucket_minute, bucket_lead, MINUTE_BUCKET, LEAD_BUCKET  # noqa: E402

CACHE = ROOT / "engine" / "app" / "cache" / "winprob.json"
API = "https://api.opendota.com/api"
MATCH_LIMIT = 100


def build_table(samples: list[tuple[int, int, bool]]) -> dict:
    buckets: dict = {}
    for clock_s, lead, win in samples:
        mb = str(bucket_minute(clock_s))
        lb = str(bucket_lead(lead))
        cell = buckets.setdefault(mb, {}).setdefault(lb, {"wins": 0, "total": 0})
        cell["total"] += 1
        if win:
            cell["wins"] += 1
    return {"minute_bucket": MINUTE_BUCKET, "lead_bucket": LEAD_BUCKET, "buckets": buckets}


def fetch_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "dota2-live-helper"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def main() -> None:
    try:
        pro = fetch_json(f"{API}/proMatches")
    except urllib.error.URLError as e:
        print(f"ERROR: could not reach OpenDota: {e}", file=sys.stderr)
        sys.exit(1)
    ids = [m["match_id"] for m in pro][:MATCH_LIMIT]
    samples: list[tuple[int, int, bool]] = []
    kept = 0
    for mid in ids:
        try:
            m = fetch_json(f"{API}/matches/{mid}")
        except urllib.error.URLError:
            continue
        adv = m.get("radiant_gold_adv")
        win = m.get("radiant_win")
        if not adv or win is None:
            continue
        kept += 1
        for minute, g in enumerate(adv):
            samples.append((minute * 60, int(g), bool(win)))
        time.sleep(1)  # be polite to the free API
    table = build_table(samples)
    table["generated"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(table))
    print(f"Wrote {CACHE}: {kept} matches, {len(samples)} samples")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Make executable, run the transform test**

Run:
```bash
chmod +x scripts/fit_winprob.py
cd engine && .venv/bin/python -m pytest tests/test_fit_winprob.py -v
```
Expected: PASS (1 passed). The test imports only `build_table` (pure); no network.

- [ ] **Step 5: Commit**

```bash
cd /home/tahseen-dar/Projects/dota2-live-helper
git add scripts/fit_winprob.py engine/tests/test_fit_winprob.py
git commit -m "feat(scripts): OpenDota win-prob fit + pure build_table"
```

---

### Task 3: The `macro` advisor (+ `respawn_seconds`, context extension)

**Files:**
- Modify: `engine/app/state.py` (add `HeroState.respawn_seconds`)
- Modify: `engine/app/gsi.py` (parse `respawn_seconds`)
- Modify: `engine/app/advisors/context.py` (add `net_worth_lead`, `roshan_dead_clock`, `winprob_table`)
- Create: `engine/app/advisors/macro.py`
- Test: `engine/tests/test_macro.py`

**Interfaces:**
- Consumes: `GameState`/`HeroState`, `win_probability`.
- Produces (in `app.advisors.macro`):
  - `RoshanState(BaseModel)` — `dead_clock: int`, `window_start_s: int`, `window_end_s: int`, `status: str`.
  - `MacroAdvice(BaseModel)` — `win_prob: float | None`, `net_worth_lead: int | None`, `recommendation: str`, `reasons: list[str]`, `buyback_ready: bool`, `roshan: RoshanState | None`.
  - `advise(ctx: AdviceContext) -> MacroAdvice`.
- Extends `AdviceContext` with `net_worth_lead: int | None = None`, `roshan_dead_clock: int | None = None`, `winprob_table: object | None = None`.
- Adds `HeroState.respawn_seconds: int | None = None`.

- [ ] **Step 1: Add `respawn_seconds` to HeroState + parse it**

In `engine/app/state.py`, add to `HeroState` (after `buyback_cooldown`):
```python
    respawn_seconds: int | None = None
```
In `engine/app/gsi.py`, inside the `HeroState(...)` construction in `parse_gsi`, add:
```python
            respawn_seconds=h.get("respawn_seconds"),
```

- [ ] **Step 2: Extend the context**

Append to the `AdviceContext` dataclass in `engine/app/advisors/context.py` (after `matchup_data`):
```python
    net_worth_lead: int | None = None
    roshan_dead_clock: int | None = None
    winprob_table: object | None = None
```

- [ ] **Step 3: Write the failing tests**

`engine/tests/test_macro.py`:
```python
from app.state import GameState, HeroState, PlayerState, MapState
from app.advisors.context import AdviceContext
from app.advisors import macro


def _ctx(*, alive=True, respawn=0, gold=1000, buyback_cost=300, buyback_cd=0,
         gpm=500, daytime=True, items=None, clock=1200, lead=None, rosh_dead=None):
    state = GameState(clock_time=clock, items=items or [])
    state.hero = HeroState(name="npc_dota_hero_skeleton_king", level=16, alive=alive,
                           respawn_seconds=respawn, buyback_cost=buyback_cost, buyback_cooldown=buyback_cd)
    state.player = PlayerState(gold=gold, gpm=gpm)
    state.map = MapState(clock_time=clock, daytime=daytime)
    return AdviceContext(state=state, net_worth_lead=lead, roshan_dead_clock=rosh_dead, winprob_table=None)


def test_dead_without_buyback_plays_safe():
    adv = macro.advise(_ctx(alive=False, respawn=45, gold=100, buyback_cost=1200))
    assert adv.buyback_ready is False
    assert adv.recommendation == "PLAY_SAFE"


def test_high_winprob_and_itemized_pushes():
    adv = macro.advise(_ctx(lead=12000, clock=2400, items=["item_black_king_bar"]))
    assert adv.win_prob is not None and adv.win_prob >= 0.6
    assert adv.recommendation == "PUSH"


def test_roshan_window_take_rosh():
    # rosh died at 1000s; now 1500s -> within [1480,1660] window -> contestable
    adv = macro.advise(_ctx(clock=1500, rosh_dead=1000))
    assert adv.roshan is not None
    assert adv.roshan.status == "contestable"
    assert adv.recommendation == "TAKE_ROSH"


def test_low_winprob_defends():
    adv = macro.advise(_ctx(lead=-12000, clock=2400))
    assert adv.win_prob is not None and adv.win_prob <= 0.4
    assert adv.recommendation == "DEFEND"


def test_behind_farm():
    adv = macro.advise(_ctx(gpm=300))
    assert adv.recommendation == "FARM"
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `cd engine && .venv/bin/python -m pytest tests/test_macro.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.advisors.macro'`.

- [ ] **Step 5: Implement the advisor**

`engine/app/advisors/macro.py`:
```python
from pydantic import BaseModel, Field
from app.advisors.context import AdviceContext
from app.winprob import win_probability

_WIN_HIGH = 0.6
_WIN_LOW = 0.4
_GPM_TARGET = 450
_ROSH_MIN = 480   # 8:00 after death
_ROSH_MAX = 660   # 11:00 after death


class RoshanState(BaseModel):
    dead_clock: int
    window_start_s: int
    window_end_s: int
    status: str


class MacroAdvice(BaseModel):
    win_prob: float | None = None
    net_worth_lead: int | None = None
    recommendation: str
    reasons: list[str] = Field(default_factory=list)
    buyback_ready: bool = False
    roshan: RoshanState | None = None


def _roshan(ctx: AdviceContext) -> RoshanState | None:
    dc = ctx.roshan_dead_clock
    now = ctx.state.clock_time
    if dc is None or now is None:
        return None
    ws, we = dc + _ROSH_MIN, dc + _ROSH_MAX
    if now < ws:
        status = "counting"
    elif now <= we:
        status = "contestable"
    else:
        status = "likely_up"
    return RoshanState(dead_clock=dc, window_start_s=ws, window_end_s=we, status=status)


def advise(ctx: AdviceContext) -> MacroAdvice:
    hero = ctx.state.hero
    player = ctx.state.player
    clock = ctx.state.clock_time

    buyback_ready = bool(
        hero.alive
        and hero.buyback_cooldown == 0
        and hero.buyback_cost is not None
        and player.gold is not None
        and player.gold >= hero.buyback_cost
    )

    win_prob = None
    if ctx.net_worth_lead is not None and clock is not None:
        win_prob = win_probability(ctx.net_worth_lead, clock, ctx.winprob_table)

    rosh = _roshan(ctx)
    dead = hero.alive is False
    behind = player.gpm is not None and player.gpm < _GPM_TARGET
    night = ctx.state.map.daytime is False
    itemized = "item_black_king_bar" in ctx.state.items

    reasons: list[str] = []
    if dead and hero.respawn_seconds:
        reasons.append(f"dead {hero.respawn_seconds}s — don't force")
    reasons.append("buyback up" if buyback_ready else "no buyback — avoid risky fights")
    if player.gpm is not None:
        reasons.append(f"GPM {player.gpm} — {'behind' if behind else 'on track'}")
    if night:
        reasons.append("night — group for pickoffs")
    if itemized:
        reasons.append("BKB up — fight through magic")
    if rosh is not None:
        reasons.append(f"Roshan {rosh.status}")
    if win_prob is not None:
        reasons.append(f"win {round(win_prob * 100)}%")

    rec = _recommend(dead, buyback_ready, win_prob, rosh, behind, night, itemized)
    return MacroAdvice(
        win_prob=win_prob, net_worth_lead=ctx.net_worth_lead, recommendation=rec,
        reasons=reasons, buyback_ready=buyback_ready, roshan=rosh,
    )


def _recommend(dead, buyback_ready, win_prob, rosh, behind, night, itemized) -> str:
    if dead and not buyback_ready:
        return "PLAY_SAFE"
    if win_prob is not None and win_prob >= _WIN_HIGH and itemized:
        return "PUSH"
    if rosh is not None and rosh.status in ("contestable", "likely_up") \
            and not (win_prob is not None and win_prob <= _WIN_LOW):
        return "TAKE_ROSH"
    if win_prob is not None and win_prob <= _WIN_LOW:
        return "DEFEND"
    if behind:
        return "FARM"
    if night:
        return "GROUP"
    return "FARM"
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd engine && .venv/bin/python -m pytest tests/test_macro.py -v`
Expected: PASS (5 passed). Then full suite: `.venv/bin/python -m pytest tests -q` — all green (earlier advisors unaffected; context extension is additive; `respawn_seconds` is additive).

- [ ] **Step 7: Commit**

```bash
cd /home/tahseen-dar/Projects/dota2-live-helper
git add engine/app/state.py engine/app/gsi.py engine/app/advisors/context.py engine/app/advisors/macro.py engine/tests/test_macro.py
git commit -m "feat(engine): macro advisor (recommendation ladder + win% + roshan)"
```

---

### Task 4: State fields + `/networth` + `/roshan` + wire macro

**Files:**
- Modify: `engine/app/state.py` (GameState `net_worth_lead`, `roshan_dead_clock`)
- Modify: `engine/app/advice.py` (load WINPROB_TABLE; `macro` field; call advisor)
- Modify: `engine/app/main.py` (POST `/networth`, `/roshan`)
- Test: `engine/tests/test_networth_roshan_endpoint.py`

**Interfaces:**
- Consumes: `macro.advise`/`MacroAdvice`, `load_winprob`.
- Produces:
  - `GameState.net_worth_lead: int | None`, `GameState.roshan_dead_clock: int | None` (NOT touched by `update_from_raw`).
  - `AdvicePayload.macro: MacroAdvice | None`.
  - `POST /networth` body `{"lead": int}` → sets `STATE.net_worth_lead`, rebuilds+broadcasts, returns `{"ok": True, "lead": N}`.
  - `POST /roshan` body `{}` → sets `STATE.roshan_dead_clock = STATE.clock_time`; `{"clear": true}` → sets it to `None`; rebuilds+broadcasts, returns `{"ok": True, "roshan_dead_clock": N}`.

- [ ] **Step 1: Add GameState fields**

In `engine/app/state.py`, add to `GameState` (after `ally_heroes`):
```python
    net_worth_lead: int | None = None
    roshan_dead_clock: int | None = None
```
`update_from_raw` is unchanged, so both persist across GSI updates.

- [ ] **Step 2: Wire macro into `build_advice`**

Replace `engine/app/advice.py` with:
```python
from pydantic import BaseModel, Field
from app.state import GameState
from app.modules.timings import TimingHit
from app.advisors.context import AdviceContext
from app.advisors import timings as timings_advisor
from app.advisors import build_coach
from app.advisors import draft as draft_advisor
from app.advisors import macro as macro_advisor
from app.advisors.build_coach import BuildAdvice
from app.advisors.draft import DraftAdvice
from app.advisors.macro import MacroAdvice
from app.build_data import load_build_data
from app.matchups import load_matchups
from app.winprob import load_winprob

BUILD_DATA = load_build_data()
MATCHUP_DATA = load_matchups()
WINPROB_TABLE = load_winprob()


class AdvicePayload(BaseModel):
    clock_time: int | None = None
    connected: bool = True
    timings: list[TimingHit] = Field(default_factory=list)
    build: BuildAdvice | None = None
    draft: DraftAdvice | None = None
    macro: MacroAdvice | None = None


def build_advice(state: GameState, *, horizon_s: int = 600, limit: int = 6) -> AdvicePayload:
    ctx = AdviceContext(
        state=state, horizon_s=horizon_s, limit=limit,
        enemy_heroes=state.enemy_heroes,
        ally_heroes=state.ally_heroes,
        build_db=BUILD_DATA.builds,
        trait_db=BUILD_DATA.traits,
        item_names=BUILD_DATA.item_names,
        hero_names=BUILD_DATA.hero_names,
        matchup_data=MATCHUP_DATA,
        net_worth_lead=state.net_worth_lead,
        roshan_dead_clock=state.roshan_dead_clock,
        winprob_table=WINPROB_TABLE,
    )
    return AdvicePayload(
        clock_time=state.clock_time,
        timings=timings_advisor.advise(ctx),
        build=build_coach.advise(ctx),
        draft=draft_advisor.advise(ctx),
        macro=macro_advisor.advise(ctx),
    )
```

- [ ] **Step 3: Write the failing endpoint test**

`engine/tests/test_networth_roshan_endpoint.py`:
```python
from fastapi.testclient import TestClient
from app.main import app, STATE, HUB


def setup_function():
    STATE.net_worth_lead = None
    STATE.roshan_dead_clock = None
    STATE.clock_time = None
    HUB.last = None


def test_networth_sets_lead_and_returns():
    client = TestClient(app)
    r = client.post("/networth", json={"lead": 5000})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "lead": 5000}
    assert STATE.net_worth_lead == 5000


def test_roshan_records_current_clock_and_clear():
    client = TestClient(app)
    client.post("/gsi", json={"map": {"clock_time": 1000}})
    r = client.post("/roshan", json={})
    assert r.json() == {"ok": True, "roshan_dead_clock": 1000}
    assert STATE.roshan_dead_clock == 1000
    r2 = client.post("/roshan", json={"clear": True})
    assert r2.json() == {"ok": True, "roshan_dead_clock": None}


def test_macro_present_in_payload():
    client = TestClient(app)
    client.post("/networth", json={"lead": 3000})
    HUB.last = None
    with client.websocket_connect("/ws") as ws:
        client.post("/gsi", json={"map": {"clock_time": 1200}, "hero": {"alive": True}})
        data = ws.receive_json()
    assert data["macro"] is not None
    assert data["macro"]["recommendation"]
    assert data["macro"]["win_prob"] is not None
```

- [ ] **Step 4: Run test to verify it fails**

Run: `cd engine && .venv/bin/python -m pytest tests/test_networth_roshan_endpoint.py -v`
Expected: FAIL — `/networth` and `/roshan` return 404.

- [ ] **Step 5: Add the endpoints**

In `engine/app/main.py`, add these routes immediately AFTER the `/heroes` handler and BEFORE the `if _DIST.exists():` static mount:
```python
@app.post("/networth")
async def networth(request: Request) -> dict:
    body = await request.json()
    STATE.net_worth_lead = body.get("lead")
    await HUB.broadcast(build_advice(STATE).model_dump())
    return {"ok": True, "lead": STATE.net_worth_lead}


@app.post("/roshan")
async def roshan(request: Request) -> dict:
    body = await request.json()
    STATE.roshan_dead_clock = None if body.get("clear") else STATE.clock_time
    await HUB.broadcast(build_advice(STATE).model_dump())
    return {"ok": True, "roshan_dead_clock": STATE.roshan_dead_clock}
```

- [ ] **Step 6: Run the focused test, then the full suite**

Run: `cd engine && .venv/bin/python -m pytest tests/test_networth_roshan_endpoint.py -v`
Expected: PASS (3 passed).
Run: `cd engine && .venv/bin/python -m pytest tests -q`
Expected: PASS (all).

- [ ] **Step 7: Commit**

```bash
cd /home/tahseen-dar/Projects/dota2-live-helper
git add engine/app/state.py engine/app/advice.py engine/app/main.py engine/tests/test_networth_roshan_endpoint.py
git commit -m "feat(engine): macro in payload + /networth and /roshan endpoints"
```

---

### Task 5: Dashboard macro panel (win meter + net-worth entry + Rosh button)

**Files:**
- Create: `dashboard/src/panels/macro.js`
- Modify: `dashboard/index.html`, `dashboard/src/main.js`, `dashboard/src/style.css`

**Interfaces:**
- Consumes: WebSocket `AdvicePayload.macro` (`{win_prob, net_worth_lead, recommendation, reasons[], buyback_ready, roshan{dead_clock, window_start_s, window_end_s, status}}`); `POST /networth {lead}`; `POST /roshan {}` / `{clear:true}`.
- Produces: a macro panel (win% meter, net-worth input, recommendation + reasons, Rosh button) rendered from `payload.macro`.

- [ ] **Step 1: Add markup to index.html**

In `dashboard/index.html`, inside `<main>`, add after the `#draft-panel` section:
```html
      <section id="macro-panel" class="panel">
        <h2>Macro</h2>
        <div class="winbar"><div id="win-fill"></div><span id="win-pct">—</span></div>
        <label class="nwl">Net-worth lead
          <input id="nwl-input" type="number" step="500" placeholder="e.g. 4000" />
        </label>
        <div id="macro-rec">—</div>
        <ul id="macro-reasons"></ul>
        <button id="rosh-btn" type="button">Rosh died</button>
        <button id="rosh-clear" type="button">clear</button>
        <span id="rosh-info"></span>
      </section>
```

- [ ] **Step 2: Create the macro panel**

`dashboard/src/panels/macro.js`:
```js
function mmss(total) {
  const s = Math.max(0, Math.floor(total));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function renderMacro(payload) {
  const m = payload.macro;
  const rec = document.getElementById("macro-rec");
  const fill = document.getElementById("win-fill");
  const pct = document.getElementById("win-pct");
  const reasons = document.getElementById("macro-reasons");
  const roshInfo = document.getElementById("rosh-info");
  if (!m) {
    rec.textContent = "—";
    return;
  }
  rec.textContent = m.recommendation;
  rec.className = `rec-${m.recommendation}`;
  if (m.win_prob == null) {
    fill.style.width = "0%";
    pct.textContent = "—";
  } else {
    const p = Math.round(m.win_prob * 100);
    fill.style.width = `${p}%`;
    pct.textContent = `${p}%`;
  }
  reasons.innerHTML = (m.reasons || []).map((r) => `<li>${r}</li>`).join("");
  if (m.roshan && payload.clock_time != null) {
    const until = m.roshan.window_start_s - payload.clock_time;
    roshInfo.textContent =
      m.roshan.status === "counting"
        ? `Rosh window in ${mmss(until)}`
        : `Rosh ${m.roshan.status}`;
  } else {
    roshInfo.textContent = "";
  }
}

export function initMacroControls(engineHost) {
  const base = `http://${engineHost}`;
  const input = document.getElementById("nwl-input");
  const post = (path, body) =>
    fetch(`${base}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).catch((e) => console.error(path, e));

  input.addEventListener("change", () => {
    const lead = input.value === "" ? null : parseInt(input.value, 10);
    post("/networth", { lead });
  });
  document.getElementById("rosh-btn").addEventListener("click", () => post("/roshan", {}));
  document.getElementById("rosh-clear").addEventListener("click", () => post("/roshan", { clear: true }));
}
```

- [ ] **Step 3: Wire into main.js**

In `dashboard/src/main.js`, add the imports alongside the others:
```js
import { renderMacro, initMacroControls } from "./panels/macro.js";
```
Add `renderMacro(payload);` inside `onMessage` (after `renderDraft(payload);`), and add `initMacroControls(ENGINE_HOST);` alongside the other init calls (before `connect(...)`).

- [ ] **Step 4: Add styles**

Append to `dashboard/src/style.css`:
```css
.winbar { position: relative; height: 22px; background: #331616; border-radius: 6px; overflow: hidden; margin-bottom: .5rem; }
#win-fill { height: 100%; width: 0; background: linear-gradient(90deg, #2f6b3a, #6ee787); transition: width .3s; }
.winbar #win-pct { position: absolute; top: 0; left: 50%; transform: translateX(-50%); line-height: 22px; font-variant-numeric: tabular-nums; }
.nwl { display: block; font-size: .8rem; color: #b8c0cc; margin-bottom: .5rem; }
#nwl-input { width: 8rem; margin-left: .4rem; background: #0b0d11; color: #e6e6e6; border: 1px solid #20242c; border-radius: 6px; padding: .3rem; }
#macro-rec { font-size: 1.4rem; font-weight: 700; margin: .3rem 0; }
.rec-PUSH, .rec-TAKE_ROSH { color: #6ee787; }
.rec-DEFEND, .rec-PLAY_SAFE { color: #ff9a9a; }
.rec-FARM, .rec-GROUP, .rec-SMOKE { color: #9ecbff; }
#macro-reasons { list-style: none; margin: .2rem 0; padding: 0; font-size: .82rem; color: #8a93a0; }
#macro-reasons li { padding: .1rem 0; }
#rosh-btn, #rosh-clear { background: #20242c; color: #e6e6e6; border: 1px solid #333; border-radius: 6px; padding: .3rem .6rem; cursor: pointer; }
#rosh-info { font-size: .82rem; color: #ffd479; margin-left: .5rem; }
```

- [ ] **Step 5: Build the dashboard**

Run: `cd dashboard && npm run build`
Expected: build succeeds, no errors. (In-browser visual smoke — enter a net-worth lead, click "Rosh died", watch the meter + recommendation — is deferred to the user.)

- [ ] **Step 6: Commit**

```bash
cd /home/tahseen-dar/Projects/dota2-live-helper
git add dashboard
git commit -m "feat(dashboard): macro panel with win meter, net-worth entry, Rosh button"
```

---

## Self-Review

- **Spec coverage:** fit-script-to-cache keyless engine (Tasks 1-2, spec §3-4) ✓; empirical table + logistic fallback + `win_probability` (Task 1, spec §4) ✓; OpenDota fit + pure `build_table` (Task 2, spec §4) ✓; macro advisor signals + recommendation ladder + `MacroAdvice`/`RoshanState` (Task 3, spec §5) ✓; `net_worth_lead`/`roshan_dead_clock` + `/networth` + `/roshan` + macro in payload (Task 4, spec §3/§5) ✓; dashboard win meter + net-worth entry + macro panel + Rosh button (Task 5, spec §6) ✓; offline tests incl. pure transform (Tasks 1-4, spec §7) ✓; graceful degradation (no cache → logistic, no lead → None, no rosh → None) ✓; VAC-safe/keyless (Global Constraints). Post-game review is out of scope (P4b).
- **Placeholder scan:** no TBD/TODO; every code step is complete. The fit run is a documented user step; `build_table` is unit-tested regardless of live data.
- **Type consistency:** `bucket_minute`/`bucket_lead`/`win_probability`/`load_winprob` (Task 1) reused by the fit script (Task 2) and the macro advisor (Task 3); `MacroAdvice`/`RoshanState`, `AdviceContext` (net_worth_lead/roshan_dead_clock/winprob_table added Task 3, consumed Task 4), `HeroState.respawn_seconds` (added Task 3, parsed Task 3), `WINPROB_TABLE`, and the dashboard's `payload.macro.*` field names all match across tasks. `build_advice(state)` keeps its signature so `/gsi`, `/enemies`, `/allies` are unaffected; the new endpoints mirror the existing manual-input pattern.
```
