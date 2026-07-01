# Dota 2 Live Helper — P3 Draft Helper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a draft-helper pillar that ranks the player's pocket heroes against the entered enemy lineup (counter) and allies (synergy) using cached Herald-bracket Stratz data, degrading gracefully to win-rate-only when the cache is absent.

**Architecture:** A refresh script (the only Stratz client, keyed by `STRATZ_API_KEY`) writes a gitignored `matchups.json` cache. The engine stays keyless and offline: `matchups.py` loads the cache plus a committed Herald win-rate seed, and a `draft` advisor ranks pocket heroes from them. `POST /allies` mirrors `/enemies`; a dashboard draft panel + ally picker render `payload.draft`.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, pytest (engine); Vite + vanilla JS (dashboard). Refresh script uses stdlib `urllib` (no new runtime deps). Stratz GraphQL.

## Global Constraints

- **Patch 7.41d.** Base Herald win rates live in a committed seed `engine/app/data/herald_winrates.json`; counter/synergy come from the gitignored Stratz cache `engine/app/cache/matchups.json`. Data is JSON; advisors carry logic.
- **VAC-safe & keyless engine:** the engine and advisors NEVER call the network. Only `scripts/refresh_matchups.py` calls Stratz, reading `STRATZ_API_KEY` from the environment. Input is GSI + manual enemy/ally entry + cached public stats.
- **Offline tests:** no test performs a live network call. The Stratz response→cache transform is a pure function tested on a saved sample.
- **Display-agnostic engine:** advisors return Pydantic advice objects; no HTTP/WebSocket/DOM imports. `main.py` is the only HTTP/WS layer.
- **Graceful degradation:** with no cache, the draft advisor sets `has_data=false`, ranks by base win rate only, and emits a run-refresh `note`. Absence of a specific enemy/ally in the cache contributes nothing.
- **Hero keys are exact GSI internal keys** (legacy traps as in P2: Wraith King=`npc_dota_hero_skeleton_king`, Zeus=`npc_dota_hero_zuus`, Necrophos=`npc_dota_hero_necrolyte`, Timbersaw=`npc_dota_hero_shredder`, Windranger=`npc_dota_hero_windrunner`). The cache is keyed by hero KEY (ids converted at refresh time).
- **Pydantic v2** (`BaseModel`, `Field`, `model_validate`, alias for the reserved word `with`). **Python 3.11+.**
- **Run pytest from `engine/` via `.venv/bin/python`.** Post-P2 suite is 23 tests; must stay green.
- **Project root:** `/home/tahseen-dar/Projects/dota2-live-helper`.

---

## File Structure

```
engine/app/
  data/
    heroes.json              # regenerated to include numeric `id`
    herald_winrates.json     # committed seed: hero_key -> Herald base win rate (fraction)
  cache/matchups.json        # gitignored, written by refresh script (vs/with per hero, keyed by key)
  matchups.py                # HeroMatchups/MatchupData + load_matchups()
  advisors/
    context.py               # + ally_heroes, matchup_data
    draft.py                 # advise(ctx) -> DraftAdvice
  advice.py                  # load MATCHUP_DATA; AdvicePayload + draft field; call draft advisor
  state.py                   # GameState + ally_heroes
  main.py                    # + POST /allies
scripts/refresh_matchups.py  # Stratz client + pure transform (only network caller)
engine/tests/
  test_matchups.py
  test_refresh_transform.py
  test_draft.py
  test_allies_endpoint.py
dashboard/src/
  panels/draft.js
  panels/allies.js
  main.js, index.html, style.css
```

---

### Task 1: heroes.json +id, Herald win-rate seed, matchups loader

**Files:**
- Modify (regenerate): `engine/app/data/heroes.json`
- Create: `engine/app/data/herald_winrates.json`
- Create: `engine/app/matchups.py`
- Test: `engine/tests/test_matchups.py`

**Interfaces:**
- Produces (in `app.matchups`):
  - `HeroMatchups(BaseModel)` — `vs: dict[str, float] = {}`, `with_: dict[str, float] = {}` (alias `"with"`, `populate_by_name=True`).
  - `MatchupData(BaseModel)` — `has_data: bool`, `bracket: str | None = None`, `heroes: dict[str, HeroMatchups] = {}`, `base_winrates: dict[str, float] = {}`.
  - `CACHE_PATH: Path`, `SEED_PATH: Path`.
  - `load_matchups(cache_path: Path = CACHE_PATH, seed_path: Path = SEED_PATH) -> MatchupData` — always loads the seed into `base_winrates`; loads the cache (`vs`/`with`) if the file exists (`has_data=True`), else `has_data=False` with empty `heroes`.

- [ ] **Step 1: Regenerate heroes.json with id (deterministic)**

Run from project root (adjust the KB path if needed):
```bash
jq '[.[] | {id: .id, key: .name, display: .localized_name}]' \
  ../dota2-knowledge-base/raw-data/heroes.json > engine/app/data/heroes.json
jq 'length, .[0]' engine/app/data/heroes.json   # sanity: ~120+, first has id/key/display
```
Adding `id` is additive; the P2 `test_build_data` assertions use `key`/`display` and are unaffected.

- [ ] **Step 2: Write the Herald win-rate seed**

`engine/app/data/herald_winrates.json` (fractions; from `../dota2-knowledge-base/herald-climbing-heroes.md` where listed, else a neutral 0.50 flagged for the user to refine):
```json
{
  "npc_dota_hero_skeleton_king": 0.561,
  "npc_dota_hero_spectre": 0.553,
  "npc_dota_hero_necrolyte": 0.539,
  "npc_dota_hero_bristleback": 0.536,
  "npc_dota_hero_riki": 0.520,
  "npc_dota_hero_phantom_assassin": 0.520,
  "npc_dota_hero_techies": 0.516,
  "npc_dota_hero_zuus": 0.514,
  "npc_dota_hero_juggernaut": 0.514,
  "npc_dota_hero_sniper": 0.500,
  "npc_dota_hero_medusa": 0.500
}
```

- [ ] **Step 3: Write the failing tests**

`engine/tests/test_matchups.py`:
```python
import json
from pathlib import Path
from app.matchups import load_matchups, MatchupData, HeroMatchups


def test_missing_cache_still_loads_seed():
    md = load_matchups(cache_path=Path("/nonexistent/matchups.json"))
    assert md.has_data is False
    assert md.heroes == {}
    assert md.base_winrates["npc_dota_hero_skeleton_king"] == 0.561


def test_cache_parses_with_and_vs(tmp_path):
    cache = tmp_path / "matchups.json"
    cache.write_text(json.dumps({
        "bracket": "HERALD",
        "generated": "2026-07-01",
        "heroes": {
            "npc_dota_hero_skeleton_king": {
                "vs": {"npc_dota_hero_zuus": 0.58},
                "with": {"npc_dota_hero_lion": 0.55},
            }
        },
    }))
    md = load_matchups(cache_path=cache)
    assert md.has_data is True
    assert md.bracket == "HERALD"
    hm = md.heroes["npc_dota_hero_skeleton_king"]
    assert hm.vs["npc_dota_hero_zuus"] == 0.58
    assert hm.with_["npc_dota_hero_lion"] == 0.55
    assert md.base_winrates["npc_dota_hero_zuus"] == 0.514
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `cd engine && .venv/bin/python -m pytest tests/test_matchups.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.matchups'`.

- [ ] **Step 5: Implement the loader**

`engine/app/matchups.py`:
```python
import json
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict

CACHE_PATH = Path(__file__).parent / "cache" / "matchups.json"
SEED_PATH = Path(__file__).parent / "data" / "herald_winrates.json"


class HeroMatchups(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    vs: dict[str, float] = Field(default_factory=dict)
    with_: dict[str, float] = Field(default_factory=dict, alias="with")


class MatchupData(BaseModel):
    has_data: bool
    bracket: str | None = None
    heroes: dict[str, HeroMatchups] = Field(default_factory=dict)
    base_winrates: dict[str, float] = Field(default_factory=dict)


def load_matchups(cache_path: Path = CACHE_PATH, seed_path: Path = SEED_PATH) -> MatchupData:
    base = json.loads(seed_path.read_text())
    if not cache_path.exists():
        return MatchupData(has_data=False, base_winrates=base)
    raw = json.loads(cache_path.read_text())
    heroes = {k: HeroMatchups.model_validate(v) for k, v in raw.get("heroes", {}).items()}
    return MatchupData(
        has_data=True, bracket=raw.get("bracket"),
        heroes=heroes, base_winrates=base,
    )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd engine && .venv/bin/python -m pytest tests/test_matchups.py -v`
Expected: PASS (2 passed). Then full suite: `.venv/bin/python -m pytest tests -q` — all green.

- [ ] **Step 7: Commit**

```bash
cd /home/tahseen-dar/Projects/dota2-live-helper
git add engine/app/data/heroes.json engine/app/data/herald_winrates.json engine/app/matchups.py engine/tests/test_matchups.py
git commit -m "feat(engine): heroes.json ids, Herald win-rate seed, matchups loader"
```

---

### Task 2: Stratz refresh script + pure transform

**Files:**
- Create: `scripts/refresh_matchups.py`
- Test: `engine/tests/test_refresh_transform.py`

**Interfaces:**
- Produces (in `scripts/refresh_matchups.py`, importable for the transform test):
  - `transform_matchup(matchup: dict, id_to_key: dict[int, str]) -> dict` — given ONE hero's Stratz `matchUp` entry (`{"vs": [...], "with": [...]}`, each item `{heroId2, winCount, matchCount}`) and an id→key map, returns `{"vs": {key: winrate}, "with": {key: winrate}}`, skipping entries with `matchCount == 0` or an unknown id. `winrate = winCount / matchCount`.
  - `build_query(hero_id: int) -> tuple[str, dict]`, `fetch_matchup(hero_id, api_key) -> dict` (network — not unit-tested), and a `main()` that writes `engine/app/cache/matchups.json`.

> **Schema-verification note (do not skip):** the exact Stratz GraphQL field names and bracket
> enum must be confirmed against the live schema at `https://api.stratz.com/graphiql` (needs the
> user's key). The query below reflects Stratz's documented `heroStats.matchUp` shape
> (`vs`/`with` arrays of `{heroId2, winCount, matchCount}`, `bracketBasicIds: [HERALD]`). If the
> live schema differs, adjust `build_query` AND the sample in the transform test together — the
> transform logic (winCount/matchCount, id→key) stays the same. The implementer cannot run the
> live fetch (no key); that is the user's one-time step (README, Task documented below).

- [ ] **Step 1: Write the failing transform test**

`engine/tests/test_refresh_transform.py`:
```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from refresh_matchups import transform_matchup


def test_transform_maps_ids_to_keys_and_computes_winrate():
    matchup = {
        "vs": [
            {"heroId2": 22, "winCount": 58, "matchCount": 100},
            {"heroId2": 44, "winCount": 47, "matchCount": 100},
            {"heroId2": 99, "winCount": 5, "matchCount": 0},      # skip: no matches
            {"heroId2": 777, "winCount": 1, "matchCount": 2},     # skip: unknown id
        ],
        "with": [{"heroId2": 26, "winCount": 55, "matchCount": 100}],
    }
    id_to_key = {
        22: "npc_dota_hero_zuus",
        44: "npc_dota_hero_phantom_assassin",
        26: "npc_dota_hero_lion",
    }
    out = transform_matchup(matchup, id_to_key)
    assert out["vs"] == {
        "npc_dota_hero_zuus": 0.58,
        "npc_dota_hero_phantom_assassin": 0.47,
    }
    assert out["with"] == {"npc_dota_hero_lion": 0.55}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && .venv/bin/python -m pytest tests/test_refresh_transform.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'refresh_matchups'`.

- [ ] **Step 3: Implement the refresh script**

`scripts/refresh_matchups.py`:
```python
#!/usr/bin/env python3
"""Refresh Herald counter/synergy data from Stratz into engine/app/cache/matchups.json.

Only network caller in the project. Needs env STRATZ_API_KEY (free key from stratz.com).
Schema: verify against https://api.stratz.com/graphiql if Stratz changes field names.
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEROES = ROOT / "engine" / "app" / "data" / "heroes.json"
BUILDS = ROOT / "engine" / "app" / "data" / "builds"
CACHE = ROOT / "engine" / "app" / "cache" / "matchups.json"
STRATZ_URL = "https://api.stratz.com/graphql"


def transform_matchup(matchup: dict, id_to_key: dict[int, str]) -> dict:
    def conv(rows):
        out = {}
        for r in rows or []:
            mc = r.get("matchCount", 0)
            key = id_to_key.get(r.get("heroId2"))
            if mc and key:
                out[key] = round(r.get("winCount", 0) / mc, 4)
        return out
    return {"vs": conv(matchup.get("vs")), "with": conv(matchup.get("with"))}


def build_query(hero_id: int) -> tuple[str, dict]:
    query = """
    query M($h: Short!) {
      heroStats {
        matchUp(heroId: $h, take: 300, bracketBasicIds: [HERALD]) {
          heroId
          vs { heroId2 winCount matchCount }
          with { heroId2 winCount matchCount }
        }
      }
    }"""
    return query, {"h": hero_id}


def fetch_matchup(hero_id: int, api_key: str) -> dict:
    query, variables = build_query(hero_id)
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(
        STRATZ_URL, data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "STRATZ_API",  # Stratz requires a UA
        },
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())
    matchups = data["data"]["heroStats"]["matchUp"]
    return matchups[0] if matchups else {"vs": [], "with": []}


def main() -> None:
    api_key = os.environ.get("STRATZ_API_KEY")
    if not api_key:
        print("ERROR: set STRATZ_API_KEY (free key from stratz.com)", file=sys.stderr)
        sys.exit(1)
    heroes = json.loads(HEROES.read_text())
    key_to_id = {h["key"]: h["id"] for h in heroes}
    id_to_key = {h["id"]: h["key"] for h in heroes}
    pocket = [p.stem for p in sorted(BUILDS.glob("*.json"))]  # file stems, e.g. "skeleton_king"
    # map file stem -> hero key via display/build hero field
    pocket_keys = []
    for stem in pocket:
        build = json.loads((BUILDS / f"{stem}.json").read_text())
        pocket_keys.append(build["hero"])

    out_heroes = {}
    for hero_key in pocket_keys:
        hero_id = key_to_id.get(hero_key)
        if hero_id is None:
            print(f"  ! no id for {hero_key}, skipping", file=sys.stderr)
            continue
        matchup = fetch_matchup(hero_id, api_key)
        out_heroes[hero_key] = transform_matchup(matchup, id_to_key)
        print(f"  ✓ {hero_key}")

    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(
        {"bracket": "HERALD", "generated": "run-date", "heroes": out_heroes}, indent=2))
    print(f"Wrote {CACHE} ({len(out_heroes)} heroes)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Make executable, run the transform test, and verify no live call in tests**

Run:
```bash
chmod +x scripts/refresh_matchups.py
cd engine && .venv/bin/python -m pytest tests/test_refresh_transform.py -v
```
Expected: PASS (1 passed). The test imports only `transform_matchup` (pure) — no network.

- [ ] **Step 5: Commit**

```bash
cd /home/tahseen-dar/Projects/dota2-live-helper
git add scripts/refresh_matchups.py engine/tests/test_refresh_transform.py
git commit -m "feat(scripts): Stratz matchup refresh + pure transform"
```

---

### Task 3: The `draft` advisor

**Files:**
- Modify: `engine/app/advisors/context.py` (add `ally_heroes`, `matchup_data`)
- Create: `engine/app/advisors/draft.py`
- Test: `engine/tests/test_draft.py`

**Interfaces:**
- Consumes: `AdviceContext`, `MatchupData`/`HeroMatchups`.
- Produces (in `app.advisors.draft`):
  - `DraftPick(BaseModel)` — `hero: str`, `display: str`, `score: float`, `base_winrate: float | None`, `counter: float | None`, `synergy: float | None`, `reasons: list[str]`, `countered: bool`.
  - `DraftAdvice(BaseModel)` — `has_data: bool`, `bracket: str | None`, `note: str | None`, `picks: list[DraftPick]`.
  - `advise(ctx: AdviceContext) -> DraftAdvice`.
- Extends `AdviceContext` with `ally_heroes: list[str] = field(default_factory=list)` and `matchup_data: object | None = None`.

- [ ] **Step 1: Extend the context**

Append two fields to the `AdviceContext` dataclass in `engine/app/advisors/context.py` (after `hero_names`):
```python
    ally_heroes: list[str] = field(default_factory=list)
    matchup_data: object | None = None
```

- [ ] **Step 2: Write the failing tests**

`engine/tests/test_draft.py`:
```python
from app.state import GameState
from app.advisors.context import AdviceContext
from app.advisors import draft
from app.matchups import MatchupData, HeroMatchups


def _ctx(enemies=None, allies=None, has_data=True):
    heroes = {
        "npc_dota_hero_skeleton_king": HeroMatchups(
            vs={"npc_dota_hero_zuus": 0.58, "npc_dota_hero_phantom_assassin": 0.45},
            **{"with": {"npc_dota_hero_lion": 0.55}},
        ),
        "npc_dota_hero_riki": HeroMatchups(
            vs={"npc_dota_hero_zuus": 0.49}, **{"with": {}},
        ),
    }
    md = MatchupData(
        has_data=has_data, bracket="HERALD", heroes=(heroes if has_data else {}),
        base_winrates={"npc_dota_hero_skeleton_king": 0.561, "npc_dota_hero_riki": 0.520},
    )
    return AdviceContext(
        state=GameState(),
        build_db={"npc_dota_hero_skeleton_king": None, "npc_dota_hero_riki": None},
        hero_names={"npc_dota_hero_skeleton_king": "Wraith King", "npc_dota_hero_riki": "Riki",
                    "npc_dota_hero_zuus": "Zeus", "npc_dota_hero_phantom_assassin": "Phantom Assassin",
                    "npc_dota_hero_lion": "Lion"},
        enemy_heroes=enemies or [], ally_heroes=allies or [], matchup_data=md,
    )


def test_ranks_pocket_heroes_by_score():
    adv = draft.advise(_ctx(enemies=["npc_dota_hero_zuus"]))
    assert adv.has_data is True
    assert [p.hero for p in adv.picks][0] == "npc_dota_hero_skeleton_king"  # 0.561 base + strong vs zeus
    assert adv.picks[0].counter == 0.58


def test_countered_flag_and_reason():
    adv = draft.advise(_ctx(enemies=["npc_dota_hero_phantom_assassin"]))
    wk = next(p for p in adv.picks if p.hero == "npc_dota_hero_skeleton_king")
    assert wk.countered is True  # vs PA 0.45 < 0.47
    assert any("weak vs Phantom Assassin" in r for r in wk.reasons)


def test_synergy_included():
    adv = draft.advise(_ctx(allies=["npc_dota_hero_lion"]))
    wk = next(p for p in adv.picks if p.hero == "npc_dota_hero_skeleton_king")
    assert wk.synergy == 0.55
    assert any("synergy w/ Lion" in r for r in wk.reasons)


def test_degraded_without_cache_ranks_by_base():
    adv = draft.advise(_ctx(enemies=["npc_dota_hero_zuus"], has_data=False))
    assert adv.has_data is False
    assert adv.note is not None
    assert adv.picks[0].hero == "npc_dota_hero_skeleton_king"  # base 0.561 > 0.520
    assert adv.picks[0].counter is None
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd engine && .venv/bin/python -m pytest tests/test_draft.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.advisors.draft'`.

- [ ] **Step 4: Implement the advisor**

`engine/app/advisors/draft.py`:
```python
from pydantic import BaseModel, Field
from app.advisors.context import AdviceContext

_STRONG = 0.53
_WEAK = 0.47
_SYNERGY = 0.52
_REFRESH_NOTE = "Run scripts/refresh_matchups.py (needs STRATZ_API_KEY) for counter/synergy."


class DraftPick(BaseModel):
    hero: str
    display: str
    score: float
    base_winrate: float | None = None
    counter: float | None = None
    synergy: float | None = None
    reasons: list[str] = Field(default_factory=list)
    countered: bool = False


class DraftAdvice(BaseModel):
    has_data: bool
    bracket: str | None = None
    note: str | None = None
    picks: list[DraftPick] = Field(default_factory=list)


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _pct(x: float) -> str:
    return f"{round(x * 100)}%"


def advise(ctx: AdviceContext) -> DraftAdvice:
    md = ctx.matchup_data
    if md is None:
        return DraftAdvice(has_data=False, note=_REFRESH_NOTE)

    picks: list[DraftPick] = []
    for hero in ctx.build_db:
        base = md.base_winrates.get(hero)
        hm = md.heroes.get(hero)
        vs = hm.vs if hm else {}
        wth = hm.with_ if hm else {}

        enemy_wrs = [vs[e] for e in ctx.enemy_heroes if e in vs]
        ally_wrs = [wth[a] for a in ctx.ally_heroes if a in wth]
        counter = _mean(enemy_wrs)
        synergy = _mean(ally_wrs)

        score = (base if base is not None else 0.5)
        if counter is not None:
            score += counter - 0.5
        if synergy is not None:
            score += synergy - 0.5

        reasons: list[str] = []
        for e in ctx.enemy_heroes:
            if e in vs:
                name = ctx.hero_names.get(e, e)
                if vs[e] >= _STRONG:
                    reasons.append(f"strong vs {name} ({_pct(vs[e])})")
                elif vs[e] < _WEAK:
                    reasons.append(f"weak vs {name} ({_pct(vs[e])})")
        for a in ctx.ally_heroes:
            if a in wth and wth[a] >= _SYNERGY:
                reasons.append(f"synergy w/ {ctx.hero_names.get(a, a)} ({_pct(wth[a])})")

        countered = any(vs[e] < _WEAK for e in ctx.enemy_heroes if e in vs)
        picks.append(DraftPick(
            hero=hero, display=ctx.hero_names.get(hero, hero),
            score=round(score, 4), base_winrate=base,
            counter=counter, synergy=synergy, reasons=reasons, countered=countered,
        ))

    picks.sort(key=lambda p: p.score, reverse=True)
    return DraftAdvice(
        has_data=md.has_data, bracket=md.bracket,
        note=None if md.has_data else _REFRESH_NOTE, picks=picks,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd engine && .venv/bin/python -m pytest tests/test_draft.py -v`
Expected: PASS (4 passed).

- [ ] **Step 6: Commit**

```bash
cd /home/tahseen-dar/Projects/dota2-live-helper
git add engine/app/advisors/context.py engine/app/advisors/draft.py engine/tests/test_draft.py
git commit -m "feat(engine): draft advisor ranking pocket heroes by counter/synergy"
```

---

### Task 4: `GameState.ally_heroes` + `/allies` + wire draft into the aggregator

**Files:**
- Modify: `engine/app/state.py` (add `ally_heroes`)
- Modify: `engine/app/advice.py` (load matchups; add `draft` field; call advisor)
- Modify: `engine/app/main.py` (POST `/allies`)
- Test: `engine/tests/test_allies_endpoint.py`

**Interfaces:**
- Consumes: `draft.advise`/`DraftAdvice`, `load_matchups`.
- Produces:
  - `GameState.ally_heroes: list[str]` (default empty; NOT touched by `update_from_raw`).
  - `AdvicePayload.draft: DraftAdvice | None`.
  - `POST /allies` body `{"heroes": [...]}` → sets `STATE.ally_heroes`, rebuilds+broadcasts, returns `{"ok": True, "count": N}`.

- [ ] **Step 1: Add `ally_heroes` to GameState**

In `engine/app/state.py`, add the field after `enemy_heroes`:
```python
    enemy_heroes: list[str] = Field(default_factory=list)
    ally_heroes: list[str] = Field(default_factory=list)
    raw: dict = Field(default_factory=dict)
```
`update_from_raw` is unchanged, so both lineups persist across GSI updates.

- [ ] **Step 2: Wire draft into `build_advice`**

Replace `engine/app/advice.py` with:
```python
from pydantic import BaseModel, Field
from app.state import GameState
from app.modules.timings import TimingHit
from app.advisors.context import AdviceContext
from app.advisors import timings as timings_advisor
from app.advisors import build_coach
from app.advisors import draft as draft_advisor
from app.advisors.build_coach import BuildAdvice
from app.advisors.draft import DraftAdvice
from app.build_data import load_build_data
from app.matchups import load_matchups

BUILD_DATA = load_build_data()
MATCHUP_DATA = load_matchups()


class AdvicePayload(BaseModel):
    clock_time: int | None = None
    connected: bool = True
    timings: list[TimingHit] = Field(default_factory=list)
    build: BuildAdvice | None = None
    draft: DraftAdvice | None = None


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
    )
    return AdvicePayload(
        clock_time=state.clock_time,
        timings=timings_advisor.advise(ctx),
        build=build_coach.advise(ctx),
        draft=draft_advisor.advise(ctx),
    )
```

- [ ] **Step 3: Write the failing endpoint test**

`engine/tests/test_allies_endpoint.py`:
```python
from fastapi.testclient import TestClient
from app.main import app, STATE, HUB


def setup_function():
    STATE.enemy_heroes = []
    STATE.ally_heroes = []
    HUB.last = None


def test_allies_sets_state_and_returns_count():
    client = TestClient(app)
    r = client.post("/allies", json={"heroes": ["npc_dota_hero_lion"]})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "count": 1}
    assert STATE.ally_heroes == ["npc_dota_hero_lion"]


def test_draft_present_in_payload_after_enemies():
    client = TestClient(app)
    client.post("/enemies", json={"heroes": ["npc_dota_hero_zuus"]})
    HUB.last = None
    with client.websocket_connect("/ws") as ws:
        client.post("/gsi", json={"map": {"clock_time": 60}})
        data = ws.receive_json()
    assert "draft" in data and data["draft"] is not None
    assert isinstance(data["draft"]["picks"], list)
    assert len(data["draft"]["picks"]) >= 1  # pocket heroes ranked
```

- [ ] **Step 4: Run test to verify it fails**

Run: `cd engine && .venv/bin/python -m pytest tests/test_allies_endpoint.py -v`
Expected: FAIL — `/allies` 404 and/or `draft` missing from payload.

- [ ] **Step 5: Add the `/allies` endpoint**

In `engine/app/main.py`, add this route immediately AFTER the existing `/enemies` handler and BEFORE the `if _DIST.exists():` static mount:
```python
@app.post("/allies")
async def allies(request: Request) -> dict:
    body = await request.json()
    STATE.ally_heroes = list(body.get("heroes", []))
    await HUB.broadcast(build_advice(STATE).model_dump())
    return {"ok": True, "count": len(STATE.ally_heroes)}
```

- [ ] **Step 6: Run the focused test, then the full suite**

Run: `cd engine && .venv/bin/python -m pytest tests/test_allies_endpoint.py -v`
Expected: PASS (2 passed).
Run: `cd engine && .venv/bin/python -m pytest tests -q`
Expected: PASS (all — the draft advisor runs in degraded mode since no cache file exists, which is fine).

- [ ] **Step 7: Commit**

```bash
cd /home/tahseen-dar/Projects/dota2-live-helper
git add engine/app/state.py engine/app/advice.py engine/app/main.py engine/tests/test_allies_endpoint.py
git commit -m "feat(engine): draft in payload + ally_heroes + /allies endpoint"
```

---

### Task 5: Dashboard draft panel + ally picker

**Files:**
- Create: `dashboard/src/panels/draft.js`
- Create: `dashboard/src/panels/allies.js`
- Modify: `dashboard/index.html`, `dashboard/src/main.js`, `dashboard/src/style.css`

**Interfaces:**
- Consumes: WebSocket `AdvicePayload.draft` (`{has_data, bracket, note, picks[]{hero, display, score, base_winrate, counter, synergy, reasons[], countered}}`); `GET /heroes`; `POST /allies`.
- Produces: an ally-entry chip bar and a draft ranking panel on the dashboard.

- [ ] **Step 1: Add markup to index.html**

In `dashboard/index.html`, inside `<main>`, add after the existing `#build-panel` section:
```html
      <section id="allies-panel" class="panel">
        <h2>Ally lineup</h2>
        <div id="ally-chips"></div>
        <input id="ally-search" list="hero-list" placeholder="add ally hero…" autocomplete="off" />
      </section>
      <section id="draft-panel" class="panel">
        <h2>Draft — pick ranking</h2>
        <div id="draft-body"><em>enter the enemy lineup…</em></div>
      </section>
```
(The `#hero-list` datalist already exists from the enemy picker and is reused.)

- [ ] **Step 2: Create the draft panel renderer**

`dashboard/src/panels/draft.js`:
```js
function pct(x) {
  return x == null ? "—" : `${Math.round(x * 100)}%`;
}

export function renderDraft(payload) {
  const el = document.getElementById("draft-body");
  const d = payload.draft;
  if (!d || !d.picks || d.picks.length === 0) {
    el.innerHTML = "<em>enter the enemy lineup…</em>";
    return;
  }
  const note = d.has_data ? "" : `<div class="draft-note">${d.note || ""}</div>`;
  const rows = d.picks
    .map((p, i) => {
      const best = i === 0 ? "best" : "";
      const badge = p.countered ? `<span class="countered">⚠ countered</span>` : "";
      const why = p.reasons.length ? ` — ${p.reasons.join("; ")}` : "";
      return `<li class="pick ${best}">
        <span class="rank">${i + 1}.</span>
        <span class="pname">${p.display}</span> ${badge}
        <span class="pscore">${pct(p.score)}</span>
        <span class="pwhy">${why}</span>
      </li>`;
    })
    .join("");
  el.innerHTML = `${note}<ol class="picks">${rows}</ol>`;
}
```

- [ ] **Step 3: Create the ally picker (mirrors the enemy picker)**

`dashboard/src/panels/allies.js`:
```js
// Ally picker: same UX as the enemy picker, posts to /allies.
export function initAllies(engineHost) {
  const base = `http://${engineHost}`;
  const chips = document.getElementById("ally-chips");
  const search = document.getElementById("ally-search");
  let heroes = [];
  let selected = [];

  const displayToKey = () => Object.fromEntries(heroes.map((h) => [h.display, h.key]));
  const keyToDisplay = () => Object.fromEntries(heroes.map((h) => [h.key, h.display]));

  function render() {
    const names = keyToDisplay();
    chips.innerHTML = selected
      .map((k) => `<span class="chip ally" data-key="${k}">${names[k] || k} ✕</span>`)
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
    await fetch(`${base}/allies`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ heroes: selected }),
    }).catch((e) => console.error("allies POST failed", e));
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
    .then((list) => { heroes = list; })
    .catch((e) => console.error("heroes fetch failed", e));
}
```

- [ ] **Step 4: Wire into main.js**

Replace `dashboard/src/main.js` with:
```js
import { connect } from "./ws.js";
import { renderTimings, renderClock } from "./panels/timings.js";
import { renderBuild } from "./panels/build.js";
import { initEnemies } from "./panels/enemies.js";
import { renderDraft } from "./panels/draft.js";
import { initAllies } from "./panels/allies.js";

// Single-process: engine serves this page (same host:port). Vite dev (5173) -> engine :3000.
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
  renderDraft(payload);
}

initEnemies(ENGINE_HOST);
initAllies(ENGINE_HOST);
connect(WS_URL, onMessage, onStatus);
```

- [ ] **Step 5: Add styles**

Append to `dashboard/src/style.css`:
```css
.chip.ally { background: #16331c; color: #9ee7a0; }
#ally-search { width: 100%; box-sizing: border-box; background: #0b0d11; color: #e6e6e6; border: 1px solid #20242c; border-radius: 6px; padding: .4rem; }
.draft-note { font-size: .8rem; color: #ffd479; margin-bottom: .4rem; }
ol.picks { list-style: none; margin: 0; padding: 0; }
.pick { display: flex; flex-wrap: wrap; align-items: baseline; gap: .4rem; padding: .25rem 0; border-bottom: 1px solid #20242c; }
.pick.best { background: #14251a; }
.pick .rank { color: #6b7280; }
.pick .pname { font-weight: 600; }
.pick .pscore { color: #9ee7a0; margin-left: auto; font-variant-numeric: tabular-nums; }
.pick .pwhy { flex-basis: 100%; font-size: .8rem; color: #8a93a0; }
.countered { color: #ff9a9a; font-size: .8rem; }
```

- [ ] **Step 6: Build the dashboard**

Run: `cd dashboard && npm run build`
Expected: build succeeds, no errors. (In-browser visual smoke — add enemies/allies, watch the ranking — is deferred to the user.)

- [ ] **Step 7: Commit**

```bash
cd /home/tahseen-dar/Projects/dota2-live-helper
git add dashboard
git commit -m "feat(dashboard): draft ranking panel + ally picker"
```

---

## Self-Review

- **Spec coverage:** refresh-script-to-cache keyless engine (Tasks 1-2, spec §3) ✓; cache schema + hero-id mapping + Stratz query with schema-verification note (Tasks 1-2, spec §4) ✓; draft advisor scoring/degradation/`DraftAdvice` (Task 3, spec §5) ✓; `ally_heroes` + `/allies` + draft in payload (Task 4, spec §3/§5) ✓; dashboard draft panel + ally picker (Task 5, spec §6) ✓; offline tests incl. pure transform test (Tasks 2-4, spec §7) ✓; graceful degradation without cache (Tasks 1,3,4) ✓; VAC-safe/keyless engine (Global Constraints). Base win rate sourced from the committed KB seed the spec introduced for the fallback (§5), used as the base component throughout — a deliberate simplification over a second Stratz query, noted here.
- **Placeholder scan:** no TBD/TODO; every code step is complete. The Stratz schema-verification is a concrete, scoped step (the transform is unit-tested regardless).
- **Type consistency:** `MatchupData`/`HeroMatchups` (with the `with`→`with_` alias), `DraftAdvice`/`DraftPick`, `AdviceContext` (ally_heroes/matchup_data added Task 3, consumed Task 4), `load_matchups`, `MATCHUP_DATA`, `transform_matchup`, and the dashboard's `payload.draft.*` field names all match across tasks. `build_advice(state)` keeps its signature so `/gsi`, `/enemies` (P2) are unaffected; `/allies` mirrors `/enemies` exactly.
```
