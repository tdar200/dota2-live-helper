# Dota 2 Live Helper — P0 Backbone + P1 Timings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the live backbone — Dota's GSI feeds a FastAPI engine that pushes advice over WebSocket to a second-monitor JS dashboard — and ship the first pillar (clock-based timing countdowns) end-to-end.

**Architecture:** One FastAPI process receives GSI POSTs at `/gsi`, parses them into a single in-memory `GameState`, runs read-only feature modules (only `timings` in this plan) that emit advice objects, combines them into one payload, and broadcasts it to connected dashboards over a WebSocket hub. The engine is display-agnostic; the dashboard is one of potentially several front-ends. The timing engine is pure math over a data table of periodic events, so it is fully unit-testable offline.

**Tech Stack:** Python 3.11+, FastAPI, Uvicorn, Pydantic v2, pytest (engine); Vite + vanilla JS (dashboard). No database — state is in-memory; cold data caching arrives in later plans.

## Global Constraints

- **Patch context:** 7.41d. All timing constants live in one table (`app/timing_constants.py`) and must be verifiable against `../dota2-knowledge-base` and in-client; never hard-code timing numbers inside logic.
- **VAC-safe only:** the engine consumes Valve GSI + the user's manual inputs only. No memory reads, no process injection, no scraping of live opponents. (Nothing in this plan touches the game process.)
- **Display-agnostic engine:** feature modules return advice objects; they must not know about HTTP, WebSocket, or the DOM.
- **Single source of time:** all timing logic uses GSI `map.clock_time` (the displayed game clock, integer seconds; negative before horn), never wall-clock.
- **Python:** 3.11+. **Pydantic:** v2 API (`model_dump`, `BaseModel`). **Node:** 18+ for Vite.
- **Project root:** `/home/tahseen-dar/Projects/dota2-live-helper`. Engine under `engine/`, dashboard under `dashboard/`, helper scripts under `scripts/`.
- **GSI install path (Linux native Steam):** `~/.local/share/Steam/steamapps/common/dota 2 beta/game/dota/cfg/gamestate_integration/gamestate_integration_helper.cfg`.

---

## File Structure

```
dota2-live-helper/
  engine/
    requirements.txt
    app/
      __init__.py
      config.py              # Settings (ports, account id, dota cfg path)
      state.py               # GameState + sub-models (Pydantic)
      gsi.py                 # raw GSI dict -> GameState
      hub.py                 # WebSocket connection manager / broadcast
      advice.py              # AdvicePayload model + build_advice(state)
      timing_constants.py    # the 7.41d periodic-event table (data only)
      modules/
        __init__.py
        timings.py           # pure timing math (PeriodicEvent, next_occurrences)
      main.py                # FastAPI app: /gsi, /ws, static mount, wiring
    tests/
      __init__.py
      conftest.py
      fixtures/
        gsi_early_game.json  # representative GSI player payload
      test_gsi.py
      test_timings.py
      test_advice.py
      test_endpoints.py
  dashboard/
    package.json
    vite.config.js
    index.html
    src/
      main.js                # boot: connect WS, mount panels
      ws.js                  # reconnecting WebSocket client
      panels/timings.js      # render the timings panel
      style.css
  scripts/
    install_gsi_config.sh    # write the GSI cfg into the Dota dir
    replay_gsi.py            # replay a fixture JSON into /gsi for offline testing
  README.md
```

---

### Task 1: Engine scaffold + `/gsi` endpoint accepting GSI POSTs

**Files:**
- Create: `engine/requirements.txt`
- Create: `engine/app/__init__.py` (empty)
- Create: `engine/app/config.py`
- Create: `engine/app/state.py`
- Create: `engine/app/main.py`
- Create: `engine/tests/__init__.py` (empty)
- Create: `engine/tests/conftest.py`
- Test: `engine/tests/test_endpoints.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces:
  - `app.config.Settings` with attrs `host: str = "127.0.0.1"`, `port: int = 3000`, `account_id: str | None = None`, `dota_cfg_dir: str`.
  - `app.config.get_settings() -> Settings`.
  - `app.state.GameState` Pydantic model with at least `clock_time: int | None = None` and `raw: dict = {}`; method `update_from_raw(raw: dict) -> None` (full parsing added in Task 2; here it just stores `raw` and copies `raw["map"]["clock_time"]` if present).
  - `app.main.app` (FastAPI), `app.main.STATE` (module-level `GameState`), `POST /gsi` returns `{"ok": true}` and updates `STATE`.

- [ ] **Step 1: Write requirements file**

`engine/requirements.txt`:
```
fastapi==0.115.*
uvicorn[standard]==0.32.*
pydantic==2.*
pytest==8.*
httpx==0.27.*
```

- [ ] **Step 2: Create config module**

`engine/app/config.py`:
```python
from functools import lru_cache
from pathlib import Path
from pydantic import BaseModel


class Settings(BaseModel):
    host: str = "127.0.0.1"
    port: int = 3000
    account_id: str | None = None
    dota_cfg_dir: str = str(
        Path.home()
        / ".local/share/Steam/steamapps/common/dota 2 beta"
        / "game/dota/cfg/gamestate_integration"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 3: Create minimal GameState**

`engine/app/state.py`:
```python
from pydantic import BaseModel, Field


class GameState(BaseModel):
    clock_time: int | None = None
    raw: dict = Field(default_factory=dict)

    def update_from_raw(self, raw: dict) -> None:
        self.raw = raw
        clock = raw.get("map", {}).get("clock_time")
        if isinstance(clock, int):
            self.clock_time = clock
```

- [ ] **Step 4: Create FastAPI app with `/gsi`**

`engine/app/main.py`:
```python
from fastapi import FastAPI, Request
from app.state import GameState

app = FastAPI(title="Dota 2 Live Helper")
STATE = GameState()


@app.post("/gsi")
async def gsi(request: Request) -> dict:
    raw = await request.json()
    STATE.update_from_raw(raw)
    return {"ok": True}
```

- [ ] **Step 5: Write the failing test**

`engine/tests/conftest.py`:
```python
import sys
from pathlib import Path

# Make `app` importable when running pytest from engine/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
```

`engine/tests/test_endpoints.py`:
```python
from fastapi.testclient import TestClient
from app.main import app, STATE


def test_gsi_accepts_post_and_updates_clock():
    client = TestClient(app)
    payload = {"map": {"clock_time": 95}}
    resp = client.post("/gsi", json=payload)
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    assert STATE.clock_time == 95
```

- [ ] **Step 6: Run test to verify it fails**

Run: `cd engine && python -m pytest tests/test_endpoints.py -v`
Expected: FAIL (collection error / ModuleNotFoundError) before deps installed, then after `pip install -r requirements.txt` it should PASS. Install first: `cd engine && python -m pip install -r requirements.txt`.

- [ ] **Step 7: Run test to verify it passes**

Run: `cd engine && python -m pytest tests/test_endpoints.py -v`
Expected: PASS (1 passed).

- [ ] **Step 8: Commit**

```bash
cd /home/tahseen-dar/Projects/dota2-live-helper
git add engine
git commit -m "feat(engine): scaffold FastAPI app with /gsi endpoint"
```

---

### Task 2: Parse GSI payload into a structured GameState

**Files:**
- Modify: `engine/app/state.py`
- Create: `engine/app/gsi.py`
- Create: `engine/tests/fixtures/gsi_early_game.json`
- Test: `engine/tests/test_gsi.py`

**Interfaces:**
- Consumes: `GameState` from Task 1.
- Produces:
  - Sub-models on `app.state`: `HeroState(name: str | None, level: int | None, alive: bool | None, buyback_cost: int | None, buyback_cooldown: int | None)`, `PlayerState(gold: int | None, gpm: int | None, xpm: int | None)`, `MapState(clock_time: int | None, game_state: str | None, daytime: bool | None)`.
  - `GameState` gains `map: MapState`, `hero: HeroState`, `player: PlayerState`, `items: list[str]` (item names in slots 0–8, skipping empty), and keeps `clock_time` as a convenience mirror of `map.clock_time`.
  - `app.gsi.parse_gsi(raw: dict) -> GameState` returning a fully populated `GameState`.
  - `GameState.update_from_raw(raw)` now delegates to `parse_gsi` and copies fields onto self.

- [ ] **Step 1: Add the fixture (representative GSI player payload)**

`engine/tests/fixtures/gsi_early_game.json`:
```json
{
  "provider": {"name": "Dota 2", "appid": 570, "version": 47, "timestamp": 1700000000},
  "map": {
    "name": "start",
    "matchid": "7654321000",
    "game_time": 130,
    "clock_time": 95,
    "daytime": true,
    "game_state": "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS",
    "paused": false,
    "win_team": "none"
  },
  "player": {
    "steamid": "76561198000000000",
    "name": "tahseen",
    "activity": "playing",
    "kills": 1, "deaths": 0, "assists": 2,
    "last_hits": 20, "denies": 3,
    "gold": 1500, "gold_reliable": 300, "gold_unreliable": 1200,
    "gpm": 380, "xpm": 420
  },
  "hero": {
    "id": 35,
    "name": "npc_dota_hero_sniper",
    "level": 6,
    "alive": true,
    "respawn_seconds": 0,
    "buyback_cost": 300,
    "buyback_cooldown": 0,
    "health": 820, "max_health": 820,
    "mana": 300, "max_mana": 300
  },
  "items": {
    "slot0": {"name": "item_phase_boots", "purchaser": 0},
    "slot1": {"name": "item_magic_wand", "purchaser": 0},
    "slot2": {"name": "empty"},
    "slot3": {"name": "empty"},
    "slot4": {"name": "empty"},
    "slot5": {"name": "empty"}
  }
}
```

- [ ] **Step 2: Write the failing test**

`engine/tests/test_gsi.py`:
```python
import json
from pathlib import Path
from app.gsi import parse_gsi

FIX = Path(__file__).parent / "fixtures" / "gsi_early_game.json"


def test_parse_gsi_populates_state():
    raw = json.loads(FIX.read_text())
    state = parse_gsi(raw)
    assert state.map.clock_time == 95
    assert state.clock_time == 95
    assert state.map.daytime is True
    assert state.hero.name == "npc_dota_hero_sniper"
    assert state.hero.level == 6
    assert state.hero.buyback_cost == 300
    assert state.player.gold == 1500
    assert state.items == ["item_phase_boots", "item_magic_wand"]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd engine && python -m pytest tests/test_gsi.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.gsi'`.

- [ ] **Step 4: Expand state models**

Replace `engine/app/state.py` with:
```python
from pydantic import BaseModel, Field


class MapState(BaseModel):
    clock_time: int | None = None
    game_state: str | None = None
    daytime: bool | None = None


class HeroState(BaseModel):
    name: str | None = None
    level: int | None = None
    alive: bool | None = None
    buyback_cost: int | None = None
    buyback_cooldown: int | None = None


class PlayerState(BaseModel):
    gold: int | None = None
    gpm: int | None = None
    xpm: int | None = None


class GameState(BaseModel):
    clock_time: int | None = None
    map: MapState = Field(default_factory=MapState)
    hero: HeroState = Field(default_factory=HeroState)
    player: PlayerState = Field(default_factory=PlayerState)
    items: list[str] = Field(default_factory=list)
    raw: dict = Field(default_factory=dict)

    def update_from_raw(self, raw: dict) -> None:
        from app.gsi import parse_gsi

        fresh = parse_gsi(raw)
        self.clock_time = fresh.clock_time
        self.map = fresh.map
        self.hero = fresh.hero
        self.player = fresh.player
        self.items = fresh.items
        self.raw = raw
```

- [ ] **Step 5: Implement the parser**

`engine/app/gsi.py`:
```python
from app.state import GameState, MapState, HeroState, PlayerState


def parse_gsi(raw: dict) -> GameState:
    m = raw.get("map", {}) or {}
    h = raw.get("hero", {}) or {}
    p = raw.get("player", {}) or {}
    items_obj = raw.get("items", {}) or {}

    items: list[str] = []
    for i in range(9):  # slot0..slot8 are inventory
        slot = items_obj.get(f"slot{i}")
        if slot and slot.get("name") and slot["name"] != "empty":
            items.append(slot["name"])

    map_state = MapState(
        clock_time=m.get("clock_time"),
        game_state=m.get("game_state"),
        daytime=m.get("daytime"),
    )
    return GameState(
        clock_time=m.get("clock_time"),
        map=map_state,
        hero=HeroState(
            name=h.get("name"),
            level=h.get("level"),
            alive=h.get("alive"),
            buyback_cost=h.get("buyback_cost"),
            buyback_cooldown=h.get("buyback_cooldown"),
        ),
        player=PlayerState(
            gold=p.get("gold"),
            gpm=p.get("gpm"),
            xpm=p.get("xpm"),
        ),
        items=items,
    )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd engine && python -m pytest tests/test_gsi.py tests/test_endpoints.py -v`
Expected: PASS (all).

- [ ] **Step 7: Commit**

```bash
cd /home/tahseen-dar/Projects/dota2-live-helper
git add engine
git commit -m "feat(engine): parse GSI payload into structured GameState"
```

---

### Task 3: Timing engine (pure math, no I/O)

**Files:**
- Create: `engine/app/modules/__init__.py` (empty)
- Create: `engine/app/modules/timings.py`
- Test: `engine/tests/test_timings.py`

**Interfaces:**
- Consumes: nothing (pure module).
- Produces:
  - `PeriodicEvent(BaseModel)` with `name: str`, `first_spawn_s: int`, `interval_s: int | None` (None = one-shot), `end_s: int | None = None`, `category: str`.
  - `TimingHit(BaseModel)` with `name: str`, `category: str`, `next_time_s: int`, `seconds_until: int`.
  - `next_occurrences(now_s: int, events: list[PeriodicEvent]) -> list[TimingHit]` — for each event, the soonest spawn at or after `now_s` (skips events whose window has ended or that never recur after `now_s`), sorted by `seconds_until` ascending.

- [ ] **Step 1: Write the failing tests**

`engine/tests/test_timings.py`:
```python
from app.modules.timings import PeriodicEvent, next_occurrences


def ev(name, first, interval, end=None, cat="test"):
    return PeriodicEvent(name=name, first_spawn_s=first, interval_s=interval, end_s=end, category=cat)


def test_periodic_before_first_spawn():
    hits = next_occurrences(0, [ev("bounty", 0, 180)])
    assert hits[0].next_time_s == 0
    assert hits[0].seconds_until == 0


def test_periodic_midcycle_rounds_up():
    hits = next_occurrences(200, [ev("bounty", 0, 180)])
    # spawns at 0,180,360 -> soonest >= 200 is 360
    assert hits[0].next_time_s == 360
    assert hits[0].seconds_until == 160


def test_oneshot_in_future():
    hits = next_occurrences(100, [ev("first_neutral", 420, None)])
    assert hits[0].next_time_s == 420
    assert hits[0].seconds_until == 320


def test_oneshot_in_past_is_dropped():
    hits = next_occurrences(500, [ev("first_neutral", 420, None)])
    assert hits == []


def test_window_end_drops_event():
    # water runes only at 120 and 240, window ends at 240
    hits = next_occurrences(300, [ev("water", 120, 120, end=240)])
    assert hits == []


def test_sorted_by_soonest():
    events = [ev("a", 0, 300), ev("b", 0, 120)]
    hits = next_occurrences(50, events)
    assert [h.name for h in hits] == ["b", "a"]  # b next at 120, a next at 300
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd engine && python -m pytest tests/test_timings.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.modules.timings'`.

- [ ] **Step 3: Implement the timing engine**

`engine/app/modules/timings.py`:
```python
from pydantic import BaseModel


class PeriodicEvent(BaseModel):
    name: str
    first_spawn_s: int
    interval_s: int | None = None  # None => one-shot
    end_s: int | None = None       # last second the event can occur (inclusive)
    category: str = "general"


class TimingHit(BaseModel):
    name: str
    category: str
    next_time_s: int
    seconds_until: int


def _next_time(now_s: int, e: PeriodicEvent) -> int | None:
    if e.interval_s is None:
        t = e.first_spawn_s
        return t if t >= now_s else None
    if now_s <= e.first_spawn_s:
        t = e.first_spawn_s
    else:
        elapsed = now_s - e.first_spawn_s
        steps = (elapsed + e.interval_s - 1) // e.interval_s  # ceil
        t = e.first_spawn_s + steps * e.interval_s
    if e.end_s is not None and t > e.end_s:
        return None
    return t


def next_occurrences(now_s: int, events: list[PeriodicEvent]) -> list[TimingHit]:
    hits: list[TimingHit] = []
    for e in events:
        t = _next_time(now_s, e)
        if t is None:
            continue
        hits.append(
            TimingHit(
                name=e.name,
                category=e.category,
                next_time_s=t,
                seconds_until=t - now_s,
            )
        )
    hits.sort(key=lambda h: h.seconds_until)
    return hits
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd engine && python -m pytest tests/test_timings.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
cd /home/tahseen-dar/Projects/dota2-live-helper
git add engine
git commit -m "feat(engine): pure timing engine with periodic/one-shot events"
```

---

### Task 4: Timing constants table (7.41d) + verification note

**Files:**
- Create: `engine/app/timing_constants.py`
- Test: `engine/tests/test_timings.py` (append)

**Interfaces:**
- Consumes: `PeriodicEvent` from Task 3.
- Produces: `app.timing_constants.GAME_EVENTS: list[PeriodicEvent]`.

> **Verification requirement (do not skip):** before committing, cross-check every constant
> below against `../dota2-knowledge-base/game-data-and-formulas.md` and, where possible, the
> live client. The values below are the 7.41d-era defaults; correct any that disagree and
> note the source in a comment. The math is already tested in Task 3 — this task is about the
> data being right.

- [ ] **Step 1: Write the constants table**

`engine/app/timing_constants.py`:
```python
"""Patch 7.41d periodic-event timings, in seconds of game clock_time.

Cross-checked against ../dota2-knowledge-base. Correct here if the client disagrees;
the timing math (modules/timings.py) is patch-agnostic and tested separately.
"""
from app.modules.timings import PeriodicEvent

GAME_EVENTS: list[PeriodicEvent] = [
    # Bounty runes: at 0:00, then every 3:00.
    PeriodicEvent(name="Bounty runes", first_spawn_s=0, interval_s=180, category="rune"),
    # Water runes: 2:00 and 4:00 only.
    PeriodicEvent(name="Water rune", first_spawn_s=120, interval_s=120, end_s=240, category="rune"),
    # Power runes: every 2:00 from 6:00.
    PeriodicEvent(name="Power rune", first_spawn_s=360, interval_s=120, category="rune"),
    # Wisdom runes: 7:00, then every 7:00.
    PeriodicEvent(name="Wisdom rune", first_spawn_s=420, interval_s=420, category="rune"),
    # Lotus pool: every 3:00 from 3:00.
    PeriodicEvent(name="Lotus", first_spawn_s=180, interval_s=180, category="lotus"),
    # Neutral item tiers (one-shot unlocks).
    PeriodicEvent(name="Neutral T1", first_spawn_s=420, interval_s=None, category="neutral"),
    PeriodicEvent(name="Neutral T2", first_spawn_s=1020, interval_s=None, category="neutral"),
    PeriodicEvent(name="Neutral T3", first_spawn_s=1620, interval_s=None, category="neutral"),
    PeriodicEvent(name="Neutral T4", first_spawn_s=2220, interval_s=None, category="neutral"),
    PeriodicEvent(name="Neutral T5", first_spawn_s=3600, interval_s=None, category="neutral"),
    # Day/night flips every 5:00; first night at 5:00.
    PeriodicEvent(name="Night/Day flip", first_spawn_s=300, interval_s=300, category="cycle"),
    # Camp stack window (pull at x:53 every minute, from 1:53).
    PeriodicEvent(name="Stack camp", first_spawn_s=113, interval_s=60, category="stack"),
]
```

- [ ] **Step 2: Write a sanity test for the table**

Append to `engine/tests/test_timings.py`:
```python
from app.timing_constants import GAME_EVENTS
from app.modules.timings import next_occurrences


def test_constants_produce_sorted_upcoming_events_at_5min():
    hits = next_occurrences(300, GAME_EVENTS)  # at clock 5:00
    assert hits, "expected upcoming events at 5:00"
    # sorted ascending and all in the future-or-now
    assert all(h.seconds_until >= 0 for h in hits)
    assert hits == sorted(hits, key=lambda h: h.seconds_until)
    names = {h.name for h in hits}
    assert "Power rune" in names  # next power rune at 6:00 -> 60s away
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `cd engine && python -m pytest tests/test_timings.py -v`
Expected: PASS (7 passed).

- [ ] **Step 4: Commit**

```bash
cd /home/tahseen-dar/Projects/dota2-live-helper
git add engine
git commit -m "feat(engine): add 7.41d timing constants table"
```

---

### Task 5: Advice aggregator — combine module output into one payload

**Files:**
- Create: `engine/app/advice.py`
- Test: `engine/tests/test_advice.py`

**Interfaces:**
- Consumes: `GameState` (Task 2), `next_occurrences`/`TimingHit` (Task 3), `GAME_EVENTS` (Task 4).
- Produces:
  - `AdvicePayload(BaseModel)` with `clock_time: int | None`, `connected: bool = True`, `timings: list[TimingHit]`.
  - `build_advice(state: GameState, *, horizon_s: int = 600, limit: int = 6) -> AdvicePayload` — returns the next `limit` timing events within `horizon_s` seconds; empty timings when `state.clock_time is None`.

- [ ] **Step 1: Write the failing test**

`engine/tests/test_advice.py`:
```python
from app.state import GameState
from app.advice import build_advice


def test_build_advice_returns_upcoming_timings():
    state = GameState(clock_time=300)
    state.map.clock_time = 300
    payload = build_advice(state, horizon_s=600, limit=6)
    assert payload.clock_time == 300
    assert len(payload.timings) <= 6
    assert payload.timings == sorted(payload.timings, key=lambda h: h.seconds_until)
    assert all(h.seconds_until <= 600 for h in payload.timings)


def test_build_advice_no_clock_yields_empty():
    payload = build_advice(GameState())
    assert payload.clock_time is None
    assert payload.timings == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && python -m pytest tests/test_advice.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.advice'`.

- [ ] **Step 3: Implement the aggregator**

`engine/app/advice.py`:
```python
from pydantic import BaseModel, Field
from app.state import GameState
from app.modules.timings import TimingHit, next_occurrences
from app.timing_constants import GAME_EVENTS


class AdvicePayload(BaseModel):
    clock_time: int | None = None
    connected: bool = True
    timings: list[TimingHit] = Field(default_factory=list)


def build_advice(state: GameState, *, horizon_s: int = 600, limit: int = 6) -> AdvicePayload:
    if state.clock_time is None:
        return AdvicePayload(clock_time=None, timings=[])
    hits = next_occurrences(state.clock_time, GAME_EVENTS)
    hits = [h for h in hits if h.seconds_until <= horizon_s][:limit]
    return AdvicePayload(clock_time=state.clock_time, timings=hits)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd engine && python -m pytest tests/test_advice.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
cd /home/tahseen-dar/Projects/dota2-live-helper
git add engine
git commit -m "feat(engine): advice aggregator combining timing module output"
```

---

### Task 6: WebSocket hub + broadcast advice on every GSI update

**Files:**
- Create: `engine/app/hub.py`
- Modify: `engine/app/main.py`
- Test: `engine/tests/test_endpoints.py` (append)

**Interfaces:**
- Consumes: `AdvicePayload`/`build_advice` (Task 5), `GameState` (Task 2).
- Produces:
  - `app.hub.Hub` with `async connect(ws)`, `disconnect(ws)`, `async broadcast(message: dict)`, and attribute `last: dict | None` (last broadcast payload, replayed to new clients on connect).
  - `app.main` exposes `HUB = Hub()`, a `GET /ws` WebSocket route, and `/gsi` now builds advice and broadcasts it.

- [ ] **Step 1: Implement the hub**

`engine/app/hub.py`:
```python
from fastapi import WebSocket


class Hub:
    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()
        self.last: dict | None = None

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.clients.add(ws)
        if self.last is not None:
            await ws.send_json(self.last)

    def disconnect(self, ws: WebSocket) -> None:
        self.clients.discard(ws)

    async def broadcast(self, message: dict) -> None:
        self.last = message
        dead = []
        for ws in self.clients:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)
```

- [ ] **Step 2: Wire hub + advice into main**

Replace `engine/app/main.py` with:
```python
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from app.state import GameState
from app.advice import build_advice
from app.hub import Hub

app = FastAPI(title="Dota 2 Live Helper")
STATE = GameState()
HUB = Hub()


@app.post("/gsi")
async def gsi(request: Request) -> dict:
    raw = await request.json()
    STATE.update_from_raw(raw)
    payload = build_advice(STATE).model_dump()
    await HUB.broadcast(payload)
    return {"ok": True}


@app.websocket("/ws")
async def ws(websocket: WebSocket) -> None:
    await HUB.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # we don't expect client messages; keeps it open
    except WebSocketDisconnect:
        HUB.disconnect(websocket)
```

- [ ] **Step 3: Write the failing test**

Append to `engine/tests/test_endpoints.py`:
```python
import json
from pathlib import Path

FIX = Path(__file__).parent / "fixtures" / "gsi_early_game.json"


def test_ws_receives_advice_after_gsi_post():
    client = TestClient(app)
    with client.websocket_connect("/ws") as websocket:
        raw = json.loads(FIX.read_text())
        resp = client.post("/gsi", json=raw)
        assert resp.status_code == 200
        data = websocket.receive_json()
        assert data["clock_time"] == 95
        assert isinstance(data["timings"], list)
        assert len(data["timings"]) >= 1
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd engine && python -m pytest tests -v`
Expected: PASS (all tests across files).

- [ ] **Step 5: Commit**

```bash
cd /home/tahseen-dar/Projects/dota2-live-helper
git add engine
git commit -m "feat(engine): WebSocket hub broadcasting advice on GSI update"
```

---

### Task 7: Offline replay script + GSI config installer

**Files:**
- Create: `scripts/replay_gsi.py`
- Create: `scripts/install_gsi_config.sh`
- Test: `engine/tests/test_endpoints.py` (append a replay-shaped test)

**Interfaces:**
- Consumes: the running engine's `/gsi` endpoint (HTTP). For the test, the in-process `TestClient`.
- Produces:
  - `scripts/replay_gsi.py` CLI: `python scripts/replay_gsi.py <fixture.json> [--url http://127.0.0.1:3000/gsi] [--clock N] [--repeat K --interval S]` — POSTs the fixture (optionally overriding `map.clock_time`) to the engine; used to drive the pipeline without being in a live game.
  - `scripts/install_gsi_config.sh`: writes `gamestate_integration_helper.cfg` into the Dota cfg dir (creating it if missing), pointing at `http://127.0.0.1:3000/gsi`.

- [ ] **Step 1: Write the replay script**

`scripts/replay_gsi.py`:
```python
#!/usr/bin/env python3
"""Replay a recorded GSI fixture into the engine for offline testing."""
import argparse
import json
import time
import urllib.request


def post(url: str, payload: dict) -> int:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        return resp.status


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("fixture")
    ap.add_argument("--url", default="http://127.0.0.1:3000/gsi")
    ap.add_argument("--clock", type=int, default=None, help="override map.clock_time")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--interval", type=float, default=1.0)
    args = ap.parse_args()

    payload = json.loads(open(args.fixture).read())
    for i in range(args.repeat):
        if args.clock is not None:
            payload.setdefault("map", {})["clock_time"] = args.clock + i
        status = post(args.url, payload)
        print(f"POST {i+1}/{args.repeat} -> {status} (clock={payload.get('map', {}).get('clock_time')})")
        if i + 1 < args.repeat:
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Write the GSI installer**

`scripts/install_gsi_config.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail
CFG_DIR="${1:-$HOME/.local/share/Steam/steamapps/common/dota 2 beta/game/dota/cfg/gamestate_integration}"
mkdir -p "$CFG_DIR"
CFG_FILE="$CFG_DIR/gamestate_integration_helper.cfg"
cat > "$CFG_FILE" <<'EOF'
"Dota 2 Live Helper"
{
    "uri"           "http://127.0.0.1:3000/gsi"
    "timeout"       "5.0"
    "buffer"        "0.1"
    "throttle"      "0.1"
    "heartbeat"     "30.0"
    "data"
    {
        "provider"      "1"
        "map"           "1"
        "player"        "1"
        "hero"          "1"
        "abilities"     "1"
        "items"         "1"
    }
}
EOF
echo "Wrote $CFG_FILE"
```

- [ ] **Step 3: Make scripts executable + write a replay-shaped test**

Run: `chmod +x scripts/replay_gsi.py scripts/install_gsi_config.sh`

Append to `engine/tests/test_endpoints.py`:
```python
def test_replay_shape_clock_override_changes_advice():
    client = TestClient(app)
    raw = json.loads(FIX.read_text())
    raw["map"]["clock_time"] = 360  # power rune is due now
    with client.websocket_connect("/ws") as websocket:
        client.post("/gsi", json=raw)
        data = websocket.receive_json()
        assert data["clock_time"] == 360
        names = [t["name"] for t in data["timings"]]
        assert "Power rune" in names
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd engine && python -m pytest tests -v`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
cd /home/tahseen-dar/Projects/dota2-live-helper
git add engine scripts
git commit -m "feat(scripts): GSI replay tool + config installer"
```

---

### Task 8: Dashboard (Vite + vanilla JS) with live timings panel

**Files:**
- Create: `dashboard/package.json`
- Create: `dashboard/vite.config.js`
- Create: `dashboard/index.html`
- Create: `dashboard/src/main.js`
- Create: `dashboard/src/ws.js`
- Create: `dashboard/src/panels/timings.js`
- Create: `dashboard/src/style.css`

**Interfaces:**
- Consumes: the engine WebSocket at `ws://127.0.0.1:3000/ws` emitting `AdvicePayload` JSON (`clock_time`, `connected`, `timings[]` of `{name, category, next_time_s, seconds_until}`).
- Produces: a single page that renders a connection indicator and a live, sorted timings list with mm:ss countdowns.

- [ ] **Step 1: Create package + Vite config**

`dashboard/package.json`:
```json
{
  "name": "dota2-live-helper-dashboard",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite --port 5173",
    "build": "vite build",
    "preview": "vite preview"
  },
  "devDependencies": {
    "vite": "^5.4.0"
  }
}
```

`dashboard/vite.config.js`:
```js
import { defineConfig } from "vite";

export default defineConfig({
  build: { outDir: "dist", emptyOutDir: true },
});
```

- [ ] **Step 2: Create the page shell**

`dashboard/index.html`:
```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Dota 2 Live Helper</title>
    <link rel="stylesheet" href="/src/style.css" />
  </head>
  <body>
    <header>
      <h1>Live Helper</h1>
      <span id="status" class="status off">disconnected</span>
      <span id="clock" class="clock">--:--</span>
    </header>
    <main>
      <section id="timings-panel" class="panel">
        <h2>Timings</h2>
        <ul id="timings-list"></ul>
      </section>
    </main>
    <script type="module" src="/src/main.js"></script>
  </body>
</html>
```

- [ ] **Step 3: Create the WebSocket client**

`dashboard/src/ws.js`:
```js
// Reconnecting WebSocket: calls onMessage(payload) and onStatus(bool).
export function connect(url, onMessage, onStatus) {
  let ws;
  const open = () => {
    ws = new WebSocket(url);
    ws.onopen = () => onStatus(true);
    ws.onclose = () => {
      onStatus(false);
      setTimeout(open, 1000);
    };
    ws.onerror = () => ws.close();
    ws.onmessage = (e) => {
      try {
        onMessage(JSON.parse(e.data));
      } catch (_) {}
    };
  };
  open();
}
```

- [ ] **Step 4: Create the timings panel renderer**

`dashboard/src/panels/timings.js`:
```js
function mmss(total) {
  const s = Math.max(0, total);
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}:${String(r).padStart(2, "0")}`;
}

export function renderTimings(payload) {
  const list = document.getElementById("timings-list");
  list.innerHTML = "";
  for (const t of payload.timings || []) {
    const li = document.createElement("li");
    li.className = `timing cat-${t.category}`;
    li.innerHTML = `<span class="name">${t.name}</span>
                    <span class="eta">${mmss(t.seconds_until)}</span>`;
    list.appendChild(li);
  }
}

export function renderClock(payload) {
  const clock = document.getElementById("clock");
  clock.textContent = payload.clock_time == null ? "--:--" : mmss(payload.clock_time);
}
```

- [ ] **Step 5: Wire it together in main.js**

`dashboard/src/main.js`:
```js
import { connect } from "./ws.js";
import { renderTimings, renderClock } from "./panels/timings.js";

const WS_URL = `ws://${location.hostname || "127.0.0.1"}:3000/ws`;
const statusEl = document.getElementById("status");

function onStatus(up) {
  statusEl.textContent = up ? "connected" : "disconnected";
  statusEl.className = `status ${up ? "on" : "off"}`;
}

function onMessage(payload) {
  renderClock(payload);
  renderTimings(payload);
}

connect(WS_URL, onMessage, onStatus);
```

- [ ] **Step 6: Add styling**

`dashboard/src/style.css`:
```css
:root { color-scheme: dark; }
body { margin: 0; font: 16px/1.4 system-ui, sans-serif; background: #11141a; color: #e6e6e6; }
header { display: flex; gap: 1rem; align-items: center; padding: .75rem 1rem; background: #0b0d11; }
h1 { font-size: 1.1rem; margin: 0; }
.status { font-size: .8rem; padding: .15rem .5rem; border-radius: 999px; }
.status.on { background: #16331c; color: #6ee787; }
.status.off { background: #331616; color: #ff7b7b; }
.clock { margin-left: auto; font-variant-numeric: tabular-nums; font-size: 1.2rem; }
.panel { padding: 1rem; }
#timings-list { list-style: none; margin: 0; padding: 0; }
.timing { display: flex; justify-content: space-between; padding: .4rem .6rem; border-bottom: 1px solid #20242c; }
.timing .eta { font-variant-numeric: tabular-nums; color: #9ecbff; }
.cat-rune .name::before { content: "🔵 "; }
.cat-neutral .name::before { content: "🟤 "; }
.cat-stack .name::before { content: "📦 "; }
.cat-lotus .name::before { content: "🌸 "; }
.cat-cycle .name::before { content: "🌗 "; }
```

- [ ] **Step 7: Install + manual smoke test**

Run:
```bash
cd dashboard && npm install
npm run dev    # serves on http://127.0.0.1:5173
```
In another terminal start the engine and replay a fixture:
```bash
cd engine && python -m uvicorn app.main:app --host 127.0.0.1 --port 3000 &
python ../scripts/replay_gsi.py tests/fixtures/gsi_early_game.json --clock 300 --repeat 5 --interval 1
```
Expected: the dashboard at :5173 shows status "connected", clock `5:00`, and a sorted timings list (Power rune, Stack camp, etc.) with mm:ss countdowns updating.

- [ ] **Step 8: Commit**

```bash
cd /home/tahseen-dar/Projects/dota2-live-helper
git add dashboard
git commit -m "feat(dashboard): Vite vanilla dashboard with live timings panel"
```

---

### Task 9: Single-process serving + README run instructions

**Files:**
- Modify: `engine/app/main.py`
- Create: `README.md`

**Interfaces:**
- Consumes: built dashboard at `dashboard/dist` (from `npm run build`).
- Produces: engine serves the built dashboard at `/` when `dashboard/dist` exists; `GET /` returns the dashboard `index.html`. CORS allowed for the Vite dev origin so dev mode keeps working.

- [ ] **Step 1: Mount static dashboard + dev CORS**

Replace the top of `engine/app/main.py` imports and app setup (keep the `/gsi` and `/ws` handlers from Task 6) with:
```python
from pathlib import Path
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.state import GameState
from app.advice import build_advice
from app.hub import Hub

app = FastAPI(title="Dota 2 Live Helper")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
STATE = GameState()
HUB = Hub()

_DIST = Path(__file__).resolve().parents[2] / "dashboard" / "dist"
```

Then, at the **end** of the file (after the `/ws` handler), mount static if built:
```python
if _DIST.exists():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="dashboard")
```

- [ ] **Step 2: Verify existing tests still pass**

Run: `cd engine && python -m pytest tests -v`
Expected: PASS (all). (Static mount is conditional and does not shadow `/gsi` or `/ws`.)

- [ ] **Step 3: Write the README**

`README.md`:
```markdown
# Dota 2 Live Helper

A VAC-safe, second-monitor assistant for climbing in Dota 2 (patch 7.41d).
Reads Valve's official Game State Integration (GSI) and shows live timings.
Built on top of ../dota2-knowledge-base.

## Setup (once)

```bash
# 1. Engine deps
cd engine && python -m pip install -r requirements.txt

# 2. Install the GSI config into Dota
../scripts/install_gsi_config.sh

# 3. Build the dashboard
cd ../dashboard && npm install && npm run build
```

## Run (each session)

```bash
cd engine && python -m uvicorn app.main:app --host 127.0.0.1 --port 3000
```

Open http://127.0.0.1:3000 on your second monitor. Launch Dota; once in a match,
timings appear live. (Restart Dota after first installing the GSI config.)

## Offline testing (no game needed)

```bash
python scripts/replay_gsi.py engine/tests/fixtures/gsi_early_game.json --clock 300 --repeat 10 --interval 1
```

## Tests

```bash
cd engine && python -m pytest tests -v
```
```

- [ ] **Step 4: Build dashboard and smoke test single-process**

Run:
```bash
cd dashboard && npm run build
cd ../engine && python -m uvicorn app.main:app --host 127.0.0.1 --port 3000 &
python ../scripts/replay_gsi.py tests/fixtures/gsi_early_game.json --clock 360 --repeat 5 --interval 1
```
Expected: visiting http://127.0.0.1:3000 (no Vite dev server running) shows the dashboard, connected, clock `6:00`, "Power rune" near the top.

- [ ] **Step 5: Commit**

```bash
cd /home/tahseen-dar/Projects/dota2-live-helper
git add engine README.md
git commit -m "feat(engine): serve built dashboard single-process + README"
```

---

## Subsequent plans (not in this plan)

Once P0+P1 is verified in a real match, each remaining pillar gets its own plan on this same backbone:
- **P2 — Build coach:** KB loader + OpenDota item/matchup cache + enemy quick-entry bar + `build_coach` module + dashboard panel.
- **P3 — Draft helper:** hero-select detection, counters/synergy/pocket-hero ranking, draft panel.
- **P4 — Win-prob / macro:** live observable-signal meter + post-game parsed-match learning.

## Self-Review

- **Spec coverage (this plan's scope = P0+P1):** GSI ingestion (Tasks 1–2) ✓; display-agnostic engine + advice objects (Tasks 3–5) ✓; WebSocket push (Task 6) ✓; second-monitor dashboard (Task 8) ✓; GSI config install (Task 7) ✓; replay-fixture testing strategy from spec §9 (Task 7) ✓; single-process run from spec §3 (Task 9) ✓; VAC-safety honored (no game-process access anywhere). Pillars P2–P4 intentionally deferred to their own plans per spec §8 sequencing.
- **Placeholder scan:** no TBD/TODO; every code step has complete code; the only "verify later" is the explicit, scoped constants-verification in Task 4, which is a real action with named sources, not a placeholder.
- **Type consistency:** `GameState`, `MapState`/`HeroState`/`PlayerState`, `PeriodicEvent`/`TimingHit`, `AdvicePayload`, `Hub`, `build_advice`, `next_occurrences` names and signatures are consistent across Tasks 1→9; the dashboard consumes exactly the `AdvicePayload` field names produced in Task 5.
```
